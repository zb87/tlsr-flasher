# TLSR SWire Flasher Compact Hardware Design (`E180-Z6907A` + `AP63203WU-7` + `USB-C`)

A compact, customized redesign based on `reference/TLSR_SWire_Flasher`, built around an in-stock **Ebyte E180-Z6907A (`TLSR8269`, 512 KB Flash)** module, a **16-pin USB Type-C receptacle** (with ESD and resettable polyfuse protection), a **2 A `AP63203WU-7` synchronous buck converter**, and an **active-HIGH `AO3401A` + `S8050` target high-side power switch**. All **33 components are 100% single-sided (Top Layer)** on a tightened **`47.00 × 26.00 mm` (`1222 mm²`)** outline—38% smaller than the earlier `58 × 34 mm` compact layout.

> For firmware source, build, and tests, see [`../firmware/README.md`](../firmware/README.md). For flashing and dumping instructions, see [`../README.md`](../README.md).

---

## 1. Key Improvements & Compact Upgrades vs. Reference Design

| Subsystem | Original Reference Design | This Design (`tlsr-flasher` Compact) | Rationale |
| :--- | :--- | :--- | :--- |
| **Board Outline & Mounting** | USB-A stick | **`47.00 × 26.00 mm` (`R = 1.8 mm`), 2× diagonal `M2` holes (TL / BR)** | Eliminates unused board area (-38% footprint) while supporting 3D-printed enclosures and standoff mounting |
| **USB Interface** | USB-A male plug | **USB Type-C 16-Pin (`TYPE-C16PIN`, `C393939`)** + 2× `5.1 kΩ` `CC1/CC2` | Reversible Type-C cables and standard `5 V` sink negotiation |
| **3.3 V Regulator** | `RT9013-33GB-MS` (`500 mA` LDO) | **`AP63203WU-7` (`C780769`, `2 A` sync buck) + `SWPA4030S3R9MT` `3.9 µH` (`C96899`)** | Eliminates LDO thermal shutdown and voltage droop during high-current **7.5" EPD** boost refresh spikes (`400 mA–1 A+`) |
| **Main RF Module** | `Ebyte E180-Z6907A` (`TLSR8269`) | **`Ebyte E180-Z6907A` (`TLSR8269`, `C518909`, same module)** | Reuses in-stock modules for `pvvx/TLSRPGM`-compatible firmware, with a full-layer copper keepout beneath the North antenna |
| **Target Power Switch** | `SI2301` (`Q1`) | **`AO3401A` P-MOSFET (`C700954`) + `S8050` NPN (`C20069125`) level shifter (`PC4 = PWR_EN`)** | Active-HIGH `PC4` enable with `100 kΩ` base pull-down (`R9`) and `47 kΩ + 100 nF` gate RC (`R7, C10`) to prevent power-on glitches |
| **USB Protection** | None | **`BSMD1206-150-6V` `1.5 A` PTC (`F1`) + `SRV05-4` ESD (`D1`) + `33 Ω` (`R1, R2`)** | Protects host USB and `TLSR8269` `DM/DP` pins from hot-plug ESD and target short circuits |
| **Assembly Process** | — | **100% Top-Side Assembly (`33/33` parts on Top Layer, `0` on Bottom)** | Completely flat underside for single-pass stencil reflow/hot-air soldering and flush enclosure mounting |

### Why `AP63203WU-7` Replaces `RT9013`
- `RT9013-33GB` is a `500 mA` linear regulator (`SOT-23-5`, `θ_JA ≈ 200 °C/W`) where `(5.0 V - 3.3 V) × I` is dissipated directly as heat. When powering a **7.5" e-paper display**, the boost circuit draws hundreds of milliamps to over an amp during full refreshes (~`0.68 W` at `400 mA` -> `>+130 °C` rise), easily tripping LDO thermal shutdown or brownout.
- **`AP63203WU-7`** (`2 A` continuous high-efficiency synchronous buck) paired with `SWPA4030S3R9MT` (`3.9 µH`) and low-ESR `2× 22 µF + 100 nF` (`C4, C5, C6`) output capacitors stays cool and handles heavy transient target loads cleanly on `PWR` and `3V3`.

---

## 2. Circuit Architecture, Schematics & Pinouts

