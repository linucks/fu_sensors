#!/usr/bin/env python3
"""
sudo apt-get install python3-serial

Can also use:
screen -S arduino  /dev/ttyACM0 9600

Kill session: ctrl-A K 

"""
import datetime
import logging
import json
import requests
import serial
import time
import paho.mqtt.client as mqtt


# Local imports
from bluelab_logs import bluelab_logs
from util import influxdb
from util import gpio_sensors
from util import dfrobot_sensors


def setup_mqtt(influx_schema, measurement, on_mqtt_message):
    ## Setup MQTT
    client = mqtt.Client()
    # client.username_pw_set(username, password=None)
    userdata = {"influx_schema": influx_schema, "measurement": measurement}
    client.user_data_set(userdata)
    # client.connect("192.168.4.1", port=1883)
    client.connect("localhost", port=1883)

    # Add different plugs
    for topic in MQTT_SUBSCRIBE_TOPICS:
        client.subscribe(topic)
    client.on_message = on_mqtt_message
    return client


def on_mqtt_message(client, userdata, message):
    """
    Process message of format:

    Received message on topic [tele/tasmota_5014E2/SENSOR]: {"Time":"1970-01-01T00:33:28","ENERGY":{"TotalStartTime":"2021-07-10T11:54:41","Total":0.003,"Yesterday":0.000,"Today":0.003,"Period":0,"Power":22,"ApparentPower":24,"ReactivePower":11,"Factor":0.90,"Voltage":246,"Current":0.098}}

    """
    global h2_data
    decoded_message = str(message.payload.decode("utf-8"))
    if True or message.topic != "h2Pwr/STATUS":
        logger.debug(f"Received message on topic [{message.topic}]: {decoded_message}")

    if message.topic == "h2Pwr/STATUS":
        try:
            data = json.loads(decoded_message)
        except json.decoder.JSONDecodeError as e:
            logger.warning(
                f"Error decoding MQTT data to JSON: {e.msg}\nMessage was: {e.doc}"
            )
            data = {"current": -1.0, "voltage": -1.0}
        h2_data.append(data)
        return

    try:
        data = json.loads(decoded_message)
    except json.decoder.JSONDecodeError as e:
        logger.warning(
            f"Error decoding MQTT data to JSON: {e.msg}\nMessage was: {e.doc}"
        )

    # Process individual message
    influx_schema = userdata["influx_schema"]
    measurement = userdata["measurement"]

    station_id = message.topic.split("/")[1]
    if station_id in MQTT_TO_STATIONID.keys():
        station_id = MQTT_TO_STATIONID[station_id]
    tags = {"station_id": station_id}

    fields = data["ENERGY"]
    fields["TotalStartTime"] = datetime.datetime.strptime(
        fields["TotalStartTime"], "%Y-%m-%dT%H:%M:%S"
    ).timestamp()
    influxdb.send_data_to_influx(
        influx_schema, measurement, tags, fields, local_timestamp=LOCAL_TIMESTAMP
    )


def is_past(trigger):
    return bool((trigger - datetime.datetime.now()).days < 0)


def create_schedule_times(schedule):
    today = datetime.date.today()
    _on_time = datetime.time(
        hour=int(schedule[0].split(":")[0]), minute=int(schedule[0].split(":")[1])
    )
    on_time = datetime.datetime.combine(today, _on_time)
    _off_time = (on_time + datetime.timedelta(hours=schedule[1])).time()
    on_time = datetime.datetime.combine(today, _on_time)
    off_time = datetime.datetime.combine(today, _off_time)
    on_time, off_time = manage_lights(on_time, off_time)
    logger.info(
        f"create_schedule_time: lights next set to go on at {on_time} and off at {off_time}"
    )
    return on_time, off_time


def manage_lights(on_time, off_time, mqtt_client=None):
    if is_past(on_time) and is_past(off_time):
        # off_time always after on_time, so if both in past, lights should be off and on_time needs
        # to be pushed to tomorrow
        on_time = on_time + datetime.timedelta(hours=24)
        off_time = off_time + datetime.timedelta(hours=24)
        if mqtt_client:
            logger.info(
                f"Turning lights off at: {datetime.datetime.now()} - next on at: {on_time}"
            )
            mqtt_client.publish("cmnd/FU_System_2/Power", "0")
    elif is_past(on_time):
        # on_time past, off_time is in future - lights should be on and on_time pushed to tomorrow
        on_time = on_time + datetime.timedelta(hours=24)
        if mqtt_client:
            logger.info(
                f"Turning lights on at: {datetime.datetime.now()} - next off at: {off_time}"
            )
            mqtt_client.publish("cmnd/FU_System_2/Power", "1")
    elif is_past(off_time):
        # off_time past, on_time is in future - lights should be off and off_time pushed to tomorrow
        off_time = off_time + datetime.timedelta(hours=24)
        if mqtt_client:
            logger.info(
                f"Turning lights off at: {datetime.datetime.now()} - next on at: {on_time}"
            )
            mqtt_client.publish("cmnd/FU_System_2/Power", "0")
    else:
        # Both on_time and off_time in the future so nothing to do
        pass
    return on_time, off_time


