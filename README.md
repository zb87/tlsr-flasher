# TLSR SWire Flasher (`E180-Z6907A` / `TLSR8269` + USB-C + `2 A` Buck)

Compact single-sided USB-C SWire programmer/dumper for Telink `TLSR825x`, `TLSR826x`, and `TLSR8208` SoCs, complete with PCB manufacturing files, custom `TLSRPGM v0.0.0.8`-compatible firmware, and host flashing/dumping scripts.

## Repository Layout

| Path | Contents | Documentation |
| :--- | :--- | :--- |
| **`./`** | Host CLI tools (`dump_firmware.py`, `TlsrPgm.py`) & browser UART-SWire recovery tool (`USBCOMFlashTx.html`) | This README |
| [`pcb/`](pcb/) | Schematics, PCB layout/routing/DRC scripts, Gerber/BOM/PnP exports, `ibom.html`, renders, `.epro2` archive | [`pcb/README.md`](pcb/README.md) |
| [`firmware/`](firmware/) | Custom `TLSR8269` (`pvvx/TLSRPGM` v0.0.0.8+ compatible) USB-CDC programmer firmware + host unit tests | [`firmware/README.md`](firmware/README.md) |

---

## Hardware Quick Reference

### `H1` — Target Programming Header (`1×5P` `2.54 mm`, East Edge)
| Pin | Net | Description |
| :---: | :--- | :--- |
| **1** | `GND` | Common ground |
| **2** | `PWR` | Software-controlled `3.3 V` (`PC4` active-HIGH via `AO3401A`, indicated by `LED2`) — recommended for power-cycle SWire activation |
| **3** | `3V3` | Always-on `3.3 V` (`AP63203WU-7` `2 A` Buck output) |
| **4** | `SWM` | Single-Wire Master (`U1.18 / PA7`, no external pull-up) |
| **5** | `EXT_RST` | Open-drain target reset (`U1.21 / PB1`, `10 kΩ` weak pull-up when released) |

### `H2` — Self-Programming Header (`1×4P` `2.54 mm`, South Edge)
`1: GND` | `2: 3V3` | `3: SWS` | `4: RST`

### On-Board Button (`SW1`)
- **Single press**: Hardware-resets the flasher (`nRESET`), re-enumerates USB-CDC, and turns `PWR` (`LED2`) off.
- **Double press (within `1.5 s`)**: Toggles target `PWR` (`OFF ↔ ON`) and `LED2` without a PC host.

---

## Using the Host Scripts (Dump & Flash)

### Prerequisites
```bash
pip install pyserial
```
On Linux, ensure your user is in the `dialout` group (or pass `-p /dev/ttyACM0`). On macOS, pass `-p /dev/cu.usbmodem*` if needed (or omit `-p` for auto-detection).

### Wiring to Target Board
- **Target without a reset pin (standard 3-wire)**:
  - `H1.1 (GND)` → Target `GND`
  - `H1.2 (PWR)` → Target `VCC / 3V3` *(do **not** connect USB/battery to the target at the same time)*
  - `H1.4 (SWM)` → Target `SWS`
- **Target with large `3V3` bulk capacitors** (e.g., flashing another `tlsr-flasher` board via `H2`, which has `~54 µF` on `3V3`):
  - Increase `PWR`-off time to **`1500 ms`** (`--pwr-off-ms 1500` or `-t 1500`) and activation to **`300 ms`** (`--act-ms 300` or `-a 300`), or tap target `SW1` (`nRESET`) during polling.

---

### 1. Dump Firmware (`dump_firmware.py`)

`dump_firmware.py` auto-detects the programmer, negotiates `1.5 Mbps` UART, polls until contact stabilizes, reads Chip ID + Flash JEDEC ID + UID, and dumps the full SPI flash with per-block hardware CRC16 verification.

- **Target `TLSR825x` (`TLSR8258`, `TLSR8253`, etc. — 3-byte SWire addressing)**:
  ```bash
  python3 dump_firmware.py
  ```
- **Target `TLSR826x` (`TLSR8269`, `TLSR8266`, `TLSR8267` — add `-u` for 2-byte SWire addressing)**:
  ```bash
  python3 dump_firmware.py -u
  ```
- **Target `TLSR8269` / boards with large `3V3` bulk capacitance**:
  ```bash
  python3 dump_firmware.py -u --pwr-off-ms 1500 --act-ms 300
  ```

Useful `dump_firmware.py` options:
- `-p <port>`: Specify serial port explicitly (e.g. `/dev/cu.usbmodem*` or `/dev/ttyACM0`)
- `-o <file.bin>`: Output filename (default: `dump_<CHIP>_<SIZE>KB_<TIMESTAMP>.bin`)
- `-d <div >`: Override SWire clock divider (try `-d 10` or `-d 12` for noisy wires or slow target RC clocks)
- `--keep-power`: Keep `PWR` enabled after dumping completes

