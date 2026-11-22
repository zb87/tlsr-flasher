#!/usr/bin/env python3
"""Autonomous, hands-free hardware spec reader and firmware dumper for TLSR_SWire_Flasher (TLSRPGM).

Workflow optimized for hand-held probe pins (PWR/VCC, GND, SWS):
1. Connects to the TLSR_SWire_Flasher programmer (auto-detects USB serial port if -p is omitted)
   and upgrades UART speed (default target: 1,500,000 bps with automatic fallback).
2. Autonomously polls by cycling PWR + SWire Activate until the user makes contact.
3. Confirms solid contact with 3 consecutive Chip ID + Flash JEDEC ID reads (debounce).
4. Prints full hardware specs (Chip ID/Rev, PC, Flash JEDEC/Capacity/Status/UID) and rings bell.
5. Dumps the entire auto-detected SPI flash with per-block hardware CRC16 verification
   (CMD_FLASH_RDCRC) and automatic re-lock/resume if a probe slips mid-dump.
6. Turns PWR off, restores programmer UART baud to 230400, saves the .bin to the current
   directory, and rings bell so you can safely release the pins.
"""

import argparse
import hashlib
import os
import signal
import struct
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional, Tuple

try:
    import serial
    import serial.tools.list_ports
except ImportError:
    print("Error: 'pyserial' is required. Install with: pip3 install pyserial", file=sys.stderr)
    sys.exit(1)

__progname__ = "TLSR_SWire_Flasher Autonomous Dumper"
__version__ = "1.0.0"

DEFAULT_UART_BAUD = 230400
AUTO_BAUD_CANDIDATES = [1500000, 921600, 230400]
MAX_BUF_READ_SIZE = 1024
MAX_RESPONSE_SIZE = 1026
MIN_RESPONSE_SIZE = 6

# Modbus-style CRC-16 lookup table (poly 0xA001, init 0xFFFF) matching TlsrPgm.py
CRC16_TABLE = (
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
    0x8201, 0x42C0, 0x4380, 0x8341, 0x4100, 0x81C1, 0x8081, 0x4040,
)

PGM_CHIP_CLK = {
    0x5562: ("TLSR825x", 24),
    0x5325: ("TLSR8266", 32),
    0x5326: ("TLSR8267", 32),
    0x5327: ("TLSR8269", 32),
    0x5591: ("TLSR8208", 32),
}

TARGET_CHIP_MAP = {
    0x5562: {"name": "TLSR8258 / TLSR8253 (825x)", "short": "TLSR825x", "sram": "64 KB", "ble": "BLE 5.0 / Mesh / Zigbee"},
    0x5324: {"name": "TLSR8253", "short": "TLSR8253", "sram": "48 KB", "ble": "BLE 5.0"},
    0x5325: {"name": "TLSR8251 / TLSR8266", "short": "TLSR8266", "sram": "32 KB", "ble": "BLE 4.2 / 5.0"},
    0x5326: {"name": "TLSR8267", "short": "TLSR8267", "sram": "32 KB", "ble": "BLE 4.2"},
    0x5327: {"name": "TLSR8269", "short": "TLSR8269", "sram": "32 KB", "ble": "BLE 4.2 / Zigbee"},
    0x5328: {"name": "TLSR8258 (A0) / TLSR8359", "short": "TLSR8258_A0", "sram": "64 KB", "ble": "BLE 5.0 / 2.4G RF"},
    0x5591: {"name": "TLSR8208", "short": "TLSR8208", "sram": "16 KB", "ble": "BLE 5.0"},
    0x5316: {"name": "TLSR8261", "short": "TLSR8261", "sram": "16 KB", "ble": "BLE 4.0"},
    0x5317: {"name": "TLSR8263", "short": "TLSR8263", "sram": "16 KB", "ble": "BLE 4.0"},
}

FLASH_MFG_MAP = {
    0x85: "Puya Semiconductor (PUYA)",
    0xE8: "Puya Semiconductor (P25Q)",
    0xEF: "Winbond",
    0xC8: "GigaDevice (GD)",
    0xC2: "Macronix (MXIC)",
    0x1C: "EON / ESMT",
    0x51: "GigaDevice / MD",
    0x68: "Boya / BoyaMicro",
    0x0B: "XTX (XT25F)",
    0x25: "Microchip / SST",
    0x9D: "ISSI",
    0x1F: "Adesto / Atmel",
    0xA1: "Fudan Micro (FM)",
    0xE0: "Berg Micro (BG)",
    0x5E: "ZBIT (ZB25VQ)",
}

