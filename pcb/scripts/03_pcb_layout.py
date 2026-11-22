#!/usr/bin/env python3
"""Stage 3: Import netlist to PCB (without --sync-attrs), configure 47.00 x 26.00 mm
rounded-rect outline + 2 diagonal M2 mounting holes (TL/BR), place ALL 33 components
on Top Layer (Single-Sided Assembly), create U1's North 2.4GHz antenna no-copper
keepout, add crisp Top/Bottom silkscreen labels, position all 33 designators in
<=4-ID batches, and verify zero-drift across 2 save->reload->readback rounds.
"""
from __future__ import annotations
import json
import math
import os
import subprocess

PROJECT = "f91760ddb2c7418299e7752f330a761d"
SCHEMATIC_UUID = "936a419812a202bd"
PCB_DOC = "3c00dcf5bcf1cf37"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "design-data")
PRECHECK = "/home/zb/code/esp32-prototype/.agents/skills/easyeda-pcb-learnings/scripts/pcb-drc-precheck.py"

# 47.00 mm x 26.00 mm (R = 1.8 mm corners, 1222 mm^2)
BOARD_W_MIL = 1850.394
BOARD_H_MIL = 1023.622
CORNER_R_MIL = 70.87

# 2x Diagonal M2 mounting holes at TL & BR (Ø2.2 mm = 86.6 mil, 2.8 mm = 110.2 mil inset)
MH_DIA_MIL = 86.6
MH_INSET_MIL = 110.2

# ALL 33 components on Top Layer ("top" = layer 1): (x_mil, y_mil, rot_deg, layer_str)
PLACEMENTS: dict[str, tuple[float, float, float, str]] = {
    # 1. USB-C Receptacle (West edge, flush lip) & Protection / ESD / CC / 22R
    "USB1": (185.0,  532.0, 270, "top"),
    "F1":   (325.0,  935.0,   0, "top"),
    "R3":   (240.0,  290.0,   0, "top"),
    "R4":   (240.0,  208.0,   0, "top"),
    "D1":   (445.0,  475.0, 180, "top"),
    "R1":   (582.0,  515.0,  90, "top"),
    "R2":   (582.0,  375.0,  90, "top"),

    # 2. AP63203WU-7 3.3V 2A Synchronous Buck + 5V Indicator (North-Center)
    "C1":   (460.0,  738.0,  90, "top"),  # <= 180 mil from U2.3 (+5V)
    "C2":   (555.0,  738.0,  90, "top"),  # <= 90 mil from U2.3 (+5V)
    "U2":   (685.0,  775.0, 270, "top"),
    "C3":   (685.0,  935.0,   0, "top"),  # BST 100nF right North of U2.6/5
    "L1":   (875.0,  775.0,   0, "top"),
    "C4":   (855.0,  945.0,   0, "top"),  # 22uF OUT #1
    "C5":   (1008.0, 943.0,  90, "top"),  # 22uF OUT #2
    "LED1": (515.0,  950.0,   0, "top"),
    "R5":   (515.0,  862.0,   0, "top"),

    # 3. Manual nRESET & RC Network + Self-Prog 1x4P Header H2 (South-West)
    "SW1":  (185.0,   88.0,   0, "top"),
    "C9":   (385.0,  150.0,   0, "top"),
    "R6":   (385.0,   65.0,   0, "top"),
    "H2":   (695.0,   95.0, 180, "top"),

    # 4. Target Switched PWR (Q2 MMBT3904 + Q1 AO3401A) & U1 3V3 Decoupling (Center)
    "R8":   (695.0,  560.0,   0, "top"),
    "R9":   (695.0,  470.0,   0, "top"),
    "Q2":   (838.0,  560.0, 180, "top"),
    "R7":   (838.0,  435.0,   0, "top"),
    "Q1":   (985.0,  595.0, 180, "top"),
    "C10":  (985.0,  465.0,   0, "top"),
    "C6":   (1000.0, 325.0,  90, "top"),
    "C7":   (1000.0, 150.0,  90, "top"),
    "C8":   (910.0,  275.0,  90, "top"),

    # 5. E180-Z6907A Core Module (Center-East, antenna pointing North)
    "U1":   (1355.0, 430.0, 180, "top"),

    # 6. Target SWire 1x5P Header H1 + PWR LED2 (Far-East)
    "H1":   (1765.0, 715.0, 270, "top"),
    "LED2": (1745.0, 385.0,   0, "top"),
    "R10":  (1745.0, 300.0,   0, "top"),
}

