# TLSR SWire Flasher (`E180-Z6907A` / `TLSR8269` + USB-C + `2 A` Buck)

Compact single-sided USB-C SWire programmer/dumper for Telink `TLSR825x`, `TLSR826x`, and `TLSR8208` SoCs, complete with PCB manufacturing files, custom `TLSRPGM v0.0.0.8`-compatible firmware, and host flashing/dumping scripts.

## Repository Layout

| Path | Contents | Documentation |
| :--- | :--- | :--- |
| **`./`** | Unified host CLI ([`TlsrPgm.py`](TlsrPgm.py)) & full WebSerial browser workbench ([`tlsr-flasher.html`](tlsr-flasher.html)) | This README |
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

### 1. Unified CLI (`TlsrPgm.py`)

`TlsrPgm.py` auto-detects the connected USB programmer (or accepts `-p <port>`), supports immediate `PWR` toggling, provides an autonomous `dump` subcommand + `-R/--retry` slip-recovery mode for hand-held probes, and retains all classic `TLSRPGM` flash/SWire/register/debug commands. See the top of [`TlsrPgm.py`](TlsrPgm.py) or `python3 TlsrPgm.py --help` for full usage details.

- **Toggle or set target power (`PWR`) and exit immediately**:
  ```bash
  python3 TlsrPgm.py --pwr          # Toggle PWR ON <-> OFF
  python3 TlsrPgm.py --pwr on       # Turn 3.3V PWR ON
  python3 TlsrPgm.py --pwr off      # Turn 3.3V PWR OFF
  ```

- **Autonomous full flash dump (`dump` — hardware CRC16 verified, auto BLE MAC + SHA-256)**:
  ```bash
  python3 TlsrPgm.py dump                                   # TLSR825x (auto port + 1.5 Mbps)
  python3 TlsrPgm.py -u dump                                # TLSR826x (2-byte SWire address)
  python3 TlsrPgm.py -u --pwr-off-ms 1500 --act-ms 300 dump # Boards with large 3V3 bulk caps
  python3 TlsrPgm.py dump -o backup.bin -s 0x80000          # Custom filename & size override
  ```

- **Autonomous Retry Mode (`-R` / `--retry`) with any subcommand** *(keeps polling until stable chip/flash lock, and re-acquires + resumes automatically if probe pins slip)*:
  ```bash
  python3 TlsrPgm.py -R i                                   # Full chip & flash info
  python3 TlsrPgm.py -R we 0x0 your_firmware.bin              # Erase sectors + flash TLSR825x
  python3 TlsrPgm.py -R -u --pwr-off-ms 1500 --act-ms 300 we 0x0 firmware/bin/tlsr_flasher_8269.bin
  python3 TlsrPgm.py -R rf 0 0x80000 backup.bin              # Read region to file
  ```

- **Self-Update Programmer Firmware (Dual-Bank USB-CDC)** *(once bootstrapped with dual-bank firmware, updates `tlsr-flasher` itself over USB-C without a second SWire programmer)*:
  ```bash
  python3 TlsrPgm.py self-info                                         # Show active Bank (0/1) & FILE_VERSION
  python3 TlsrPgm.py self-update firmware/bin/tlsr_flasher_8269.bin    # Flash alternate bank, CRC-32 verify, reboot & confirm
  make -C firmware self-update                                         # Build + self-update in one step
  ```
  *(Pass `--force` to `self-update` to bypass the `IMAGE_TYPE` check.)*

- **Classic Fixed-Timing Mode**:
  ```bash
  python3 TlsrPgm.py -p <PORT> -b 1500000 -t 100 -a 150 i
  python3 TlsrPgm.py -p <PORT> -b 1500000 -u -t 1500 -a 300 ea
  python3 TlsrPgm.py -p <PORT> -b 1500000 -u -t 1500 -a 300 we 0 firmware/bin/tlsr_flasher_8269.bin
  ```

Useful options across modes:
- `-p <port>`: Specify serial port explicitly (default: auto-discover USB programmer)
- `-b <rate|auto>`: Set UART baud (`115200`..`3000000` or `auto`)
- `-d <div>`: Override SWire clock divisor (try `-d 10` or `-d 12` for noisy wires or slow target RC clocks)
- `--keep-power`: Keep `PWR` enabled after `dump` or `-R` completes
- `--no-crc`: Skip per-block hardware CRC16 verification

> **Note:** On `TLSR8269` (`TLSR826x`) targets, **always include `-u`**!

---

### 2. Browser Workbench (`tlsr-flasher.html`)

Open [`tlsr-flasher.html`](tlsr-flasher.html) in a WebSerial-capable Chromium browser (Chrome / Edge over `https://` or `http://localhost`) for a full graphical UI implementing all `TlsrPgm.py` features directly in the browser:
- USB-CDC programmer connection, baud/SWire configuration (`swdiv`, `2B`/`3B` addr, `swbuf`), and live `PWR` ON/OFF/Toggle
- **Programmer Self-Update (Dual-Bank USB-CDC)** card in the Overview tab showing active Bank `0`/`1` + `FILE_VERSION`, local Telink header & CRC-32 check, upload progress bar, and automatic WebSerial reconnect after reboot
- Autonomous contact poller with slip recovery, hardware-CRC16 full flash dump, SHA-256 + BLE MAC detection, and drag-and-drop flashing (`we`/`wf`/`es`/`ea`)
- Target chip/JEDEC/UID specs, Flash Status Register (`fsr`/`fsw`), SWire/SRAM/analog/TLSR8208-OTP hex dump & editor, live watch (`dc`), CPU breakpoint/single-step (`bkp`/`stp`), and `SWS Printf` streaming terminal

---

## Reference Repositories & Attributions

This project builds upon and adapts the following open-source projects and hardware designs:

| Project / Author | URL | Usage in This Repository |
| :--- | :--- | :--- |
| **`pvvx/TLSRPGM`** (Victor / pvvx) | https://github.com/pvvx/TLSRPGM | Upstream `TLSRPGM` USB-CDC SWire protocol implemented in [`firmware/`](firmware/), and upstream host utility [`TlsrPgm.py`](TlsrPgm.py) (extended here with USB auto-discovery, `--pwr`, `-R/--retry`, `dump`, and the [`tlsr-flasher.html`](tlsr-flasher.html) WebSerial UI). |
| **`tsl0922` TLSR SWire Flasher** | https://oshwhub.com/tsl0922/project_rapqcvts | Original `E180-Z6907A` V1.1 schematic & pinout reference (`reference/TLSR_SWire_Flasher`), adapted into [`pcb/`](pcb/) with USB-C, ESD/PTC protection, and an `AP63203WU-7` `2 A` Buck converter. |
| **Telink `tl_zigbee_sdk` (`826x`)** | https://github.com/telink-semi (`firmware/sdk/`) | Telink `TLSR826x` startup (`cstartup_826x.S`), linker script, USB/hardware register headers, and `libdrivers_826x` bundled in [`firmware/sdk/`](firmware/sdk/) for standalone builds. |
| **`InteractiveHtmlBom`** (`openscopeproject`) | https://github.com/openscopeproject/InteractiveHtmlBom | Front-end interactive BOM viewer used to generate [`pcb/ibom.html`](pcb/ibom.html). |
