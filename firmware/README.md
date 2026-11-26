# `tlsr-flasher` Custom Firmware (`E180-Z6907A` / `TLSR8269`)

Custom `TLSR8269` USB-CDC SWire programmer firmware tailored specifically for the [`../pcb/`](../pcb/) hardware, implementing the **`pvvx/TLSRPGM` v0.0.0.8+** protocol.

---

## Features & Hardware Adaptation

- **USB-CDC Identity**: `VID 0x248A`, `PID 0x8269`, Product `"TLSR SWire Flasher"`, Serial `"TLSR8269-PGM"`, `32 MHz` PLL system clock ([`src/app_cfg.h`](src/app_cfg.h)).
- **Protocol Compatibility (`TLSRPGM` `v0.0.0.8`)**:
  - `CMDF_GET_VERSION` (reports `0x5327` `TLSR8269`, `v0.0.0.8`), `CMDF_MCU_REBOOT`, `CMDF_SWIRE_CFG` (`swdiv`, `addrlen` `2` or `3`, custom activate packet), `CMDF_EXT_POWER`, `CMDF_SWIRE_ACTIVATE` (returns target CPU `PC`), `CMDF_UART_BAUD` (no-op ACK over native USB-CDC), `CMDF_WAIT_RESP`.
  - SPI flash operations: `CMD_FLASH_READ`, `CMD_FLASH_WRITE`, `CMD_FLASH_SECT_ERASE`, `CMD_FLASH_ALL_ERASE`, `CMD_FLASH_GET_JEDEC_ID`, `CMD_FLASH_GET_STATUS`, `CMD_FLASH_WRRD`, and `CMD_FLASH_RDCRC` (hardware CRC-16).
  - SWire bus & debug: `CMD_SWIRE_READ` / `CMD_SWIRE_WRITE`, `CMD_SWIRE_AREAD` / `CMD_SWIRE_AWRITE`, `CMD_SWIRE_FIFO_READ` / `CMD_SWIRE_FIFO_FWRITE`, and `CMD_SWS_PRINTF` FIFO monitor.
  - **Dual-Bank USB-CDC Self-Update (`CMD_SELF_OTA = 0x20`)**: Stages incoming firmware to the inactive hardware bank (`0x00000` / `0x40000`, `128 KB` max), clamps target `PWR_EN = 0` and `SWM = LOW` during update, verifies full flash read-back CRC-32 before flipping the `0x4B` boot flag, and soft-reboots into the new bank.
- **`SW1` Hardware Reset Button State Machine** ([`src/board_tlsr_flasher.c`](src/board_tlsr_flasher.c)):
  - Tracks button resets across hardware `nRESET` via deep-sleep analog register `DEEP_ANA_REG0` (`0x3A`) while distinguishing MCU soft reboots (`CMDF_MCU_REBOOT`).
  - **Single press**: Resets the MCU cleanly with `PWR_EN = 0` (`OFF`) and re-enumerates USB-CDC.
  - **Rapid double-press (`< 1.5 s`, `SW1_DOUBLE_WINDOW_US`)**: Toggles `PWR_EN` (`PC4` / `LED2`) between `OFF` and `ON` for standalone target power testing.
- **Parasitic Back-Power Prevention & Power Safety**:
  - Calling `CMDF_EXT_POWER(0)` actively clamps `SWM` (`PA7`) **LOW** to drain/prevent parasitic current feeding into unpowered target chips through `SWS`.
  - When `PWR_EN = 0` at idle, `SWM` floats Hi-Z and automatically switches to hardware SWire mode on active SWire commands (preserving compatibility whether the target is wired to `H1.2 (PWR)` or `H1.3 (3V3)`).
- **`v1.0` & Revised PCB `USB DP` Compatibility**:
  - Uses hardware USB pins `PE2 (DM)` and `PE3 (DP)`.
  - Forces `U1.11 (PE0)` to **Hi-Z float** (`PE0_INPUT_ENABLE=0`, `PE0_OUTPUT_ENABLE=0`, no pull) so v1.0 PCBs with a solder bridge across `U1.11`–`U1.12` work identically to revised PCBs without signal contention.

