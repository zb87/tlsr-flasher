#!/usr/bin/env python3
"""Host-compiled C unit tests and firmware binary verification for tlsr_flasher_8269."""

import binascii
import ctypes
import os
import struct
import subprocess
import tempfile
import unittest

FW_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BIN_PATH = os.path.join(FW_DIR, "bin", "tlsr_flasher_8269.bin")

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


def crc16(data: bytes) -> bytes:
    crc = 0xFFFF
    for b in data:
        crc = (crc >> 8) ^ CRC16_TABLE[(crc ^ b) & 0xFF]
    return bytes([crc & 0xFF, (crc >> 8) & 0xFF])


def wrap_pkt(payload: bytes) -> bytes:
    return payload + crc16(payload)


def check_pkt(pkt: bytes) -> bool:
    return len(pkt) >= 6 and pkt[-2:] == crc16(pkt[:-2])


class MockGpio(ctypes.Structure):
    _fields_ = [
        ("func", ctypes.c_uint32),
        ("oen", ctypes.c_uint32),
        ("ien", ctypes.c_uint32),
        ("out", ctypes.c_uint32),
        ("pull", ctypes.c_uint32),
    ]


class TestFirmwareBinary(unittest.TestCase):
    def test_bin_header_and_crc32(self):
        with open(BIN_PATH, "rb") as f:
            fw = f.read()
        self.assertGreater(len(fw), 256)
        self.assertEqual(len(fw) % 16, 4)  # padded to 16B + 4B CRC32
        self.assertEqual(fw[6:8], b"\x5d\x02")
        self.assertEqual(fw[8:12], b"KNLT")
        fw_size = struct.unpack("<I", fw[0x18:0x1C])[0]
        self.assertEqual(fw_size, len(fw))
        calc_crc = binascii.crc32(fw[:-4]) ^ 0xFFFFFFFF
        got_crc = struct.unpack("<I", fw[-4:])[0]
        self.assertEqual(got_crc, calc_crc)

    def test_usb_descriptors_embedded(self):
        with open(BIN_PATH, "rb") as f:
            fw = f.read()
        # Look for Device Descriptor: bLength=18, bDescriptorType=1, bcdUSB=0x0110, IAD EF/02/01, EP0=8, VID=248A, PID=8269
        dev_sig = bytes.fromhex("12011001ef0201088a246982000101020301")
        self.assertIn(dev_sig, fw)
        # Look for CDC Config Descriptor header (total len = 75 = 0x4B, 2 interfaces)
        cfg_sig = bytes.fromhex("09024b000201008032")
        self.assertIn(cfg_sig, fw)