| Schematic Sheet | File Link | Contents |
| :--- | :--- | :--- |
| **Page 1 — USB Input & Protection** | [images/sch_p1.png](images/sch_p1.png) | `USB1` (16P Type-C), `R3/R4` (`5.1 kΩ` CC), `F1` (`1.5 A` PTC), `D1` (`SRV05-4` ESD), `R1/R2` (`33 Ω` `DM/DP`), `LED1`/`R5` (`+5V` red LED) |
| **Page 2 — 3.3V 2A Buck & High-Side Switch** | [images/sch_p2.png](images/sch_p2.png) | `U2` (`AP63203WU-7`), `L1` (`3.9 µH`), `C1..C6`, `Q2` (`S8050`) + `Q1` (`AO3401A`) switched `PWR` output, `LED2`/`R10` (`PWR` yellow-green LED) |
| **Page 3 — E180-Z6907A & Headers** | [images/sch_p3.png](images/sch_p3.png) | `U1` (`E180-Z6907A`), `C7/C8` (`10 µF + 100 nF`), `SW1`/`R6`/`C9` (`nRESET`), `H1` (`1×5P` target header), `H2` (`1×4P` self-prog header) |

### Key `E180-Z6907A` Signal Mapping
- `U1.10 (PE2)` ← `DM`, `U1.12 (PE3)` ← `DP` (routed through `33 Ω` series resistors `R1, R2` to USB-C; **Note: first-batch v1.0 PCBs mistakenly routed `DP` to adjacent `U1.11 (PE0)`—simply solder-bridge `U1.11` to `U1.12` during assembly; firmware keeps `PE0` floating Hi-Z for full compatibility with both v1.0 and revised PCBs**)
- `U1.4 (PC4)` → `PWR_EN` (drives `Q2` base via `R8 = 10 kΩ`; active-HIGH enables `Q1`; `R9 = 100 kΩ` pull-down prevents false turn-on)
- `U1.18 (PA7)` ↔ `SWM` (direct to `H1.4`, **intentionally no external pull-up resistor**)
- `U1.21 (PB1)` → `EXT_RST` (target reset output to `H1.5`, driven open-drain with `10 kΩ` weak pull-up in firmware)
- `U1.26 (SWS)` ↔ `SWS` (programmer self-programming SWire slave pin, broken out to `H2.3`)
- `U1.37 (nRESET)` ↔ `RST` (`10 kΩ / 100 nF` RC + side tactile switch `SW1` + `H2.4`)

### Header Pinouts

#### `H1` — Target SWire Programming Header (`1×5P 2.54 mm`, East Edge)
| Pin | Net | Description |
| :---: | :--- | :--- |
| **1** | `GND` | Common ground |
| **2** | `PWR` | Firmware-switched `3.3 V` target supply (`Q1` `AO3401A` drain, active when `PC4 = HIGH`) |
| **3** | `3V3` | Always-on `3.3 V` (`AP63203WU-7` buck output for continuous or high-current loads) |
| **4** | `SWM` | Single-Wire Master (`U1.PA7`), direct with no external pull-up |
| **5** | `EXT_RST` | Target chip hardware reset (`U1.PB1`, open-drain) |

#### `H2` — Self-Programming Header (`1×4P 2.54 mm`, South Edge)
| Pin | Net | Description |
| :---: | :--- | :--- |
| **1** | `GND` | Common ground |
| **2** | `3V3` | `3.3 V` rail |
| **3** | `SWS` | `E180-Z6907A` Single-Wire Slave (`U1.SWS`) |
| **4** | `RST` | `E180-Z6907A` hardware reset (`U1.nRESET`, shared with `SW1`) |

---

## 3. PCB Layout Specifications & Previews

- **Board Dimensions**: `47.00 × 26.00 mm` (`1850.394 × 1023.622 mil`, `R = 1.8 mm` / `70.87 mil` rounded corners), `1.6 mm` FR4, 2-layer `1 oz` copper.
- **Mounting Holes**: 2× diagonal `M2` non-plated holes (`Ø2.2 mm / 86.6 mil`, `2.8 mm / 110.2 mil` inset at Top-Left `(110.2, 913.4)` mil and Bottom-Right `(1740.2, 110.2)` mil).
- **Single-Sided Assembly Verified**: All **33/33 parts** are on the **Top Layer** (`fab/TLSR_Flasher_PickAndPlace_mm.csv` verified: all `33` entries `Layer = T`, `0` bottom parts).
- **2.4 GHz Antenna Keepout**: Locked all-layer keepout zone (`no-wires / no-fills / no-pours`) beneath `U1`'s North PCB antenna at `[1075..1620, 770..1023]` mil.
- **USB Differential Length Matching (`routing_report.json`)**: `USB_EXT` (`USB_DP`/`USB_DN`) skew = `0.096 mil` (`655.11` vs `655.01 mil`); `USB_INT` (`DP`/`DM`) skew = `0.090 mil` (`698.79` vs `698.88 mil`).

