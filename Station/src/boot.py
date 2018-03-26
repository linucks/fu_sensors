"""
    This program tests the feasibility of a sensor monitoring system

    Copyright (C) 2018  Darren Faulke (VEC), Jens Thomas (Farm Urban)

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""

# Board initialisation:
# Connects to wi-fi.
# Opens UDP socket.

# Sets up database and macros.

import pycom
import machine
import time
import socket
import struct
import sys
import binascii

from network import WLAN
from machine import Timer
from machine import UART

# =============================================================================
# Debugging and output.
# =============================================================================
PRINT_DEBUG = False     # Print debugging output.
PRINT_OUTPUT = False     # Print informational output.

# =============================================================================
# Networking.
# =============================================================================
NETWORK_SSID    = 'vec-lab'         # Router broadcast name.
NETWORK_KEY     = 'vec-lab123'      # Access key.
NETWORK_TIMEOUT = 20                # Connection timeout (s)

STATIC_IP = False
# These are only needed for static IP address.
NETWORK_IP       = '192.168.0.103'   # IP address.
NETWORK_MASK     = '255.255.255.0'   # Network mask.
NETWORK_GATEWAY  = '192.168.0.1'     # Gateway.
NETWORK_DNS      = '192.168.0.1'     # DNS server (N/A).
NETWORK_CONFIG   = (NETWORK_IP, NETWORK_MASK, NETWORK_GATEWAY, NETWORK_DNS)

#HOST_NAME       = '138.253.118.249' # MySQL server address.
HOST_NAME       = '192.168.0.101'   # MySQL server address.
HOST_PORT       =  9000             # UDP port.
HOST_ADDRESS    = (HOST_NAME, HOST_PORT)

NTP_AVAILABLE   = False             # NTP server available?
NTP_ADDRESS     = 'pool.ntp.org'    # Address of open NTP server.

# jmht - send data over the USB cable rather then wifi
DATA_OVER_USB = True

# =============================================================================
# Sensor intervals.
# =============================================================================
SENSOR_INTERVAL = 1 # Minutes.

# =============================================================================
# Data structures.
# =============================================================================
#
#   The database structure is defined as:
#
#       ,---------------------------------------------------,
#       | ID | Variable         | DB format     | Type      |
#       |----+------------------+---------------+-----------|
#       | -- | time             | datetime      | datetime  |
#       | -- | station          | char(12)      | bytes     |
#       | 01 | water_temp       | decimal(3,1)  | real      |
#       | 02 | air_temp         | decimal(3,1)  | real      |
#       | 03 | soil_humidity    | decimal(3,1)  | real      |
#       | 04 | air_humidity     | decimal(3,1)  | real      |
#       | 05 | ambient_light0   | smallint      | int       |
#       | 06 | ambient_light1   | smallint      | int       |
#       | 07 | ph_level         | decimal(2,2)  | real      |
#       | 08 | orp_level        | decimal(2,2)  | real      |
#       '---------------------------------------------------'

# =============================================================================
# Colour definitions for LED.
# =============================================================================
GREEN = 0x00ff00 # Green.
AMBER = 0xff8000 # Amber.
RED   = 0xff0000 # Red.
BLUE  = 0x0000ff # Blue.
BLACK = 0x000000 # Black.

# =============================================================================
# Initialisation.
# =============================================================================
# -----------------------------------------------------------------------------
# Turn of Pycom heartbeat.
# -----------------------------------------------------------------------------
pycom.heartbeat(False)  # Turn off pulsing LED heartbeat.

chrono = Timer.Chrono()
if DATA_OVER_USB:
    # Kill the REPL?
    #os.dupterm(None)
    BUS = 0
    BAUDRATE = 9600
    uart = UART(BUS, BAUDRATE)
    uart.init(BAUDRATE, bits=8, parity=None, stop=1)
else:
    wlan = WLAN(mode=WLAN.STA)

#   ,-----------------------------------------------------------,
#   | If there are multiple stations then we need a unique      |
#   | identity so we can chart the data specific to it. We can  |
#   | use the mac address for this so that this code can be     |
#   | used without modifying it for each station.               |
#   '-----------------------------------------------------------'
station_mac = binascii.hexlify(machine.unique_id())
#station_mac = machine.unique_id()
if PRINT_OUTPUT:
    print("Station MAC = {}.".format(station_mac.decode()))

# -----------------------------------------------------------------------------
# Connect to access point.
# -----------------------------------------------------------------------------
def connect_to_network():

    if STATIC_IP:
        if PRINT_OUTPUT:
            print("Using static IP address with:")
            print("\tIP          : {}".format(NETWORK_IP))
            print("\tSubnet mask : {}".format(NETWORK_MASK))
            print("\tGateway     : {}".format(NETWORK_GATEWAY))
            print("\tDNS server  : {}".format(NETWORK_DNS))
            print()
        wlan.ifconfig(config=NETWORK_CONFIG)
    else:
        if PRINT_OUTPUT:
            print("IP address will be assigned via DHCP.")

    if PRINT_OUTPUT:
        print("Looking for access point.", end="")

    nets = wlan.scan()
    for net in nets:
        if PRINT_OUTPUT:
            print(".", end="")
        if net.ssid == NETWORK_SSID:
            if PRINT_OUTPUT:
                print("\nFound {} access point!".format(NETWORK_SSID))
            break

    if PRINT_OUTPUT:
        print("Connecting", end="")

#   ,-----------------------------------------------------------,
#   | The wlan.connect timeout doesn't actually do anything so  |
#   | an alternative timeout method has been implemented.       |
#   | See Pycom forum topic 2201.                               |
#   '-----------------------------------------------------------'
    wlan.connect(net.ssid, auth=(net.sec, NETWORK_KEY))
    chrono.start()
    start_loop = chrono.read()
    start_scan = start_loop
    while not wlan.isconnected():
        if chrono.read() - start_scan >= NETWORK_TIMEOUT:
            error = True
            break
        if chrono.read() - start_loop >= NETWORK_TIMEOUT / 50:
            start_loop = chrono.read()
            if PRINT_OUTPUT:
                print(".", end="")

    chrono.stop()
# -----------------------------------------------------------------------------

#if wlan.isconnected():
#    wlan.disconnect

if not DATA_OVER_USB:
    connect_to_network()

    # -----------------------------------------------------------------------------
    # End if unable to connect.
    # -----------------------------------------------------------------------------
    # Connection keeps dropping.
    if not wlan.isconnected():
        if PRINT_OUTPUT:
            print("\nCouldn't connect to access point.")
        pycom.rgbled(RED)
        sys.exit(1)

    if PRINT_OUTPUT:
        print("")
        print("\nSuccessfully connected to network.")

    # -----------------------------------------------------------------------------
    # Print network info.
    # -----------------------------------------------------------------------------
    if PRINT_OUTPUT:
        print("Network config:\n")
        ip, mask, gateway, dns = wlan.ifconfig()
        print("\tIP          : {}".format(ip))
        print("\tSubnet mask : {}".format(mask))
        print("\tGateway     : {}".format(gateway))
        print("\tDNS server  : {}".format(dns))
        print()
        time.sleep(1)

    # -----------------------------------------------------------------------------
    # Create network socket.
    # -----------------------------------------------------------------------------
    if PRINT_OUTPUT:
        print("Trying to create a network socket.")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        if PRINT_OUTPUT:
            print("Socket created.\n")
    except:
        if PRINT_OUTPUT:
            print("Failed to create socket - quitting.\n")
        error = True
        pycom.rgbled(RED)
        sys.exit()

    sock.setblocking(False)