---

## Pin Mapping (`E180-Z6907A` / `TLSR8269`)

| Module Pin | MCU GPIO | Net | Mode / Function |
| :--- | :--- | :--- | :--- |
| `U1.4` | `PC4` | `PWR_EN` | Active-HIGH push-pull (`Q2` `S8050` + `Q1` `AO3401A` + `LED2`) |
| `U1.10` | `PE2` | `DM` | Hardware USB `D-` |
| `U1.11` | `PE0` | *(v1.0 bridge)* | Hi-Z float (for v1.0 `U1.11`–`U1.12` solder bridge compatibility) |
| `U1.12` | `PE3` | `DP` | Hardware USB `D+` |
| `U1.18` | `PA7` | `SWM` | Hardware SWire Master (`H1.4`, no external pull-up) |
| `U1.21` | `PB1` | `EXT_RST` | Open-drain target reset (`H1.5`: drives `LOW` or Hi-Z with `10 kΩ` pull-up) |
| `U1.26` | `PB0` | `SWS` | SWire Slave (`H2.3`, `1 MΩ` pull-up) |
| `U1.37` | `nRESET` | `RST` | Hardware reset (`SW1`, `H2.4`, `10 kΩ / 100 nF` RC) |

---

## Build & Test

### Build Target Firmware (`/opt/tc32` toolchain required)
```bash
make -C firmware clean all
```
Output binary: [`bin/tlsr_flasher_8269.bin`](bin/tlsr_flasher_8269.bin) (`8,740` bytes, verified by `tl_check_fw.py`).

### Run Host Unit & Protocol Test Suite
```bash
python3 firmware/tests/test_firmware.py
```
Compiles [`tests/host_harness.c`](tests/host_harness.c) against stubbed Telink registers and verifies CRC-16, all `CMDF_*` and `CMD_*` handlers, `2`-byte and `3`-byte SWire addressing, `EXT_RST` open-drain + `SWM` clamp behavior, and `SW1` single/double-press state transitions.

---

## Flashing onto `tlsr-flasher` (`H2`)

### Subsequent Updates via USB-CDC Self-Update (No Second Programmer Needed)
Once `tlsr-flasher` is running dual-bank firmware (`CMD_SELF_OTA`), plug it in over USB-C and run:
```bash
make -C firmware self-update
# or directly:
python3 ../TlsrPgm.py self-update bin/tlsr_flasher_8269.bin
```

### Initial Bootstrap / Recovery via `H2` (SWire)
1. Wire an existing SWire programmer to `H2` (`GND`–`GND`, `PWR`–`3V3`, `SWM`–`SWS`; leave USB-C unplugged on the target `tlsr-flasher`).
2. Flash from the parent directory (`tlsr-flasher/`):
   ```bash
   python3 ../TlsrPgm.py -p <PORT> -b 1500000 -u -t 1500 -a 300 we 0 bin/tlsr_flasher_8269.bin
   ```
   *(See [`../README.md`](../README.md) for optional `ea` full erase and `-R/--retry` flashing options.)*

---

## Reference Repositories & Attributions

- **`pvvx/TLSRPGM`** (https://github.com/pvvx/TLSRPGM): Wire protocol specification, command IDs, CRC-16 framing, and SWire activation model implemented in [`src/tlsrpgm.c`](src/tlsrpgm.c) and [`src/swm.c`](src/swm.c).
- **Telink `tl_zigbee_sdk` (`826x`)** ([`sdk/`](sdk/)): `TLSR826x` startup (`cstartup_826x.S`), linker script (`boot_826x.link`), USB/GPIO/clock headers, `tl_check_fw.py`, and `libdrivers_826x` linked in [`Makefile`](Makefile).
