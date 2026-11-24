#!/usr/bin/env python3
"""
TLSR82xx / TLSR825x / TLSR826x / TLSR8208 SWire Programmer & Autonomous Flasher
==============================================================================

Requirements:
  pip3 install pyserial          # Required (only missing import triggers at runtime)
  pip3 install keyboard          # Optional (enables Esc abort in monitor loops)

Hardware Wiring (3-wire SWire via PWR switching; no dedicated RST wire needed):
  Programmer PWR (H1.2) -> Target VCC / 3V3 (do NOT power target externally)
  Programmer GND (H1.1) -> Target GND
  Programmer SWM (H1.4) -> Target SWS
  Programmer EXT_RST (H1.5) -> Optional target nRST (released unless PWR=0)

  Note for targets with large 3V3 bulk capacitors (e.g. >30 uF):
    Increase PWR discharge time (`--pwr-off-ms 1500` or `-t 1500`) and SWire
    activation pulse (`--act-ms 300` or `-a 300`) so VCC bleeds low enough
    for clean power-on SWire capture.

  Note for TLSR826x targets (TLSR8266, TLSR8267, TLSR8269):
    Always pass `-u` / `--u2b` to select 2-byte SWire addressing instead of
    the default 3-byte addressing (used by TLSR825x and TLSR8208).

Operation Modes:
  1. USB Port Auto-Discovery:
     Omit `-p / --port` to automatically scan attached USB serial devices,
     prioritize USB CDC/UART adapters, probe each at 230400 bps via
     CMDF_GET_VERSION, and select the first responding TLSRPGM programmer.

  2. Immediate Target Power Control (`--pwr` / `--power`):
     Sets or toggles the programmer PWR output and exits immediately:
       TlsrPgm.py --pwr              Toggle PWR (ON <-> OFF) and exit
       TlsrPgm.py --pwr on           Turn target 3.3V PWR ON and exit
       TlsrPgm.py --pwr off          Turn target 3.3V PWR OFF and exit

  3. Autonomous Full Flash Dump (`dump` subcommand):
     Cycles PWR + SWire Activate until 3 consecutive stable Chip ID & JEDEC ID
     reads match, prints full hardware specs (chip, SRAM, BLE info, flash
     vendor/capacity/status/UID), dumps the full SPI flash with per-block
     hardware CRC16 verification (and automatic slip re-lock/resume), saves
     atomically, reports SHA-256 + detected BLE MAC, and turns PWR OFF.
       TlsrPgm.py dump
       TlsrPgm.py dump -o backup.bin
       TlsrPgm.py dump -s 0x80000
       TlsrPgm.py -u --pwr-off-ms 1500 --act-ms 300 dump

  4. Autonomous Retry Mode (`-R` / `--retry` with any subcommand):
     Wraps any subcommand (`we`, `wf`, `rf`, `es`, `ea`, `i`, `ds`, `df`, `da`,
     `do`, `fsr`, `fsw`, `rs`, `ws`, `ra`, `ro`, `wa`, etc.) with the same
     contact-wait loop before execution AND automatic re-lock/resume if hand-held
     probe pins slip mid-transfer during flash read, write, or sector erase:
       TlsrPgm.py -R we 0x0 firmware.bin
       TlsrPgm.py -R -u --pwr-off-ms 1500 --act-ms 300 we 0x0 pgm_fw.bin
       TlsrPgm.py -R rf 0 0x80000 dump.bin
       TlsrPgm.py -R i

  5. Classic Fixed-Timing Mode (scripted / single-shot):
     Runs a single `-t` reset / `-a` activate pulse (or attaches live if both are
     0) before executing the subcommand:
       TlsrPgm.py -p /dev/ttyACM0 -b 1500000 -t 100 -a 150 we 0x0 firmware.bin
       TlsrPgm.py -p /dev/cu.usbmodem1 -u -t 1500 -a 300 ea

Global Options:
  -p, --port PORT        Serial device path (default: auto-discover USB PGM)
  -b, --baud RATE|auto   PGM UART speed: 115200..3000000 or "auto"
                         (default: auto 1500000->921600->230400 for dump/-R,
                         230400 otherwise)
  --pwr, --power [STATE] Target power control: on | off | toggle (bare --pwr =
                         toggle) and exit immediately
  -R, --retry            Enable autonomous contact lock + slip recovery mode
  --act-ms MS            SWire activation pulse ms per retry attempt (def: 150)
  --pwr-off-ms MS        PWR-off discharge ms per retry attempt (def: 60)
  --stable-reads N       Consecutive matching ID reads to confirm lock (def: 3)
  --no-crc               Skip hardware CRC16 block checks (FW >= 0.0.0.3)
  --keep-power           Leave target PWR ON after `dump` or `-R` finishes
  -u, --u2b              Use 2-byte SWire address mode (required for TLSR826x)
  -d, --div DIV          Override SWire clock divisor (0 = auto ~4.8 Mbit/s div)
  -t, --trst MS          Classic pre-op hard reset time in ms (PWR=0 duration)
  -a, --act MS           Classic pre-op SWire activation ms (<0 = soft reboot)
  -z, --zw SEC           Wait SEC seconds for CPU wake before main command
  -s, --stopcpu          Halt CPU ([0x0602] = 0x05) before main command
  -c, --cpustall         Stall CPU ([0x0602] = 0x06) before main command
  -r, --run              Post-op CPU Reboot/Run ([0x0602] = 0x88)
  -g, --go               Post-op CPU Go ([0x0602] = 0x08)
  -m, --mrst             Post-op MCU Soft Reset ([0x006f] = 0x20)
  -o, --osws ADDR        Post-op open SWS Printf stream at SRAM ADDR (FW>=0.0.0.8)
  -w, --wrktime          Print total elapsed execution time in seconds

Subcommands:
  dump [-o FILE] [-s BYTES]       Autonomous probe + CRC16 full flash dump
  i                               Inspect Chip ID, PC, JEDEC ID, UID, flash/regs
  rf <addr> <size> <file>         Read SPI flash region to binary file
  we <addr> <file>                Erase affected 4KB sectors + write file to flash
  wf <addr> <file>                Write file to flash WITHOUT erasing sectors
  es <addr> <size>                Erase flash sectors covering [addr, addr+size)
  ea                              Erase ALL flash (full chip erase)
  fsr                             Read SPI flash status register (1 byte)
  fsw <val>                       Write byte <val> to SPI flash status register
  df <addr> <size>                Hex-dump SPI flash region to terminal
  rs <addr> <size> <file>         Read SWire/SRAM/register region to file
  ws <addr> <file>                Write binary file to SWire/SRAM/registers
  wsb <addr> <val>                Write 8-bit byte to SWire/SRAM/register address
  wsw <addr> <val>                Write 16-bit little-endian word to SWire addr
  wsd <addr> <val>                Write 32-bit little-endian dword to SWire addr
  ds <addr> <size>                Hex-dump SWire/SRAM/register region to terminal
  da <addr> <size>                Hex-dump analog registers (auto-enables ALGM clk)
  ra <addr> <size> <file>         Read analog registers to binary file (max 256 B)
  wa <addr> <file>                Write binary file to analog registers
  do <addr> <size>                Hex-dump TLSR8208 OTP memory (Chip ID 0x5591)
  ro <addr> <size> <file>         Read TLSR8208 OTP memory to binary file
  dc <addr> <sec>                 Continuously monitor uint32 at SWire addr (0x6bc=PC)
  bkp <addr>                      Set HW breakpoint at addr, run, wait & dump CPU regs
  stp <count>                     Stall CPU, single-step <count> times & dump regs
  sws <sram_addr>                 Stream SWS Printf ring buffer live (e.g. 0x84E700)

Notes:
  * Numeric arguments accept decimal or 0x... hex (e.g. 0x76000, 4096).
  * Hardware CRC16 read verification uses CMD_FLASH_RDCRC (PGM FW >= 0.0.0.3).
  * SWS Printf uses CMD_SWS_PRINTF (PGM FW >= 0.0.0.8 recommended).
"""

##### TlsrPgm.py #####
###  Autor: pvvx   ###
## https://github.com/pvvx/TLSRPGM ##

import sys
import signal
import struct
try:
	import serial
	import serial.tools.list_ports
except ImportError:
	serial = None
import platform
import time
import argparse
import hashlib
import os
import io
from datetime import datetime

try:
 import keyboard
except ImportError:
 class keyboard:
  @staticmethod
  def is_pressed(*args, **kwargs):
   return False

__progname__ = 'TLSR82xx TlsrPgm'
__filename__ = 'TlsrPgm'
__version__ = '26.04.26'

DEFAULT_UART_BAUD = 230400
AUTO_BAUD_CANDIDATES = [1500000, 921600, 230400]

FLASH_SECTOR_SIZE = 4096

#sws_flg = 2
#sws_addr = 0
sws_enable = False
pgm = None

crctable = (
0x0000, 0xC0C1, 0xC181, 0x0140, 0xC301, 0x03C0, 0x0280, 0xC241,
0xC601, 0x06C0, 0x0780, 0xC741, 0x0500, 0xC5C1, 0xC481, 0x0440,
0xCC01, 0x0CC0, 0x0D80, 0xCD41, 0x0F00, 0xCFC1, 0xCE81, 0x0E40,
0x0A00, 0xCAC1, 0xCB81, 0x0B40, 0xC901, 0x09C0, 0x0880, 0xC841,
0xD801, 0x18C0, 0x1980, 0xD941, 0x1B00, 0xDBC1, 0xDA81, 0x1A40,
0x1E00, 0xDEC1, 0xDF81, 0x1F40, 0xDD01, 0x1DC0, 0x1C80, 0xDC41,
0x1400, 0xD4C1, 0xD581, 0x1540, 0xD701, 0x17C0, 0x1680, 0xD641,
0xD201, 0x12C0, 0x1380, 0xD341, 0x1100, 0xD1C1, 0xD081, 0x1040,
0xF001, 0x30C0, 0x3180, 0xF141, 0x3300, 0xF3C1, 0xF281, 0x3240,
0x3600, 0xF6C1, 0xF781, 0x3740, 0xF501, 0x35C0, 0x3480, 0xF441,
0x3C00, 0xFCC1, 0xFD81, 0x3D40, 0xFF01, 0x3FC0, 0x3E80, 0xFE41,
0xFA01, 0x3AC0, 0x3B80, 0xFB41, 0x3900, 0xF9C1, 0xF881, 0x3840,
0x2800, 0xE8C1, 0xE981, 0x2940, 0xEB01, 0x2BC0, 0x2A80, 0xEA41,
0xEE01, 0x2EC0, 0x2F80, 0xEF41, 0x2D00, 0xEDC1, 0xEC81, 0x2C40,
0xE401, 0x24C0, 0x2580, 0xE541, 0x2700, 0xE7C1, 0xE681, 0x2640,
0x2200, 0xE2C1, 0xE381, 0x2340, 0xE101, 0x21C0, 0x2080, 0xE041,
0xA001, 0x60C0, 0x6180, 0xA141, 0x6300, 0xA3C1, 0xA281, 0x6240,
0x6600, 0xA6C1, 0xA781, 0x6740, 0xA501, 0x65C0, 0x6480, 0xA441,
0x6C00, 0xACC1, 0xAD81, 0x6D40, 0xAF01, 0x6FC0, 0x6E80, 0xAE41,
0xAA01, 0x6AC0, 0x6B80, 0xAB41, 0x6900, 0xA9C1, 0xA881, 0x6840,
0x7800, 0xB8C1, 0xB981, 0x7940, 0xBB01, 0x7BC0, 0x7A80, 0xBA41,
0xBE01, 0x7EC0, 0x7F80, 0xBF41, 0x7D00, 0xBDC1, 0xBC81, 0x7C40,
0xB401, 0x74C0, 0x7580, 0xB541, 0x7700, 0xB7C1, 0xB681, 0x7640,
0x7200, 0xB2C1, 0xB381, 0x7340, 0xB101, 0x71C0, 0x7080, 0xB041,
0x5000, 0x90C1, 0x9181, 0x5140, 0x9301, 0x53C0, 0x5280, 0x9241,
0x9601, 0x56C0, 0x5780, 0x9741, 0x5500, 0x95C1, 0x9481, 0x5440,
0x9C01, 0x5CC0, 0x5D80, 0x9D41, 0x5F00, 0x9FC1, 0x9E81, 0x5E40,
0x5A00, 0x9AC1, 0x9B81, 0x5B40, 0x9901, 0x59C0, 0x5880, 0x9841,
0x8801, 0x48C0, 0x4980, 0x8941, 0x4B00, 0x8BC1, 0x8A81, 0x4A40,
0x4E00, 0x8EC1, 0x8F81, 0x4F40, 0x8D01, 0x4DC0, 0x4C80, 0x8C41,
0x4400, 0x84C1, 0x8581, 0x4540, 0x8701, 0x47C0, 0x4680, 0x8641,
0x8201, 0x42C0, 0x4380, 0x8341, 0x4100, 0x81C1, 0x8081, 0x4040 )
def crc16(data: bytearray, length):
	crc = 0xFFFF
	for i in range(0, length):
		crc = (crc >> 8) ^ crctable[(crc ^ data[i]) & 0xFF]
	return bytearray([crc&0xFF,(crc>>8)&0xFF])
def crc_blk(data: bytearray):
	return data+crc16(data, len(data))
def crc_chk(data: bytearray):
	c = data[len(data)-2:];
	if c == crc16(data, len(data)-2):
		return 1
	return 0
def arg_auto_int(x):
	return int(x, 0)
def hex_dump(addr, blk):
	print('%06x: ' % addr, end='')
	for i in range(len(blk)):
		if (i+1) % 16 == 0:
			print('%02x ' % blk[i])
			if i < len(blk) - 1:
				print('%06x: ' % (addr + i + 1), end='')
		else:
			print('%02x ' % blk[i], end='')
	if len(blk) % 16 != 0:
		print('')