MAC_CANDIDATE_ADDRS = [
    (0x76000, "Custom FW / ATC / BTHome (0x76000)"),
    (0x7F000, "Telink Stock / 512KB Config (0x7F000)"),
    (0xFF000, "Telink Stock / 1MB Config (0xFF000)"),
    (0x3F000, "Telink Stock / 256KB Config (0x3F000)"),
    (0x1F000, "Telink Stock / 128KB Config (0x1F000)"),
]

KNOWN_TELINK_OUIS = {
    (0xA4, 0xC1, 0x38),
    (0x48, 0xA0, 0x6D),
    (0x60, 0x57, 0xC6),
    (0xB8, 0xD8, 0x12),
    (0xC4, 0x4F, 0x33),
}


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc = (crc >> 8) ^ CRC16_TABLE[(crc ^ b) & 0xFF]
    return bytes((crc & 0xFF, (crc >> 8) & 0xFF))


def crc_blk(data: bytes) -> bytes:
    return data + crc16(data)


def crc_chk(data: bytes) -> bool:
    if len(data) < 2:
        return False
    return data[-2:] == crc16(data[:-2])


def arg_auto_int(value: str) -> int:
    return int(value, 0)


def bcd_ver_str(ver_bytes: List[int]) -> str:
    return ".".join(f"{(b >> 8) & 0x0F}.{b & 0x0F}" for b in ver_bytes)


def beep(times: int = 1) -> None:
    """Emit terminal bell(s) for hands-free audio notification."""
    sys.stdout.write("\a" * times)
    sys.stdout.flush()


def is_valid_ieee_mac(mac_bytes: bytes) -> bool:
    if len(mac_bytes) != 6:
        return False
    if mac_bytes.count(0xFF) >= 4 or mac_bytes.count(0x00) >= 4:
        return False
    # Unicast check on MSB (stored little-endian, so byte 5 is MSB)
    if (mac_bytes[5] & 0x01) != 0:
        return False
    return True


def find_mac_in_dump(image: bytes) -> Tuple[str, str]:
    fallback: Optional[Tuple[str, str]] = None
    for addr, desc in MAC_CANDIDATE_ADDRS:
        if addr + 6 > len(image):
            continue
        candidate = image[addr : addr + 6]
        if is_valid_ieee_mac(candidate):
            mac_str = ":".join(f"{b:02X}" for b in reversed(candidate))
            oui = (candidate[5], candidate[4], candidate[3])
            if oui in KNOWN_TELINK_OUIS:
                return mac_str, f"0x{addr:06X} ({desc})"
            if fallback is None:
                fallback = (mac_str, f"0x{addr:06X} ({desc})")
    return fallback if fallback else ("Not detected", "None")


@dataclass
class TargetSpecs:
    chip_id: int
    chip_rev: int
    chip_name: str
    chip_short: str
    sram_size: str
    ble_info: str
    pc: int
    cpu_state: int
    jedec_id: int
    flash_mfg: str
    flash_size: int
    flash_size_str: str
    flash_status: int
    flash_uid: Optional[bytes]


