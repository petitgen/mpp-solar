"""
MPP Solar Inverter Command Library
reference library of serial commands (and responses) for PIP-4048MS inverters
mppinverter.py
"""

import serial
import time
import re
import logging
import json
import glob
import os
import usb.core, usb.util, usb.control
from os import path

from .mppcommand import mppCommand

log = logging.getLogger('MPP-Solar')


class MppSolarError(Exception):
    pass


class NoDeviceError(MppSolarError):
    pass


class NoTestResponseDefined(MppSolarError):
    pass


def getCommandsFromJson():
    """
    Read in all the json files in the commands subdirectory
    this builds a list of all valid commands
    """
    COMMANDS = []
    here = path.abspath(path.dirname(__file__))
    files = glob.glob(here + '/commands/*.json')
    for file in sorted(files):
        log.debug("Loading command information from {}".format(file))
        with open(file) as f:
            try:
                data = json.load(f)
            except Exception as e:
                log.debug("Error processing JSON in {}".format(file))
                log.debug(e)
                continue
            if data['regex']:
                regex = re.compile(data['regex'])
            else:
                regex = None
            if 'help' in data:
                help = data['help']
            else:
                help = ""
            COMMANDS.append(mppCommand(data['name'], data['description'], data['type'], data['response'], data['test_responses'], regex, help=help))
    return COMMANDS


def isTestDevice(serial_device):
    """
    Determine if this instance is just a Test connection
    """
    if serial_device == 'TEST':
        return True
    return False


def isDirectUsbDevice(serial_device):
    """
    Determine if this instance is using direct USB connection
    (instead of a serial connection)
    """
    if not serial_device:
        return False
    match = re.search("^.*hidraw\\d$", serial_device)
    if match:
        log.debug("Device matches hidraw regex")
        return True
    return False

def isDirectUsbDeviceNoDriver():
    """
    Determine if this instance is using direct USB connection without Driver
    """
    return False


