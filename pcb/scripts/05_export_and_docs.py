#!/usr/bin/env python3
"""Stage 5: Official Manufacturing Exports, Single-Sided PnP Verification, BOM,
Live Native Viewport Captures, 2D Routed Blueprint, and 3D Isometric Renders.

Outputs under pcb/:
  - fab/TLSR_Flasher_Gerber.zip
  - fab/TLSR_Flasher_PickAndPlace_mm.csv   (asserted 100% Top-Layer single-sided)
  - fab/TLSR_Flasher_BOM.csv               (33 components mapped to LCSC + inventory)
  - design-data/tlsr-flasher.epro2
  - design-data/routing_report.json
  - design-data/board_3d_model_obj/board.obj.zip
  - images/pcb_top_routed.png
  - images/pcb_bottom_routed.png
  - images/pcb_routed_2d.png
  - images/pcb_3d_top_bottom.png
"""
from __future__ import annotations
import csv
import json
import os
import shutil
import subprocess
import zipfile
from PIL import Image, ImageDraw, ImageFont

PROJECT = "tlsr-flasher"
PROJ_UUID = "f91760ddb2c7418299e7752f330a761d"
PCB_DOC = "3c00dcf5bcf1cf37"
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(OUT_DIR, "design-data")
FAB_DIR = os.path.join(OUT_DIR, "fab")
IMG_DIR = os.path.join(OUT_DIR, "images")
STAGE_DIR = os.path.join(DATA_DIR, "stages")
RENDER_3D = "/home/zb/code/esp32-prototype/.agents/skills/easyeda-pcb-learnings/scripts/render-3d-obj.py"

W_MIL = 1850.394
H_MIL = 1023.622
CORNER_R = 70.87
INSET = 20.0
CHAMFER = 50.0