class TlsrPgmClient:
    """Clean, resilient driver for the TLSR_SWire_Flasher (TLSRPGM) board."""

    CMD_FUNCS = 0
    CMD_FLASH_READ = 1
    CMD_FLASH_GET_JEDEC_ID = 5
    CMD_FLASH_GET_STATUS = 6
    CMD_SWIRE_READ = 7
    CMD_SWIRE_WRITE = 8
    CMD_FLASH_WRRD = 13
    CMD_FLASH_RDCRC = 14

    CMDF_GET_VERSION = 0
    CMDF_SWIRE_CFG = 2
    CMDF_EXT_POWER = 3
    CMDF_SWIRE_ACTIVATE = 4
    CMDF_UART_BAUD = 5

    ERR_NONE = 0
    ERR_FUNC = 1
    ERR_LEN = 2
    ERR_READ = 3
    ERR_BUSY = 4
    ERR_CRC = 5
    ERR_BAUD = 6

    TAB_ERR = {
        ERR_NONE: "No error",
        ERR_FUNC: "Function number error",
        ERR_LEN: "Data length error",
        ERR_READ: "SWire read timeout",
        ERR_BUSY: "Analog register read timeout",
        ERR_CRC: "CRC mismatch",
        ERR_BAUD: "Invalid baud rate",
    }

    TAB_UART_BAUD = [
        115200,
        230400,
        460800,
        500000,
        921600,
        1000000,
        1500000,
        2000000,
        3000000,
    ]

    def __init__(self, port_name: str, baud: int = DEFAULT_UART_BAUD) -> None:
        self.port_name = port_name
        self._port: Optional[serial.Serial] = None
        self.err: int = 0
        self.wcnt: int = 0
        self.pgm_version: List[int] = [0, 0]
        self.pgm_ver_int: int = 0
        self.pgm_cid: int = 0
        self.pgm_pwr: int = 1
        self.pgm_swdiv: int = 5
        self.pgm_swaddrlen: int = 3
        self.pgm_swbuf: bytes = b"\x5a\x00\x06\x02\x00\x05"
        self.pgm_clk: int = 24
        self.pgm_chip: str = "?"
        self.pgm_swsps: float = 0.96
        self.reopen(baud, port_name)

    @property
    def is_open(self) -> bool:
        return self._port is not None and self._port.is_open

    def reopen(self, baud: int, port_name: Optional[str] = None) -> bool:
        target = port_name or self.port_name
        if self._port is not None:
            try:
                self._port.close()
            except OSError:
                pass
            self._port = None
        try:
            ser = serial.Serial(
                target,
                baud,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                timeout=0.15,
            )
            ser.setRTS(False)
            ser.setDTR(False)
            time.sleep(0.05)
            ser.reset_output_buffer()
            ser.reset_input_buffer()
            self._port = ser
            self.port_name = target
            return True
        except (serial.SerialException, OSError):
            self._port = None
            return False

    def _read_exact(self, length: int) -> Optional[bytes]:
        if not self._port:
            return None
        try:
            data = self._port.read(length)
            return data
        except (serial.SerialException, OSError):
            return None

    def command(self, wblk: bytes, rdlen: Optional[int] = None) -> Optional[bytes]:
        if not self._port:
            self.err = 100
            return None
        pkt = crc_blk(wblk)
        try:
            self._port.reset_input_buffer()
            written = self._port.write(pkt)
        except (serial.SerialException, OSError):
            self.err = 100
            return None
        if written != len(pkt):
            self.err = 100
            return None

        if rdlen is None:
            rdlen = MAX_RESPONSE_SIZE
            chklen = MIN_RESPONSE_SIZE
        else:
            chklen = rdlen

        self.wcnt = 0
        rblk = self._read_exact(rdlen)
        if rblk is None or len(rblk) < chklen:
            self.err = self.ERR_LEN + 100
            return None
        if not crc_chk(rblk):
            self.err = self.ERR_CRC + 100
            return None
        if rblk[0] != wblk[0]:
            self.err = self.ERR_FUNC + 100
            return None
        self.err = rblk[1]
        self.wcnt = rblk[2] | (rblk[3] << 8)
        if self.err != self.ERR_NONE:
            return None
        return rblk

    def get_version(self) -> bool:
        data = self.command(struct.pack("<BBH", self.CMD_FUNCS, self.CMDF_GET_VERSION, 0), 19)
        if data is None:
            return False
        self.pgm_version = [data[5], data[4]]
        self.pgm_ver_int = (data[5] << 8) | data[4]
        self.pgm_cid, self.pgm_pwr, self.pgm_swdiv, self.pgm_swaddrlen = struct.unpack("<HBBB", data[6:11])
        self.pgm_swbuf = data[11:17]
        if self.pgm_cid == 0 and self.pgm_ver_int == 0:
            return False
        self.pgm_chip, self.pgm_clk = PGM_CHIP_CLK.get(self.pgm_cid, ("?", 32))
        if self.pgm_swdiv > 0:
            self.pgm_swsps = self.pgm_clk / 5.0 / self.pgm_swdiv
        return True

    def set_pgm_config(self, swdiv: Optional[int] = None, swaddrlen: Optional[int] = None, swbuf: Optional[bytes] = None) -> bool:
        if swdiv is None:
            swdiv = self.pgm_swdiv
        if swaddrlen is None:
            swaddrlen = self.pgm_swaddrlen
        if swbuf is None:
            swbuf = self.pgm_swbuf
        data = self.command(
            struct.pack("<BBHBB", self.CMD_FUNCS, self.CMDF_SWIRE_CFG, 0, swdiv, swaddrlen) + swbuf,
            14,
        )
        if data is None:
            return False
        self.pgm_swdiv, self.pgm_swaddrlen = struct.unpack("<BB", data[4:6])
        self.pgm_swbuf = data[6:12]
        if self.pgm_swdiv > 0:
            self.pgm_swsps = self.pgm_clk / 5.0 / self.pgm_swdiv
        return True

    def set_uart_baud(self, baud: int) -> bool:
        if baud not in self.TAB_UART_BAUD:
            return False
        idx = self.TAB_UART_BAUD.index(baud)
        if self._port and self._port.baudrate == baud:
            return True
        prev_baud = int(self._port.baudrate) if self._port else DEFAULT_UART_BAUD
        data = self.command(struct.pack("<BBH", self.CMD_FUNCS, self.CMDF_UART_BAUD, idx), 6)
        if data is None:
            return False
        if not self.reopen(baud):
            self.reopen(prev_baud)
            return False
        if not self.get_version():
            # Try restoring PGM back to 230400 from the attempted baud before giving up
            self.command(struct.pack("<BBH", self.CMD_FUNCS, self.CMDF_UART_BAUD, 1), 6)
            self.reopen(DEFAULT_UART_BAUD)
            return False
        return True

    def set_pin_pwr(self, on: int) -> bool:
        data = self.command(struct.pack("<BBH", self.CMD_FUNCS, self.CMDF_EXT_POWER, 1 if on else 0), 7)
        return data is not None

    def activate(self, tms: int) -> Optional[int]:
        """Turn PWR on and pulse SWire Activate for tms ms. Returns CPU PC on success, else None."""
        if not self._port:
            return None
        count = 0
        if tms > 0:
            count = int(tms / ((self.pgm_swaddrlen + 5.7) * 5 * self.pgm_swdiv / 2400.0))
            if count > 0xFFFF:
                count = 0xFFFF

        old_timeout = self._port.timeout
        self._port.timeout = tms / 1000.0 + 0.4
        try:
            wblk = struct.pack("<BBH", self.CMD_FUNCS, self.CMDF_SWIRE_ACTIVATE, count)
            self._port.reset_input_buffer()
            if self._port.write(crc_blk(wblk)) != len(wblk) + 2:
                self.err = 100
                return None
            rblk = self._read_exact(6)
            if rblk is None or len(rblk) < 6 or rblk[0] != wblk[0]:
                self.err = self.ERR_LEN + 100
                return None
            self.err = rblk[1]
            self.wcnt = rblk[2] | (rblk[3] << 8)
            if 0 < self.wcnt <= 4:
                extra = self._read_exact(self.wcnt)
                if extra is None:
                    self.err = self.ERR_LEN + 100
                    return None
                rblk += extra
            if not crc_chk(rblk):
                self.err = self.ERR_CRC + 100
                return None
            if self.err != self.ERR_NONE or len(rblk) < 10:
                return None
            return struct.unpack("<I", rblk[4:8])[0]
        except (serial.SerialException, OSError):
            self.err = 100
            return None
        finally:
            if self._port:
                self._port.timeout = old_timeout

    def swire_read(self, offset: int, size: int) -> Optional[bytes]:
        offset &= 0xFFFFFF
        data = self.command(
            struct.pack("<BBHH", self.CMD_SWIRE_READ, offset & 0xFF, (offset >> 8) & 0xFFFF, size),
            size + 6,
        )
        if data is None or self.wcnt != size:
            return None
        return data[4 : 4 + size]

    def swire_write(self, offset: int, wdata: bytes) -> bool:
        offset &= 0xFFFFFF
        data = self.command(
            struct.pack("<BBH", self.CMD_SWIRE_WRITE, offset & 0xFF, (offset >> 8) & 0xFFFF) + wdata,
            6,
        )
        return data is not None and self.wcnt == len(wdata)

    def read_chip_id(self) -> Optional[Tuple[int, int]]:
        raw = self.swire_read(0x7D, 3)
        if raw is None or len(raw) != 3:
            return None
        cver = raw[0]
        cid = raw[1] | (raw[2] << 8)
        return cid, cver

    def read_flash_jedec_id(self) -> Optional[Tuple[int, int, int, int]]:
        data = self.command(struct.pack("<BBH", self.CMD_FLASH_GET_JEDEC_ID, 0, 0), 9)
        if data is None or self.wcnt != 3:
            return None
        mfg, mem_type, cap = data[4], data[5], data[6]
        jedec_id = (mfg << 16) | (mem_type << 8) | cap
        return jedec_id, mfg, mem_type, cap

    def read_flash_status(self) -> Optional[int]:
        data = self.command(struct.pack("<BBH", self.CMD_FLASH_GET_STATUS, 0, 0), 7)
        if data is None or self.wcnt != 1:
            return None
        return data[4]

    def read_flash_uid(self, uid_len: int = 16) -> Optional[bytes]:
        rdsize = uid_len + 4  # 4 dummy bytes for SPI 0x4B
        data = self.command(struct.pack("<BBHHB", self.CMD_FLASH_WRRD, 0, 0, rdsize, 0x4B), rdsize + 6)
        if data is None or self.wcnt != rdsize + 1:
            return None
        return data[8 : 8 + uid_len]

    def read_flash_chunk(self, offset: int, size: int) -> Optional[bytes]:
        offset &= 0xFFFFFF
        data = self.command(
            struct.pack("<BBHH", self.CMD_FLASH_READ, offset & 0xFF, (offset >> 8) & 0xFFFF, size),
            size + 6,
        )
        if data is None or self.wcnt != size:
            return None
        return data[4 : 4 + size]

    def read_flash_crc16(self, offset: int, size: int) -> Optional[bytes]:
        offset &= 0xFFFFFF
        data = self.command(
            struct.pack("<BBHH", self.CMD_FLASH_RDCRC, offset & 0xFF, (offset >> 8) & 0xFFFF, size),
            6,
        )
        if data is None:
            return None
        return data[2:4]

    def close(self, power_off: bool = True) -> None:
        if not self._port or not self._port.is_open:
            return
        try:
            if power_off:
                self.set_pin_pwr(0)
            if self._port.baudrate != DEFAULT_UART_BAUD:
                self.command(struct.pack("<BBH", self.CMD_FUNCS, self.CMDF_UART_BAUD, 1), 6)
        except Exception:
            pass
        finally:
            try:
                self._port.close()
            except OSError:
                pass
            self._port = None