| View | Preview File |
| :--- | :--- |
| **2D Top / Bottom Routed Blueprint** | [images/pcb_routed_2d.png](images/pcb_routed_2d.png) |
| **3D Top / Flat Bottom Render** | [images/pcb_3d_top_bottom.png](images/pcb_3d_top_bottom.png) |
| **EasyEDA Live Top View** | [images/pcb_top_routed.png](images/pcb_top_routed.png) |
| **EasyEDA Live Bottom View** | [images/pcb_bottom_routed.png](images/pcb_bottom_routed.png) |

---

## 4. Bill of Materials (BOM — 33 Parts / 23 Line Items)

Full CSV: [fab/TLSR_Flasher_BOM.csv](fab/TLSR_Flasher_BOM.csv) · Interactive BOM Viewer: [ibom.html](ibom.html)

| Designator | Qty | Value / Spec | MPN | Package | LCSC # | Stock Status |
| :--- | :---: | :--- | :--- | :--- | :---: | :--- |
| `U1` | 1 | `E180-Z6907A` (`TLSR8269`) | `E180-Z6907A` | `Stamp-SMD-37P` | `C518909` | **In stock (`2 pcs`)** |
| `U2` | 1 | `AP63203WU-7` (`3.3 V / 2 A` Buck) | `AP63203WU-7` | `TSOT-23-6` | `C780769` | **In stock (`15 pcs`)** |
| `L1` | 1 | `3.9 µH` `3 A` Power Inductor | `SWPA4030S3R9MT` | `SMD 4030` | `C96899` | **In stock (`14 pcs`)** |
| `Q1` | 1 | `AO3401A` P-MOSFET | `AO3401A` | `SOT-23-3` | `C700954` | **In stock (`20 pcs`)** |
| `Q2` | 1 | `S8050` NPN BJT | `S8050` | `SOT-23-3` | `C20069125` | **In stock (`50 pcs`)** |
| `D1` | 1 | `SRV05-4` USB ESD Array | `SRV05-4` | `SOT-23-6` | `C384887` | **Order (LCSC)** |
| `F1` | 1 | `BSMD1206-150-6V` `1.5 A` PTC | `BSMD1206-150-6V` | `1206` | `C883132` | **Order (LCSC)** |
| `USB1` | 1 | `TYPE-C16PIN` USB-C Receptacle | `TYPE-C16PIN` | `SMD 16P + 4 TH` | `C393939` | **In stock (`30 pcs`)** |
| `SW1` | 1 | `TS-1088R-02526` Side Tactile Switch | `TS-1088R-02526` | `SMD 4×3 mm` | `C455281` | **In stock (`50 pcs`)** |
| `LED1` | 1 | Red `0603` LED (`+5V`) | `NCD0603R1` | `0603` | `C84263` | **In stock (`50 pcs`)** |
| `LED2` | 1 | Yellow-Green `0603` LED (`PWR`) | `NCD0603C1` | `0603` | `C84264` | **In stock (`50 pcs`)** |
| `C1, C7` | 2 | `10 µF 16 V` X5R `0603` | `HGC0603R5106M160NTHJ` | `0603` | `C7472959` | **In stock (`20 pcs`)** |
| `C4, C5` | 2 | `22 µF 10 V` X5R `0603` | `HGC0603R5226M100NTHJ` | `0603` | `C7432770` | **In stock (`100 pcs`)** |
| `C2, C3, C6, C8, C9, C10` | 6 | `100 nF 50 V` X7R `0603` | `0603X7R104K500NT` | `0603` | `C48579281` | **In stock (`300 pcs`)** |
| `R1, R2` | 2 | `33 Ω ±1%` `0603` | `FRC0603F33R0TS` | `0603` | `C2909394` | **Not stocked (order, or substitute in-stock `22 Ω` `C2930077`)** |
| `R3, R4` | 2 | `5.1 kΩ ±1%` `0603` | `FRC0603F5101TS` | `0603` | `C2907044` | **In stock (`300 pcs`)** |
| `R5` | 1 | `4.7 kΩ ±1%` `0603` | `FRC0603F4701TS` | `0603` | `C2907034` | **In stock (`300 pcs`)** |
| `R6, R8` | 2 | `10 kΩ ±1%` `0603` | `FRC0603F1002TS` | `0603` | `C2906982` | **In stock (`300 pcs`)** |
| `R7` | 1 | `47 kΩ ±1%` `0603` | `FRC0603F4702TS` | `0603` | `C2907042` | **In stock (`100 pcs`)** |
| `R9` | 1 | `100 kΩ ±1%` `0603` | `FRC0603F1003TS` | `0603` | `C2906980` | **In stock (`200 pcs`)** |
| `R10` | 1 | `2.2 kΩ ±1%` `0603` | `FRC0603F2201TS` | `0603` | `C2907005` | **In stock (`100 pcs`)** |
| `H1` | 1 | `1×5P` `2.54 mm` Pin Header | `PZ254V-11-05P` | `HDR-TH 1×5P` | `C492404` | **In stock (cut from `1×40P` strips)** |
| `H2` | 1 | `1×4P` `2.54 mm` Pin Header | `PZ254V-11-04P` | `HDR-TH 1×4P` | `C2691448` | **In stock (cut from `1×40P` strips)** |