BOM_ROWS = [
    ("U1",       1, "E180-Z6907A (Telink TLSR8269 Zigbee/2.4GHz SoC Module)", "E180-Z6907A",     "Stamp-SMD-37P",       "C518909",   "Top", "Stocked (2 pcs, parts_inventory.md)", "User-supplied / hand-soldered module; North antenna keepout"),
    ("U2",       1, "AP63203WU-7 (3.8-32V in, 3.3V fixed 2A Sync Buck)",     "AP63203WU-7",     "TSOT-23-6",           "C780769",   "Top", "Stocked (15 pcs, parts_inventory.md)", "Replaces RT9013 LDO for e-paper / high-current bursts"),
    ("L1",       1, "3.9uH +-20% 3A Shielded Power Inductor",                "SWPA4030S3R9MT",  "SMD 4030 (4x4mm)",    "C96899",    "Top", "Stocked (14 pcs, parts_inventory.md)", "Paired with AP63203WU-7 (pin-adjacent 35 mil SW bridge)"),
    ("Q1",       1, "AO3401A P-Channel MOSFET (-30V, -4.2A, 54mOhm)",        "AO3401A",         "SOT-23-3",            "C700954",   "Top", "Stocked (20 pcs, parts_inventory.md)", "Target PWR high-side switch controlled via Q2/PWR_EN"),
    ("Q2",       1, "S8050 NPN BJT (25V, 0.5A, hFE 200-350)",                "S8050",           "SOT-23-3",            "C20069125", "Top", "Stocked (50 pcs, parts_inventory.md)", "Active-HIGH level shifter from PC4 (PWR_EN) to Q1 gate"),
    ("D1",       1, "SRV05-4 Low-Capacitance USB ESD Protection Array",      "SRV05-4",         "SOT-23-6",            "C384887",   "Top", "Order (LCSC)",                        "Protects USB_DP, USB_DN, +5V rail"),
    ("F1",       1, "1.5A 6V Resettable PTC Polyfuse",                       "BSMD1206-150-6V", "1206",                "C883132",   "Top", "Order (LCSC)",                        "Input overcurrent protection between VBUS_RAW and +5V"),
    ("USB1",     1, "USB Type-C 16P 2.0 Receptacle",                         "TYPE-C16PIN",     "SMD 16P + 4 TH Tabs", "C393939",   "Top", "Stocked (30 pcs, parts_inventory.md)", "West board edge; SH1<->3 & SH2<->4 L2 bridged"),
    ("SW1",      1, "TS-1088R-02526 Side-Actuated Micro Push Button",        "TS-1088R-02526",  "SMD 4x3mm",           "C455281",   "Top", "Stocked (50 pcs, parts_inventory.md)", "Manual TLSR8269 nRESET trigger on South-West edge"),
    ("LED1",     1, "Red SMD Indicator LED (+5V Rail)",                      "NCD0603R1",       "0603",                "C84263",    "Top", "Stocked (50 pcs, parts_inventory.md)", "+5V input power indicator via R5 (4.7k)"),
    ("LED2",     1, "Yellow-Green SMD Indicator LED (Switched Target PWR)",  "NCD0603C1",       "0603",                "C84264",    "Top", "Stocked (50 pcs, parts_inventory.md)", "Switched Target PWR active indicator via R10 (2.2k)"),
    ("C1,C7",    2, "10uF 16V X5R 0603 MLCC Capacitor",                      "HGC0603R5106M160NTHJ", "0603",                "C7472959",  "Top", "Stocked (20 pcs, parts_inventory.md)", "C1 = AP63203 VIN bulk; C7 = E180 VDD bulk"),
    ("C4,C5",    2, "22uF 10V X5R 0603 MLCC Capacitor",                      "HGC0603R5226M100NTHJ", "0603",                "C7432770",  "Top", "Stocked (100 pcs, parts_inventory.md)","2x 22uF AP63203 3V3 buck output filter bank"),
    ("C2,C3,C6,C8,C9,C10", 6, "100nF 50V X7R 0603 MLCC Capacitor",           "0603X7R104K500NT", "0603",            "C48579281", "Top", "Stocked (300 pcs, parts_inventory.md)","HF bypass (U2 VIN/BST/3V3, U1 VDD, nRESET RC, Q1 gate RC)"),
    ("R1,R2",    2, "33 Ohm +-1% 0603 Resistor",                             "FRC0603F33R0TS",  "0603",                "C2909394",  "Top", "Stocked (0603 Resistor Sample Book)", "USB D-/D+ series impedance damping resistors"),
    ("R3,R4",    2, "5.1k Ohm +-1% 0603 Resistor",                           "FRC0603F5101TS",  "0603",                "C2907044",  "Top", "Stocked (300 pcs, parts_inventory.md)","USB-C CC1 & CC2 5V Rd sink pull-downs"),
    ("R5",       1, "4.7k Ohm +-1% 0603 Resistor",                           "FRC0603F4701TS",  "0603",                "C2907034",  "Top", "Stocked (300 pcs, parts_inventory.md)","LED1 (+5V Red) current limiting resistor"),
    ("R6,R8",    2, "10k Ohm +-1% 0603 Resistor",                            "FRC0603F1002TS",  "0603",                "C2906982",  "Top", "Stocked (300 pcs, parts_inventory.md)","R6 = nRESET RC pull-up; R8 = PWR_EN -> Q2 base drive"),
    ("R7",       1, "47k Ohm +-1% 0603 Resistor",                            "FRC0603F4702TS",  "0603",                "C2907042",  "Top", "Stocked (100 pcs, parts_inventory.md)","Q1 AO3401A VGS gate pull-up to 3V3 (Default OFF)"),
    ("R9",       1, "100k Ohm +-1% 0603 Resistor",                           "FRC0603F1003TS",  "0603",                "C2906980",  "Top", "Stocked (200 pcs, parts_inventory.md)","Q2 base pull-down to GND (prevents floating boot glitch)"),
    ("R10",      1, "2.2k Ohm +-1% 0603 Resistor",                           "FRC0603F2201TS",  "0603",                "C2907005",  "Top", "Stocked (100 pcs, parts_inventory.md)","LED2 (PWR Green) current limiting resistor"),
    ("H1",       1, "1x5P 2.54mm Male Pin Header (Target SWire)",            "PZ254V-11-05P",   "HDR-TH 1x5P P2.54mm", "C492404",   "Top", "Standard 2.54mm header / LCSC",        "East edge: 1:GND, 2:PWR, 3:3V3, 4:SWM (no PU), 5:EXT_RST"),
    ("H2",       1, "1x4P 2.54mm Male Pin Header (Self-Program)",            "PZ254V-11-04P",   "HDR-TH 1x4P P2.54mm", "C2691448",  "Top", "Standard 2.54mm header / LCSC",        "South edge: 1:GND, 2:3V3, 3:SWS, 4:RST"),
]


def cli(args: list[str], parse_json: bool = False, check: bool = True):
    p = subprocess.run(["easyeda"] + args, capture_output=True, text=True)
    if check and p.returncode != 0:
        raise RuntimeError(
            f"Command failed ({p.returncode}): {' '.join(args)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}"
        )
    if not check:
        return p
    return json.loads(p.stdout) if parse_json else p.stdout