class TestProtocolAndBoard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmpdir = tempfile.TemporaryDirectory()
        so_path = os.path.join(cls.tmpdir.name, "libfwtest.so")
        cmd = [
            "gcc", "-shared", "-fPIC", "-O2", "-Wall", "-Wextra",
            "-include", os.path.join(FW_DIR, "tests", "host_stub_inc", "tl_common.h"),
            "-I", os.path.join(FW_DIR, "tests", "host_stub_inc"),
            "-I", os.path.join(FW_DIR, "src"),
            os.path.join(FW_DIR, "tests", "host_harness.c"),
            os.path.join(FW_DIR, "src", "board_tlsr_flasher.c"),
            os.path.join(FW_DIR, "src", "tlsrpgm.c"),
            "-o", so_path,
        ]
        subprocess.run(cmd, check=True)
        cls.lib = ctypes.CDLL(so_path)

    @classmethod
    def tearDownClass(cls):
        cls.tmpdir.cleanup()

    def setUp(self):
        self.lib.host_boot(1)
        ctypes.c_uint8.in_dll(self.lib, "mock_target_fail").value = 0
        ctypes.c_uint32.in_dll(self.lib, "mock_wait_poll_until_ready").value = 0
        ctypes.c_uint32.in_dll(self.lib, "mock_wait_polls").value = 0

    def send(self, pkt: bytes, chunked: bool = False) -> bytes:
        self.lib.host_reset_usb()
        if chunked and len(pkt) > 64:
            for off in range(0, len(pkt), 64):
                chunk = pkt[off : off + 64]
                is_short = 1 if len(chunk) < 64 else 0
                buf = (ctypes.c_uint8 * len(chunk))(*chunk)
                self.lib.host_feed_usb(buf, len(chunk), is_short)
                self.lib.tlsrpgm_poll()
        else:
            buf = (ctypes.c_uint8 * len(pkt))(*pkt)
            self.lib.host_feed_usb(buf, len(pkt), 1 if len(pkt) < 64 else 0)
            self.lib.tlsrpgm_poll()
        tx_len = ctypes.c_uint16.in_dll(self.lib, "tx_len").value
        tx_arr = (ctypes.c_uint8 * 4096).in_dll(self.lib, "tx_buf")
        return bytes(tx_arr[:tx_len])

    def test_pe0_always_high_z_and_safe_defaults(self):
        pe0 = MockGpio.in_dll(self.lib, "mock_pe0_gpio")
        pwr = MockGpio.in_dll(self.lib, "mock_pwr_gpio")
        rst = MockGpio.in_dll(self.lib, "mock_rst_gpio")
        self.assertEqual((pe0.func, pe0.oen, pe0.ien, pe0.pull), (0, 0, 0, 0))
        self.assertEqual((pwr.oen, pwr.out), (1, 0))
        self.assertEqual((rst.oen, rst.pull), (0, 2))  # released Hi-Z with 10k PU

    def test_sw1_single_and_double_reset_state_machine(self):
        # Cold boot -> PWR OFF
        self.assertEqual(self.lib.board_get_pwr_en(), 0)
        # First SW1 press -> still PWR OFF, armed for 1.5s
        self.lib.host_boot(0)
        self.assertEqual(self.lib.board_get_pwr_en(), 0)
        # Wait > 1.5s -> window expires; another SW1 press is still single reset (PWR OFF)
        self.lib.host_advance_us(1600000)
        self.lib.host_boot(0)
        self.assertEqual(self.lib.board_get_pwr_en(), 0)
        # Second SW1 press within 1.5s -> double-press toggles PWR 0 -> 1!
        self.lib.host_advance_us(300000)
        self.lib.host_boot(0)
        self.assertEqual(self.lib.board_get_pwr_en(), 1)
        # Wait > 1.5s, then double-press again -> toggles PWR 1 -> 0!
        self.lib.host_advance_us(2000000)
        self.lib.host_boot(0)  # Press 1: safe reset PWR=0, remembers pre_pwr=1
        self.assertEqual(self.lib.board_get_pwr_en(), 0)
        self.lib.host_advance_us(200000)
        self.lib.host_boot(0)  # Press 2: toggles pre_pwr 1 -> 0
        self.assertEqual(self.lib.board_get_pwr_en(), 0)

    def test_soft_reboot_does_not_trigger_sw1_double_press(self):
        resp = self.send(wrap_pkt(struct.pack("<BBH", 0, 1, 0)))
        self.assertTrue(check_pkt(resp))
        self.assertEqual(resp[1], 0)
        self.lib.host_boot(0)
        self.assertEqual(self.lib.board_get_pwr_en(), 0)
        # Subsequent single SW1 press arms window rather than toggling immediately
        self.lib.host_boot(0)
        self.assertEqual(self.lib.board_get_pwr_en(), 0)

    def test_get_version_and_ext_power_and_swm_clamping(self):
        resp = self.send(wrap_pkt(struct.pack("<BBH", 0, 0, 0)))
        self.assertEqual(len(resp), 19)
        self.assertTrue(check_pkt(resp))
        self.assertEqual((resp[5], resp[4]), (0, 8))
        cid, pwr, swdiv, addrlen = struct.unpack("<HBBB", resp[6:11])
        self.assertEqual((cid, pwr, swdiv, addrlen), (0x5327, 0, 7, 3))

        # CMDF_EXT_POWER(1)
        resp = self.send(wrap_pkt(struct.pack("<BBH", 0, 3, 1)))
        self.assertEqual(len(resp), 7)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(resp[4], 1)
        swm = MockGpio.in_dll(self.lib, "mock_swm_gpio")
        self.assertEqual(swm.func, 13)  # AS_SWM

        # CMDF_EXT_POWER(0) -> clamps SWM LOW, drives EXT_RST LOW, PWR OFF
        resp = self.send(wrap_pkt(struct.pack("<BBH", 0, 3, 0)))
        self.assertEqual(len(resp), 7)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(resp[4], 0)
        swm = MockGpio.in_dll(self.lib, "mock_swm_gpio")
        rst = MockGpio.in_dll(self.lib, "mock_rst_gpio")
        self.assertEqual((swm.func, swm.oen, swm.out, swm.pull), (0, 1, 0, 0))
        self.assertEqual((rst.oen, rst.out), (1, 0))

    def test_swire_cfg_activate_and_baud(self):
        swbuf = b"\x5a\x00\x06\x02\x01\x05"
        resp = self.send(wrap_pkt(struct.pack("<BBHBB", 0, 2, 0, 5, 2) + swbuf))
        self.assertEqual(len(resp), 14)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(resp[4:6], b"\x05\x02")
        self.assertEqual(resp[6:12], swbuf)

        resp = self.send(wrap_pkt(struct.pack("<BBH", 0, 4, 10)))
        self.assertEqual(len(resp), 10)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(struct.unpack("<I", resp[4:8])[0], 0x00001234)

        ctypes.c_uint8.in_dll(self.lib, "mock_target_fail").value = 1
        resp = self.send(wrap_pkt(struct.pack("<BBH", 0, 4, 10)))
        self.assertEqual(len(resp), 6)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(resp[1], 3)  # ERR_READ

        ctypes.c_uint8.in_dll(self.lib, "mock_target_fail").value = 0
        self.assertEqual(self.send(wrap_pkt(struct.pack("<BBH", 0, 5, 4)))[1], 0)
        self.assertEqual(self.send(wrap_pkt(struct.pack("<BBH", 0, 5, 9)))[1], 6)  # ERR_BAUD

    def test_flash_write_read_rdcrc_jedec_status_wrrd(self):
        payload = bytes((i * 7 + 3) & 0xFF for i in range(256))
        resp = self.send(wrap_pkt(struct.pack("<BBH", 2, 0, 0x10) + payload), chunked=True)
        self.assertEqual(len(resp), 6)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(resp[1], 0)
        self.assertEqual(struct.unpack("<H", resp[2:4])[0], 256)

        resp = self.send(wrap_pkt(struct.pack("<BBHH", 1, 0, 0x10, 256)))
        self.assertEqual(len(resp), 262)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(resp[4:260], payload)

        resp = self.send(wrap_pkt(struct.pack("<BBHH", 14, 0, 0x10, 256)))
        self.assertEqual(len(resp), 6)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(resp[2:4], crc16(payload))

        resp = self.send(wrap_pkt(struct.pack("<BBH", 5, 0, 0)))
        self.assertEqual(len(resp), 9)
        self.assertEqual(resp[4:7], b"\x85\x60\x13")

        resp = self.send(wrap_pkt(struct.pack("<BBHHB", 13, 0, 0, 20, 0x4B)))
        self.assertEqual(len(resp), 26)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(struct.unpack("<H", resp[2:4])[0], 21)

    def test_exact_64_byte_variable_packet_idle_dispatch(self):
        # 4 + 58 + 2 = 64 bytes exact multiple of 64B endpoint
        data58 = bytes(range(58))
        pkt = wrap_pkt(struct.pack("<BBH", 8, 0x20, 0x00) + data58)
        self.assertEqual(len(pkt), 64)
        resp = self.send(pkt, chunked=True)
        self.assertEqual(resp, b"")  # waiting for 2ms idle
        self.lib.host_advance_us(2500)
        tx_len = ctypes.c_uint16.in_dll(self.lib, "tx_len").value
        tx_arr = (ctypes.c_uint8 * 4096).in_dll(self.lib, "tx_buf")
        resp = bytes(tx_arr[:tx_len])
        self.assertEqual(len(resp), 6)
        self.assertTrue(check_pkt(resp))
        self.assertEqual(struct.unpack("<H", resp[2:4])[0], 58)

    def test_wait_resp_and_sws_printf_and_bad_crc(self):
        # Bad CRC on fixed packet
        bad = struct.pack("<BBH", 0, 0, 0) + b"\x00\x00"
        resp = self.send(bad)
        self.assertEqual(resp[1], 5)  # ERR_CRC

        # WAIT_RESP
        sram = (ctypes.c_uint8 * 65536).in_dll(self.lib, "mock_target_sram")
        sram[0x6BC] = 0x78
        sram[0x6BD] = 0x56
        sram[0x6BE] = 0x34
        sram[0x6BF] = 0x12
        ctypes.c_uint32.in_dll(self.lib, "mock_wait_poll_until_ready").value = 3
        ack = self.send(wrap_pkt(struct.pack("<BBHBH", 16, 0xBC, 0x06, 0x02, 0x06) + b"\x05"))
        self.assertEqual(len(ack), 6)
        self.assertEqual(ack[1], 0)
        self.lib.host_reset_usb()
        for _ in range(3):
            self.lib.tlsrpgm_poll()
        tx_len = ctypes.c_uint16.in_dll(self.lib, "tx_len").value
        tx_arr = (ctypes.c_uint8 * 4096).in_dll(self.lib, "tx_buf")
        wresp = bytes(tx_arr[:tx_len])
        self.assertEqual(len(wresp), 10)
        self.assertTrue(check_pkt(wresp))
        self.assertEqual(wresp[4:8], b"\x78\x56\x34\x12")
        self.assertEqual(sram[0x602], 0x05)

        # SWS_PRINTF
        msg = b"hello tlsr\n"
        sram[0xE700] = 0x55
        sram[0xE701] = len(msg)
        for i, ch in enumerate(msg):
            sram[0xE702 + i] = ch
        ack = self.send(wrap_pkt(struct.pack("<BBHB", 15, 0x00, 0xE7, 0)))
        self.assertEqual(len(ack), 6)
        self.assertEqual(struct.unpack("<H", ack[2:4])[0], 1)
        self.lib.host_reset_usb()
        self.lib.tlsrpgm_poll()
        tx_len = ctypes.c_uint16.in_dll(self.lib, "tx_len").value
        tx_arr = (ctypes.c_uint8 * 4096).in_dll(self.lib, "tx_buf")
        self.assertEqual(bytes(tx_arr[:tx_len]), msg)
        self.assertEqual(sram[0xE701], 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
