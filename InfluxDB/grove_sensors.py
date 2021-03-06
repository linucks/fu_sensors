#!/usr/bin/env python3
"""
https://learn.adafruit.com/adafruits-raspberry-pi-lesson-4-gpio-setup/configuring-i2c
cd /opt
sudo git clone https://github.com/Seeed-Studio/grove.py
export PYTHONPATH=/opt/grove.py

# BME680
https://github.com/pimoroni/bme680-python
sudo pip3 install bme680
Need to edit:
sudo vi /usr/local/lib/python3.7/dist-packages/bme680/__init__.py
to import smbus2 as smbus

# Systemd
sudo bash -c "cat <<EOF >/etc/systemd/system/bruntwood_sensors.service
[Unit]
After=openvpn-client@rpizero1.service

[Service]
ExecStart=python3 /opt/fu_sensors/InfluxDB/grove_sensors.py
WorkingDirectory=/opt/fu_sensors/InfluxDB
Environment="PYTHONPATH=/opt/grove.py"
Restart=always
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=bruntwood_sensors
User=pi
Group=pi

[Install]
WantedBy=multi-user.target
EOF
"

sudo systemctl enable bruntwood_sensors.service
sudo systemctl start bruntwood_sensors.service


"""
from collections import namedtuple
import logging
import requests
import sys
import time

from grove import grove_ultrasonic_ranger
from grove import grove_light_sensor_v1_2
#from grove import grove_temperature_humidity_bme680
import bme680


INFLUX_URL = 'http://10.8.0.1:8086/write?db=bruntwood'
STATION_MAC = 'bruntwood'
SAMPLE_WINDOW = 60 * 5
MOCK = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s [bruntwood_sensors]: %(message)s')
logger = logging.getLogger()


def readings_to_influxdb_line(readings, station_id, include_timestamp=False):
    data = ""
    for k, v in readings.items():
        data += 'fu_sensor,stationid={},sensor={} measurement={}' \
               .format(station_id, k, v)
        if include_timestamp is True:
            timestamp = utime.mktime(rtc.now())
            data += ' {}000000000'.format(timestamp)
        data += "\n"
    return data


def send_data(iline):
    if MOCK:
        logger.info('sending data{}'.format(iline))
        return
    success = False
    number_of_retries = 3
    while not success and number_of_retries > 0:
        try:
            requests.post(INFLUX_URL, data=iline)
            success = True
        except Exception as e:
            logger.warn('network error: {}'.format(e))
            number_of_retries -= 1
            pass
    return success


def take_readings():
    global sonar, light, sensor_bme680, gas_baseline
    readings = {}
    readings['distance'] = sonar.get_distance()
    readings['light'] = light.light
    d = bme680_readings(sensor_bme680)
    air_quality = air_quality_score(d.gas_resistance, d.humidity, gas_baseline)
    readings['temperature'] = d.temperature
    readings['humidity'] = d.humidity
    readings['pressure'] = d.pressure
    readings['air_quality'] = air_quality

    # d = bme680.read()
    # readings['temperature'] = d.temperature
    # readings['humidity'] = d.humidity
    # readings['pressure'] = d.pressure
    # if d.heat_stable:
    #     readings['air_quality'] = d.gas_resistance
    # else:
    #     readings['air_quality'] = 0
    return readings


def setup_bme680():
    # Plugged into Grove I2C socket => I2C_ADDR_PRIMARY
    sensor = bme680.BME680(bme680.I2C_ADDR_PRIMARY)
    # These oversampling settings can be tweaked to
    # change the balance between accuracy and noise in
    # the data.
    sensor.set_humidity_oversample(bme680.OS_2X)
    sensor.set_pressure_oversample(bme680.OS_4X)
    sensor.set_temperature_oversample(bme680.OS_8X)
    sensor.set_filter(bme680.FILTER_SIZE_3)
    sensor.set_gas_status(bme680.ENABLE_GAS_MEAS)

    sensor.set_gas_heater_temperature(320)
    sensor.set_gas_heater_duration(150)
    sensor.select_gas_heater_profile(0)
    return sensor


