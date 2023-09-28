APP:
  mock: False
  log_level: "DEBUG"
  poll_interval: 60 * 5
  gpio_sensors: False
  station_id: "main_sump"

MQTT:
  username: MQTT_USER
  password: MQTT_PASSWORD
  host: MQTT_HOST
  port: 1883
  sensor_topic: "main_sump/sensor"
  bluelab_topic: "bluelab"

BLUELAB:
  available: False
  tag_to_stationid: [["52rf", "lettus_grow"], ["4q3f", "main_sump"]]
  log_dir: "/home/pi/.local/share/Bluelab/Connect/logs"
# tasmota_EOB226 - orig
# tasmota_EOB226:
#   module: "Sonoff Pow R2"
#   class: "power"
#   name: "EOB226"
#   topic: "EOB226"
#   power_topic: "EOB226/tele/SENSOR"
#   power_template: "{{ value_json['ENERGY'].Power }}"
#   power_unit: "W"
#   power_precision: 0
#   power_state_topic: "EOB226/tele/STATE"
#   power_state_template: "{{ value_json['POWER'] }}"
#   power_state_on: "ON"
#   power_state_off: "OFF"
#   power_payload_on: "ON"
#   power_payload_off: "OFF"
#   availability_topic: "EOB226/tele/LWT"
#   payload_available: "Online"
#   payload_not_available: "Offline"
#   qos: 1
#   retain: false
#   device_class: "power"
#   unique_id: "EOB226"
#   icon: "mdi:power-socket-us"
