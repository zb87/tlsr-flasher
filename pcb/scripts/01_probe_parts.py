#!/usr/bin/env python3
"""Probe exact symbol pin/bbox/designator geometry and PCB footprint pad geometry
for all unique System Library devices used in tlsr-flasher.
Saves results to design-data/probe_bundle.json and clears probe sheets.
"""
from __future__ import annotations
import json
import os
import subprocess

PROJECT = "f91760ddb2c7418299e7752f330a761d"
P1_UUID = "48f86e153a22ba1c"
PCB_UUID = "3c00dcf5bcf1cf37"
SYS_LIB = "0819f05c4eef4c71ace90d822a990e87"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "design-data")
os.makedirs(DATA_DIR, exist_ok=True)
OUT_PATH = os.path.join(DATA_DIR, "probe_bundle.json")

# Unique parts: sampleKey -> (libraryUuid, deviceUuid, role, check_pcb_fp)
UNIQUE_PARTS: dict[str, tuple[str, str, str, bool]] = {
    "E180":     (SYS_LIB, "cbb003c3987643819c5e2cec9988e2cb", "mcu",       True),  # E180-Z6907A (C518909)
    "USBC":     (SYS_LIB, "b4de8f0f4a564327b51be4d1ed6f4b35", "connector", True),  # TYPE-C16PIN (C393939)
    "SRV05":    (SYS_LIB, "e5f3360875a64a2d97d70eeb098b223a", "diode",     True),  # SRV05-4 ESD (C384887)
    "PTC_1A5":  (SYS_LIB, "05cd847d1763435a86da8096499ba2c9", "fuse",      True),  # BSMD1206-150-6V (C883132)
    "AP63203":  (SYS_LIB, "e25f0d003ec44bd1987511a4c8ea23ad", "regulator", True),  # AP63203WU-7 (C780769)
    "L_3U9":    (SYS_LIB, "c311b6fc417b435394069573712ed6b5", "inductor",  True),  # SWPA4030S3R9MT (C96899)
    "AO3401A":  (SYS_LIB, "c9c0d5c4c0f842539abe3355695d746d", "mosfet",    True),  # AO3401A (C700954)
    "S8050":    (SYS_LIB, "f714063fa18048f2956344f6558686ce", "bjt",       True),  # S8050 (C20069125)
    "SW_RST":   (SYS_LIB, "74bd52f1120e4bee9df6a4e8c1f72428", "switch",    True),  # TS-1088R-02526 (C455281)
    "HDR_5P":   (SYS_LIB, "a39f9c9126e24625a6e7edb3fdff00c6", "connector", True),  # PZ254V-11-05P (C492404)
    "HDR_4P":   (SYS_LIB, "9b540f58c6ad4e26b03d1a299cfb1108", "connector", True),  # PZ254V-11-04P (C2691448)
    "LED_RED":  (SYS_LIB, "7d938e3f05d04ef7abb058b22e337109", "led",       True),  # NCD0603R1 (C84263)
    "LED_GRN":  (SYS_LIB, "ffec3f6d6d7645debd8e107be396b5f1", "led",       True),  # NCD0603C1 (C84264)
    "C_100N":   (SYS_LIB, "b470d7af3c48415db6a4748fa8e62805", "capacitor", True),  # 100nF 50V 0603 (C48579281)
    "C_10U":    (SYS_LIB, "345d8669720442d6a8747f19c9226485", "capacitor", False), # 10uF 16V 0603 (C7472959)
    "C_22U":    (SYS_LIB, "78c549e435f745ff89f256a309aff34c", "capacitor", False), # 22uF 10V 0603 (C7432770)
    "R_33R":    (SYS_LIB, "8880fde5f6d4473582cf920ed09a09aa", "resistor",  True),  # 33R 0603 (C2909394)
    "R_2K2":    (SYS_LIB, "f24a8f70db714104b387f51f08abca40", "resistor",  False), # 2.2k 0603 (C2907005)
    "R_4K7":    (SYS_LIB, "f564766cebdf4a748137af6d281a33c8", "resistor",  False), # 4.7k 0603 (C2907034)
    "R_5K1":    (SYS_LIB, "7f73bc9b909b4d519d5499acdd443b44", "resistor",  False), # 5.1k 0603 (C2907044)
    "R_10K":    (SYS_LIB, "7d0a4241f13846d38eb1c0e45cc6ecf8", "resistor",  False), # 10k 0603 (C2906982)
    "R_47K":    (SYS_LIB, "560477ba21ea4ffb9f5ac912d0dd396c", "resistor",  False), # 47k 0603 (C2907042)
    "R_100K":   (SYS_LIB, "a8ced70c90564625b1939eaf737576ef", "resistor",  False), # 100k 0603 (C2906980)
}