def list_candidate_ports() -> List[str]:
    ports = list(serial.tools.list_ports.comports())
    usb_ports = []
    other_ports = []
    for p in ports:
        dev = p.device
        desc = (p.description or "") + " " + (p.hwid or "")
        is_usb = (
            p.vid is not None
            or "USB" in desc.upper()
            or "ttyUSB" in dev
            or "ttyACM" in dev
            or "cu.usb" in dev
        )
        if is_usb:
            usb_ports.append(dev)
        elif not dev.startswith("/dev/ttyS"):
            other_ports.append(dev)
    return sorted(usb_ports) + sorted(other_ports)


def connect_programmer(port_arg: Optional[str], baud_arg: Optional[int], u2b: bool, swdiv_arg: int) -> TlsrPgmClient:
    candidates = [port_arg] if port_arg else list_candidate_ports()
    if not candidates:
        print("Error: No USB serial ports found. Plug in TLSR_SWire_Flasher or pass -p <port>.", file=sys.stderr)
        sys.exit(1)

    pgm: Optional[TlsrPgmClient] = None
    for cand in candidates:
        print(f"Probing programmer on {cand} @ {DEFAULT_UART_BAUD} bps... ", end="", flush=True)
        client = TlsrPgmClient(cand, DEFAULT_UART_BAUD)
        if not client.is_open:
            print("open failed")
            continue
        if client.get_version():
            print(f"ok ({client.pgm_chip} PGM v{bcd_ver_str(client.pgm_version)})")
            pgm = client
            break
        print("no response")
        client.close(power_off=False)

    if pgm is None:
        print("Error: Could not communicate with TLSR_SWire_Flasher board.", file=sys.stderr)
        sys.exit(1)

    if pgm.pgm_ver_int < 4:
        print("Warning: Programmer firmware < 0.0.0.4; some features may be limited.")

    swaddrlen = 2 if u2b else 3
    swd = swdiv_arg if swdiv_arg > 0 else int(round(pgm.pgm_clk / 4.8))
    if pgm.pgm_swaddrlen != swaddrlen or pgm.pgm_swdiv != swd or pgm.pgm_swbuf[4] != 0:
        if not pgm.set_pgm_config(swdiv=swd, swaddrlen=swaddrlen, swbuf=b"\x5a\x00\x06\x02\x00\x05"):
            print("Error: Failed to configure SWire settings on programmer.", file=sys.stderr)
            pgm.close(power_off=False)
            sys.exit(1)

    baud_targets = [baud_arg] if baud_arg else AUTO_BAUD_CANDIDATES
    active_baud = DEFAULT_UART_BAUD
    for target_baud in baud_targets:
        if target_baud == DEFAULT_UART_BAUD:
            active_baud = DEFAULT_UART_BAUD
            break
        print(f"Switching UART speed to {target_baud} bps... ", end="", flush=True)
        if pgm.set_uart_baud(target_baud):
            print("ok")
            active_baud = target_baud
            break
        print("fallback")

    print(
        f"Programmer ready: {pgm.port_name} @ {active_baud} bps | "
        f"SWire {pgm.pgm_swsps:.2f} Mbit/s (div={pgm.pgm_swdiv}, addrlen={pgm.pgm_swaddrlen})"
    )
    return pgm