# Upright Top-Silkscreen (Layer 3) designator anchors
DESIGNATOR_COORDS: dict[str, tuple[float, float]] = {
    "USB1": ( 45.0,  748.0),
    "F1":   (295.0,  848.0),
    "R3":   (105.0,  280.0),
    "R4":   (306.0,  196.0),
    "D1":   (415.0,  560.0),
    "R1":   (555.0,  582.0),
    "R2":   (512.0,  315.0),

    "C1":   (438.0,  642.0),
    "C2":   (532.0,  642.0),
    "U2":   (660.0,  672.0),
    "C3":   (752.0,  935.0),
    "L1":   (870.0,  654.0),
    "C4":   (835.0,  872.0),
    "C5":   (928.0,  930.0),
    "LED1": (582.0,  848.0),
    "R5":   (378.0,  848.0),

    "SW1":  (150.0,  146.0),
    "C9":   (454.0,  140.0),
    "R6":   (454.0,   54.0),
    "H2":   (412.0,  192.0),

    "R8":   (672.0,  600.0),
    "R9":   (672.0,  405.0),
    "Q2":   (782.0,  628.0),
    "R7":   (815.0,  368.0),
    "Q1":   (965.0,  666.0),
    "C10":  (945.0,  392.0),
    "C6":   (1042.0, 315.0),
    "C7":   (1042.0, 140.0),
    "C8":   (835.0,  265.0),

    "U1":   (1330.0,  52.0),
    "LED2": (1712.0, 422.0),
    "R10":  (1628.0, 290.0),
    "H1":   (1655.0, 962.0),
}