def find_font(size: int) -> ImageFont.ImageFont:
    for p in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ):
        if os.path.exists(p):
            return ImageFont.truetype(p, size=size)
    return ImageFont.load_default()


def write_bom(out_csv: str) -> None:
    os.makedirs(os.path.dirname(out_csv), exist_ok=True)
    with open(out_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Designators", "Qty", "Value_Description", "ManufacturerPart", "Footprint", "LCSC_Part", "Side", "Source_Status", "Notes"])
        for row in BOM_ROWS:
            w.writerow(row)
    assert sum(r[1] for r in BOM_ROWS) == 33, f"Expected 33 parts, got {sum(r[1] for r in BOM_ROWS)}"
    print(f"✓ Wrote 33-component BOM ({len(BOM_ROWS)} unique lines): {out_csv}")


def render_routed_2d(dump: dict, out_png: str) -> None:
    W, H = 1920, 920
    img = Image.new("RGB", (W, H), (14, 19, 27))
    dr = ImageDraw.Draw(img)
    f_h1 = find_font(24)
    f_h2 = find_font(15)
    f_sm = find_font(12)
    f_xs = find_font(10)

    dr.text((32, 18), "TLSR SWire Flasher (E180-Z6907A + AP63203WU-7 + USB-C) — Final 2-Layer Routed Blueprint (DRC = 0)", fill=(240, 246, 255), font=f_h1)
    dr.text((32, 48), "Left: TOP LAYER (All 33 Parts Single-Sided + L1 Copper + GND Pour)    |    Right: BOTTOM LAYER (0 Components + L2 Return Copper + GND Pour)", fill=(145, 205, 255), font=f_h2)

    pour_poly_raw = [
        (INSET + CHAMFER, INSET),
        (W_MIL - INSET - CHAMFER, INSET),
        (W_MIL - INSET, INSET + CHAMFER),
        (W_MIL - INSET, H_MIL - INSET - CHAMFER),
        (W_MIL - INSET - CHAMFER, H_MIL - INSET),
        (INSET + CHAMFER, H_MIL - INSET),
        (INSET, H_MIL - INSET - CHAMFER),
        (INSET, INSET + CHAMFER),
    ]

    # Panel 1: TOP (X: 0..1850.4, Y: 0..1023.6)
    sc = 0.45
    ox, oy = 55, 725
    def tp(mx: float, my: float) -> tuple[float, float]:
        return (ox + mx * sc, oy - my * sc)

    dr.rounded_rectangle([tp(0, H_MIL), tp(W_MIL, 0)], radius=int(CORNER_R * sc), fill=(16, 44, 92), outline=(225, 200, 95), width=3)
    dr.polygon([tp(px, py) for px, py in pour_poly_raw], fill=(24, 62, 54), outline=(80, 195, 130))
    dr.rectangle([tp(1075, 1023), tp(1620, 770)], fill=(65, 24, 36), outline=(255, 95, 110), width=2)
    dr.text((tp(1145, 910)[0], tp(1145, 910)[1]), "2.4GHz ANTENNA KEEPOUT", fill=(255, 155, 165), font=f_sm)

    for hx, hy in [(110.2, 913.4), (1740.2, 110.2)]:
        cx, cy = tp(hx, hy)
        r = 43.3 * sc
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(14, 19, 27), outline=(225, 200, 95), width=2)

    for lay_target, col in ((2, (35, 135, 195)), (1, (238, 82, 72))):
        for tr in dump["copper"]["lines"]:
            if int(tr["layer"]) != lay_target:
                continue
            lw = max(2, int(round(float(tr.get("lineWidth", 10)) * sc)))
            dr.line([tp(tr["startX"], tr["startY"]), tp(tr["endX"], tr["endY"])], fill=col, width=lw)

    for c in dump["components"]:
        for pad in c.get("pads", []):
            if pad.get("layer") not in (1, 12):
                continue
            px, py = pad["x"], pad["y"]
            pw, ph = pad.get("width", 30), pad.get("height", 30)
            dr.rectangle([tp(px - pw / 2, py + ph / 2), tp(px + pw / 2, py - ph / 2)], fill=(225, 185, 65))
            if pad.get("layer") == 12:
                cx, cy = tp(px, py)
                dr.ellipse([cx - 3.5, cy - 3.5, cx + 3.5, cy + 3.5], fill=(14, 19, 27))

    for v in dump["copper"]["vias"]:
        cx, cy = tp(v["x"], v["y"])
        r = 12 * sc
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(225, 185, 65), outline=(255, 240, 175))
        dr.ellipse([cx - 2.0, cy - 2.0, cx + 2.0, cy + 2.0], fill=(14, 19, 27))

    for s in dump.get("silk", []):
        if s.get("Layer") == 3 and s.get("BBox"):
            bb = s["BBox"]
            dr.text(tp(bb["MinX"], bb["MaxY"]), str(s.get("Text", "")), fill=(235, 245, 255), font=f_xs)

    # Panel 2: BOTTOM (mirrored X)
    ox_b, oy_b = 1015, 725
    def bp(mx: float, my: float) -> tuple[float, float]:
        return (ox_b + (W_MIL - mx) * sc, oy_b - my * sc)

    dr.rounded_rectangle([bp(W_MIL, H_MIL), bp(0, 0)], radius=int(CORNER_R * sc), fill=(16, 44, 92), outline=(225, 200, 95), width=3)
    dr.polygon([bp(px, py) for px, py in pour_poly_raw], fill=(24, 62, 54), outline=(80, 195, 130))
    dr.rectangle([bp(1620, 1023), bp(1075, 770)], fill=(65, 24, 36), outline=(255, 95, 110), width=2)
    dr.text((bp(1555, 910)[0], bp(1555, 910)[1]), "NO COPPER KEEPOUT", fill=(255, 155, 165), font=f_sm)

    for hx, hy in [(110.2, 913.4), (1740.2, 110.2)]:
        cx, cy = bp(hx, hy)
        r = 43.3 * sc
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(14, 19, 27), outline=(225, 200, 95), width=2)

    for tr in dump["copper"]["lines"]:
        if int(tr["layer"]) != 2:
            continue
        lw = max(2, int(round(float(tr.get("lineWidth", 10)) * sc)))
        dr.line([bp(tr["startX"], tr["startY"]), bp(tr["endX"], tr["endY"])], fill=(75, 185, 250), width=lw)

    for c in dump["components"]:
        for pad in c.get("pads", []):
            if pad.get("layer") != 12:
                continue
            px, py = pad["x"], pad["y"]
            pw, ph = pad.get("width", 50), pad.get("height", 50)
            dr.ellipse([bp(px + pw / 2, py + ph / 2), bp(px - pw / 2, py - ph / 2)], fill=(214, 173, 41))
            cx, cy = bp(px, py)
            dr.ellipse([cx - 3.0, cy - 3.0, cx + 3.0, cy + 3.0], fill=(14, 19, 27))

    for v in dump["copper"]["vias"]:
        cx, cy = bp(v["x"], v["y"])
        r = 12 * sc
        dr.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(225, 185, 65), outline=(255, 240, 175))
        dr.ellipse([cx - 2.0, cy - 2.0, cx + 2.0, cy + 2.0], fill=(14, 19, 27))

    dr.text((55, 815), "Board: 47.00 x 26.00 mm (R=1.8mm, 2x M2 diagonal holes TL/BR)  |  Assembly: Single-Sided Top Only (33/33 Parts)  |  Native DRC: 0 Errors", fill=(195, 215, 240), font=f_h2)
    os.makedirs(os.path.dirname(out_png), exist_ok=True)
    img.save(out_png)
    print("✓ Saved 2D copper blueprint:", out_png)