---

## 5. Verification Checks & Manufacturing Deliverables

- **Schematic Strict Gate**: `P1_USB_Input`, `P2_Power_Tree`, and `P3_TLSR_Headers` all pass `easyeda sch gate --strict` (`0 fatal, 0 error, 0 warn`, `22` nets, `33/33` components connected).
- **Cold-Reloaded Native PCB DRC**: **`passed = True`, `total = 0`** ([design-data/drc_final.json](design-data/drc_final.json)).
- **PCB DFM Audit (`easyeda pcb check`)**: **`ERROR = 0`**, `WARN = 17` (`221` tracks, `41` vias, `130` pads; `dangling=0, acute=0, nonOrtho=0, overPad=0, clearance=0, viaInPad=0, silkOverPad=0, silkOffBoard=0, silkFlipped=0, antennaKeepout=0, zoneViolation=0`) ([design-data/check_final.txt](design-data/check_final.txt)).
- **Offline Geometry Pre-Check (`pcb-drc-precheck.py`)**: silkscreen gaps `< 3.0 mil` = `0`, acute bends = `0`, dangling endpoints = `0`, pour-only SMD `GND` pads = `0`.
- **Manufacturing Outputs, CAD Case & Repro Scripts**:
  - Gerber Archive (`15` files): [fab/TLSR_Flasher_Gerber.zip](fab/TLSR_Flasher_Gerber.zip)
  - Pick & Place (`mm`, verified 100% Top-Side): [fab/TLSR_Flasher_PickAndPlace_mm.csv](fab/TLSR_Flasher_PickAndPlace_mm.csv)
  - BOM CSV: [fab/TLSR_Flasher_BOM.csv](fab/TLSR_Flasher_BOM.csv)
  - Interactive HTML BOM: [ibom.html](ibom.html)
  - EasyEDA Pro Project Archive: [design-data/tlsr-flasher.epro2](design-data/tlsr-flasher.epro2)
  - Automated EasyEDA Build Scripts: [scripts/](scripts/)
  - 3D-Printable Enclosure (Onshape FeatureScript + STEP/STL): [case/](case/)

---

## 6. Reference Projects & Attributions

- **`tsl0922` TLSR SWire Flasher** (https://oshwhub.com/tsl0922/project_rapqcvts): Reference for the `E180-Z6907A` V1.1 core topology, `AO3401` + `S8050` high-side target power switch, and omitting the external `SWM` pull-up resistor (archived locally in `reference/TLSR_SWire_Flasher/`).
- **`pvvx/TLSRPGM`** (https://github.com/pvvx/TLSRPGM): Hardware interface architecture and `TLSR8269` SWire programmer reference.
- **`openscopeproject/InteractiveHtmlBom`** (https://github.com/openscopeproject/InteractiveHtmlBom): Interactive HTML BOM viewer used to generate [ibom.html](ibom.html).