def wait_for_target(
    pgm: TlsrPgmClient,
    act_ms: int,
    pwr_off_ms: int,
    stable_reads: int,
    expected_ids: Optional[Tuple[int, int]] = None,
    banner_msg: str = "Waiting for target pins (PWR->VCC, GND, SWS)... touch & hold steady",
) -> Tuple[int, int, int, int]:
    """Poll by power-cycling PWR + SWire Activate until stable Chip ID + JEDEC ID are confirmed."""
    attempt = 0
    t_start = time.monotonic()
    print(f"\n[~] {banner_msg}")
    while True:
        attempt += 1
        # Every 10th cycle use a slightly longer PWR-off to drain larger target bulk capacitors
        off_sec = (max(pwr_off_ms, 150) if attempt % 10 == 0 else pwr_off_ms) / 1000.0
        pgm.set_pin_pwr(0)
        time.sleep(off_sec)

        pc = pgm.activate(act_ms)
        if pc is None:
            elapsed = time.monotonic() - t_start
            print(f"\r[~] Waiting for contact... {elapsed:5.1f}s (attempts: {attempt})   ", end="", flush=True)
            continue

        # Halt CPU immediately before checking contact stability
        if not pgm.swire_write(0x602, b"\x05"):
            continue

        readings: List[Tuple[int, int, int]] = []
        stable = True
        for i in range(stable_reads):
            if i > 0:
                time.sleep(0.025)
            id_pair = pgm.read_chip_id()
            jedec = pgm.read_flash_jedec_id()
            if id_pair is None or jedec is None:
                stable = False
                break
            cid, cver = id_pair
            jedec_id = jedec[0]
            if cid in (0x0000, 0xFFFF) or jedec_id in (0x000000, 0xFFFFFF):
                stable = False
                break
            readings.append((cid, cver, jedec_id))

        if not stable or len(set(readings)) != 1:
            print(f"\r[!] Contact bounced at {time.monotonic() - t_start:4.1f}s, stabilizing...        ", end="", flush=True)
            continue

        cid, cver, jedec_id = readings[0]
        if expected_ids is not None and (cid, jedec_id) != expected_ids:
            print(
                f"\r[!] Target mismatch (got Chip=0x{cid:04X} JEDEC=0x{jedec_id:06X}), retrying...   ",
                end="",
                flush=True,
            )
            continue

        print(f"\r[+] Target locked in {time.monotonic() - t_start:.1f}s (attempt #{attempt})!                ")
        return pc, cid, cver, jedec_id