def verify_single_sided_pnp(pnp_csv: str) -> None:
    import io
    raw = open(pnp_csv, "rb").read()
    text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    delim = "\t" if "\t" in text.splitlines()[0] else ","
    rows = list(csv.DictReader(io.StringIO(text), delimiter=delim))
    assert len(rows) == 33, f"Expected 33 PickAndPlace components, got {len(rows)}"
    layer_col = next((k for k in rows[0].keys() if "layer" in k.lower()), None)
    assert layer_col is not None, f"Could not find Layer column in {list(rows[0].keys())}"
    bad = [r for r in rows if "bot" in str(r[layer_col]).lower() or str(r[layer_col]).strip() in ("2", "B")]
    assert not bad, f"Bottom-side components found in PnP CSV: {bad}"
    print(f"✓ Verified single-sided PnP CSV ({len(rows)} entries, all {layer_col} = Top, 0 Bottom components).")


def main() -> None:
    os.makedirs(FAB_DIR, exist_ok=True)
    os.makedirs(IMG_DIR, exist_ok=True)
    os.makedirs(STAGE_DIR, exist_ok=True)

    cli(["doc", "open", PCB_DOC, "--project", PROJECT])

    # 1. Capture live Top & Bottom routed viewport PNGs
    show_all = []
    for lid in range(1, 14):
        show_all += ["--show", str(lid)]
    cli(["pcb", "layer-visibility"] + show_all + ["--project", PROJECT, "--doc", PCB_DOC])
    cli(["editor", "panels", "--left", "closed", "--right", "closed", "--project", PROJECT])
    cli(["pcb", "stage-snapshot", "--stage", "routed_top", "--fit-mode", "board", "--out", STAGE_DIR, "--project", PROJECT, "--doc", PCB_DOC])
    shutil.copy2(os.path.join(STAGE_DIR, "routed_top", "snapshot.png"), os.path.join(IMG_DIR, "pcb_top_routed.png"))

    cli(["pcb", "layer-visibility", "--hide", "1", "--hide", "3", "--hide", "5", "--hide", "7", "--hide", "9", "--show", "2", "--show", "4", "--show", "11", "--show", "12", "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "stage-snapshot", "--stage", "routed_bottom", "--fit-mode", "board", "--out", STAGE_DIR, "--project", PROJECT, "--doc", PCB_DOC])
    shutil.copy2(os.path.join(STAGE_DIR, "routed_bottom", "snapshot.png"), os.path.join(IMG_DIR, "pcb_bottom_routed.png"))

    cli(["pcb", "layer-visibility"] + show_all + ["--project", PROJECT, "--doc", PCB_DOC])
    s = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
    assert s.get("result", {}).get("saved") is True
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])
    print("✓ Captured Top & Bottom live routed viewport PNGs and restored all layers.")

    # 2. Report & Manufacturing Exports
    rep = cli(["pcb", "report", "--project", PROJECT, "--doc", PCB_DOC])
    with open(os.path.join(DATA_DIR, "routing_report.json"), "w", encoding="utf-8") as f:
        f.write(rep)

    win = cli(["project", "info", "--project", PROJECT], parse_json=True)["windowId"]
    gerber_out = os.path.join(FAB_DIR, "TLSR_Flasher_Gerber.zip")
    pnp_out = os.path.join(FAB_DIR, "TLSR_Flasher_PickAndPlace_mm.csv")
    epro_out = os.path.join(DATA_DIR, "tlsr-flasher.epro2")
    obj_dir = os.path.join(DATA_DIR, "board_3d_model_obj")
    obj_zip = os.path.join(obj_dir, "board.obj.zip")

    for path in (gerber_out, pnp_out, epro_out):
        if os.path.exists(path):
            os.remove(path)
    if os.path.exists(obj_dir):
        shutil.rmtree(obj_dir)

    cli(["pcb", "export-gerber", "--window", win, "--project", PROJECT, "--doc", PCB_DOC, "--unit", "mm", "--out", gerber_out])
    with zipfile.ZipFile(gerber_out) as zf:
        gnames = zf.namelist()
        assert len(gnames) >= 8, f"Unexpectedly few Gerber files: {gnames}"
    print(f"✓ Exported Gerber ZIP ({len(gnames)} files): {gerber_out}")

    cli(["pcb", "export-placement", "--window", win, "--project", PROJECT, "--doc", PCB_DOC, "--format", "csv", "--unit", "mm", "--out", pnp_out])
    verify_single_sided_pnp(pnp_out)

    write_bom(os.path.join(FAB_DIR, "TLSR_Flasher_BOM.csv"))

    cli(["project", "export-source", "--uuid", PROJ_UUID, "--window", win, "--out", epro_out])
    print("✓ Exported native project backup (.epro2):", epro_out)

    cli(["pcb", "export-3d", "--format", "obj", "--window", win, "--doc", PCB_DOC, "--out", obj_dir])
    assert os.path.isfile(obj_zip), obj_zip
    print("✓ Exported live 3D OBJ package:", obj_zip)

    # 3. Render 2D Copper Blueprint & 3D Isometric Top/Bottom Preview
    final_dump = json.load(open(os.path.join(DATA_DIR, "pcb_final_dump.json"), encoding="utf-8"))
    render_routed_2d(final_dump, os.path.join(IMG_DIR, "pcb_routed_2d.png"))

    out_3d = os.path.join(IMG_DIR, "pcb_3d_top_bottom.png")
    subprocess.run([
        "python3", RENDER_3D,
        "--zip", obj_zip,
        "--out", out_3d,
        "--dump", os.path.join(DATA_DIR, "pcb_final_dump.json"),
        "--title", "TLSR SWire Flasher (Single-Sided Top, Flat Bottom)",
    ], check=True)
    print("✓ Rendered 3D isometric preview:", out_3d)


if __name__ == "__main__":
    main()