def cli(args: list[str], parse_json: bool = True):
    p = subprocess.run(["easyeda"] + args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(args)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")
    return json.loads(p.stdout) if parse_json else p.stdout


def main() -> None:
    # 1. Open P1 and extract exact sheet geometry via SVG
    cli(["doc", "open", P1_UUID, "--project", PROJECT], parse_json=False)
    win = cli(["project", "info", "--project", PROJECT])["windowId"]
    svg_path = os.path.join(DATA_DIR, "sheet_before.svg")
    cli([
        "sch", "export-image", "--scope", "page", "--format", "svg",
        "--page", P1_UUID, "--project", PROJECT, "--window", win, "--out", svg_path,
    ], parse_json=False)
    sheet_exact = cli(["sch", "sheet-geometry", "--from-svg", svg_path, "--json"])["result"]
    print("✓ Sheet exact geometry:", json.dumps(sheet_exact["sheet"]), flush=True)

    # 2. Check if P1 already has PRB1..PRB23 from prior run, otherwise place them
    probe_map = {
        f"PRB{idx}": {"sampleKey": skey, "libraryUuid": lib_u, "uuid": dev_u, "role": role}
        for idx, (skey, (lib_u, dev_u, role, _)) in enumerate(UNIQUE_PARTS.items(), start=1)
    }
    pre_snap = cli([
        "sch", "list", "--project", PROJECT, "--doc", P1_UUID,
        "--include-device-identity", "--include-pins", "--include-bbox",
        "--include-wires", "--include-page-primitives",
    ])["result"]
    existing_des = {c["designator"] for c in pre_snap["components"] if c.get("componentType") == "part"}
    if existing_des != set(probe_map.keys()):
        cli(["sch", "clear", "--project", PROJECT, "--doc", P1_UUID], parse_json=False)
        for idx, (skey, (lib_u, dev_u, role, _)) in enumerate(UNIQUE_PARTS.items(), start=1):
            des = f"PRB{idx}"
            gx = 150 + ((idx - 1) % 6) * 180
            gy = 720 - ((idx - 1) // 6) * 160
            cli([
                "sch", "place", "--project", PROJECT, "--doc", P1_UUID,
                "--lib", lib_u, "--uuid", dev_u,
                "--x", str(gx), "--y", str(gy), "--rotation", "0",
                "--designator", des,
            ], parse_json=False)
        sch_snap = cli([
            "sch", "list", "--project", PROJECT, "--doc", P1_UUID,
            "--include-device-identity", "--include-pins", "--include-bbox",
            "--include-wires", "--include-page-primitives",
        ])["result"]
    else:
        print("✓ Reusing already-placed PRB1..PRB23 on P1!", flush=True)
        sch_snap = pre_snap

    des_geom = cli(["sch", "designator-geometry", "--project", PROJECT, "--doc", P1_UUID])
    cli(["sch", "clear", "--project", PROJECT, "--doc", P1_UUID], parse_json=False)
    cli(["sch", "save", "--project", PROJECT, "--doc", P1_UUID], parse_json=False)

    # 3. Probe PCB footprints on PCB1 at rotation=0
    cli(["doc", "open", PCB_UUID, "--project", PROJECT], parse_json=False)
    cli(["pcb", "clear", "--project", PROJECT, "--doc", PCB_UUID], parse_json=False)
    pcb_items = [(k, v) for k, v in UNIQUE_PARTS.items() if v[3]]
    for idx, (skey, (lib_u, dev_u, role, _)) in enumerate(pcb_items, start=1):
        cli([
            "pcb", "add-component", "--project", PROJECT, "--doc", PCB_UUID,
            "--library", lib_u, "--uuid", dev_u,
            "--x", str(400 + ((idx - 1) % 4) * 800),
            "--y", str(400 + ((idx - 1) // 4) * 700),
            "--rotation", "0", "--designator", f"FP_{skey}",
            "--unique-id", f"prb_{idx}", "--nets", "{}",
        ], parse_json=False)

    pcb_snap = cli([
        "pcb", "list", "--include-bbox", "--include-pads",
        "--project", PROJECT, "--doc", PCB_UUID,
    ])["result"]["components"]
    cli(["pcb", "clear", "--project", PROJECT, "--doc", PCB_UUID], parse_json=False)
    cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_UUID], parse_json=False)

    bundle = {
        "projectUuid": PROJECT,
        "p1Uuid": P1_UUID,
        "pcbUuid": PCB_UUID,
        "sheetExact": sheet_exact,
        "probeMap": probe_map,
        "schList": sch_snap,
        "designators": des_geom,
        "pcbFootprints": pcb_snap,
    }
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(bundle, f, ensure_ascii=False, indent=2)

    print("\n=== PROBED SCHEMATIC PINS ===")
    for c in sch_snap["components"]:
        if c.get("componentType") != "part":
            continue
        des = c["designator"]
        skey = probe_map[des]["sampleKey"]
        pins = [(p["pinNumber"], p["pinName"], round(p["x"] - c["x"], 2), round(p["y"] - c["y"], 2)) for p in c["pins"]]
        print(f"  {skey:10s} ({des}): bbox={c['bbox']} pins={pins}")

    print("\n=== PROBED PCB FOOTPRINTS (0 deg) ===")
    for fc in pcb_snap:
        pads = [(p["padNumber"], p["layer"], round(p["x"] - fc["x"], 2), round(p["y"] - fc["y"], 2), p.get("shape"), p.get("hole")) for p in fc.get("pads", [])]
        print(f"  {fc['designator']:14s}: bbox={fc['bbox']} anchor=({fc['x']},{fc['y']}) pads={pads}")

    print(f"\n✓ Saved {OUT_PATH}", flush=True)


if __name__ == "__main__":
    main()