MOCK = False
POLL_INTERVAL = 60 * 5
HAVE_BLUELAB = False
HAVE_MQTT = False
GPIO_SENSORS = True
CONTROL_LIGHTS = False
LOCAL_TIMESTAMP = True
LOG_LEVEL = logging.DEBUG


# Influxdb Configuration
influxdb.MOCK = MOCK
SENSOR_STATION_ID = "rpi"
MEASUREMENT_SENSOR = "sensors"
BUCKET = "cryptfarm"
TOKEN = open("TOKEN").readline().strip()
ORG = "Farm Urban"
INFLUX_URL = "http://farmuaa1:8086"
influx_schema = {
    "endpoint": INFLUX_URL,
    "org": ORG,
    "token": TOKEN,
    "bucket": BUCKET,
}
sensor_influx_tags = {"station_id": SENSOR_STATION_ID}

# MQTT Data
MEASUREMENT_MQTT = "energy"
MEASUREMENT_BLUELAB = "bluelab"
# MQTT_TO_STATIONID = { 'FU_System_2': 'Propagation'}
MQTT_TO_STATIONID = {}
MQTT_SUBSCRIBE_TOPICS = [
    "tele/FU_Fans/SENSOR",
    "tele/FU_System_1/SENSOR",
    "tele/FU_System_2/SENSOR",
    "h2Pwr/STATUS",
]
BLUELAB_TAG_TO_STATIONID = {"52rf": "sys1", "4q3f": "sys2"}
LIGHT_SCHEDULE = ("06:00", 16)


# Logging
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [rpi2]: %(message)s")
logger = logging.getLogger()
if HAVE_MQTT:
    mqtt_client = setup_mqtt(influx_schema, MEASUREMENT_MQTT, on_mqtt_message)

h2_data = []
if CONTROL_LIGHTS:
    on_time, off_time = create_schedule_times(LIGHT_SCHEDULE)
if GPIO_SENSORS:
    gpio_sensors.setup_devices()
if HAVE_MQTT:
    mqtt_client.loop_start()
last_timestamp = datetime.datetime.now() - datetime.timedelta(seconds=POLL_INTERVAL)
logger.info(
    f"\n\n### Sensor service starting loop at: {datetime.datetime.strftime(datetime.datetime.now(),'%d-%m-%Y %H:%M:%S')} ###\n\n"
)
loopcount = 0
while True:
    # Below seems to raise an exception - not sure why
    # if not mqtt_client.is_connected():
    #    logger.info("mqtt_client reconnecting")
    #    mqtt_client.reconnect()
    if CONTROL_LIGHTS:
        on_time, off_time = manage_lights(on_time, off_time, mqtt_client)

    if loopcount > 0:
        # We run the first set of readings immediately so we have data to send -
        # mainly for debugging and checking purposes.
        sample_start = time.time()
        sample_end = sample_start + POLL_INTERVAL
        gpio_sensors.reset_flow_counter()
        while time.time() < sample_end:
            #  Need to loop so paddle can count rotations
            pass

    data = dfrobot_sensors.sensor_readings()
    if data is None:
        # No data from dfrobot Arduino sensors
        data = {}
    if GPIO_SENSORS:
        data["flow"] = gpio_sensors.flow_rate(POLL_INTERVAL)
        data["distance"] = gpio_sensors.distance_sensor.distance

    # Send sensor data from dfrobot Arduino and direct sensors
    influxdb.send_data_to_influx(
        influx_schema,
        MEASUREMENT_SENSOR,
        sensor_influx_tags,
        data,
        local_timestamp=LOCAL_TIMESTAMP,
    )

    if HAVE_BLUELAB:
        bluelab_data = bluelab_logs.sample_bluelab_data(last_timestamp, POLL_INTERVAL)
        if bluelab_data is not None and len(bluelab_data) > 0:
            for d in bluelab_data:
                #  ['tag', 'timestamp', 'ec', 'ph', 'temp']
                tags = {"station_id": BLUELAB_TAG_TO_STATIONID[d.tag]}
                fields = {"cond": d.ec, "ph": d.ph, "temp": d.temp}
                influxdb.send_data_to_influx(
                    influx_schema,
                    MEASUREMENT_BLUELAB,
                    tags,
                    fields,
                    timestamp=d.timestamp,
                )

    if len(h2_data):
        current = sum([d["current"] for d in h2_data]) / len(h2_data)
        voltage = sum([d["voltage"] for d in h2_data]) / len(h2_data)
        h2_measurement = "h2pwr"
        h2_tags = {"station_id": "rpi"}
        h2_fields = {"current": current, "voltage": voltage}
        influxdb.send_data_to_influx(
            influx_schema, h2_measurement, h2_tags, h2_fields, local_timestamp=True
        )
        h2_data = []

    last_timestamp = datetime.datetime.now()
    loopcount += 1