---

### 2. Flash / Erase / Inspect (`TlsrPgm.py`)

Replace `<PORT>` with your device path (e.g. `/dev/ttyACM0` or `/dev/cu.usbmodem*`; see `python3 TlsrPgm.py -h` for defaults).

- **Inspect target Chip ID & Flash JEDEC ID**:
  - `TLSR825x`:
    ```bash
    python3 TlsrPgm.py -p <PORT> -b 1500000 -t 100 -a 150 i
    ```
  - `TLSR826x` (`TLSR8269`, add `-u`):
    ```bash
    python3 TlsrPgm.py -p <PORT> -b 1500000 -u -t 1500 -a 300 i
    ```

- **Flash firmware (`we` = sector erase + write at address `0`)**:
  - `TLSR825x` target:
    ```bash
    python3 TlsrPgm.py -p <PORT> -b 1500000 -t 100 -a 150 we 0 your_firmware.bin
    ```
  - `TLSR826x` (`TLSR8269`) target (e.g. flashing another `tlsr-flasher` board):
    ```bash
    python3 TlsrPgm.py -p <PORT> -b 1500000 -u -t 1500 -a 300 we 0 firmware/bin/tlsr_flasher_8269.bin
    ```

- **Full chip erase (`ea`)** before flashing (recommended if switching firmware families or clearing old NVM):
  ```bash
  python3 TlsrPgm.py -p <PORT> -b 1500000 -u -t 1500 -a 300 ea
  python3 TlsrPgm.py -p <PORT> -b 1500000 -u -t 1500 -a 300 we 0 firmware/bin/tlsr_flasher_8269.bin
  ```

- **Read flash region (`rf <addr> <size> <out.bin>`)**:
  ```bash
  python3 TlsrPgm.py -p <PORT> -b 1500000 -t 100 -a 150 rf 0 0x80000 backup.bin
  ```

> **Note:** On `TLSR8269` (`TLSR826x`) targets, **always include `-u`** on both `dump_firmware.py` and `TlsrPgm.py`.

---

### 3. Bootstrap Without Another SWire Programmer (`USBCOMFlashTx.html`)

If you do not have a second SWire programmer to flash the initial firmware onto a blank `tlsr-flasher`, open [`USBCOMFlashTx.html`](USBCOMFlashTx.html) in a WebSerial-capable browser (Chrome/Edge) with a standard USB-UART adapter (with `RTS`) wired to `H2`:
- `UART TX` → `H2.3 (SWS)`
- `UART RTS` → `H2.4 (RST)`
- `UART 3V3` → `H2.2 (3V3)` *(or power `tlsr-flasher` via USB-C and leave `3V3` disconnected)*
- `UART GND` → `H2.1 (GND)`

---

## Reference Repositories & Attributions

This project builds upon and adapts the following open-source projects and hardware designs:

| Project / Author | URL | Usage in This Repository |
| :--- | :--- | :--- |
| **`pvvx/TLSRPGM`** (Victor / pvvx) | https://github.com/pvvx/TLSRPGM | Upstream `TLSRPGM` USB-CDC SWire protocol implemented in [`firmware/`](firmware/), and upstream host utility [`TlsrPgm.py`](TlsrPgm.py) (with [`dump_firmware.py`](dump_firmware.py) implementing the same protocol). |
| **`tsl0922` TLSR SWire Flasher** | https://oshwhub.com/tsl0922/project_rapqcvts | Original `E180-Z6907A` V1.1 schematic & pinout reference (`reference/TLSR_SWire_Flasher`), adapted into [`pcb/`](pcb/) with USB-C, ESD/PTC protection, and an `AP63203WU-7` `2 A` Buck converter. |
| **`pvvx/TlsrComSwireWriter`** (Victor / pvvx) | https://github.com/pvvx/TlsrComSwireWriter | UART TX-SWS flashing concept and [`USBCOMFlashTx.html`](USBCOMFlashTx.html) browser recovery/bootstrap writer. |
| **Telink `tl_zigbee_sdk` (`826x`)** | https://github.com/telink-semi (`firmware/sdk/`) | Telink `TLSR826x` startup (`cstartup_826x.S`), linker script, USB/hardware register headers, and `libdrivers_826x` bundled in [`firmware/sdk/`](firmware/sdk/) for standalone builds. |
| **`InteractiveHtmlBom`** (`openscopeproject`) | https://github.com/openscopeproject/InteractiveHtmlBom | Front-end interactive BOM viewer used to generate [`pcb/ibom.html`](pcb/ibom.html). |