def hex2str(blk):
	s = ''
	for i in range(len(blk)):
		s += '%02x' % (blk[i])
		if i < len(blk)-1:
			s += ' '
	return s
def bcd2str(blk):
	s = ''
	for i in range(len(blk)):
		s += '%d.%d' % ((blk[i]>>8)&0x0f, blk[i]&0x0f)
		if i < len(blk)-1:
			s += '.'
	return s

TARGET_CHIP_MAP = {
	0x5562: {'name': 'TLSR8258 / TLSR8253 (825x)', 'short': 'TLSR825x', 'sram': '64 KB', 'ble': 'BLE 5.0 / Mesh / Zigbee'},
	0x5324: {'name': 'TLSR8253', 'short': 'TLSR8253', 'sram': '48 KB', 'ble': 'BLE 5.0'},
	0x5325: {'name': 'TLSR8251 / TLSR8266', 'short': 'TLSR8266', 'sram': '32 KB', 'ble': 'BLE 4.2 / 5.0'},
	0x5326: {'name': 'TLSR8267', 'short': 'TLSR8267', 'sram': '32 KB', 'ble': 'BLE 4.2'},
	0x5327: {'name': 'TLSR8269', 'short': 'TLSR8269', 'sram': '32 KB', 'ble': 'BLE 4.2 / Zigbee'},
	0x5328: {'name': 'TLSR8258 (A0) / TLSR8359', 'short': 'TLSR8258_A0', 'sram': '64 KB', 'ble': 'BLE 5.0 / 2.4G RF'},
	0x5591: {'name': 'TLSR8208', 'short': 'TLSR8208', 'sram': '16 KB', 'ble': 'BLE 5.0'},
	0x5316: {'name': 'TLSR8261', 'short': 'TLSR8261', 'sram': '16 KB', 'ble': 'BLE 4.0'},
	0x5317: {'name': 'TLSR8263', 'short': 'TLSR8263', 'sram': '16 KB', 'ble': 'BLE 4.0'},
}

FLASH_MFG_MAP = {
	0x85: 'Puya Semiconductor (PUYA)',
	0xE8: 'Puya Semiconductor (P25Q)',
	0xEF: 'Winbond',
	0xC8: 'GigaDevice (GD)',
	0xC2: 'Macronix (MXIC)',
	0x1C: 'EON / ESMT',
	0x51: 'GigaDevice / MD',
	0x68: 'Boya / BoyaMicro',
	0x0B: 'XTX (XT25F)',
	0x25: 'Microchip / SST',
	0x9D: 'ISSI',
	0x1F: 'Adesto / Atmel',
	0xA1: 'Fudan Micro (FM)',
	0xE0: 'Berg Micro (BG)',
	0x5E: 'ZBIT (ZB25VQ)',
}

MAC_CANDIDATE_ADDRS = [
	(0x76000, 'Custom FW / ATC / BTHome (0x76000)'),
	(0x7F000, 'Telink Stock / 512KB Config (0x7F000)'),
	(0xFF000, 'Telink Stock / 1MB Config (0xFF000)'),
	(0x3F000, 'Telink Stock / 256KB Config (0x3F000)'),
	(0x1F000, 'Telink Stock / 128KB Config (0x1F000)'),
]

KNOWN_TELINK_OUIS = {
	(0xA4, 0xC1, 0x38),
	(0x48, 0xA0, 0x6D),
	(0x60, 0x57, 0xC6),
	(0xB8, 0xD8, 0x12),
	(0xC4, 0x4F, 0x33),
}

def arg_baud(x):
	if isinstance(x, str) and x.strip().lower() == 'auto':
		return 'auto'
	return int(x, 0)

def beep(times=1):
	sys.stdout.write('\a' * times)
	sys.stdout.flush()

def is_valid_ieee_mac(mac_bytes):
	if len(mac_bytes) != 6:
		return False
	if mac_bytes.count(0xFF) >= 4 or mac_bytes.count(0x00) >= 4:
		return False
	if (mac_bytes[5] & 0x01) != 0:
		return False
	return True

def find_mac_in_dump(image):
	fallback = None
	for addr, desc in MAC_CANDIDATE_ADDRS:
		if addr + 6 > len(image):
			continue
		candidate = image[addr : addr + 6]
		if is_valid_ieee_mac(candidate):
			mac_str = ':'.join('%02X' % b for b in reversed(candidate))
			oui = (candidate[5], candidate[4], candidate[3])
			if oui in KNOWN_TELINK_OUIS:
				return mac_str, '0x%06X (%s)' % (addr, desc)
			if fallback is None:
				fallback = (mac_str, '0x%06X (%s)' % (addr, desc))
	return fallback if fallback else ('Not detected', 'None')

def list_candidate_ports():
	ports = list(serial.tools.list_ports.comports())
	usb_ports = []
	other_ports = []
	for p in ports:
		dev = p.device
		desc = (p.description or '') + ' ' + (p.hwid or '')
		is_usb = (
			p.vid is not None
			or 'USB' in desc.upper()
			or 'ttyUSB' in dev
			or 'ttyACM' in dev
			or 'cu.usb' in dev
		)
		if is_usb:
			usb_ports.append(dev)
		elif not dev.startswith('/dev/ttyS'):
			other_ports.append(dev)
	return sorted(usb_ports) + sorted(other_ports)

def print_specs_report(specs):
	wip = 'BUSY' if (specs['flash_status'] & 0x01) else 'READY'
	bp = (specs['flash_status'] >> 2) & 0x07
	uid_hex = ' '.join('%02X' % b for b in specs['flash_uid']) if specs['flash_uid'] else 'Unavailable'
	print('=' * 68)
	print('                  TARGET HARDWARE SPECIFICATIONS')
	print('=' * 68)
	print('  Chip Name       : %s' % specs['chip_name'])
	print('  Chip ID / Rev   : 0x%04X / Rev 0x%02X' % (specs['chip_id'], specs['chip_rev']))
	print('  Internal SRAM   : %s (%s)' % (specs['sram_size'], specs['ble_info']))
	print('  CPU PC / [0602] : 0x%08X / 0x%02X' % (specs['pc'], specs['cpu_state']))
	print('-' * 68)
	print('  Flash Vendor    : %s' % specs['flash_mfg'])
	print('  Flash JEDEC ID  : 0x%06X' % specs['jedec_id'])
	print('  Flash Capacity  : %s (0x%06X bytes)' % (specs['flash_size_str'], specs['flash_size']))
	print('  Flash Status    : 0x%02X (%s, BP=%d)' % (specs['flash_status'], wip, bp))
	print('  Flash Unique ID : %s' % uid_hex)
	print('=' * 68)