def bme680_gas_baseline(sensor_bme680):
    logger.info("Initialising BME680 and getting burn-in data")
    start_time = time.time()
    curr_time = time.time()
    burn_in_time = 300  # 5 minutes
    if MOCK:
        burn_in_time = 30
    burn_in_data = []
    # Collect gas resistance burn-in values, then use the average
    # of the last 50 values to set the upper limit for calculating
    # gas_baseline.
    while curr_time - start_time < burn_in_time:
        curr_time = time.time()
        if sensor_bme680.get_sensor_data() and sensor_bme680.data.heat_stable:
            gas = sensor_bme680.data.gas_resistance
            burn_in_data.append(gas)
            time.sleep(1)
    num_points = min(len(burn_in_data), 50)
    gas_baseline = sum(burn_in_data[-num_points:]) / float(num_points)
    logger.info("Got gas_baseline %s",gas_baseline)
    return gas_baseline


def air_quality_score(gas_resistance, humidity, gas_baseline):
    AIR_QUALITY_RANGE = 500
    humidity_baseline = AIR_QUALITY_RANGE * 0.4 # Set the humidity baseline to 40%, an optimal indoor humidity.
    humidity_weighting = 0.25 # Set the balance between humidity and gas reading in calculation of air_quality_score (25:75, humidity:gas)

    gas_offset = gas_baseline - gas_resistance
    humidity_offset = humidity - humidity_baseline

    # Calculate hum_score as the distance from the hum_baseline.
    if humidity_offset > 0:
        humidity_score = (AIR_QUALITY_RANGE - humidity_baseline - humidity_offset)
        humidity_score /= (AIR_QUALITY_RANGE - humidity_baseline)
        humidity_score *= (humidity_weighting * AIR_QUALITY_RANGE)
    else:
        humidity_score = (humidity_baseline + humidity_offset)
        humidity_score /= humidity_baseline
        humidity_score *= (humidity_weighting * AIR_QUALITY_RANGE)

    # Calculate gas_score as the distance from the gas_baseline.
    if gas_offset > 0:
        gas_score = (gas_resistance / gas_baseline)
        gas_score *= (AIR_QUALITY_RANGE - (humidity_weighting * AIR_QUALITY_RANGE))
    else:
        gas_score = AIR_QUALITY_RANGE - (humidity_weighting * AIR_QUALITY_RANGE)

    return int(humidity_score + gas_score)


def bme680_readings(sensor_bme680):
    error = False
    if sensor_bme680.get_sensor_data() and sensor_bme680.data.heat_stable:
        gas_resistance = sensor_bme680.data.gas_resistance
        temperature = sensor_bme680.data.temperature
        humidity = sensor_bme680.data.humidity
        pressure = sensor_bme680.data.pressure
    else:
        logger.warn("Error taking bme680_readings")
        error = True
        gas_resistance = -1
        temperature = 0
        humidity = -1
        pressure = -1
    r = namedtuple('readings', ['gas_resistance', 'temperature', 'humidity', 'pressure', 'error'])
    return r(gas_resistance, temperature, humidity, pressure, error)

pin = 5
adc_channel = 0
# Plugged into D5 socket
sonar = grove_ultrasonic_ranger.GroveUltrasonicRanger(pin)
# Plugged into A0 socket
light = grove_light_sensor_v1_2.GroveLightSensor(adc_channel)
# Plugged into I2C socket
# sensor_bme680 = grove_temperature_humidity_bme680.GroveBME680()
sensor_bme680 = setup_bme680()
# This takes 5 minutes
gas_baseline = bme680_gas_baseline(sensor_bme680)

while True:
    sample_start = time.time()
    sample_end = sample_start + SAMPLE_WINDOW
    rate_cnt = 0
    while time.time() < sample_end:
        pass
    time.sleep(2)  # Need to add in pause or the distance sensor or else it measures 0.0
    readings = take_readings()
    iline = readings_to_influxdb_line(readings, STATION_MAC)
    success = send_data(iline)