def probe_target_specs(pgm: TlsrPgmClient, pc: int, cid: int, cver: int, size_override: Optional[int]) -> TargetSpecs:
    chip_meta = TARGET_CHIP_MAP.get(cid)
    if chip_meta:
        chip_name = chip_meta["name"]
        chip_short = chip_meta["short"]
        sram_size = chip_meta["sram"]
        ble_info = chip_meta["ble"]
    else:
        chip_name = f"Unknown TLSR (0x{cid:04X})"
        chip_short = f"TLSR_{cid:04X}"
        sram_size = "Unknown"
        ble_info = "Unknown"

    pc_raw = pgm.swire_read(0x6BC, 4)
    if pc_raw and len(pc_raw) == 4:
        pc = struct.unpack("<I", pc_raw)[0]
    cpu_state_raw = pgm.swire_read(0x602, 1)
    cpu_state = cpu_state_raw[0] if cpu_state_raw else 0

    jedec = pgm.read_flash_jedec_id()
    if jedec:
        jedec_id, mfg, _mem_type, cap = jedec
        flash_mfg = FLASH_MFG_MAP.get(mfg, f"Unknown Vendor (0x{mfg:02X})")
        if size_override is not None:
            flash_size = size_override
            flash_size_str = f"{flash_size // 1024} KB (override)"
        elif 0x10 <= cap <= 0x1A:
            flash_size = 1 << cap
            if flash_size >= 1024 * 1024:
                flash_size_str = f"{flash_size // (1024 * 1024)} MB ({flash_size // 1024} KB)"
            else:
                flash_size_str = f"{flash_size // 1024} KB"
        else:
            flash_size = 512 * 1024
            flash_size_str = f"512 KB (assumed, raw cap 0x{cap:02X})"
    else:
        jedec_id = 0
        flash_mfg = "Unknown"
        flash_size = size_override if size_override is not None else 512 * 1024
        flash_size_str = f"{flash_size // 1024} KB (fallback)"

    flash_status = pgm.read_flash_status()
    if flash_status is None:
        flash_status = 0

    flash_uid = pgm.read_flash_uid(uid_len=16)

    return TargetSpecs(
        chip_id=cid,
        chip_rev=cver,
        chip_name=chip_name,
        chip_short=chip_short,
        sram_size=sram_size,
        ble_info=ble_info,
        pc=pc,
        cpu_state=cpu_state,
        jedec_id=jedec_id,
        flash_mfg=flash_mfg,
        flash_size=flash_size,
        flash_size_str=flash_size_str,
        flash_status=flash_status,
        flash_uid=flash_uid,
    )