def cli(args: list[str], parse_json: bool = False, check: bool = True):
    p = subprocess.run(["easyeda"] + args, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(args)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")
    if not check:
        return p
    return json.loads(p.stdout) if parse_json else p.stdout


def verify_placement(d: dict, label: str) -> None:
    comps = d["components"]
    assert len(comps) == len(PLACEMENTS), f"[{label}] Expected {len(PLACEMENTS)} components, got {len(comps)}"
    by_ref = {c["designator"]: c for c in comps}
    assert set(by_ref.keys()) == set(PLACEMENTS.keys())

    for ref, (tx, ty, trot, _) in PLACEMENTS.items():
        c = by_ref[ref]
        assert c["layer"] == 1, f"[{label}] SINGLE-SIDED VIOLATION: {ref} is on layer {c['layer']}, expected 1 (Top)!"
        assert math.hypot(c["x"] - tx, c["y"] - ty) < 0.25, f"[{label}] {ref} pos drift: ({c['x']},{c['y']}) vs ({tx},{ty})"

    # Verify USB1 opens West (SMD pads East of USB1 anchor) and U1 antenna points North
    usb_pads = {p["padNumber"]: p for p in by_ref["USB1"]["pads"]}
    assert usb_pads["A6"]["x"] > by_ref["USB1"]["x"], f"USB1 rotation wrong! A6.x={usb_pads['A6']['x']} <= USB1.x={by_ref['USB1']['x']}"
    assert by_ref["U1"]["bbox"]["maxY"] > by_ref["U1"]["y"] + 450, f"U1 antenna not pointing North! bbox={by_ref['U1']['bbox']}"

    # Pairwise 2D component envelope gap >= 20.0 mil across all 33 parts
    small = []
    for i in range(len(comps)):
        for j in range(i + 1, len(comps)):
            a, b = comps[i], comps[j]
            ba, bb = a["bbox"], b["bbox"]
            dx = max(0.0, ba["minX"] - bb["maxX"], bb["minX"] - ba["maxX"])
            dy = max(0.0, ba["minY"] - bb["maxY"], bb["minY"] - ba["maxY"])
            gap = math.hypot(dx, dy)
            if gap < 20.0:
                small.append((a["designator"], b["designator"], round(gap, 2)))
    print(f"[{label}] Pairwise component gaps < 20 mil: {small}", flush=True)
    assert not small, f"[{label}] Tight component pair(s): {small}"


def main() -> None:
    cli(["doc", "open", PCB_DOC, "--project", PROJECT])

    # 1. Import schematic netlist if PCB does not yet have all 33 parts (NEVER pass --sync-attrs)
    cur_comps = cli(["pcb", "list", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)["result"].get("components", [])
    if len(cur_comps) != len(PLACEMENTS):
        cli(["pcb", "import-changes", "--project", PROJECT, "--doc", PCB_DOC, "--schematic", SCHEMATIC_UUID])
        sv_imp = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
        assert sv_imp.get("result", {}).get("saved") is True
        cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])

    show_args = []
    for lid in range(1, 14):
        show_args += ["--show", str(lid)]
    cli(["pcb", "layer-visibility"] + show_args + ["--project", PROJECT, "--doc", PCB_DOC])

    # 2. Set rounded-rect board outline 47.00 x 26.00 mm (R = 1.8 mm) + 2 diagonal M2 holes
    cli(["pcb", "lock", "--all", "--unlock", "--project", PROJECT, "--doc", PCB_DOC])
    cli([
        "pcb", "outline-round",
        "--rect", f"0,0,{BOARD_W_MIL:.3f},{BOARD_H_MIL:.3f}",
        "--radius", f"{CORNER_R_MIL:.2f}",
        "--project", PROJECT, "--doc", PCB_DOC,
    ])
    # Clear old regions & layer-12 mounting-hole slots before re-milling
    regs = cli(["pcb", "region", "list", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)["result"].get("regions", [])
    if regs:
        cli(["pcb", "region", "delete", "--ids", ",".join(r["primitiveId"] for r in regs), "--project", PROJECT, "--doc", PCB_DOC])
    fills12 = cli(["pcb", "fill", "list", "--layer", "12", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)["result"].get("fills", [])
    if fills12:
        cli(["pcb", "fill", "delete", "--ids", ",".join(fl["primitiveId"] for fl in fills12), "--project", PROJECT, "--doc", PCB_DOC])
    cli([
        "pcb", "mount-holes",
        "--dia", f"{MH_DIA_MIL:.1f}",
        "--inset", f"{MH_INSET_MIL:.1f}",
        "--corners", "tl,br",
        "--project", PROJECT, "--doc", PCB_DOC,
    ])
    print("✓ Configured 47.00 x 26.00 mm rounded outline + 2 diagonal M2 holes!", flush=True)

    # 3. Place all 33 parts deterministically on Top Layer (layer = 1)
    comps = cli(["pcb", "list", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)["result"]["components"]
    by_ref = {c["designator"]: c for c in comps}
    assert set(by_ref.keys()) == set(PLACEMENTS.keys()), f"Ref mismatch: {set(by_ref.keys()) ^ set(PLACEMENTS.keys())}"

    for ref, (tx, ty, trot, tlay) in PLACEMENTS.items():
        patch = json.dumps({"x": tx, "y": ty, "rotation": trot, "layer": tlay})
        cli(["pcb", "modify", "--project", PROJECT, "--doc", PCB_DOC, "--id", by_ref[ref]["primitiveId"], "--patch", patch])

    # Lock edge connectors & module so autoroute doesn't nudge them
    cli(["pcb", "lock", "--project", PROJECT, "--doc", PCB_DOC,
         "--ids", f"{by_ref['USB1']['primitiveId']},{by_ref['U1']['primitiveId']},{by_ref['H1']['primitiveId']},{by_ref['H2']['primitiveId']}"])
    print("✓ Placed all 33 components on Top Layer (Single-Sided)!", flush=True)

    # 4. Create locked Top & Bottom no-copper keepout under U1's North 2.4GHz antenna (Y = [1085 .. 1338.6])
    for lyr in (1, 2):
        cli([
            "pcb", "region", "create",
            "--layer", str(lyr),
            "--rect", "1075,770,1620,1023",
            "--rule", "no-wires", "--rule", "no-fills", "--rule", "no-pours",
            "--locked",
            "--project", PROJECT, "--doc", PCB_DOC,
        ])
    print("✓ Created Top & Bottom 2.4GHz antenna no-copper keepout [1075..1620, 770..1023]!", flush=True)

    # 5. Clear free silk strings and add clean Top (Layer 3) & Bottom (Layer 4) labels
    cli(["pcb", "clear", "--only", "silk", "--no-verify", "--project", PROJECT, "--doc", PCB_DOC])

    # Re-read placed pads for H1 and H2 so pin labels align right next to their exact pads
    comps_now = {c["designator"]: c for c in cli(["pcb", "list", "--include-pads", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)["result"]["components"]}
    h1_pads = {p["padNumber"]: p for p in comps_now["H1"]["pads"]}
    h2_pads = {p["padNumber"]: p for p in comps_now["H2"]["pads"]}

    h1_names = {"1": "GND", "2": "PWR", "3": "3V3", "4": "SWM", "5": "RST"}
    h2_names = {"1": "GND", "2": "3V3", "3": "SWS", "4": "RST"}

    TOP_FREE_SILK = [
        ("USB-C 5V",   35.0,  425.0, 22, 5, "Arial"),
        ("5V",        230.0,  848.0, 20, 5, "Arial"),
        ("nRST",       26.0,  180.0, 20, 5, "Arial"),
        ("SELF PROG", 605.0,  212.0, 20, 5, "Arial"),
        ("TARGET",   1622.0,  462.0, 20, 5, "Arial"),
    ]
    # H1 vertical labels just West of H1 pads (H1 minX ~ 1710, U1 maxX ~ 1605 -> 1652 sits cleanly between them)
    for pnum, lbl in h1_names.items():
        py = h1_pads[pnum]["y"] - 12.0
        TOP_FREE_SILK.append((lbl, 1652.0, py, 20, 5, "Arial"))

    # H2 horizontal labels just North of H2 pads (H2 maxY ~ 150)
    for pnum, lbl in h2_names.items():
        px = h2_pads[pnum]["x"] - 16.0
        TOP_FREE_SILK.append((lbl, px, 168.0, 20, 5, "Arial"))

    for txt, sx, sy, fsz, lw, ff in TOP_FREE_SILK:
        cli([
            "pcb", "silk-add",
            "--text", txt, "--x", f"{sx:.2f}", "--y", f"{sy:.2f}",
            "--font-family", ff, "--font-size", str(fsz), "--line-width", str(lw), "--layer", "3",
            "--project", PROJECT, "--doc", PCB_DOC,
        ])

    # Bottom Layer 4 board badge + duplicate H1/H2 pinout guide (flat bottom assembly)
    BOT_FREE_SILK = [
        ("TLSR SWire Flasher V1.1 (Single-Sided Top)", 1490.0, 820.0, 30, 5, "Arial"),
        ("E180-Z6907A + AP63203WU-7 | 47x26mm", 1450.0, 740.0, 26, 5, "Arial"),
        ("Target 1x5P: 1=GND 2=PWR 3=3V3 4=SWM 5=EXT_RST", 1540.0, 520.0, 24, 5, "Arial"),
        ("Self-Prog 1x4P: 1=GND 2=3V3 3=SWS 4=RST", 1500.0, 320.0, 24, 5, "Arial"),
    ]
    for txt, sx, sy, fsz, lw, ff in BOT_FREE_SILK:
        cli([
            "pcb", "silk-add",
            "--text", txt, "--x", f"{sx:.2f}", "--y", f"{sy:.2f}",
            "--font-family", ff, "--font-size", str(fsz), "--line-width", str(lw), "--layer", "4",
            "--project", PROJECT, "--doc", PCB_DOC,
        ])
    print("✓ Added Top & Bottom silkscreen labels!", flush=True)

    s0 = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
    assert s0.get("result", {}).get("saved") is True
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])

    mid_dump = os.path.join(DATA_DIR, "pcb_mid_placement_dump.json")
    cli(["pcb", "dump", "--project", PROJECT, "--doc", PCB_DOC, "--out", mid_dump])
    d_mid = json.load(open(mid_dump, encoding="utf-8"))

    des_items = [s for s in d_mid["silk"] if s.get("Kind") == "attribute" and s.get("Key") == "Designator"]
    assert len(des_items) == len(PLACEMENTS), f"Expected {len(PLACEMENTS)} designators, got {len(des_items)}"
    des_ids = [s["ID"] for s in des_items]
    for k in range(0, len(des_ids), 4):
        batch = ",".join(des_ids[k:k + 4])
        cli([
            "pcb", "silk-set", "--ids", batch,
            "--font-family", "Arial", "--font-size", "30", "--line-width", "5",
            "--rotation", "0", "--mirror=false", "--reverse=false",
            "--project", PROJECT, "--doc", PCB_DOC,
        ])

    for s_item in des_items:
        ref = s_item["Text"]
        pid = s_item["ID"]
        tx, ty = DESIGNATOR_COORDS[ref]
        cli([
            "pcb", "silk-set", "--ids", pid,
            "--x", f"{tx:.2f}", "--y", f"{ty:.2f}", "--rotation", "0",
            "--project", PROJECT, "--doc", PCB_DOC,
        ])
    print("✓ Positioned all 33 upright designators in <=4-ID batches!", flush=True)

    # ==================== ROUND 1 (layout_r1) ====================
    s1 = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
    assert s1.get("result", {}).get("saved") is True
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "layer-visibility"] + show_args + ["--project", PROJECT, "--doc", PCB_DOC])

    r1_dump = os.path.join(DATA_DIR, "pcb_layout_r1_dump.json")
    cli(["pcb", "dump", "--include-copper", "--project", PROJECT, "--doc", PCB_DOC, "--out", r1_dump])
    d1 = json.load(open(r1_dump, encoding="utf-8"))
    verify_placement(d1, "layout_r1")

    pre = subprocess.run(["python3", PRECHECK, "--board", r1_dump], capture_output=True, text=True)
    print(pre.stdout, flush=True)
    assert pre.returncode == 0, f"Offline precheck failed:\n{pre.stdout}\n{pre.stderr}"

    r1_lint = cli(["pcb", "layout-lint", "--project", PROJECT, "--doc", PCB_DOC], check=False)
    print("[layout_r1] layout-lint:\n" + "\n".join(r1_lint.stdout.splitlines()[:6]), flush=True)
    assert "0 short, 0 overlap, 0 off-board, 0 tight" in r1_lint.stdout, r1_lint.stdout

    r1_chk = cli(["pcb", "check", "--project", PROJECT, "--doc", PCB_DOC], check=False)
    print("[layout_r1] pcb check:\n" + "\n".join(r1_chk.stdout.splitlines()[:10]), flush=True)
    assert (
        "ERROR=0" in r1_chk.stdout
        and "silkOverPad=0" in r1_chk.stdout
        and "silkOffBoard=0" in r1_chk.stdout
        and "silkFlipped=0" in r1_chk.stdout
    ), r1_chk.stdout

    # ==================== ROUND 2 (layout_r2) ====================
    s2 = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
    assert s2.get("result", {}).get("saved") is True
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "layer-visibility"] + show_args + ["--project", PROJECT, "--doc", PCB_DOC])

    r2_dump = os.path.join(DATA_DIR, "pcb_layout_r2_dump.json")
    cli(["pcb", "dump", "--include-copper", "--project", PROJECT, "--doc", PCB_DOC, "--out", r2_dump])
    d2 = json.load(open(r2_dump, encoding="utf-8"))
    verify_placement(d2, "layout_r2")
    assert d1.get("semanticSha256") == d2.get("semanticSha256"), "Semantic drift across layout R1->R2!"
    print(f"✓ TWO-ROUND PLACEMENT VERIFIED! semanticSha256={d2.get('semanticSha256')}", flush=True)


if __name__ == "__main__":
    main()