class TLSRPGM:
	MAX_BUF_READ_SIZE = 1024
	MAX_RESPONSE_SIZE = 1026
	MIN_RESPONSE_SIZE = 6

	FLASH_SECTOR_SIZE = FLASH_SECTOR_SIZE

	CMD_FUNCS = 0
	CMD_FLASH_READ = 1
	CMD_FLASH_WRITE = 2
	CMD_FLASH_SECT_ERASE = 3
	CMD_FLASH_ALL_ERASE = 4
	CMD_FLASH_GET_JEDEC_ID = 5
	CMD_FLASH_GET_STATUS = 6
	CMD_SWIRE_READ = 7
	CMD_SWIRE_WRITE = 8
	CMD_SWIRE_AREAD = 9
	CMD_SWIRE_AWRITE = 10
	CMD_SWIRE_FIFO_READ = 11
	CMD_SWIRE_FIFO_FWRITE = 12
	CMD_FLASH_WRRD = 13
	CMD_FLASH_RDCRC = 14 # FW ver >= 0.0.0.3
	CMD_SWS_PRINTF = 15 # FW ver >= 0.0.0.4
	CMD_WAIT_RESP = 16 # FW ver >= 0.0.0.5

	CMDF_GET_VERSION = 0
	CMDF_MCU_REBOOT = 1
	CMDF_SWIRE_CFG = 2
	CMDF_EXT_POWER = 3
	CMDF_SWIRE_ACTIVATE = 4
	CMDF_UART_BAUD = 5

	ERR_NONE = 0 # Errors None                               
	ERR_FUNC = 1 # Function number error                     
	ERR_LEN  = 2 # Data length error                         
	ERR_READ = 3 # Swire read timeout                        
	ERR_BUSY = 4 # Timeout flag while reading analog register
	ERR_CRC  = 5 # Error CRC                                 
	ERR_BAUD = 6 # Invalid baud rate number                  
	ERR_MAX  = 7 

	ERR_RETRY_COUNT = 3

	port = None
	err = 0
	wcnt = 0

	tab_err = [ \
		"Errors None", \
		"Function number error!", \
		"Data length error!", \
		"SWire read timeout!", \
		"Timeout flag while reading analog register!", \
		"Error CRC!", \
		"Invalid baud rate number!", \
	]

	tab_uart_baud = [ \
		115200, \
		230400, \
		460800, \
		500000, \
		921600, \
		1000000, \
		1500000, \
		2000000, \
		3000000, \
	]

	pgm_version = 0
	pgm_ver_int = 0
	pgm_cid = 0
	pgm_pwr = 1

	pgm_swsps = 0.96
	pgm_clk = 24
	pgm_swdiv = 5
	pgm_swaddrlen = 3
	pgm_swbuf = b'\x5a\x00\x06\x02\x00\x05'
	ext_chip = None
	pgm_chip = '?'
	#-----------------------------------------------
	# Functions for an PGM device
	#-----------------------------------------------
	def __init__(self, port, baud = DEFAULT_UART_BAUD, quiet = False):
		self._port = None
		self.quiet = quiet
		self.reopen(baud, port)
	# Open/ReOpen com-port
	def reopen(self, baud, port = None):
		if port == None:
			if self.port == None:
				if not self.quiet:
					print('ReOpen ?')
				return False
			else:
				if self._port is not None:
					try:
						self._port.close()
					except:
						pass
				port = self.port
			if not self.quiet:
				print('ReOpen %s, %d bit/s...' % (port, baud), end = ' ')
		else:
			if not self.quiet:
				print('Open %s, %d bit/s...' % (port, baud), end = ' ')
		try:
			self._port = serial.Serial(port, baud, \
									   serial.EIGHTBITS,\
									   serial.PARITY_NONE, \
									   serial.STOPBITS_ONE)
			self._port.setRTS(False)
			self._port.setDTR(False)
			time.sleep(0.05)
			self._port.flushOutput()
			self._port.flushInput()
			self._port.reset_output_buffer()
			self._port.reset_input_buffer()
			self._port.timeout = 0.15
		except:
			if not self.quiet:
				print('Error!')
			self._port = None
			return False
		if not self.quiet:
			print('ok')
		self.port = port
		return True
	# Send to usb-com-port
	def write(self, wblk):
		self._port.reset_input_buffer()
		return self._port.write(wblk)
	# Read usb-com-port
	def read(self, rdlen):
		try:
			rblk = self._port.read(rdlen)
			#if len(rblk) < rdlen:
			#	rblk += self._port.read(rdlen - len(rblk))
		except:
			print('\rError read %s!' % (self.port), file=sys.stderr)
			return None
		return rblk
	def error_msg(self):
		err = self.err & 0xff
		if err >= self.ERR_MAX:
			return 'Unknown error!'
		return self.tab_err[err]
	def command(self, wblk, rdlen = None):
		if self._port is None:
			self.err = 100
			return None
		try:
			w = self.write(crc_blk(wblk))
		except:
			self.err = 100
			return None
		if w != len(wblk)+2:
			self.err = 100
			return None
		if rdlen == None:
			rdlen = self.MAX_RESPONSE_SIZE
			chklen = self.MIN_RESPONSE_SIZE
		else:
			chklen = rdlen
		self.wcnt = 0
		rblk = self.read(rdlen)
		if rblk == None or len(rblk) < chklen:
			self.err =  self.ERR_LEN +100
			return None;
		if not crc_chk(rblk):
			self.err =  self.ERR_CRC +100
			return None;
		if rblk[0] != wblk[0]:
			self.err =  self.ERR_FUNC +100
			return None;
		self.err = rblk[1];
		self.wcnt = rblk[2] | (rblk[3]<<8)
		if self.err != self.ERR_NONE:
			return None;
		return rblk
	# Set Default UART speed on PGM board
	def close(self, power_off = False):
		if self._port is None or not self._port.is_open:
			return
		try:
			if power_off:
				self.SetPinRST(0)
			if self._port.baudrate != DEFAULT_UART_BAUD:
				self.command(struct.pack('<BBH', self.CMD_FUNCS, self.CMDF_UART_BAUD, 1), 6)
		except:
			pass
		try:
			self._port.close()
		except:
			pass
		self._port = None
	# Set UART speed on PGM board
	def SetUartBaud(self, baud = DEFAULT_UART_BAUD):
		for i in range(len(self.tab_uart_baud)):
			if self.tab_uart_baud[i] == baud:
				if not self.quiet:
					print('Set Speed UART PGM board %d bits/s...' % (baud), end = ' ')
				prev_baud = int(self._port.baudrate) if self._port else DEFAULT_UART_BAUD
				data = self.command(struct.pack('<BBH', self.CMD_FUNCS, self.CMDF_UART_BAUD, i), 6)
				if data == None:
					if not self.quiet:
						print('Error(%d)' % self.err, file=sys.stderr)
					return False
				if not self.quiet:
					print('ok')
				if self._port.baudrate != baud:
					if not self.reopen(baud):
						self.reopen(prev_baud)
						if not self.quiet:
							print('Please reset PGM board!')
						return False
				return True
		print('Invalid PGM baud rate (%d)!' % (baud))
		return False
	# Reset/Power pin On/Off
	def SetPinRST(self, out = 1):
		out_val = 1 if out else 0
		data = self.command(struct.pack('<BBH', self.CMD_FUNCS, self.CMDF_EXT_POWER, out_val), 7)
		if data == None:
			if not self.quiet:
				print('\rError(%d) Set pin RST/Power!' % self.err, file=sys.stderr)
			return False
		self.pgm_pwr = data[4]
		return True
	# Get version pgm board
	def GetVersion(self, quiet = None):
		if quiet is None:
			quiet = self.quiet
		data = self.command(struct.pack('<BBH', self.CMD_FUNCS, self.CMDF_GET_VERSION, 0), 19)
		if data == None:
			if not quiet:
				print('\rError(%d) Read PGM Version and Config!' % self.err)
			return False
		self.pgm_version = [data[5], data[4]]
		self.pgm_ver_int = (data[5] << 8) | data[4]
		(self.pgm_cid, self.pgm_pwr, self.pgm_swdiv, self.pgm_swaddrlen) = struct.unpack('<HBBB', data[6:11])
		self.pgm_swbuf = data[11:17]
		if self.pgm_cid == 0 and self.pgm_ver_int == 0:
			if not quiet:
				print('Connection to the PGM board?')
			return False
		if self.pgm_cid == 0x5562:
			self.pgm_chip = 'TLSR825x'
			self.pgm_clk = 24
		elif self.pgm_cid == 0x5325:
			self.pgm_chip = 'TLSR8266'
			self.pgm_clk = 32
		elif self.pgm_cid == 0x5326:
			self.pgm_chip = 'TLSR8267'
			self.pgm_clk = 32
		elif self.pgm_cid == 0x5327:
			self.pgm_chip = 'TLSR8269'
			self.pgm_clk = 32
		elif self.pgm_cid == 0x5591:
			self.pgm_chip = 'TLSR8208'
			self.pgm_clk = 32
		else:
			self.pgm_clk = 32
			self.pgm_chip = '?'
		self.pgm_swsps = self.pgm_clk/5/self.pgm_swdiv if self.pgm_swdiv else 0.0
		if not quiet:
			print('PGM: ChipID: 0x%04x (%s), ver:' % (self.pgm_cid, self.pgm_chip), bcd2str(self.pgm_version))
			if self.pgm_ver_int < 4:
				print('Attention: this program requires PGM version 0.0.0.4 or higher!')
			print('swdiv %d, addrlen %d, swbuf [%s], ' % (self.pgm_swdiv, self.pgm_swaddrlen, hex2str(self.pgm_swbuf)), end = '')
			if self.pgm_pwr != 0:
				print('pwr On')
			else:
				print('pwr Off')
			print('SWire bit rate: %.4f Mbits/s' % self.pgm_swsps)
		return True
	# Set ext addr  
	def setextadr(self, eaddr = 0):
		swbuf = struct.pack('<BBBBBB',0x5a,0,6,2,eaddr & 0xff,5)
		data = self.command(struct.pack('<BBHBB', self.CMD_FUNCS, self.CMDF_SWIRE_CFG, 0, self.pgm_swdiv, self.pgm_swaddrlen) + swbuf, 14)
		if data == None:
			print('Error(%d) Set PGM Config!' % self.err, file=sys.stderr)
			return False
		return True
	# Set Speed SWM pgm board
	def SetPgmConfig(self, swdiv = None, swaddrlen = None, swbuf = None):
		if swdiv == None:
			swdiv = self.pgm_swdiv;
		if swaddrlen == None:
			swaddrlen = self.pgm_swaddrlen;
		if swbuf == None:
			swbuf = self.pgm_swbuf;
		data = self.command(struct.pack('<BBHBB', self.CMD_FUNCS, self.CMDF_SWIRE_CFG, 0, swdiv, swaddrlen) + swbuf, 14)
		if data == None:
			print('Error(%d) Set PGM Config!' % self.err, file=sys.stderr)
			return False
		(self.pgm_swdiv, self.pgm_swaddrlen) = struct.unpack('<BB', data[4:6])
		self.pgm_swbuf = data[6:12]
		print('PGM: swdiv %d, addrlen %d, swbuf [%s]' % (self.pgm_swdiv, self.pgm_swaddrlen, hex2str(self.pgm_swbuf)))
		self.pgm_swsps = self.pgm_clk/5/self.pgm_swdiv
		print('SWire bit rate: %.4f Mbits/s' % self.pgm_swsps)
		return True
	# Reset/Power pin On, Activate, get PC
	def Activate(self, tms, quiet = False):
		count = 0
		if tms > 0:
			count = int(tms/((self.pgm_swaddrlen + 5.7)*5*self.pgm_swdiv/2400))
			if count > 0xffff:
				count = 0xffff
		t = self._port.timeout
		self._port.timeout = tms/1000 + 0.5
		if not quiet:
			print('Activate %d ms... ' % tms, end = '')
		wblk = struct.pack('<BBH', self.CMD_FUNCS, self.CMDF_SWIRE_ACTIVATE, count)
		try:
			self.write(crc_blk(wblk))
			rblk = self.read(6)
		except:
			self._port.timeout = t
			self.err = 100
			return False
		if rblk == None or len(rblk) < 6:
			self._port.timeout = t
			self.err =  self.ERR_LEN +100
			if not quiet:
				print('\r\nTimeout response - Check PGM connected!') 
			return False
		if len(rblk) != 6 or rblk[0] != wblk[0]:
			self._port.timeout = t
			self.err =  self.ERR_FUNC +100
			if not quiet:
				print('\r\nIncorrect response - Check PGM connected!') 
			return False
		self.err = rblk[1];
		self.wcnt = rblk[2] | (rblk[3]<<8)
		if self.wcnt > 0 and self.wcnt <= 4:
			extra = self.read(self.wcnt)
			if extra is None:
				self._port.timeout = t
				self.err = self.ERR_LEN + 100
				return False
			rblk += extra
		self._port.timeout = t
		if not crc_chk(rblk):
			self.err =  self.ERR_CRC +100
			if not quiet:
				print('\r\nIncorrect response - BAD CRC!') 
			return False
		if self.err != self.ERR_NONE:
			if not quiet:
				if self.err >= len(self.tab_err):
					print('\r\nError(%d): Unknown error!' % (self.err), file=sys.stderr)
				else:
					if self.err == self.ERR_READ:
						print('Error!')
						print('Check SWM<->SWS connection or Reset/Activation time!', file=sys.stderr)
					print('\r\nError(%d): %s' % (self.err, self.tab_err[self.err]), file=sys.stderr)
			return False
		if len(rblk) >= 10:
			self.ext_pc = struct.unpack('<I', rblk[4:8])
			if not quiet:
				print('ok')
				print('CPU PC=0x%08x' % (self.ext_pc))
		else:
			if not quiet:
				print('\r\nUnknown response!') 
			return False
		return True
	#-----------------------------------------------
	# Functions for an external device
	#-----------------------------------------------
	# Read Flash Status
	def ReadFlashStatus(self):
		data = self.command(struct.pack('<BBH', self.CMD_FLASH_GET_STATUS, 0, 0), 7)
		if data == None or self.wcnt != 1:
			print('\rError get Flash Status! (%d)' % self.err, file=sys.stderr) 
			return None
		print('Flash Status Register: 0x%02x' % data[4])
		return data[4]
	# Waiting for Flash to be ready
	def WaitingFlashReady(self, count = 300):
		while count > 0:
			data = self.command(struct.pack('<BBH', self.CMD_FLASH_GET_STATUS, 0, 0), 7)
			if data == None or self.wcnt != 1:
				print('\rError get Flash Status! (%d)' % self.err, file=sys.stderr) 
				return False
			if (data[4] & 0x01) == 0:
				#print('Flash status 0x%02x, cnt %d' % (data[4], count))
				return True
			count -= 1
		print('\rTimeout! Flash Status 0x%02x!' % data[4]) 
		return False
	# Write Flash Status
	def WriteFlashStatus(self, fstatus = 0):
		data = self.command(struct.pack('<BBHHB', self.CMD_FLASH_WRRD, 0, 0, 0, 6), 6)
		if data == None:
			print('\rError Write Flash Status! (%d)' % self.err, file=sys.stderr) 
			return None
		data = self.command(struct.pack('<BBHHBB', self.CMD_FLASH_WRRD, 0, 0, 0, 1, fstatus&0xff), 6)
		if data == None:
			print('\rError Write Flash Status! (%d)' % self.err, file=sys.stderr)
			return None
		if not self.WaitingFlashReady():
			return None
		#data = self.command(struct.pack('<BBHHB', self.CMD_FLASH_WRRD, 0, 0, 1, 5), 7)
		#if data == None:
		#	print('\rError get Flash Status! (%d)' % self.err) 
		#	return None
		#print('Flash Status Register 0x%02x' % data[4])
		return True
	# CPcpu Ext. Chip
	def ReadPCcpu(self):
		rdsize = 0x4
		offset = 0x6bc
		data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
		if data == None or self.wcnt != rdsize:
			print('\rError Read SWire data! (%d)' % self.err, file=sys.stderr) 
			return False
		self.ext_pc = struct.unpack('<I', data[4:8])
		rdsize = 0x1
		offset = 0x602
		data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
		if data == None or self.wcnt != rdsize:
			print('\rError Read SWire data! (%d)' % self.err, file=sys.stderr) 
			return False
		print('CPU PC=0x%08x' % self.ext_pc, '([0x0602] = 0x%02x)' % data[4])
		return True
	# Dump Ext. Chip regs
	def DumpChipRegs(self, offset = 0x60, size = 0x20):
		print('-------------------------------------------------------')
		print('\rREGISTERS:')
		rdsize = self.MAX_BUF_READ_SIZE
		while size > 0:
			if rdsize > size:
				rdsize = size
			data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
			if data == None or self.wcnt != rdsize:
				print('\rError Read SWire data! (%d)' % self.err, file=sys.stderr) 
				return False
			hex_dump(offset, data[4:rdsize+4])
			offset += rdsize
			size -= rdsize
		return True
	# Dump Ext. Chip Flash
	def DumpChipFlash(self, offset = 0x0, size = 0x20):
		print('-------------------------------------------------------')
		print('\rFLASH:')
		rdsize = self.MAX_BUF_READ_SIZE
		while size > 0:
			if rdsize > size:
				rdsize = size
			data = self.command(struct.pack('<BBHH', self.CMD_FLASH_READ, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
			if data == None or self.wcnt != rdsize:
				print('\rError Read SWire data! (%d)' % self.err, file=sys.stderr) 
				return False
			hex_dump(offset, data[4:rdsize+4])
			offset += rdsize
			size -= rdsize
		return True
	# Dump Ext. Chip Ana regs
	def DumpChipARegs(self, offset = 0x0, rdsize = None):
		if not self.EnableClkALGM():
			return False
		if rdsize == None:
			if self.pgm_swaddrlen == 3:
				rdsize = 0x100
			else:
				rdsize = 0x80
		data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_AREAD, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
		if data == None or self.wcnt != rdsize:
			print('\rError Read SWire data! (%d)' % self.err, file=sys.stderr) 
			return False
		print('-------------------------------------------------------')
		print('\rANALOG REGISTERS:')
		hex_dump(offset, data[4:rdsize+4])
		return True
	# Dump Ext. Chip FlashUID
	def DumpChipFlashUID(self, offset = 0, rdsize = None):
		if rdsize == None:
			if self.ext_chip == 'TLSR8208':
				rdsize = 0x10
			else:
				rdsize = 0x20
		rdsize +=4 # +4 dimmy
		data = self.command(struct.pack('<BBHHB', self.CMD_FLASH_WRRD, offset & 0xff, (offset>>8) & 0xffff, rdsize, 0x4B), rdsize+6)
		if data == None or self.wcnt != rdsize + 1:
			print('\rError Read Flash UID! (%d)' % self.err, file=sys.stderr)
			return False
		print('-------------------------------------------------------')
		print('\rFLASH UID:')
		hex_dump(offset, data[8:rdsize+4])
		return True
	# Read Ext. Chip ID
	def ReadChipID(self):
		rdsize = 3
		offset = 0x7d
		data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
		if data == None or self.wcnt != rdsize:
			print('\rError get Chip ID! (%d)' % self.err, file=sys.stderr) 
			return False
		self.ext_cver = data[4]
		self.ext_cid = data[5] | (data[6]<<8)
		if self.ext_cid == 0x5562:
			self.ext_chip = 'TLSR825x'
		elif self.ext_cid == 0x5325:
			self.ext_chip = 'TLSR8266'
		elif self.ext_cid == 0x5326:
			self.ext_chip = 'TLSR8267'
		elif self.ext_cid == 0x5327:
			self.ext_chip = 'TLSR8269'
		elif self.ext_cid == 0x5591:
			self.ext_chip = 'TLSR8208'
		else:
			self.ext_chip = None
		if self.ext_chip == None:
			print('Chip ID: 0x%04X, rev: 0x%02X' % (self.ext_cid, self.ext_cver))
		else:
			print('Chip %s ID: 0x%04X, rev: 0x%02X' % (self.ext_chip, self.ext_cid, self.ext_cver))
		return True
	# Read Flash JEDEC ID
	def ReadFlashJEDECID(self):
		data = self.command(struct.pack('<BBH', self.CMD_FLASH_GET_JEDEC_ID, 0, 0), 6+3)
		if data == None or self.wcnt != 3:
			print('\rError get Flash JEDEC ID! (%d)' % self.err) 
			return False
		self.jedecid = (data[4]<<16) | (data[5]<<8) | data[6]
		print('Flash JEDEC ID: 0x%06X, Size: %d kbytes' % (self.jedecid, ((1<<data[6])>>10)))
		return True
	# Read Flash CRC16 (FW ver >= 0.0.0.3)
	def ReadFlashCRC16(self, offset, size):
		offset &= 0xffffff
		data = self.command(struct.pack('<BBHH', self.CMD_FLASH_RDCRC, offset & 0xff, (offset>>8) & 0xffff, size), 6)
		if data == None:
			return None
		return data[2:4]
	# Verify flash block via hardware CRC16 with 256-byte fallback
	def VerifyBlockCRC(self, offset, blk, rdcrc_limit = 1024):
		size = len(blk)
		if size <= rdcrc_limit:
			hw_crc = self.ReadFlashCRC16(offset, size)
			if hw_crc is not None:
				return hw_crc == crc16(blk, size), rdcrc_limit
			if self.err == self.ERR_LEN and rdcrc_limit > 256:
				rdcrc_limit = 256
			else:
				return False, rdcrc_limit
		sub = 0
		while sub < size:
			part = blk[sub : sub + rdcrc_limit]
			hw_crc = self.ReadFlashCRC16(offset + sub, len(part))
			if hw_crc is None or hw_crc != crc16(part, len(part)):
				return False, rdcrc_limit
			sub += len(part)
		return True, rdcrc_limit
	# Autonomous target contact poller (PWR cycle + SWire activate + ID debounce)
	def WaitForTarget(self, act_ms = 150, pwr_off_ms = 60, stable_reads = 3, expected_ids = None,
					  banner_msg = 'Waiting for target pins (PWR->VCC, GND, SWS)... touch & hold steady'):
		attempt = 0
		t_start = time.monotonic()
		prev_quiet = self.quiet
		self.quiet = True
		print('\n[~] %s' % banner_msg)
		try:
			while True:
				attempt += 1
				off_sec = (max(pwr_off_ms, 150) if attempt % 10 == 0 else pwr_off_ms) / 1000.0
				self.SetPinRST(0)
				time.sleep(off_sec)
				if not self.Activate(act_ms, quiet = True):
					elapsed = time.monotonic() - t_start
					print('\r[~] Waiting for contact... %5.1fs (attempts: %d)   ' % (elapsed, attempt), end = '', flush = True)
					continue
				if not self.WriteRegsData(0x602, b'\x05'):
					continue
				readings = []
				stable = True
				for i in range(max(1, stable_reads)):
					if i > 0:
						time.sleep(0.025)
					# Probe Chip ID
					cid_raw = self.ReadRegsData(0x7d, 3)
					if cid_raw is None or self.wcnt != 3:
						stable = False
						break
					cver = cid_raw[4]
					cid = cid_raw[5] | (cid_raw[6] << 8)
					# Probe Flash JEDEC ID
					jdata = self.command(struct.pack('<BBH', self.CMD_FLASH_GET_JEDEC_ID, 0, 0), 9)
					if jdata is None or self.wcnt != 3:
						stable = False
						break
					jedec_id = (jdata[4] << 16) | (jdata[5] << 8) | jdata[6]
					if cid in (0x0000, 0xFFFF) or jedec_id in (0x000000, 0xFFFFFF):
						stable = False
						break
					readings.append((cid, cver, jedec_id))
				if not stable or len(set(readings)) != 1:
					print('\r[!] Contact bounced at %4.1fs, stabilizing...        ' % (time.monotonic() - t_start), end = '', flush = True)
					continue
				cid, cver, jedec_id = readings[0]
				if expected_ids is not None and (cid, jedec_id) != expected_ids:
					print('\r[!] Target mismatch (got Chip=0x%04X JEDEC=0x%06X), retrying...   ' % (cid, jedec_id), end = '', flush = True)
					continue
				self.ext_cver = cver
				self.ext_cid = cid
				if cid == 0x5562:
					self.ext_chip = 'TLSR825x'
				elif cid == 0x5325:
					self.ext_chip = 'TLSR8266'
				elif cid == 0x5326:
					self.ext_chip = 'TLSR8267'
				elif cid == 0x5327:
					self.ext_chip = 'TLSR8269'
				elif cid == 0x5591:
					self.ext_chip = 'TLSR8208'
				else:
					self.ext_chip = None
				self.jedecid = jedec_id
				print('\r[+] Target locked in %.1fs (attempt #%d)!                ' % (time.monotonic() - t_start, attempt))
				pc_val = self.ext_pc[0] if isinstance(self.ext_pc, tuple) else self.ext_pc
				return pc_val, cid, cver, jedec_id
		finally:
			self.quiet = prev_quiet
	# Probe full hardware specifications once target is locked
	def ProbeTargetSpecs(self, pc, cid, cver, size_override = None):
		prev_quiet = self.quiet
		self.quiet = True
		try:
			chip_meta = TARGET_CHIP_MAP.get(cid)
			if chip_meta:
				chip_name = chip_meta['name']
				chip_short = chip_meta['short']
				sram_size = chip_meta['sram']
				ble_info = chip_meta['ble']
			else:
				chip_name = 'Unknown TLSR (0x%04X)' % cid
				chip_short = 'TLSR_%04X' % cid
				sram_size = 'Unknown'
				ble_info = 'Unknown'
			pc_raw = self.ReadRegsData(0x6bc, 4)
			if pc_raw is not None and len(pc_raw) >= 8:
				pc = struct.unpack('<I', pc_raw[4:8])[0]
			cpu_raw = self.ReadRegsData(0x602, 1)
			cpu_state = cpu_raw[4] if cpu_raw is not None and len(cpu_raw) >= 5 else 0
			jdata = self.command(struct.pack('<BBH', self.CMD_FLASH_GET_JEDEC_ID, 0, 0), 9)
			if jdata is not None and self.wcnt == 3:
				mfg, _mem_type, cap = jdata[4], jdata[5], jdata[6]
				jedec_id = (mfg << 16) | (_mem_type << 8) | cap
				flash_mfg = FLASH_MFG_MAP.get(mfg, 'Unknown Vendor (0x%02X)' % mfg)
				if size_override is not None:
					flash_size = size_override
					flash_size_str = '%d KB (override)' % (flash_size // 1024)
				elif 0x10 <= cap <= 0x1A:
					flash_size = 1 << cap
					if flash_size >= 1024 * 1024:
						flash_size_str = '%d MB (%d KB)' % (flash_size // (1024 * 1024), flash_size // 1024)
					else:
						flash_size_str = '%d KB' % (flash_size // 1024)
				else:
					flash_size = 512 * 1024
					flash_size_str = '512 KB (assumed, raw cap 0x%02X)' % cap
			else:
				jedec_id = 0
				flash_mfg = 'Unknown'
				flash_size = size_override if size_override is not None else 512 * 1024
				flash_size_str = '%d KB (fallback)' % (flash_size // 1024)
			fs_raw = self.command(struct.pack('<BBH', self.CMD_FLASH_GET_STATUS, 0, 0), 7)
			flash_status = fs_raw[4] if fs_raw is not None and self.wcnt == 1 else 0
			uid_rdsize = 16 + 4
			uid_raw = self.command(struct.pack('<BBHHB', self.CMD_FLASH_WRRD, 0, 0, uid_rdsize, 0x4B), uid_rdsize + 6)
			flash_uid = bytes(uid_raw[8 : 8 + 16]) if uid_raw is not None and self.wcnt == uid_rdsize + 1 else None
			return {
				'chip_id': cid,
				'chip_rev': cver,
				'chip_name': chip_name,
				'chip_short': chip_short,
				'sram_size': sram_size,
				'ble_info': ble_info,
				'pc': pc,
				'cpu_state': cpu_state,
				'jedec_id': jedec_id,
				'flash_mfg': flash_mfg,
				'flash_size': flash_size,
				'flash_size_str': flash_size_str,
				'flash_status': flash_status,
				'flash_uid': flash_uid,
			}
		finally:
			self.quiet = prev_quiet
	# Autonomous full/sized flash dump with hardware CRC16 and slip recovery
	def DumpFlashAutonomous(self, specs, use_crc = True, act_ms = 150, pwr_off_ms = 60, stable_reads = 3):
		total = specs['flash_size']
		buf = bytearray(total)
		offset = 0
		t_dump_start = time.monotonic()
		rdcrc_limit = self.MAX_BUF_READ_SIZE
		crc_enabled = use_crc and self.pgm_ver_int >= 3
		retries_used = 0
		slip_recoveries = 0
		mode_str = 'Hardware CRC16 verified' if crc_enabled else 'CRC16 disabled'
		print('\n[*] Dumping %d KB flash (%s) — keep pins steady...' % (total // 1024, mode_str))
		while offset < total:
			chunk_size = min(self.MAX_BUF_READ_SIZE, total - offset)
			block_ok = False
			for _ in range(3):
				data = self.command(struct.pack('<BBHH', self.CMD_FLASH_READ, offset & 0xff, (offset>>8) & 0xffff, chunk_size), chunk_size + 6)
				if data is None or self.wcnt != chunk_size:
					retries_used += 1
					continue
				blk = data[4 : 4 + chunk_size]
				if crc_enabled:
					ok, rdcrc_limit = self.VerifyBlockCRC(offset, blk, rdcrc_limit)
					if not ok:
						retries_used += 1
						continue
				buf[offset : offset + chunk_size] = blk
				block_ok = True
				break
			if not block_ok:
				slip_recoveries += 1
				beep(1)
				print('\n[!] Link lost at 0x%06X (%.1f%%) — re-hold probes to resume automatically...' % (offset, offset * 100.0 / total))
				self.WaitForTarget(
					act_ms = act_ms,
					pwr_off_ms = pwr_off_ms,
					stable_reads = stable_reads,
					expected_ids = (specs['chip_id'], specs['jedec_id']),
					banner_msg = 'Re-acquiring target to resume from 0x%06X...' % offset,
				)
				print('[*] Resuming dump...')
				continue
			offset += chunk_size
			elapsed = max(time.monotonic() - t_dump_start, 0.001)
			speed_kbs = (offset / 1024.0) / elapsed
			pct = offset * 100.0 / total
			eta = (total - offset) / 1024.0 / speed_kbs if speed_kbs > 0 else 0.0
			bar_len = 28
			filled = int(bar_len * offset / total)
			bar = '#' * filled + '-' * (bar_len - filled)
			print('\r  [%s] %5.1f%%  %4d/%d KB  %5.1f KB/s  ETA %4.1fs ' % (bar, pct, offset // 1024, total // 1024, speed_kbs, eta), end = '', flush = True)
		elapsed_total = time.monotonic() - t_dump_start
		print('\n[+] Read complete in %.2fs (retries=%d, slip_recoveries=%d)' % (elapsed_total, retries_used, slip_recoveries))
		return bytes(buf)
	# Read Blocks Flash to stream (with optional CRC16 & slip recovery when retry_cfg is set)
	def ReadBlockFlash(self, stream, offset = 0, size = 0x80000, retry_cfg = None, use_crc = False):
		offset &= 0xffffff
		rdsize = self.MAX_BUF_READ_SIZE
		rdcrc_limit = self.MAX_BUF_READ_SIZE
		crc_enabled = bool(use_crc and self.pgm_ver_int >= 3)
		while size > 0:
			if rdsize > size:
				rdsize = size
			print('\rRead from 0x%06x...' % offset, end = '')
			attempts = 3 if retry_cfg else 1
			blk = None
			for _ in range(attempts):
				data = self.command(struct.pack('<BBHH', self.CMD_FLASH_READ, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
				if data == None or self.wcnt != rdsize:
					continue
				cand = data[4:rdsize+4]
				if crc_enabled:
					ok, rdcrc_limit = self.VerifyBlockCRC(offset, cand, rdcrc_limit)
					if not ok:
						continue
				blk = cand
				break
			if blk is None:
				if retry_cfg:
					beep(1)
					print('\n[!] Link lost reading flash at 0x%06x — re-acquiring target...' % offset)
					self.WaitForTarget(
						act_ms = retry_cfg['act_ms'],
						pwr_off_ms = retry_cfg['pwr_off_ms'],
						stable_reads = retry_cfg['stable_reads'],
						expected_ids = retry_cfg.get('expected_ids'),
						banner_msg = 'Re-acquiring target to resume flash read from 0x%06X...' % offset,
					)
					continue
				print('\rError Read Flash data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			stream.write(blk);
			size -= rdsize
			offset += rdsize
		print('\r                               \r',  end = '')
		return True
	# Read Blocks Reg/Sram to stream
	def ReadBlockRegs(self, stream, offset = 0x40000, size = 0x10000):
		offset &= 0xffffff
		rdsize = self.MAX_BUF_READ_SIZE
		while size > 0:
			if rdsize > size:
				rdsize = size
			print('\rRead from 0x%06x...' % offset, end = '')
			data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
			if data == None or self.wcnt != rdsize:
				print('\rError Read SWire data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			stream.write(data[4:rdsize+4]);
			size -= rdsize
			offset += rdsize
		print('\r                               \r',  end = '')
		return True
	# Read Reg/Sram Data 
	def ReadRegsData(self, offset = 0x800000, size = 4):
		data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, size), size+6)
		if data == None or self.wcnt != size:
			print('Error Read SWire data! (%d)' % self.err, file=sys.stderr)
			return None
		return data
	# Write Reg/Sram Data 
	def WriteRegsData(self, offset = 0x602, wdata = b'\x05'):
		offset &= 0xffffff
		wrsize = len(wdata)
		data = self.command(struct.pack('<BBH', self.CMD_SWIRE_WRITE, offset & 0xff, (offset>>8) & 0xffff) + wdata, 6)
		if data == None or self.wcnt != wrsize:
			print('\rError Write SWire data at 0x%06x! ' % offset, end = '', file=sys.stderr)
			return False
		return True
	# Write Blocks Reg/Sram from stream
	def WriteBlockRegs(self, stream, offset = 0, size = 0):
		wrsize = self.MAX_BUF_READ_SIZE
		cnt_err = self.ERR_RETRY_COUNT
		while size > 0:
			offset &= 0xffffff
			data = stream.read(wrsize)
			wrsize = len(data)
			if not data or wrsize == 0: # end of stream
				print(' Error Read file!', file=sys.stderr)
				return False
			while 1:
				print('\rWrite to 0x%06x...' % offset, end = '')
				rdata = self.command(struct.pack('<BBH', self.CMD_SWIRE_WRITE, offset & 0xff, (offset>>8) & 0xffff)+data, 6)
				if rdata == None or self.wcnt != wrsize:
					cnt_err -= 1
					if cnt_err == 0:
						print('\rError Write Swire data at 0x%06x!' % offset, file=sys.stderr)
						return False
					print(' Error', cnt_err)
				else:
					cnt_err = self.ERR_RETRY_COUNT
				break
			offset += wrsize
			size -= wrsize
		print('\r                               \r',  end = '')
		return True
	# Read Blocks Analog Reg to stream
	def ReadBlockAnalogRegs(self, stream, offset = 0x000, size = None):
		if not self.EnableClkALGM():
			return False
		if size == None:
			if self.pgm_swaddrlen == 3:
				size = 0x100
			else:
				size = 0x80
		offset &= 0xff
		rdsize = self.MAX_BUF_READ_SIZE
		cnt_err = self.ERR_RETRY_COUNT
		while size > 0:
			if rdsize > size:
				rdsize = size
			print('\rRead from 0x%06x...' % offset, end = '')
			data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_AREAD, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
			if data == None  or self.wcnt != rdsize:
				print('\rError Read SWire data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			stream.write(data[4:rdsize+4]);
			size -= rdsize
			offset += rdsize
		print('\r                               \r',  end = '')
		return True
	# Write Blocks Analog Reg from stream
	def WriteBlockAnalogRegs(self, stream, offset = 0x000, size = 0x100):
		if not self.EnableClkALGM():
			return False
		wrsize = 0x100
		cnt_err = self.ERR_RETRY_COUNT
		while size > 0:
			offset &= 0x0ff
			data = stream.read(wrsize)
			wrsize = len(data)
			if not data or wrsize == 0: # end of stream
				print(' Error Read file!')
				return False
			while 1:
				print('\rWrite to 0x%06x...' % offset, end = '')
				rdata = self.command(struct.pack('<BBH', self.CMD_SWIRE_AWRITE, offset & 0xff, (offset>>8) & 0xffff)+data, 6)
				if rdata == None or self.wcnt != wrsize:
					cnt_err -= 1
					if cnt_err == 0:
						print('\rError Write aregs data at 0x%06x!' % offset, file=sys.stderr)
						return False
					print(' Error', cnt_err)
				else:
					cnt_err = self.ERR_RETRY_COUNT
				break
			offset += wrsize
			size -= wrsize
		print('\r                               \r',  end = '')
		return True
	# Read FlashUID
	def ReadFlashUID(self):
		offset = 0
		rdsize = 256+4 # 8+4
		data = self.command(struct.pack('<BBHHB', self.CMD_FLASH_WRRD, offset & 0xff, (offset>>8) & 0xffff, rdsize, 0x4B), rdsize+6)
		if data == None: # or self.wcnt+1 != rdsize:
			print('\rError Read Flash UID! (%d)' % self.err, file=sys.stderr)
			return False
		self.FlashUID = data[8:16]
		print('Flash UID:' , self.FlashUID)
		hex_dump(0, data[8:264])
		return True
	def _retry_relock_and_unlock(self, offset, action_label, retry_cfg):
		beep(1)
		print('\n[!] Link lost during %s at 0x%06x — re-acquiring target...' % (action_label, offset))
		self.WaitForTarget(
			act_ms = retry_cfg['act_ms'],
			pwr_off_ms = retry_cfg['pwr_off_ms'],
			stable_reads = retry_cfg['stable_reads'],
			expected_ids = retry_cfg.get('expected_ids'),
			banner_msg = 'Re-acquiring target to resume %s at 0x%06X...' % (action_label, offset),
		)
		return self.FlashUnlock() is not None
	# Erase Sectors Flash
	def EraseSectorsFlash(self, offset = 0, count = 1, retry_cfg = None):
		cnt_err = self.ERR_RETRY_COUNT
		for i in range(count):
			offset = offset & (0xffffff^(self.FLASH_SECTOR_SIZE-1))
			print('\rErase sector at 0x%06x...' % offset, end = '')
			while 1:
				data = self.command(struct.pack('<BBH', self.CMD_FLASH_SECT_ERASE, offset & 0xff, (offset>>8) & 0xffff), 6)
				if data == None:
					if not self.WaitingFlashReady():
						if retry_cfg and self._retry_relock_and_unlock(offset, 'sector erase', retry_cfg):
							cnt_err = self.ERR_RETRY_COUNT
							continue
						return False
					cnt_err -= 1
					if cnt_err == 0:
						if retry_cfg and self._retry_relock_and_unlock(offset, 'sector erase', retry_cfg):
							cnt_err = self.ERR_RETRY_COUNT
							continue
						print('\rError Erase sector at 0x%06x!' % offset, file=sys.stderr)
						return False
					print(' Error', cnt_err)
				else:
					if not self.WaitingFlashReady():
						if retry_cfg and self._retry_relock_and_unlock(offset, 'sector erase', retry_cfg):
							cnt_err = self.ERR_RETRY_COUNT
							continue
						return False
					cnt_err = self.ERR_RETRY_COUNT
					break
			offset += self.FLASH_SECTOR_SIZE
		print('\r                               \r',  end = '')
		return True
	# Erase All Blocks Flash
	def EraseAllFlash(self):
		data = self.command(struct.pack('<BBH', self.CMD_FLASH_ALL_ERASE, 0, 0))
		if data == None:
			print('\rError Erase All Flash! (%d)' % self.err, file=sys.stderr)
			return False
		return self.WaitingFlashReady(3000)
	# Write Blocks Flash from stream
	def WriteBlockFlash(self, stream, offset = 0, size = 0, erase = True, retry_cfg = None, use_crc = True):
		wrsize = 0x100 # Flash write max 256 bytes
		cnt_err = self.ERR_RETRY_COUNT
		if erase and (offset & (self.FLASH_SECTOR_SIZE-1)) != 0:
			erasec = offset & (0xffffff^(self.FLASH_SECTOR_SIZE-1))
		else:
			erasec = 0xffffffff # = flag
		while size > 0:
			offset &= 0xffffff
			if erase:
				wrsec = offset & (0xffffff^(self.FLASH_SECTOR_SIZE-1))
				if erasec != wrsec:
					print('\rErase at 0x%06x...' % offset, end = '')
					while 1:
						data = self.command(struct.pack('<BBH', self.CMD_FLASH_SECT_ERASE, offset & 0xff, (offset>>8) & 0xffff), 6)
						if data == None:
							if not self.WaitingFlashReady():
								if retry_cfg and self._retry_relock_and_unlock(offset, 'sector erase', retry_cfg):
									cnt_err = self.ERR_RETRY_COUNT
									continue
								return False
							cnt_err -= 1
							if cnt_err == 0:
								if retry_cfg and self._retry_relock_and_unlock(offset, 'sector erase', retry_cfg):
									cnt_err = self.ERR_RETRY_COUNT
									continue
								print('\rError Erase sector at 0x%06x!' % offset, file=sys.stderr)
								return 0
							print(' Error', cnt_err)
						else:
							if not self.WaitingFlashReady():
								if retry_cfg and self._retry_relock_and_unlock(offset, 'sector erase', retry_cfg):
									cnt_err = self.ERR_RETRY_COUNT
									continue
								return False
							cnt_err = self.ERR_RETRY_COUNT
							break
					erasec = wrsec
			data = stream.read(wrsize)
			wrsize = len(data)
			if not data or wrsize == 0: # end of stream
				print(' Error Read file!', file=sys.stderr)
				return False
			if any(e != 0xff for e in data):
				while 1:
					print('\rWrite to 0x%06x...' % offset, end = '')
					rdata = self.command(struct.pack('<BBH', self.CMD_FLASH_WRITE, offset & 0xff, (offset>>8) & 0xffff)+data, 6)
					if rdata == None or self.wcnt != wrsize:
						if not self.WaitingFlashReady():
							if retry_cfg and self._retry_relock_and_unlock(offset, 'flash write', retry_cfg):
								cnt_err = self.ERR_RETRY_COUNT
								continue
							return False
						cnt_err -= 1
						if cnt_err == 0:
							if retry_cfg and self._retry_relock_and_unlock(offset, 'flash write', retry_cfg):
								cnt_err = self.ERR_RETRY_COUNT
								continue
							print('\rError Write Flash data at 0x%06x!' % offset, file=sys.stderr)
							return False
						print(' Error', cnt_err)
					else:
						if not self.WaitingFlashReady():
							if retry_cfg and self._retry_relock_and_unlock(offset, 'flash write', retry_cfg):
								cnt_err = self.ERR_RETRY_COUNT
								continue
							return False
						if use_crc and self.pgm_ver_int >= 0x0003:
							rdata = self.command(struct.pack('<BBHH', self.CMD_FLASH_RDCRC, offset & 0xff, (offset>>8) & 0xffff, wrsize), 6)
							if rdata == None or rdata[2:4] != crc16(data, len(data)):
								if retry_cfg:
									cnt_err -= 1
									if cnt_err > 0:
										continue
									if self._retry_relock_and_unlock(offset, 'CRC verify', retry_cfg):
										cnt_err = self.ERR_RETRY_COUNT
										continue
								print('\rFlash CRC16 check error in block at 0x%06x!' % offset, file=sys.stderr)
								return False
						cnt_err = self.ERR_RETRY_COUNT
						break
			offset += wrsize
			size -= wrsize
		print('\r                               \r',  end = '')
		return True
	# Enable CLK ALGM on 825x
	def EnableClkALGM(self):
		rdsize = 4
		offset = 0x61
		data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, rdsize), rdsize+6)
		if data == None or self.wcnt != rdsize:
			print('Error Read SWire data! (%d)' % self.err, file=sys.stderr) 
			return False
		x = bytearray(data[4:8])
		# TLSR825x - bit 3, TLSR826x - bit 1
		if self.pgm_swaddrlen == 3:
			msk_bit = 0x08
		else:
			msk_bit = 0x02
		if (x[0] & msk_bit) != 0 or (x[3] & msk_bit) == 0:
			x[0] &= ~msk_bit # reg 0x61 reg_rst1
			x[3] |= msk_bit # reg 0x64 reg_clk_en1
			data = self.command(struct.pack('<BBH', self.CMD_SWIRE_WRITE, offset & 0xff, (offset>>8) & 0xffff) + x, 6)
			if data == None or self.wcnt != rdsize:
				#print('Error!') 
				print('Error Write SWire data! (%d)' % self.err, file=sys.stderr) 
				print('Error Activate ALGM!', file=sys.stderr)
				return False
		return True
	def WaitPC(self, ttime = 1, dw = 0):
		if ttime < 1:
			ttime = 1
		flgsleep = False
		flgrun = False
		i = 0
		offset = 0x6bc
		dw = dw & 0xffffff
		#print('Wait PC == 0x%06x...' % dw)
		wblk = struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, 4) 
		t1 = time.time()
		t2 = t1
		te = t1 + ttime
		sws_enable = True
		while t2 < te and sws_enable:
			if keyboard.is_pressed("esc"):
				print()
				print('Keyboard Break!')
				break
			self.write(crc_blk(wblk))
			rblk = self.read(6)
			t2 = time.time()
			if rblk == None or len(rblk) < 6 or rblk[0] != wblk[0]:
				print('\r\nError Read response!', file=sys.stderr) 
				return False
			self.err = rblk[1];
			self.wcnt = rblk[2] | (rblk[3]<<8)
			if self.wcnt == 4 and self.err == 0:
				rblk += self.read(4)
				if crc_chk(rblk):
					if flgsleep:
						t1 = t2
						print()
					self.ext_reg = struct.unpack('<I', rblk[4:8])
					print('\rPC: 0x%06x' % self.ext_reg, end = '')
					if flgrun:
						print(' (%.3f)' % (t2-t1), end = '')
					if dw == self.ext_reg[0]:
						print(' - ok')
						return True
					flgsleep = False
					flgrun = True
				else:
					print('\r\nError Read response!', file=sys.stderr)
					return False
			else:
				print('\r\nError CPU sleep!', file=sys.stderr)
				return False
		print()
		return True
	# Dump CPU registers
	def DumpCPURegs(self):
		print('-------------------------------------------------------')
		if self.pgm_swaddrlen == 2 and self.ext_chip == None:
			self.ReadChipID()
		print('CPU registers:')
		rblk = self.ReadRegsData(0x0680,128)
		if rblk == None:
			return False
		regs = struct.unpack('<IIIIIIIIIIIIIIIIIIIIIIIIIIIIIIII', rblk[4:132])
		print("flg: 0x%08x (psr)" % regs[16])
		if self.ext_chip == 'TLSR8266':
			print("r00: 0x%08x ???: 0x%08x" %  (regs[0], regs[17]))
			print("r01: 0x%08x" %  regs[1])
			print("r02: 0x%08x s02: 0x%08x" %  (regs[2], regs[18]))
		else:
			print("r00: 0x%08x s00: 0x%08x" %  (regs[0], regs[17]))
			print("r01: 0x%08x" %  regs[1])
			print("r02: 0x%08x" %  regs[2])
		for i in range(8):
			print("r%02d: 0x%08x s%02d: 0x%08x" % (i+3, regs[i+3], i+3, regs[i+19]))
		print("r11: 0x%08x (fp) 0x%08x" % (regs[11], regs[11+16]))
		print("r12: 0x%08x (ip) 0x%08x" % (regs[12], regs[12+16]))
		print("r13: 0x%08x (sp) 0x%08x" % (regs[13], regs[13+16]))
		print("r14: 0x%08x (lr) 0x%08x" % (regs[14], regs[14+16]))
		if self.ext_chip == 'TLSR8266':
			print("r15: 0x%08x (pc)" % (regs[15]))
		else:
			print("r15: 0x%08x (pc) 0x%08x" % (regs[15], regs[18]))
			print("m64: 0x%08x =(mul32*32)>>32" % regs[31]) # 0x6fc = (mul32*32)>>32

		rblk = self.ReadRegsData(regs[13], 48)
		if rblk == None:
			return False
		stek = struct.unpack('<IIIIIIIIIIII', rblk[4:52])
		print("SP 0x%06x:" % regs[13])
		print("0x%08x 0x%08x 0x%08x 0x%08x" % (stek[0], stek[1], stek[2], stek[3]))
		print("0x%08x 0x%08x 0x%08x 0x%08x" % (stek[4], stek[5], stek[6], stek[7]))
		print("0x%08x 0x%08x 0x%08x 0x%08x" % (stek[8], stek[9], stek[10], stek[11]))

		return True
	# Test
	def TestDebugPC(self, ttime = 1, offset = 0x6bc):
		if ttime < 1:
			ttime = 1
		flgsleep = False
		flgrun = False
		i = 0
		print('Read register addres 0x%06x:' % offset)
		wblk = struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, 4) 
		t1 = time.time()
		t2 = t1
		te = t1 + ttime
		sws_enable = True
		while t2 < te and sws_enable:
			if keyboard.is_pressed("esc"):
				print()
				print('Keyboard Break!')
				break
			self.write(crc_blk(wblk))
			rblk = self.read(6)
			t2 = time.time()
			if rblk == None or len(rblk) < 6 or rblk[0] != wblk[0]:
				print('\r\nError Read response!', file=sys.stderr) 
				return False
			self.err = rblk[1];
			self.wcnt = rblk[2] | (rblk[3]<<8)
			if self.wcnt == 4 and self.err == 0:
				rblk += self.read(4)
				if crc_chk(rblk):
					if flgsleep:
						t1 = t2
						print()
					self.ext_reg = struct.unpack('<I', rblk[4:8])
					print('\r0x%08x' % self.ext_reg, end = '')
					if flgrun:
						print(' (%.3f)' % (t2-t1), end = '')
					flgsleep = False
					flgrun = True
				else:
					print('\r\nError Read response!', file=sys.stderr) 
					return False
			else:
				if flgrun:
					print()
				print('\rCPU sleep? (%.3f sec)' % (t2-t1), end = '')
				if not flgsleep:
					t1 = t2
				flgsleep = True
				flgrun = False
		print()
		return True
	# Fast Wait Response & Write
	def WaitResp(self, twait_sec = 1, offset = 0x6bc, wraddr = None, wrdata = None):
		if twait_sec < 1:
			twait_sec = 1
		if wraddr != None and wrdata != None:
			data = self.command(struct.pack('<BBHBH', self.CMD_WAIT_RESP, offset & 0xff, (offset>>8) & 0xffff, wraddr & 0xff, (wraddr>>8) & 0xffff) + wrdata, 6)
		elif wraddr == None and wrdata == None:
			data = self.command(struct.pack('<BBH', self.CMD_WAIT_RESP, offset & 0xff, (offset>>8) & 0xffff), 6)
		else:
			print('Invalid arguments Wait Response command!') 
			return False
		if data == None:
			print('Error Wait Respone command! (%d)' % self.err, file=sys.stderr) 
			return False
		t1 = time.time()
		te = t1 + twait_sec
		tt = t1
		while tt < te:
			if keyboard.is_pressed("esc"):
				print()
				print('Keyboard Break!')
				break
			rblk = self.read(10)
			if rblk == None:
				print()
				return False
			if len(rblk) == 0:
				tt = time.time()
				if tt - t1 > 1:
					print('\rSleep %.0f sec?' % (tt-t1), end = '')
					t1 == tt
				continue
			if len(rblk) < 10 or rblk[0] != self.CMD_WAIT_RESP:
				print('\r\nError Read response!', file=sys.stderr) 
				return False
			if rblk[2] == 4 and rblk[3] == 0 and rblk[1] == 0 and crc_chk(rblk):
				self.ext_pc = struct.unpack('<I', rblk[4:8])
				if offset == 0x6bc:
					print('\rCPU PC=0x%08x          ' % self.ext_pc)
				else:
					print('\rReg at 0x%06x=0x%08x   ' % (offset, self.ext_pc))
				if wraddr != None and wrdata != None:
					if wraddr == 0x602 and (wrdata == b'\x05' or wrdata == b'\x06'):
						data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, wraddr & 0xff, (wraddr>>8) & 0xffff, 1), 7)
						if data == None or self.wcnt != 1:
							print('\rError Read SWire data! (%d)' % self.err, file=sys.stderr) 
							return False
						if wrdata == b'\x05':
							if data[4] != 5:
								print('\rError: CPU capture failed! ([0x0602] = 0x%02x)' % data[4], file=sys.stderr) 
								return False
							print('CPU Stopped ([0x0602] = 0x05)')
						if wrdata == b'\x06':
							if data[4] != 6:
								print('\rError: CPU capture failed! ([0x0602] = 0x%02x)' % data[4], file=sys.stderr) 
								return False
							print('CPU Stall ([0x0602] = 0x06)')
						offset = 0x6bc
						data = self.command(struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, 4), 10)
						if data == None or self.wcnt != 4:
							print('\rError Read SWire data! (%d)' % self.err, file=sys.stderr) 
							return False
						self.ext_pc = struct.unpack('<I', data[4:8])
						print('CPU PC=0x%08x' % self.ext_pc)
						return True
					else:
						s = hex2str(wrdata)
						print('Wr [0x%06x] = %s)' %(wraddr, s))
			else:
				print('\r\nError Read response!', file=sys.stderr)
				return False
			return True
		print()
		return False
	# Wait CPU run
	def WaitCPU(self, twait_sec = 1, offset = 0x6bc, flg_stop = False, flg_stall = False):
		if twait_sec < 1:
			twait_sec = 1
		if self.pgm_ver_int >= 5:
			if flg_stop:
				return self.WaitResp(twait_sec, offset, 0x0602, b'\x05')
			elif flg_stall:
				return self.WaitResp(twait_sec, offset, 0x0602, b'\x06')
			return self.WaitResp(twait_sec, offset)
		flgsleep = False
		wblk = struct.pack('<BBHH', self.CMD_SWIRE_READ, offset & 0xff, (offset>>8) & 0xffff, 4) 
		t1 = time.time()
		t2 = t1
		te = t1 + twait_sec
		sws_enable = True
		while t2 < te and sws_enable:
			if keyboard.is_pressed("esc"):
				print()
				print('Keyboard Break!')
				break
			self.write(crc_blk(wblk))
			rblk = self.read(6)
			t2 = time.time()
			if rblk == None:
				print()
				return False
			if len(rblk) < 6 or rblk[0] != wblk[0]:
				print('\r\nError Read response!', file=sys.stderr) 
				return False
			self.err = rblk[1];
			self.wcnt = rblk[2] | (rblk[3]<<8)
			if self.wcnt == 4 and self.err == 0:
				rdata = self.read(4)
				if rdata == None:
					print()
					return False
				rblk += rdata
				if crc_chk(rblk):
					if flgsleep:
						t1 = t2
						print()
					self.ext_pc = struct.unpack('<I', rblk[4:8])
					if offset == 0x6bc:
						print('\rCPU PC=0x%08x' % self.ext_pc)
					else:
						print('\rReg32 at 0x%06x=0x%08x' % (offset, self.ext_pc))
					if flg_stop:
						print('CPU Stop...', end = ' ')
						if not self.WriteRegsData(0x602, b'\x05'):
							return False
						print('ok')
					if flg_stall:
						print('CPU Stall...', end = ' ')
						if not self.WriteRegsData(0x602, b'\x06'):
							return False
						print('ok')
					return True
				else:
					print('\r\nError Read response!', file=sys.stderr) 
					return False
			else:
				print('\rCPU sleep? (%.3f sec)' % (t2-t1), end = '')
				if not flgsleep:
					t1 = t2
				flgsleep = True
		print()
		return False
	def FlashUnlock(self):
		print('Write 0 to Flash Status Register...')
		if self.WriteFlashStatus(0) == None:
			return None
		ret = self.ReadFlashStatus()
		if ret == None or ret != 0:
			print('\r\nError unlock Flash!', file=sys.stderr) 
			return None
		return ret
	def SwsPrintf(self, offset = 0x84E700):
		if self.pgm_ver_int < 8:
			print('Attention: this program requires PGM version 0.0.0.8 or higher!')
			return False
		print('Open SWS Printf at SRAM address 0x%06x...' % (offset), end = '')
		data = self.command(struct.pack('<BBHB', self.CMD_SWS_PRINTF, offset & 0xff, (offset>>8) & 0xffff, 0), 6)
		if data == None or self.wcnt != 1:
			print('error!', flush=True)
			return False
		print('ok')
		self._port.timeout = 0.01
		sws_enable = True
		while sws_enable: #TODO
			if keyboard.is_pressed("esc"):
				print()
				print('Keyboard Break!')
				break
			try:
				rblk = self._port.read(253)
			except:
				#print('Error read %s!' % (self.port))
				return False
			if len(rblk) != 0:
				print(rblk.decode(encoding='ascii', errors='ignore'), end = '', flush=True) # encoding="utf-8" 
		return True
	# Dump OTP registers
	def DumpOTPRegs(self, offset = 0x3fc0, size = None):
		print('-------------------------------------------------------')
		print('\rOTP: ')
		if size == None:
			size = 0x40
		if size <= 0:
			print('Read Size = 0!', file=sys.stderr)
			return False
		if self.ext_chip != 'TLSR8208':
			print('Read OTP only for TLSR8208!', file=sys.stderr)
			return False
		regs = self.ReadRegsData(0x80010,2)
		if regs == None:
			return False
		#if not self.WriteRegsData(0x80011, b'\x10'):
		#	return False
		if not self.WriteRegsData(0x80011, b'\x30'):
			return False
		time.sleep(0.01)
		if regs[5] != 0x03:
			if not self.WriteRegsData(0x80010, b'\x03'):
				return False
		rdsize = 4
		tmp = self.ReadRegsData(0x80017, 1) # reg_otp_dat
		if tmp == None:
			return False
		status =  ~tmp[5]
		addr = offset;
		data = bytearray()
		while size > 0:
			if rdsize > size:
				rdsize = size
			if not self.WriteRegsData(0x80014, struct.pack('<H', offset & 0xffff)): # reg_otp_pa = addr;
				print('\r\nError Read OTP data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			tmp = self.ReadRegsData(0x8001C, 4) # reg_otp_rd_dat
			if tmp == None:
				print('\r\nError Read OTP data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			tmp = self.ReadRegsData(0x80017, 1) # reg_otp_dat
			if (tmp[5] & status) != 0:
				print('\r\nError Read OTP data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			tmp = self.ReadRegsData(0x8001C, 4) # reg_otp_rd_dat
			if tmp == None:
				print('\r\nError Read OTP data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			data += tmp[4:rdsize+4]
			size -= rdsize
			offset += rdsize
			if (size <= 0) or len(data) == 16:
				hex_dump(addr & 0xffff, data)
				data = bytearray()
				addr += 16
		if not self.WriteRegsData(0x80010, regs[4:6]):
			return False
		return True

	# Read Blocks OTP to stream
	def ReadBlockOTP(self, stream, offset = 0x0000, size = None):
		if size == None:
			size = 0x4000
		if size <= 0:
			print('\nRead Size = 0!', file=sys.stderr)
			return False
		if self.ext_chip != 'TLSR8208':
			print('\nRead OTP only for TLSR8208!', file=sys.stderr)
			return False
		#if not self.EnableClkALGM():
		#	return False
		regs = self.ReadRegsData(0x80010,2)
		if regs == None:
			return False
		#if not self.WriteRegsData(0x80011, b'\x10'):
		#	return False
		if not self.WriteRegsData(0x80011, b'\x30'):
			return False
		time.sleep(0.01)
		#if regs[5] != 0x03:
		if not self.WriteRegsData(0x80010, b'\x03'):
			return False
		rdsize = 4
		print('\rRead from 0x%06x...' % offset, end = '')
		data = self.ReadRegsData(0x80017, 1) # reg_otp_dat
		if data == None:
			return False
		status =  ~data[5]
		while size > 0:
			if rdsize > size:
				rdsize = size
			if (size & 0x3f) == 0:
				print('\rRead from 0x%06x...' % offset, end = '')
			if not self.WriteRegsData(0x80014, struct.pack('<H', offset & 0xffff)): # reg_otp_pa = addr;
				print('\r\nError Read OTP data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			data = self.ReadRegsData(0x8001C, 4) # reg_otp_rd_dat
			if data == None:
				print('\r\nError Read OTP data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			data = self.ReadRegsData(0x80017, 1) # reg_otp_dat
			if (data[5] & status) != 0:
				print('\r\nError Read OTP data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			data = self.ReadRegsData(0x8001C, 4) # reg_otp_rd_dat
			if data == None:
				print('\r\nError Read OTP data at 0x%06x! ' % offset, end = '', file=sys.stderr)
				return False
			stream.write(data[4:rdsize + 4]);
			size -= rdsize
			offset += rdsize
		if not self.WriteRegsData(0x80010, regs[4:6]):
			return False
		print('\r                               \r',  end = '')
		return True

_cleanup_state = {'pgm': None, 'power_off_on_exit': False}

def signal_handler(sig, frame):
	print()
	print('Keyboard Break!')
	sws_enable = False #TODO
	pgm_obj = _cleanup_state.get('pgm')
	if pgm_obj is not None:
		pgm_obj.close(power_off=_cleanup_state.get('power_off_on_exit', False))
	sys.exit(130)

def connect_programmer(port_arg):
	if serial is None:
		print("Error: 'pyserial' is required. Install with: pip3 install pyserial", file=sys.stderr)
		sys.exit(1)
	if port_arg:
		candidates = [port_arg]
	else:
		candidates = list_candidate_ports()
		if not candidates:
			print('Error: No USB serial ports found. Plug in TLSR_SWire_Flasher or pass -p <port>.', file=sys.stderr)
			sys.exit(1)

	for cand in candidates:
		if not port_arg:
			print('Probing candidate port %s...' % cand)
		client = TLSRPGM(cand, DEFAULT_UART_BAUD, quiet=bool(not port_arg))
		if client.port is None:
			if port_arg:
				sys.exit(1)
			continue
		if client.GetVersion(quiet=bool(not port_arg)):
			if not port_arg:
				print('Open %s, %d bit/s... ok' % (cand, DEFAULT_UART_BAUD))
				client.quiet = False
				client.GetVersion(quiet=False)
			return client
		if port_arg:
			client.close(power_off=False)
			sys.exit(1)
		client.close(power_off=False)

	print('Error: No responding TLSRPGM programmer found on: %s' % ', '.join(candidates), file=sys.stderr)
	sys.exit(1)

def negotiate_uart_baud(pgm, baud_arg, prefer_fast=False):
	if baud_arg == 'auto' or (baud_arg is None and prefer_fast):
		for target_baud in AUTO_BAUD_CANDIDATES:
			if target_baud == DEFAULT_UART_BAUD:
				return DEFAULT_UART_BAUD
			if pgm.SetUartBaud(target_baud):
				return target_baud
			print('Fallback to lower UART speed...')
		return DEFAULT_UART_BAUD
	target_baud = DEFAULT_UART_BAUD if baud_arg is None else baud_arg
	if target_baud != DEFAULT_UART_BAUD:
		if not pgm.SetUartBaud(target_baud):
			pgm.close(power_off=False)
			sys.exit(1)
	return target_baud

#============================= 
# main()
#============================= 
def main():
	# First time slice
	t1 = time.time()
	signal.signal(signal.SIGINT, signal_handler)

	help_epilog = """\
WIRING (3-wire SWire, no RST line required):
  Programmer PWR -> Target VCC (software-switched 3.3V)
  Programmer GND -> Target GND
  Programmer SWM -> Target SWS

OPERATION MODES:
  1. Power Control (--pwr):
     TlsrPgm.py --pwr              Toggle target PWR on <-> off and exit immediately
     TlsrPgm.py --pwr on           Turn target PWR on and exit immediately
     TlsrPgm.py --pwr off          Turn target PWR off and exit immediately

  2. Autonomous Dump (hardware-CRC16 verified, auto-resume on slip):
     TlsrPgm.py dump               Wait for contact, probe specs, dump full flash
     TlsrPgm.py dump -o fw.bin     Save dump to fw.bin (keeps retrying if probe slips)
     TlsrPgm.py dump -s 0x80000    Override detected flash size (bytes)

  3. Retry / Hand-Held Probe Mode (-R / --retry):
     Combines with any subcommand (we, wf, rf, es, ea, i, ds, df, da...).
     Repeatedly cycles PWR + SWire Activate until stable chip/flash lock, and
     automatically re-acquires & resumes if hand-held probe pins slip mid-transfer:
     TlsrPgm.py -R we 0x0 fw.bin   Auto-detect USB port, wait for contact, erase+flash
     TlsrPgm.py -R i               Wait for contact, then dump full chip/flash info

  4. Standard Fixed-Timing Mode (classic TlsrPgm):
     TlsrPgm.py -p /dev/ttyUSB0 -b 1500000 -t 100 -a 150 we 0x0 fw.bin
     TlsrPgm.py -u -t 50 -a 100 rf 0 0x80000 out.bin   (TLSR826x 2-byte SWire addr)
"""

	parser = argparse.ArgumentParser(
		description='%s version %s — TLSR82xx SWire Programmer, Power Control & Autonomous Flash Dumper' % (__progname__, __version__),
		epilog=help_epilog,
		prog=__filename__,
		formatter_class=argparse.RawDescriptionHelpFormatter)
	parser.add_argument(
		'-p', '--port',
		help='Serial port device (default: auto-discover USB programmer)',
		default=None)
	parser.add_argument(
		'-b', '--baud',
		help='UART Baud Rate, or "auto" (default: auto 1500000->921600->230400 for dump/-R, else %d)' % DEFAULT_UART_BAUD,
		type=arg_baud,
		default=None)
	parser.add_argument(
		'--pwr', '--power',
		dest='pwr',
		nargs='?',
		const='toggle',
		choices=['on', 'off', 'toggle'],
		default=None,
		help='Toggle target PWR pin (on|off|toggle; bare --pwr toggles) and exit immediately')
	parser.add_argument(
		'-R', '--retry',
		help='Autonomous retry mode: cycle PWR + Activate until stable contact, auto-resume on slip',
		action='store_true')
	parser.add_argument(
		'--act-ms',
		help='SWire activation pulse ms per retry cycle (default: 150)',
		type=arg_auto_int,
		default=150)
	parser.add_argument(
		'--pwr-off-ms',
		help='PWR-off discharge ms per retry cycle (default: 60)',
		type=arg_auto_int,
		default=60)
	parser.add_argument(
		'--stable-reads',
		help='Consecutive matching Chip+JEDEC reads before locking in retry/dump mode (default: 3)',
		type=arg_auto_int,
		default=3)
	parser.add_argument(
		'--no-crc',
		help='Skip hardware CRC16 block verification during dump / flash write / flash read',
		action='store_true')
	parser.add_argument(
		'--keep-power',
		help='Keep target PWR enabled after dump or --retry exits (default: power off)',
		action='store_true')
	parser.add_argument(
		'-t', '--trst',
		help='Hard Reset Time ms (default: 0 ms)',
		type=arg_auto_int,
		default = 0)
	parser.add_argument(
		'-a', '--act',
		help='Activation Time ms (0-off, default: 0 ms)',
		type=arg_auto_int,
		default = 0)
	parser.add_argument(
		'-z', '--zw',
		help='Wait Start CPU (default: 0 sec) (before main processing)',
		type=arg_auto_int,
		default = 0)
	parser.add_argument(
		'-s', '--stopcpu',
		help='CPU Stop (before main processing)',
		action="store_true")
	parser.add_argument(
		'-c', '--cpustall',
		help='CPU Stall (before main processing)',
		action="store_true")
	parser.add_argument(
		'-r', '--run',
		help='CPU Run (post main processing)',
		action="store_true")
	parser.add_argument(
		'-g', '--go',
		help='CPU Go (post main processing)',
		action="store_true")
	parser.add_argument(
		'-m', '--mrst',
		help='Soft Reset (MCU Reboot) (post main processing)',
		action="store_true")
	parser.add_argument(
		'-d', '--div',
		help='Set the SWire transfer rate divisor',
		type=arg_auto_int,
		default = 0)
	parser.add_argument(
		'-o', '--osws',
		help='Open SWS Printf (post main processing)',
		type=arg_auto_int,
		default = 0)
	parser.add_argument(
		'-u', '--u2b',
		help='Use 2 bytes swire address (TLSR826x)',
		action="store_true")
	parser.add_argument(
		'-w', '--wrktime',
		help='Show Worked Time',
		action="store_true")
	subparsers = parser.add_subparsers(
			dest='operation',
			help='Run '+__filename__+' {command} -h for additional help')

	parser_dump_flash = subparsers.add_parser(
			'dump',
			help='Autonomous contact detect, chip specs report & CRC16-verified full flash dump')
	parser_dump_flash.add_argument('-o', '--out', help='Output .bin filename (default: auto-named in CWD)', default=None)
	parser_dump_flash.add_argument('-s', '--size', help='Override flash dump size in bytes', type=arg_auto_int, default=None)

	parser_read_flash = subparsers.add_parser(
			'rf',
			help='Read Flash to binary file')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('size', help='Size of region', type=arg_auto_int)
	parser_read_flash.add_argument('filename', help='Name of binary file')

	parser_burn_flash = subparsers.add_parser(
			'we',
			help='Write file to Flash with sectors erases')
	parser_burn_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_burn_flash.add_argument('filename', help='Name of binary file')

	parser_write_flash = subparsers.add_parser(
			'wf',
			help='Write file to Flash without sectors erases')
	parser_write_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_write_flash.add_argument('filename', help='Name of binary file')

	parser_erase_sec_flash = subparsers.add_parser(
			'es',
			help='Erase Region (sectors) of Flash')
	parser_erase_sec_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_erase_sec_flash.add_argument('size', help='Size of region', type=arg_auto_int)

	parser_erase_all_flash = subparsers.add_parser(
			'ea',
			help='Erase All Flash')
	parser_read_fstatus = subparsers.add_parser(
			'fsr',
			help='Read Flash Status Register')
	parser_write_fstatus = subparsers.add_parser(
			'fsw',
			help='Write Flash Status Register')
	parser_write_fstatus.add_argument('fsreg', help='Register Value (byte)', type=arg_auto_int)

	parser_read_flash = subparsers.add_parser(
			'rs',
			help='Read SWire address to binary file')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('size', help='Size of region', type=arg_auto_int)
	parser_read_flash.add_argument('filename', help='Name of binary file')

	parser_write_flash = subparsers.add_parser(
			'ws',
			help='Write file to Swire addres')
	parser_write_flash.add_argument('address', help='Starting address for write', type=arg_auto_int)
	parser_write_flash.add_argument('filename', help='Name of binary file')

	parser_write_flash = subparsers.add_parser(
			'wsb',
			help='Write byte to Swire addres')
	parser_write_flash.add_argument('address', help='Write address', type=arg_auto_int)
	parser_write_flash.add_argument('value', help='byte (8 bits)', type=arg_auto_int)

	parser_write_flash = subparsers.add_parser(
			'wsw',
			help='Write 16-bit word to Swire address')
	parser_write_flash.add_argument('address', help='Write address', type=arg_auto_int)
	parser_write_flash.add_argument('value', help='short word (16 bits)', type=arg_auto_int)

	parser_write_flash = subparsers.add_parser(
			'wsd',
			help='Write 32-bit word to Swire address')
	parser_write_flash.add_argument('address', help='Write address', type=arg_auto_int)
	parser_write_flash.add_argument('value', help='word (32 bits)', type=arg_auto_int)

	parser_write_flash = subparsers.add_parser(
			'bkp',
			help='Set break-point address (TLSR825x)')
	parser_write_flash.add_argument('address', help='Write address', type=arg_auto_int)

	parser_write_flash = subparsers.add_parser(
			'stp',
			help='CPU Step')
	parser_write_flash.add_argument('count', help='Step count', type=arg_auto_int)

	parser_read_flash = subparsers.add_parser(
			'ra',
			help='Read Analog Registers to binary file')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('size', help='Size of region', type=arg_auto_int)
	parser_read_flash.add_argument('filename', help='Name of binary file')

	parser_read_flash = subparsers.add_parser(
			'ro',
			help='Read TLSR8208 OTP to binary file')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('size', help='Size of region', type=arg_auto_int)
	parser_read_flash.add_argument('filename', help='Name of binary file')

	parser_read_flash = subparsers.add_parser(
			'wa',
			help='Write file to Analog Registers')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('filename', help='Name of binary file')

	parser_read_flash = subparsers.add_parser(
			'i', help='External Chip Information')
	parser_read_flash = subparsers.add_parser(
			'ds',
			help='Dump Swire (Registers or SRAM)')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('size', help='Size of region', type=arg_auto_int)
	parser_read_flash = subparsers.add_parser(
			'df',
			help='Dump Flash')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('size', help='Size of region', type=arg_auto_int)
	parser_read_flash = subparsers.add_parser(
			'da',
			help='Dump Analog Registers')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('size', help='Size of region', type=arg_auto_int)
	parser_read_flash = subparsers.add_parser(
			'do',
			help='Dump TLSR8208 OTP registers')
	parser_read_flash.add_argument('address', help='Start address', type=arg_auto_int)
	parser_read_flash.add_argument('size', help='Size of region', type=arg_auto_int)
	parser_read_flash = subparsers.add_parser(
			'dc',
			help='Show uint32 register or SRAM address')
	parser_read_flash.add_argument('address', help='address (PC - 0x6bc)', type=arg_auto_int)
	parser_read_flash.add_argument('time', help='time (sec)', type=arg_auto_int)
	parser_read_flash = subparsers.add_parser(
			'sws',
			help='SWS Printf (PGM version >= 0.0.0.4 is used)')
	parser_read_flash.add_argument('address', help='SRAM address, (Ctrl-C - exit)', type=arg_auto_int)

	args = parser.parse_args()
	if args.pwr is None and args.operation is None:
		parser.print_help()
		sys.exit(0)

	print('=======================================================')
	print('%s version %s' % (__progname__, __version__))
	print('-------------------------------------------------------')
	pgm = connect_programmer(args.port)
	is_autonomous = bool(args.retry or args.operation == 'dump')
	post_runs = bool(args.run or args.go or args.mrst or args.osws != 0)
	power_off_exit = bool(is_autonomous and not args.keep_power and not post_runs)
	_cleanup_state['pgm'] = pgm
	_cleanup_state['power_off_on_exit'] = power_off_exit

	# Immediate power control (--pwr [on|off|toggle])
	if args.pwr is not None:
		old_pwr = 1 if pgm.pgm_pwr else 0
		if args.pwr == 'on':
			target_pwr = 1
		elif args.pwr == 'off':
			target_pwr = 0
		else:
			target_pwr = 0 if old_pwr else 1
		if not pgm.SetPinRST(target_pwr):
			pgm.close(power_off=False)
			sys.exit(1)
		state_str = lambda v: 'On (3.3V)' if v else 'Off (0V)'
		print('Target PWR (%s): %s -> %s' % (args.pwr, state_str(old_pwr), state_str(pgm.pgm_pwr)))
		pgm.close(power_off=False)
		sys.exit(0)

	swd = int(round(pgm.pgm_clk/4.8,0))
	if args.div != 0:
		swd = args.div
	if args.u2b:
		if pgm.pgm_swaddrlen != 2 or pgm.pgm_swdiv != swd or pgm.pgm_swbuf[4] != 0:
			if not pgm.SetPgmConfig(swdiv = swd, swaddrlen = 2, swbuf = b'\x5a\x00\x06\x02\x00\x05'):
				pgm.close(power_off=power_off_exit)
				sys.exit(1)
	else:
		if pgm.pgm_swaddrlen != 3 or pgm.pgm_swdiv != swd or pgm.pgm_swbuf[4] != 0:
			if not pgm.SetPgmConfig(swdiv = swd, swaddrlen = 3, swbuf = b'\x5a\x00\x06\x02\x00\x05'):
				pgm.close(power_off=power_off_exit)
				sys.exit(1)

	negotiate_uart_baud(pgm, args.baud, prefer_fast=is_autonomous)

	retry_cfg = None
	locked_info = None
	if is_autonomous:
		print('=== PreProcess (Autonomous Contact Lock) ==============')
		pc, cid, cver, jedec_id = pgm.WaitForTarget(
			act_ms = args.act_ms,
			pwr_off_ms = args.pwr_off_ms,
			stable_reads = args.stable_reads,
		)
		locked_info = (pc, cid, cver, jedec_id)
		retry_cfg = {
			'act_ms': args.act_ms,
			'pwr_off_ms': args.pwr_off_ms,
			'stable_reads': args.stable_reads,
			'expected_ids': (cid, jedec_id),
		}
	elif args.trst > 0 or args.act != 0 or args.stopcpu or args.cpustall or args.zw:
		print('=== PreProcess ========================================')
	if not is_autonomous:
		if args.zw: # Wait CPU run
			if not pgm.WaitCPU(args.zw, 0x6bc, args.stopcpu, args.cpustall):
				pgm.close()
				sys.exit(1)
		if args.trst > 0: # Hard reset (Pin RST set '0')?	
			if args.trst < 5: # min 5 ms
				args.trst = 5
			print('Hard reset Ext.MCU %d ms...' % (args.trst), end = ' ')
			if not pgm.SetPinRST(0): # Hard reset (Pin RST set '0')
				pgm.close()
				sys.exit(1)
			time.sleep(args.trst/1000) # Wait trst ms
			print('ok')
			if args.act > 0: # activate ?
				if not pgm.Activate(args.act):
					pgm.close()
					sys.exit(1)
			else: # no activate
				if not pgm.SetPinRST(1):
					pgm.close()
					sys.exit(1)
				time.sleep(0.07) # wait ext. MCU init
		else:
			if args.act > 0:
				print('Hard reset Ext.MCU 50 ms...', end = ' ')
				if not pgm.SetPinRST(0):
					pgm.close()
					sys.exit(1)
				time.sleep(0.05)
				print('ok')
				if not pgm.Activate(args.act):
					pgm.close()
					sys.exit(1)
		if args.act < 0: # No Hard reset (Pin RST set '0'), MCU Soft Reset + Activate 70 ms
			print('MCU Reboot...', end = ' ')
			if not pgm.WriteRegsData(0x6f, b'\x20'):
				pgm.close()
				sys.exit(1)
			print('ok')
			if not pgm.Activate(70): # Activate 70 ms
				pgm.close()
				sys.exit(1)
		if not args.zw:
			if args.stopcpu:	# CPU Stop ?
				print('CPU Stop...', end = ' ')
				if not pgm.WriteRegsData(0x602, b'\x05'):
					pgm.close()
					sys.exit(1)
				print('ok')
			if args.cpustall:	# CPU Stall ?
				print('CPU Stall...', end = ' ')
				if not pgm.WriteRegsData(0x602, b'\x06'):
					pgm.close()
					sys.exit(1)
				print('ok')

	# Command Read to File
	print('=== Process ===========================================')
	if args.operation == 'dump':
		pc, cid, cver, _jedec_id = locked_info
		specs = pgm.ProbeTargetSpecs(pc, cid, cver, args.size)
		print_specs_report(specs)
		beep(1)
		image = pgm.DumpFlashAutonomous(
			specs,
			use_crc = not args.no_crc,
			act_ms = args.act_ms,
			pwr_off_ms = args.pwr_off_ms,
			stable_reads = args.stable_reads,
		)
		out_path = args.out
		if not out_path:
			ts = datetime.now().strftime('%Y%m%d_%H%M%S')
			out_path = os.path.join(os.getcwd(), 'dump_%s_%dKB_%s.bin' % (specs['chip_short'], specs['flash_size'] // 1024, ts))
		tmp_path = out_path + '.part'
		with open(tmp_path, 'wb') as f:
			f.write(image)
		os.replace(tmp_path, out_path)
		sha256 = hashlib.sha256(image).hexdigest()
		mac_str, mac_src = find_mac_in_dump(image)
		is_blank = all(b == 0xFF for b in image) or all(b == 0x00 for b in image)
		beep(2)
		print('\n' + '=' * 68)
		print('  DUMP COMPLETE — SAFE TO RELEASE PINS!')
		print('=' * 68)
		print('  Saved File   : %s' % out_path)
		print('  File Size    : %d bytes (%d KB)' % (len(image), len(image) // 1024))
		print('  SHA-256      : %s' % sha256)
		print('  BLE MAC      : %s (from %s)' % (mac_str, mac_src))
		if is_blank:
			print('  [!] WARNING  : Flash contents are uniform (0xFF or 0x00)!')
		print('=' * 68)
	elif args.operation == 'rs' \
	or args.operation == 'rf' \
	or args.operation == 'ro' \
	or args.operation == 'ra':
		offset = args.address & 0x00ffffff
		size = args.size & 0x00ffffff
		if size == 0:
			print('\rError: Read size = %d!' % size, file=sys.stderr)
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('Outfile: %s' % args.filename)
		try:
			stream = open(args.filename, 'wb')
		except:
			print('Error: Not open Outfile file <%s>!' % args.filename, file=sys.stderr)
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		ret = False
		if args.operation == 'rs':
			print('Read SWire from 0x%06x to 0x%06x...' % (offset, offset + size))
			ret = pgm.ReadBlockRegs(stream, offset, size)
		elif args.operation == 'rf':
			print('Read Flash from 0x%06x to 0x%06x...' % (offset, offset + size))
			ret = pgm.ReadBlockFlash(stream, offset, size, retry_cfg=retry_cfg, use_crc=(is_autonomous and not args.no_crc))
		elif args.operation == 'ra':
			if size > 0x100 or offset + size > 0x100:
				print('Warning: Maximum number of analog registers 256!')
				if size > 0x100:
					size = 0x100
			offset &= 0x00ff
			print('Read Analog Registers from 0x%06x to 0x%06x...' % (offset, offset + size))
			ret = pgm.ReadBlockAnalogRegs(stream, offset, size)
		elif args.operation == 'ro':
			if not pgm.ReadChipID():
				stream.close()
				pgm.close(power_off=power_off_exit)
				sys.exit(1)
			if pgm.ext_chip != 'TLSR8208':
				print('\r\nRead OTP only for TLSR8208!', file=sys.stderr)
				stream.close()
				pgm.close(power_off=power_off_exit)
				sys.exit(1)
			offset &= 0xffff
			print('Read OTP from 0x%06x to 0x%06x...' % (offset, offset + size))
			ret = pgm.ReadBlockOTP(stream, offset, size)
		stream.close()
		if not ret:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	# Command Write from File
	elif args.operation == 'ws' \
	  or args.operation == 'wf' \
	  or args.operation == 'we' \
	  or args.operation == 'wa':
		offset = args.address & 0x00ffffff
		print('Inputfile: %s' % (args.filename))
		try:
			stream = open(args.filename, 'rb')
			size = os.path.getsize(args.filename)
		except:
			print('Error: Not open input file <%s>!' % args.filename, file=sys.stderr)
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		ret = False
		if size < 1:
			print('Error: File size = %d!'% size, file=sys.stderr)
		elif args.operation == 'ws':
			print('Write Swire register 0x%08x to 0x%08x...' % (offset, offset + size))
			ret = pgm.WriteBlockRegs(stream, offset, size)
		elif args.operation == 'wf' or args.operation == 'we':
			if pgm.FlashUnlock() == None:
				stream.close()
				pgm.close(power_off=power_off_exit)
				sys.exit(1)
			print('Write Flash data 0x%08x to 0x%08x...' % (offset, offset + size))
			ret = pgm.WriteBlockFlash(stream, offset, size, bool(args.operation == 'we'), retry_cfg=retry_cfg, use_crc=not args.no_crc)
		elif args.operation == 'wa':
			if size > 0x100 or offset + size > 0x100:
				print('Warning: Maximum number of analog registers 256!')
				if size > 0x100:
					size = 0x100
			offset &= 0x00ff
			print('Write Analog register 0x%08x to 0x%08x...' % (offset, offset + size))
			ret = pgm.WriteBlockAnalogRegs(stream, offset, size)
		stream.close()
		if not ret:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'es':
		if pgm.FlashUnlock() == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		count = int((args.size + FLASH_SECTOR_SIZE - 1) / FLASH_SECTOR_SIZE)
		size = (count * FLASH_SECTOR_SIZE)
		offset = args.address & (0xffffff^(FLASH_SECTOR_SIZE-1))
		print('Erase Flash %d sectors,\r\ndata from 0x%06x to 0x%06x ...' % (count, offset, offset + size))
		if not pgm.EraseSectorsFlash(offset, count, retry_cfg=retry_cfg):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'ea':
		if pgm.FlashUnlock() == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('Erase All Flash ...')
		if not pgm.EraseAllFlash():
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'fsr':
		print('Read Flash Status Register...')
		ret = pgm.ReadFlashStatus()
		if ret == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'fsw':
		print('Write 0x%02x to Flash Status Register...' % args.fsreg)
		ret = pgm.WriteFlashStatus(args.fsreg)
		if ret == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		ret = pgm.ReadFlashStatus()
		if ret == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'i':
		if not pgm.ReadChipID() \
		or not pgm.ReadPCcpu() \
		or not pgm.ReadFlashJEDECID() \
		or pgm.ReadFlashStatus() == None \
		or not pgm.DumpChipFlashUID() \
		or not pgm.DumpChipFlash() \
		or not pgm.DumpChipARegs() \
		or not pgm.DumpChipRegs():
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		if pgm.ext_chip == 'TLSR8208':
			if not pgm.DumpOTPRegs():
				pgm.close(power_off=power_off_exit)
				sys.exit(1)
	elif args.operation == 'ds':
		if not pgm.DumpChipRegs(args.address, args.size):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'df':
		if not pgm.DumpChipFlash(args.address, args.size):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'da':
		if not pgm.DumpChipARegs(args.address, args.size):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'dc':
		if not pgm.TestDebugPC(args.time, args.address):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'do':
		if not pgm.ReadChipID():
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		if pgm.ext_chip != 'TLSR8208':
			print('\r\nRead OTP only for TLSR8208!', file=sys.stderr)
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		if not pgm.DumpOTPRegs(args.address, args.size):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'sws':
		if not pgm.SwsPrintf(args.address):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'wsb':
		offset = args.address & 0x00ffffff
		b = args.value & 0xff
		print('Write byte 0x%02x to 0x%06x...' % (b, offset))
		ret = pgm.WriteRegsData(offset, struct.pack("<B", b))
		if ret == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'wsw':
		offset = args.address & 0x00ffffff
		sw = args.value & 0xffff
		print('Write 16 bits word 0x%04x to 0x%06x...' % (sw, offset))
		ret = pgm.WriteRegsData(offset, struct.pack("<H", sw))
		if ret == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'wsd':
		offset = args.address & 0x00ffffff
		dw = args.value & 0xffffffff
		print('Write 32 bits word 0x%08x to 0x%06x...' % (dw, offset))
		ret = pgm.WriteRegsData(offset, struct.pack("<I", dw))
		if ret == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'bkp':
		dw = args.address & 0x00ffffff
		print('Write break-point adress 0x%06x...' % dw)
		#pgm.setextadr(0x40)
		ret = pgm.WriteRegsData(0x610, struct.pack("<IIII", 0, dw  | 0x01000000, 0, 0))
		#pgm.setextadr(0x00)
		if ret == None:
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('CPU Go...', end = ' ')
		if not pgm.WriteRegsData(0x602, b'\x84'): # CPU Go
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('ok')
		if not pgm.WaitPC(3, dw):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		if not pgm.DumpCPURegs():
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	elif args.operation == 'stp':
		if args.count < 1:
			print('Error count:', args.count)
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('CPU Stall...', end = ' ')
		if not pgm.WriteRegsData(0x602, b'\x06'):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('ok')
		if not pgm.DumpCPURegs():
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		cnt = args.count
		print('-------------------------------------------------------')
		print('CPU %d Steps...' % cnt, end = '')
		for i in range(cnt):
			if not pgm.WriteRegsData(0x613, b'\x80'):
				pgm.close(power_off=power_off_exit)
				sys.exit(1)
		print('ok')
		if not pgm.DumpCPURegs():
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	else:
		print('No action assigned.')
	if post_runs:
		print('=== Post-Process ======================================')
	else:
		print('Done')
	# Commands / flags post main processing
	if args.run:
		print('CPU Run...', end = ' ')
		if not pgm.WriteRegsData(0x602, b'\x88'): # CPU ReBoot
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('ok')
	if args.go:
		print('CPU Go...', end = ' ')
		if not pgm.WriteRegsData(0x602, b'\x08'): # CPU Go
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('ok')
	if args.mrst:
		print('MCU Reboot...', end = ' ')
		if not pgm.WriteRegsData(0x6f, b'\x20'):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
		print('ok')
	if args.wrktime:
		# Second time slice
		t2 = time.time()
		print(" Worked Time: %.3f sec" % (t2-t1))
	if args.osws != 0:
		if not pgm.SwsPrintf(args.osws):
			pgm.close(power_off=power_off_exit)
			sys.exit(1)
	pgm.close(power_off=power_off_exit)
	sys.exit(0)

if __name__ == '__main__':
	main()