def print_specs_report(specs: TargetSpecs) -> None:
    wip = "BUSY" if (specs.flash_status & 0x01) else "READY"
    bp = (specs.flash_status >> 2) & 0x07
    uid_hex = specs.flash_uid.hex(" ").upper() if specs.flash_uid else "Unavailable"
    print("=" * 68)
    print("                  TARGET HARDWARE SPECIFICATIONS")
    print("=" * 68)
    print(f"  Chip Name       : {specs.chip_name}")
    print(f"  Chip ID / Rev   : 0x{specs.chip_id:04X} / Rev 0x{specs.chip_rev:02X}")
    print(f"  Internal SRAM   : {specs.sram_size} ({specs.ble_info})")
    print(f"  CPU PC / [0602] : 0x{specs.pc:08X} / 0x{specs.cpu_state:02X}")
    print("-" * 68)
    print(f"  Flash Vendor    : {specs.flash_mfg}")
    print(f"  Flash JEDEC ID  : 0x{specs.jedec_id:06X}")
    print(f"  Flash Capacity  : {specs.flash_size_str} (0x{specs.flash_size:06X} bytes)")
    print(f"  Flash Status    : 0x{specs.flash_status:02X} ({wip}, BP={bp})")
    print(f"  Flash Unique ID : {uid_hex}")
    print("=" * 68)


def verify_block_crc(pgm: TlsrPgmClient, offset: int, blk: bytes, rdcrc_chunk_limit: int) -> Tuple[bool, int]:
    """Verify flash block using programmer hardware CRC16. Returns (ok, updated_limit)."""
    size = len(blk)
    if size <= rdcrc_chunk_limit:
        hw_crc = pgm.read_flash_crc16(offset, size)
        if hw_crc is not None:
            return hw_crc == crc16(blk), rdcrc_chunk_limit
        if pgm.err == pgm.ERR_LEN and rdcrc_chunk_limit > 256:
            rdcrc_chunk_limit = 256
        else:
            return False, rdcrc_chunk_limit

    # Fallback: verify in 256-byte sub-chunks
    sub = 0
    while sub < size:
        part = blk[sub : sub + rdcrc_chunk_limit]
        hw_crc = pgm.read_flash_crc16(offset + sub, len(part))
        if hw_crc is None or hw_crc != crc16(part):
            return False, rdcrc_chunk_limit
        sub += len(part)
    return True, rdcrc_chunk_limit


def dump_flash_autonomous(
    pgm: TlsrPgmClient,
    specs: TargetSpecs,
    use_crc: bool,
    act_ms: int,
    pwr_off_ms: int,
    stable_reads: int,
) -> bytes:
    total = specs.flash_size
    buf = bytearray(total)
    offset = 0
    t_dump_start = time.monotonic()
    rdcrc_limit = MAX_BUF_READ_SIZE
    crc_enabled = use_crc and pgm.pgm_ver_int >= 3
    retries_used = 0
    slip_recoveries = 0

    mode_str = "Hardware CRC16 verified" if crc_enabled else "CRC16 disabled"
    print(f"\n[*] Dumping {total // 1024} KB flash ({mode_str}) — keep pins steady...")

    while offset < total:
        chunk_size = min(MAX_BUF_READ_SIZE, total - offset)
        block_ok = False

        for _ in range(3):
            blk = pgm.read_flash_chunk(offset, chunk_size)
            if blk is None or len(blk) != chunk_size:
                retries_used += 1
                continue
            if crc_enabled:
                ok, rdcrc_limit = verify_block_crc(pgm, offset, blk, rdcrc_limit)
                if not ok:
                    retries_used += 1
                    continue
            buf[offset : offset + chunk_size] = blk
            block_ok = True
            break

        if not block_ok:
            slip_recoveries += 1
            beep(1)
            print(
                f"\n[!] Link lost at 0x{offset:06X} ({offset * 100.0 / total:.1f}%) — "
                "re-hold probes to resume automatically..."
            )
            wait_for_target(
                pgm,
                act_ms=act_ms,
                pwr_off_ms=pwr_off_ms,
                stable_reads=stable_reads,
                expected_ids=(specs.chip_id, specs.jedec_id),
                banner_msg=f"Re-acquiring target to resume from 0x{offset:06X}...",
            )
            print("[*] Resuming dump...")
            continue

        offset += chunk_size
        elapsed = max(time.monotonic() - t_dump_start, 0.001)
        speed_kbs = (offset / 1024.0) / elapsed
        pct = offset * 100.0 / total
        eta = (total - offset) / 1024.0 / speed_kbs if speed_kbs > 0 else 0.0
        bar_len = 28
        filled = int(bar_len * offset / total)
        bar = "#" * filled + "-" * (bar_len - filled)
        print(
            f"\r  [{bar}] {pct:5.1f}%  {offset // 1024:4d}/{total // 1024} KB  "
            f"{speed_kbs:5.1f} KB/s  ETA {eta:4.1f}s ",
            end="",
            flush=True,
        )

    elapsed_total = time.monotonic() - t_dump_start
    print(f"\n[+] Read complete in {elapsed_total:.2f}s (retries={retries_used}, slip_recoveries={slip_recoveries})")
    return bytes(buf)