class mppInverter:
    """
    MPP Solar Inverter Command Library
    - represents an inverter (and the commands the inverter supports)
    """

    def __init__(self, serial_device=None, baud_rate=2400):
        if not serial_device:
            raise NoDeviceError("A device to communicate by must be supplied, e.g. /dev/ttyUSB0")
        self._baud_rate = baud_rate
        self._serial_device = serial_device
        self._serial_number = None
        self._test_device = isTestDevice(serial_device)
        self._direct_usb = isDirectUsbDevice(serial_device)
        self._direct_usb_no_driver = isDirectUsbDeviceNoDriver()
        self._commands = getCommandsFromJson()
        # TODO: text descrption of inverter? version numbers?

    def __str__(self):
        """
        """
        inverter = "\n"
        if self._direct_usb:
            inverter = "Inverter connected via USB on {}".format(self._serial_device)
        elif self._test_device:
            inverter = "Inverter connected as a TEST"
        else:
            inverter = "Inverter connected via serial port on {}".format(self._serial_device)
        inverter += "\n-------- List of supported commands --------\n"
        if self._commands:
            for cmd in self._commands:
                inverter += str(cmd)
        return inverter

    def getSerialNumber(self):
        if self._serial_number is None:
            response = self.execute("QID").getResponseDict()
            if response:
                self._serial_number = response["serial_number"][0]
        return self._serial_number

    def getAllCommands(self):
        """
        Return list of defined commands
        """
        return self._commands

    def _getCommand(self, cmd):
        """
        Returns the mppcommand object of the supplied cmd string
        """
        log.debug("Searching for cmd '{}'".format(cmd))
        if not self._commands:
            log.debug("No commands found")
            return None
        for command in self._commands:
            if not command.regex:
                if cmd == command.name:
                    return command
            else:
                match = command.regex.match(cmd)
                if match:
                    log.debug(command.name, command.regex)
                    log.debug("Matched: {} Value: {}".format(command.name, match.group(1)))
                    command.setValue(match.group(1))
                    return command
        return None

    def _doTestCommand(self, command):
        """
        Performs a test command execution
        """
        command.clearResponse()
        log.debug('Performing test command with %s', command)
        command.setResponse(command.getTestResponse())
        return command

    def _doSerialCommand(self, command):
        """
        Opens serial connection, sends command (multiple times if needed)
        and returns the response
        """
        command.clearResponse()
        response_line = None
        log.debug('port %s, baudrate %s', self._serial_device, self._baud_rate)
        try:
            with serial.serial_for_url(self._serial_device, self._baud_rate) as s:
                # Execute command multiple times, increase timeouts each time
                for x in range(1, 5):
                    log.debug('Command execution attempt %d...', x)
                    s.timeout = 1 + x
                    s.write_timeout = 1 + x
                    s.flushInput()
                    s.flushOutput()
                    s.write(command.full_command)
                    time.sleep(0.5 * x)  # give serial port time to receive the data
                    response_line = s.readline()
                    log.debug('serial response was: %s', response_line)
                    command.setResponse(response_line)
                    return command
        except Exception as e:
            log.debug('Serial read error', e.strerror)
        log.info('Command execution failed')
        return command

    def _doDirectUsbCommand(self, command):
        """
        Opens direct USB connection, sends command (multiple times if needed)
        and returns the response
        """
        command.clearResponse()
        response_line = ""
        usb0 = None
        try:
            usb0 = os.open(self._serial_device, os.O_RDWR | os.O_NONBLOCK)
        except Exception as e:
            log.debug('USB open error', e.strerror)
            return command
        # Send the command to the open usb connection
        to_send = command.full_command
        while (len(to_send) > 0):
            # Split the full command into smaller chucks
            send, to_send = to_send[:8], to_send[8:]
            time.sleep(0.35)
            os.write(usb0, send)
        time.sleep(0.25)
        # Read from the usb connection
        # try to a max of 100 times
        for x in range(100):
            # attempt to deal with resource busy and other failures to read
            try:
                time.sleep(0.15)
                r = os.read(usb0, 256)
                response_line += r
            except Exception as e:
                log.debug('USB read error', e.strerror)
            # Finished is \r is in response
            if ('\r' in response_line):
                # remove anything after the \r
                response_line = response_line[:response_line.find('\r') + 1]
                break
        log.debug('usb response was: %s', response_line)
        command.setResponse(response_line)
        return command

    def _doDirectUsbNoDriverCommand(self, command):
        """
        Opens direct USB connection, sends command (multiple times if needed)
        and returns the response
        """
        command.clearResponse()
        response_line = ""
        try:
            vendorId = 0x0665
            productId = 0x5161
            interface = 0
            dev = usb.core.find(idVendor=vendorId, idProduct=productId)
            if dev.is_kernel_driver_active(interface):
                dev.detach_kernel_driver(interface)
                log.debug('Active')
            dev.set_interface_altsetting(0,0)

        except Exception as e:
            log.debug('USB open error', e.strerror)
            return command
        # Send the command to the open usb connection
        to_send = command.full_command
        cmd = to_send.encode('utf-8')
        crc = crc16.crc16xmodem(cmd).to_bytes(2,'big')
        cmd = cmd+crc
        cmd = cmd+b'\r'
        while len(cmd)<8:
            cmd = cmd+b'\0'
        log.debug('Command Generated', cmd)
        time.sleep(0.25)
        # Read from the usb connection
        # try to a max of 100 times
        i=0
        while '\r' not in response_line and i<20:
            try:
                response_line+="".join([chr(i) for i in dev.read(0x81, 8, timeout * 1) if i!=0x00])
            except usb.core.USBError as e:
                if e.errno == 110:
                    log.debug('Busy ', e.strerror)
                    pass
                else:
                    log.debug('USB read error', e.strerror)
                    raise
            i+=1
        log.debug('usb response was: %s', response_line)
        command.setResponse(response_line)
        return command

    def execute(self, cmd):
        """
        Sends a command (as supplied) to inverter and returns the raw response
        """
        command = self._getCommand(cmd)
        if command is None:
            log.critical("Command not found")
            return None
        elif (self._test_device):
            log.debug('TEST connection: executing %s', command)
            return self._doTestCommand(command)
        elif (self._direct_usb_no_driver):
            log.debug('USB no driver connection: executing %s', command)
            return self._doDirectUsbNoDriverCommand(command)
        elif (self._direct_usb):
            log.debug('DIRECT USB connection: executing %s', command)
            return self._doDirectUsbCommand(command)
        else:
            log.debug('SERIAL connection: executing %s', command)
            return self._doSerialCommand(command)
