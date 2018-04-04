#!/usr/bin/env python3
"""
    This program tests connecting to a MySQL database from Python.

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


class Injector

class Connector

"""

import datetime
from datetime import datetime
import logging
import socket
import time
# 3rd-party imports
import serial

# local imports
import fu_database

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Networking.
# -----------------------------------------------------------------------------
#UDP_IP = "127.0.0.1"
UDP_IP = "192.168.0.101"
UDP_PORT = 9000

# jmht - send data over the USB cable rather then wifi
DATA_OVER_USB = True
SERIAL_PORT = '/dev/cu.usbmodemPy5a3af1'
SERIAL = None
SOCKET = None
PACKET_SIZE = 20
BAUDRATE = 9600
IN_WAITING = None

def set_time():
    """
    Waits for initial connection and sends current date and time.

    The intent for this function is to provide a fallback
    method for the station sensor board to set it's clock
    after being off without a battery back up.
    It needs to be triggered by a request, which is
    difficult because the data packet structure is fixed.
    At the moment this function is not called as the time
    is created by this program rather than the station
    sensor board.
    """
    logger.info("Waiting for NTP request.\n")
    waiting_ntp = True
    while waiting_ntp:
        data, addr = SOCKET.recvfrom(512)
        stringdata = data.decode('utf-8')
        if stringdata == "ntp":
            logger.info("Received request for NTP.")
            ntp_string = "{}".format(datetime.now())
            ntp_bytes = ntp_string.encode('utf-8')
            ntp_tuple = time.strptime(ntp_string, "%Y-%m-%d %H:%M:%S.%f")
            packet = "{},{},{},{},{},{},{},{}".format(ntp_tuple.tm_year,\
                                                    ntp_tuple.tm_mon,\
                                                    ntp_tuple.tm_mday,\
                                                    ntp_tuple.tm_hour,\
                                                    ntp_tuple.tm_min,\
                                                    ntp_tuple.tm_sec,\
                                                    ntp_tuple.tm_wday,\
                                                    ntp_tuple.tm_yday)
            logger.info("Packet = {}.".format(packet))
            SOCKET.sendto(packet.encode('utf-8'), addr)
            waiting_ntp = False

def setup_data_transfer():
    global PACKET_SIZE, BAUDRATE, IN_WAITING, SERIAL, SOCKET, DATA_OVER_USB
    if DATA_OVER_USB:
        if SERIAL_PORT.startswith('loop://'):
            SERIAL = serial.serial_for_url(SERIAL_PORT, baudrate=BAUDRATE,
                                           bytesize=serial.EIGHTBITS, timeout=2)
        else:
            SERIAL = serial.Serial(port=SERIAL_PORT, baudrate=BAUDRATE,
                                   bytesize=serial.EIGHTBITS, timeout=2)
        logger.debug("SETUP SERIAL %s", SERIAL)
        IN_WAITING = 'in_waiting'
        if not hasattr(SERIAL, IN_WAITING):
            IN_WAITING = 'inWaiting'
            if not hasattr(SERIAL, IN_WAITING):
                raise AttributeError("Ser object doesn't have in_waiting or inWaiting atrributes!")
        IN_WAITING = getattr(SERIAL, IN_WAITING)
        # poller.register(ser)
    else:
        logger.info("Networking:")
        SOCKET = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # poller.register(socket)
        logger.info("\tBinding socket to {}, port {}".format(UDP_IP, UDP_PORT))
        SOCKET.bind((UDP_IP, UDP_PORT))

def main():
    global SOCKET, SERIAL, IN_WAITING, PACKET_SIZE
    DB = fu_database.Database(db_config=fu_database.DB_CONFIG)
    if not (SOCKET or SERIAL):
        setup_data_transfer()
    error = False # Error trapping variable.
    #set_time()
    logger.info("Waiting for sensor data.\n")
    while not error:
        time.sleep(1)
        data = None
        if DATA_OVER_USB:
            global PACKET_SIZE
            to_read = IN_WAITING() # call the relevant function
            logger.info("GOT to_read %s ", to_read)
            if to_read == PACKET_SIZE:
                data = SERIAL.read(PACKET_SIZE)
            else:
                # Just clear the output buffer
                SERIAL.read(to_read)
        else:
            data, addr = SOCKET.recvfrom(512)
        if data:
            logger.info("Received %s bytes of sensor data.", len(data))
            DB.process_data(data)

    # -----------------------------------------------------------------------------
    # Tidy up.
    # -----------------------------------------------------------------------------
    if DATA_OVER_USB:
        SERIAL.close()
    else:
        SOCKET.close()
    DB.close()

if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    main()