def build_output_path(specs: TargetSpecs, out_arg: Optional[str]) -> str:
    if out_arg:
        return out_arg
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    size_kb = specs.flash_size // 1024
    filename = f"dump_{specs.chip_short}_{size_kb}KB_{ts}.bin"
    return os.path.join(os.getcwd(), filename)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"{__progname__} v{__version__}",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("-p", "--port", help="Programmer serial port (auto-detected if omitted)")
    parser.add_argument(
        "-b",
        "--baud",
        type=arg_auto_int,
        default=None,
        help="Target UART baud rate (default: auto 1500000 -> 921600 -> 230400)",
    )
    parser.add_argument("-o", "--out", help="Output .bin filename (default: auto-named in current dir)")
    parser.add_argument("-s", "--size", type=arg_auto_int, default=None, help="Override flash dump size in bytes")
    parser.add_argument("-u", "--u2b", action="store_true", help="Use 2-byte SWire addressing (TLSR826x)")
    parser.add_argument("-d", "--div", type=arg_auto_int, default=0, help="Override SWire clock divisor (0=auto)")
    parser.add_argument("--act-ms", type=int, default=150, help="SWire activation pulse duration in ms per poll cycle")
    parser.add_argument("--pwr-off-ms", type=int, default=60, help="PWR-off reset duration in ms per poll cycle")
    parser.add_argument("--stable-reads", type=int, default=3, help="Consecutive matching ID reads before locking")
    parser.add_argument("--no-crc", action="store_true", help="Skip per-block hardware CRC16 verification")
    parser.add_argument("--keep-power", action="store_true", help="Keep PWR enabled after dump completes")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    pgm: Optional[TlsrPgmClient] = None

    def handle_sigint(_sig, _frame):
        print("\n\n[!] Interrupted by user — cleaning up programmer state...")
        if pgm is not None:
            pgm.close(power_off=not args.keep_power)
        sys.exit(130)

    signal.signal(signal.SIGINT, handle_sigint)

    print("=" * 68)
    print(f"  {__progname__} v{__version__}")
    print("  Wiring: Programmer PWR->VCC, GND->GND, SWM->SWS (no RST needed)")
    print("=" * 68)

    pgm = connect_programmer(args.port, args.baud, args.u2b, args.div)

    try:
        pc, cid, cver, _jedec_id = wait_for_target(
            pgm,
            act_ms=args.act_ms,
            pwr_off_ms=args.pwr_off_ms,
            stable_reads=args.stable_reads,
        )
        specs = probe_target_specs(pgm, pc, cid, cver, args.size)
        print_specs_report(specs)
        beep(1)

        image = dump_flash_autonomous(
            pgm,
            specs,
            use_crc=not args.no_crc,
            act_ms=args.act_ms,
            pwr_off_ms=args.pwr_off_ms,
            stable_reads=args.stable_reads,
        )

        out_path = build_output_path(specs, args.out)
        tmp_path = f"{out_path}.part"
        with open(tmp_path, "wb") as f:
            f.write(image)
        os.replace(tmp_path, out_path)

        sha256 = hashlib.sha256(image).hexdigest()
        mac_str, mac_src = find_mac_in_dump(image)
        is_blank = all(b == 0xFF for b in image) or all(b == 0x00 for b in image)

        pgm.close(power_off=not args.keep_power)
        pgm = None

        beep(2)
        print("\n" + "=" * 68)
        print("  DUMP COMPLETE — SAFE TO RELEASE PINS!")
        print("=" * 68)
        print(f"  Saved File   : {out_path}")
        print(f"  File Size    : {len(image)} bytes ({len(image) // 1024} KB)")
        print(f"  SHA-256      : {sha256}")
        print(f"  BLE MAC      : {mac_str} (from {mac_src})")
        if is_blank:
            print("  [!] WARNING  : Flash contents are uniform (0xFF or 0x00)!")
        print("=" * 68)
        return 0
    finally:
        if pgm is not None:
            pgm.close(power_off=not args.keep_power)


if __name__ == "__main__":
    sys.exit(main())
