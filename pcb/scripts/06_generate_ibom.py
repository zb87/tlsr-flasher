#!/usr/bin/env python3
"""Generate an Interactive HTML BOM (ibom.html) for tlsr-flasher.

Uses openscopeproject/InteractiveHtmlBom v2.10.0 HTML/CSS/JS frontend paired
with geometry, netlist, copper pours, tracks, vias, silkscreen, fabrication
drawings, and BOM metadata parsed directly from:
  - design-data/pcb_final_dump.json
  - fab/TLSR_Flasher_Gerber.zip
  - fab/TLSR_Flasher_BOM.csv
"""
from __future__ import annotations

import csv
import json
import math
import os
import re
import subprocess
import tempfile
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PCB_DUMP = os.path.join(ROOT, "design-data", "pcb_final_dump.json")
GERBER_ZIP = os.path.join(ROOT, "fab", "TLSR_Flasher_Gerber.zip")
BOM_CSV = os.path.join(ROOT, "fab", "TLSR_Flasher_BOM.csv")
OUT_HTML = os.path.join(ROOT, "ibom.html")
TEMPLATE_HTML = "/tmp/ref_ibom.html"

MIL_TO_MM = 0.0254
TEN_MIL_TO_MM = 0.254
BOARD_W_MM = 47.0
BOARD_H_MM = 26.0


def r4(v: float) -> float:
    return round(float(v), 4)


def mil_pt(x_mil: float, y_mil: float) -> list[float]:
    return [r4(x_mil * MIL_TO_MM), r4(BOARD_H_MM - y_mil * MIL_TO_MM)]


def gerb_pt(x_mm: float, y_mm: float) -> list[float]:
    return [r4(x_mm), r4(BOARD_H_MM - y_mm)]


def tessellate_poured_arc(
    x1: float, y1: float, sweep_deg: float, x2: float, y2: float, step_deg: float = 6.0
) -> list[list[float]]:
    theta = math.radians(sweep_deg)
    if abs(theta) < 1e-6:
        return [mil_pt(x2, y2)]
    dx = x2 - x1
    dy = y2 - y1
    half = theta / 2.0
    cot_half = math.cos(half) / math.sin(half)
    cx = 0.5 * (x1 + x2) - 0.5 * dy * cot_half
    cy = 0.5 * (y1 + y2) + 0.5 * dx * cot_half
    rad = math.hypot(x1 - cx, y1 - cy)
    a1 = math.atan2(y1 - cy, x1 - cx)
    steps = max(2, int(math.ceil(abs(sweep_deg) / step_deg)))
    pts = []
    for k in range(1, steps + 1):
        ang = a1 + theta * (k / steps)
        pts.append(mil_pt(cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def parse_poured_polygon(subpoly: list) -> list[list[float]]:
    pts: list[list[float]] = []
    i = 0
    n = len(subpoly)
    while i < n:
        tok = subpoly[i]
        if tok == "L":
            i += 1
            continue
        if tok == "ARC":
            sweep_deg = float(subpoly[i + 1])
            x2 = float(subpoly[i + 2])
            y2 = float(subpoly[i + 3])
            if pts:
                # Recompute last point in Y-up mil from subpoly
                px, py = float(subpoly[i - 2]), float(subpoly[i - 1])
                pts.extend(tessellate_poured_arc(px, py, sweep_deg, x2, y2))
            else:
                pts.append(mil_pt(x2, y2))
            i += 4
            continue
        x = float(tok)
        y = float(subpoly[i + 1])
        pts.append(mil_pt(x, y))
        i += 2
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts.pop()
    return pts


def parse_gerber_coord(val_str: str, int_digits: int = 4, dec_digits: int = 5) -> float:
    return int(val_str) / (10 ** dec_digits)


def tessellate_gerber_arc_mm(
    x1: float, y1: float, x2: float, y2: float, ci: float, cj: float, cw: bool, step_deg: float = 6.0
) -> list[list[float]]:
    cx = x1 + ci
    cy = y1 + cj
    rad = math.hypot(x1 - cx, y1 - cy)
    if rad < 1e-6:
        return [gerb_pt(x2, y2)]
    a1 = math.degrees(math.atan2(y1 - cy, x1 - cx))
    a2 = math.degrees(math.atan2(y2 - cy, x2 - cx))
    if cw:
        # CW in Y-up: decreasing angle
        da = -((a1 - a2) % 360.0)
        if abs(x1 - x2) < 1e-5 and abs(y1 - y2) < 1e-5:
            da = -360.0
        elif da >= 0:
            da -= 360.0
    else:
        # CCW in Y-up: increasing angle
        da = (a2 - a1) % 360.0
        if abs(x1 - x2) < 1e-5 and abs(y1 - y2) < 1e-5:
            da = 360.0
        elif da <= 0:
            da += 360.0
    steps = max(2, int(math.ceil(abs(da) / step_deg)))
    pts = []
    for k in range(1, steps + 1):
        ang = math.radians(a1 + da * (k / steps))
        pts.append(gerb_pt(cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    return pts


def parse_gerber_layer(text: str, designator_bboxes_mm: list[tuple[float, float, float, float]] | None = None):
    """Parse RS-274X Gerber exported by EasyEDA Pro into iBOM drawings/edges."""
    apertures: dict[str, float] = {}
    cur_width = 0.2
    cur_x = 0.0
    cur_y = 0.0
    mode = "G01"  # G01, G02, G03
    in_region = False
    in_text_section = False
    region_pts: list[list[float]] = []

    items: list[dict] = []

    def is_in_ref_bbox(pts: list[list[float]]) -> bool:
        if not designator_bboxes_mm or not pts:
            return False
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx = 0.5 * (min(xs) + max(xs))
        cy = 0.5 * (min(ys) + max(ys))
        for bx0, by0, bx1, by1 in designator_bboxes_mm:
            if (bx0 - 0.35) <= cx <= (bx1 + 0.35) and (by0 - 0.35) <= cy <= (by1 + 0.35):
                return True
        return False

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line == "G04 Text Start*":
            in_text_section = True
            continue
        if line == "G04 Text End*":
            in_text_section = False
            continue
        if line.startswith("G04 "):
            continue

        m_ap = re.match(r"^%ADD(\d+)C,([0-9.]+)\*%$", line)
        if m_ap:
            apertures[f"D{m_ap.group(1)}"] = float(m_ap.group(2))
            continue
        if line.startswith("%"):
            continue

        m_sel = re.match(r"^(?:G54)?(D\d+)\*$", line)
        if m_sel and m_sel.group(1) in apertures:
            cur_width = apertures[m_sel.group(1)]
            continue

        if line == "G36*":
            in_region = True
            region_pts = []
            continue
        if line == "G37*":
            in_region = False
            if len(region_pts) >= 3:
                if region_pts[0] == region_pts[-1]:
                    region_pts.pop()
                if len(region_pts) >= 3:
                    d_obj: dict = {"polygons": [region_pts], "thickness": 0}
                    if not in_text_section:
                        d_obj["type"] = "polygon"
                        d_obj["pos"] = [0, 0]
                        d_obj["angle"] = 0
                    elif is_in_ref_bbox(region_pts):
                        d_obj["ref"] = 1
                    items.append(d_obj)
            region_pts = []
            continue

        if line in ("G75*", "G74*", "M02*"):
            continue

        # Movement / draw command
        m_cmd = re.match(
            r"^(G0[123])?(?:X(-?\d+))?(?:Y(-?\d+))?(?:I(-?\d+))?(?:J(-?\d+))?(D0[123])?\*$",
            line,
        )
        if not m_cmd:
            continue
        g_code, xs, ys, is_, js_, d_code = m_cmd.groups()
        if g_code:
            mode = g_code
        nx = parse_gerber_coord(xs) if xs is not None else cur_x
        ny = parse_gerber_coord(ys) if ys is not None else cur_y
        ci = parse_gerber_coord(is_) if is_ is not None else 0.0
        cj = parse_gerber_coord(js_) if js_ is not None else 0.0

        if d_code == "D02":
            if in_region:
                if len(region_pts) >= 3:
                    if in_text_section:
                        d_obj = {"polygons": [region_pts], "thickness": 0}
                        if is_in_ref_bbox(region_pts):
                            d_obj["ref"] = 1
                    else:
                        d_obj = {"type": "polygon", "polygons": [region_pts], "pos": [0, 0], "angle": 0, "thickness": 0}
                    items.append(d_obj)
                region_pts = [gerb_pt(nx, ny)]
        elif d_code == "D01":
            if in_region:
                if mode == "G01":
                    region_pts.append(gerb_pt(nx, ny))
                else:
                    region_pts.extend(
                        tessellate_gerber_arc_mm(cur_x, cur_y, nx, ny, ci, cj, cw=(mode == "G02"))
                    )
            else:
                if mode == "G01":
                    p1 = gerb_pt(cur_x, cur_y)
                    p2 = gerb_pt(nx, ny)
                    if p1 != p2:
                        if in_text_section:
                            txt_obj: dict = {
                                "svgpath": f"M{p1[0]},{p1[1]}L{p2[0]},{p2[1]}",
                                "thickness": r4(cur_width),
                            }
                            if is_in_ref_bbox([p1, p2]):
                                txt_obj["ref"] = 1
                            items.append(txt_obj)
                        else:
                            items.append(
                                {
                                    "type": "segment",
                                    "start": p1,
                                    "end": p2,
                                    "width": r4(cur_width),
                                }
                            )
                else:
                    # G02 / G03 arc
                    cx = cur_x + ci
                    cy = cur_y + cj
                    rad = math.hypot(cur_x - cx, cur_y - cy)
                    c_dn = gerb_pt(cx, cy)
                    p1_dn = gerb_pt(cur_x, cur_y)
                    p2_dn = gerb_pt(nx, ny)
                    if abs(cur_x - nx) < 1e-5 and abs(cur_y - ny) < 1e-5:
                        items.append(
                            {
                                "type": "circle",
                                "start": c_dn,
                                "radius": r4(rad),
                                "width": r4(cur_width),
                            }
                        )
                    else:
                        a1 = math.degrees(math.atan2(p1_dn[1] - c_dn[1], p1_dn[0] - c_dn[0]))
                        a2 = math.degrees(math.atan2(p2_dn[1] - c_dn[1], p2_dn[0] - c_dn[0]))
                        if mode == "G02":
                            sa, ea = a1, a2
                        else:
                            sa, ea = a2, a1
                        while ea <= sa:
                            ea += 360.0
                        items.append(
                            {
                                "type": "arc",
                                "start": c_dn,
                                "radius": r4(rad),
                                "startangle": r4(sa),
                                "endangle": r4(ea),
                                "width": r4(cur_width),
                            }
                        )
        cur_x, cur_y = nx, ny

    return merge_polygon_holes(items)


def _poly_signed_area(pts: list[list[float]]) -> float:
    a = 0.0
    n = len(pts)
    for i in range(n):
        x1, y1 = pts[i]
        x2, y2 = pts[(i + 1) % n]
        a += x1 * y2 - x2 * y1
    return 0.5 * a


def _point_in_poly(pt: list[float], poly: list[list[float]]) -> bool:
    x, y = pt
    inside = False
    n = len(poly)
    for i in range(n):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % n]
        if ((y1 > y) != (y2 > y)) and (x < (x2 - x1) * (y - y1) / (y2 - y1 + 1e-30) + x1):
            inside = not inside
    return inside


def merge_polygon_holes(items: list[dict]) -> list[dict]:
    """Merge Gerber G36..G37 hole contours into their enclosing outer polygons.

    EasyEDA Pro exports glyph counters (e.g. B, D, O, P, R, 0, 6, 8) as
    separate G36..G37 blocks. InteractiveHtmlBom fills each item independently
    with nonzero winding, so hole contours must live inside their parent's
    `polygons` list with opposite winding direction.
    """
    poly_indices = [i for i, it in enumerate(items) if "polygons" in it and len(it["polygons"]) == 1]
    if not poly_indices:
        return items

    info: dict[int, tuple[list[list[float]], float, tuple[float, float, float, float]]] = {}
    for idx in poly_indices:
        pts = items[idx]["polygons"][0]
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        info[idx] = (pts, _poly_signed_area(pts), (min(xs), min(ys), max(xs), max(ys)))

    drop_indices: set[int] = set()
    for idx_a in poly_indices:
        pts_a, area_a, (ax0, ay0, ax1, ay1) = info[idx_a]
        if abs(area_a) < 1e-7:
            drop_indices.add(idx_a)
            continue
        is_text_a = "type" not in items[idx_a]
        enclosing: list[tuple[float, int]] = []
        for idx_b in poly_indices:
            if idx_a == idx_b:
                continue
            if ("type" not in items[idx_b]) != is_text_a:
                continue
            pts_b, area_b, (bx0, by0, bx1, by1) = info[idx_b]
            if abs(area_b) <= abs(area_a):
                continue
            if ax0 >= bx0 and ax1 <= bx1 and ay0 >= by0 and ay1 <= by1:
                if _point_in_poly(pts_a[0], pts_b):
                    enclosing.append((abs(area_b), idx_b))
        if len(enclosing) % 2 == 1:
            # Odd nesting depth -> hole inside immediate parent (smallest enclosing area)
            enclosing.sort(key=lambda t: t[0])
            parent_idx = enclosing[0][1]
            parent_area = info[parent_idx][1]
            hole_pts = list(pts_a)
            if (area_a > 0) == (parent_area > 0):
                hole_pts.reverse()
            items[parent_idx]["polygons"].append(hole_pts)
            drop_indices.add(idx_a)

    return [it for i, it in enumerate(items) if i not in drop_indices]


def parse_npth_drl(text: str) -> list[dict]:
    holes = []
    cur_diam = 0.65
    tools: dict[str, float] = {}
    for raw in text.splitlines():
        line = raw.strip()
        m_t = re.match(r"^(T\d+)C([0-9.]+)$", line)
        if m_t:
            tools[m_t.group(1)] = float(m_t.group(2))
            continue
        if line in tools:
            cur_diam = tools[line]
            continue
        m_xy = re.match(r"^X([0-9.-]+)Y([0-9.-]+)$", line)
        if m_xy:
            x = float(m_xy.group(1))
            y = float(m_xy.group(2))
            holes.append(
                {
                    "type": "circle",
                    "start": gerb_pt(x, y),
                    "radius": r4(cur_diam / 2.0),
                    "width": 0.1,
                }
            )
    return holes


def convert_pad(pad: dict) -> dict:
    px, py = mil_pt(pad["x"], pad["y"])
    shape_info = pad["shape"]
    st = shape_info[0]
    sw = r4(float(shape_info[1]) * MIL_TO_MM)
    sh = r4(float(shape_info[2]) * MIL_TO_MM)
    rot = r4(float(pad.get("rotation", 0.0)))

    if st == "RECT":
        srad = float(shape_info[3]) * MIL_TO_MM if len(shape_info) > 3 else 0.0
        if srad > 0:
            shape = "roundrect"
        else:
            shape = "rect"
    elif st == "OVAL":
        shape = "oval"
    elif st == "ELLIPSE":
        shape = "circle" if abs(sw - sh) < 1e-3 else "oval"
    else:
        shape = "rect"

    hole = pad.get("hole")
    is_th = bool(hole)
    layers = ["F", "B"] if (pad.get("layer") == 12 or is_th) else (["F"] if pad.get("layer") == 1 else ["B"])

    out: dict = {
        "pos": [px, py],
        "size": [sw, sh],
        "angle": rot,
        "shape": shape,
        "type": "th" if is_th else "smd",
        "offset": [0, 0],
        "net": pad.get("net") or "",
        "layers": layers,
    }
    if shape == "roundrect":
        out["radius"] = r4(float(shape_info[3]) * MIL_TO_MM)

    if is_th:
        htype = hole[0]
        hw = r4(float(hole[1]) * TEN_MIL_TO_MM)
        hh = r4(float(hole[2]) * TEN_MIL_TO_MM)
        if htype == "SLOT":
            out["drillshape"] = "oblong"
            out["drillsize"] = [hw, hh]
        elif htype == "RECT":
            out["drillshape"] = "rect"
            out["drillsize"] = [hw, hh]
        else:
            out["drillshape"] = "circle"
            out["drillsize"] = [hw, hh]

    pnum = str(pad.get("padNumber", ""))
    if pnum in ("1", "A1", "A1B12"):
        out["pin1"] = 1

    return out


def lz_compress_to_base64(uncompressed: str) -> str:
    """Standard pieroxy LZString.compressToBase64 implementation."""
    if uncompressed == "":
        return ""
    key_str = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/="

    def _compress(data: str, bits_per_char: int, get_char) -> str:
        context_dictionary: dict[str, int] = {}
        context_dictionary_to_create: dict[str, bool] = {}
        context_c = ""
        context_wc = ""
        context_w = ""
        context_enlarge_in = 2
        context_dict_size = 3
        context_num_bits = 2
        context_data: list[str] = []
        context_data_val = 0
        context_data_position = 0

        def write_bits(num_bits: int, val: int) -> None:
            nonlocal context_data_val, context_data_position
            for _ in range(num_bits):
                context_data_val = (context_data_val << 1) | (val & 1)
                if context_data_position == bits_per_char - 1:
                    context_data_position = 0
                    context_data.append(get_char(context_data_val))
                    context_data_val = 0
                else:
                    context_data_position += 1
                val >>= 1

        def write_char_bits(ch: str) -> None:
            nonlocal context_enlarge_in, context_dict_size, context_num_bits
            code = ord(ch)
            if code < 256:
                write_bits(context_num_bits, 0)
                write_bits(8, code)
            else:
                write_bits(context_num_bits, 1)
                write_bits(16, code)
            context_enlarge_in -= 1
            if context_enlarge_in == 0:
                context_enlarge_in = 2 ** context_num_bits
                context_num_bits += 1

        def dec_enlarge() -> None:
            nonlocal context_enlarge_in, context_num_bits
            context_enlarge_in -= 1
            if context_enlarge_in == 0:
                context_enlarge_in = 2 ** context_num_bits
                context_num_bits += 1

        for ch in data:
            context_c = ch
            if context_c not in context_dictionary:
                context_dictionary[context_c] = context_dict_size
                context_dict_size += 1
                context_dictionary_to_create[context_c] = True

            context_wc = context_w + context_c
            if context_wc in context_dictionary:
                context_w = context_wc
            else:
                if context_w in context_dictionary_to_create:
                    if ord(context_w[0]) < 256:
                        write_bits(context_num_bits, 0)
                        write_bits(8, ord(context_w[0]))
                    else:
                        write_bits(context_num_bits, 1)
                        write_bits(16, ord(context_w[0]))
                    dec_enlarge()
                    del context_dictionary_to_create[context_w]
                else:
                    write_bits(context_num_bits, context_dictionary[context_w])
                dec_enlarge()
                context_dictionary[context_wc] = context_dict_size
                context_dict_size += 1
                context_w = context_c

        if context_w != "":
            if context_w in context_dictionary_to_create:
                if ord(context_w[0]) < 256:
                    write_bits(context_num_bits, 0)
                    write_bits(8, ord(context_w[0]))
                else:
                    write_bits(context_num_bits, 1)
                    write_bits(16, ord(context_w[0]))
                dec_enlarge()
                del context_dictionary_to_create[context_w]
            else:
                write_bits(context_num_bits, context_dictionary[context_w])
            dec_enlarge()

        write_bits(context_num_bits, 2)

        while True:
            context_data_val <<= 1
            if context_data_position == bits_per_char - 1:
                context_data.append(get_char(context_data_val))
                break
            context_data_position += 1

        return "".join(context_data)

    res = _compress(uncompressed, 6, lambda idx: key_str[idx])
    mod = len(res) % 4
    if mod == 1:
        return res + "==="
    if mod == 2:
        return res + "=="
    if mod == 3:
        return res + "="
    return res


def main() -> None:
    with open(PCB_DUMP, encoding="utf-8") as f:
        pcb = json.load(f)

    with zipfile.ZipFile(GERBER_ZIP) as z:
        gko_txt = z.read("Gerber_BoardOutlineLayer.GKO").decode("utf-8", errors="replace")
        gto_txt = z.read("Gerber_TopSilkscreenLayer.GTO").decode("utf-8", errors="replace")
        gbo_txt = z.read("Gerber_BottomSilkscreenLayer.GBO").decode("utf-8", errors="replace")
        gdl_txt = z.read("Gerber_DocumentLayer.GDL").decode("utf-8", errors="replace")
        npth_txt = z.read("Drill_NPTH_Through.DRL").decode("utf-8", errors="replace")

    # 1. Board edges (outline + M2 mounting holes + USB1 NPTH alignment holes)
    edges = parse_gerber_layer(gko_txt)
    edges.extend(parse_npth_drl(npth_txt))
    edges_bbox = {
        "minx": -0.5,
        "miny": -0.2,
        "maxx": r4(BOARD_W_MM + 0.2),
        "maxy": r4(BOARD_H_MM + 0.2),
    }

    # 2. Visible designator bounding boxes (for "References" layer toggle)
    designator_bboxes_mm: list[tuple[float, float, float, float]] = []
    for s in pcb.get("silk", []):
        if s.get("Key") == "Designator" and s.get("visible") and s.get("BBox"):
            bb = s["BBox"]
            p0 = mil_pt(bb["MinX"], bb["MaxY"])  # top-left in Y-down
            p1 = mil_pt(bb["MaxX"], bb["MinY"])  # bottom-right in Y-down
            designator_bboxes_mm.append((p0[0], p0[1], p1[0], p1[1]))

    # 3. Silkscreen & Fabrication drawings
    silk_f = parse_gerber_layer(gto_txt, designator_bboxes_mm)
    silk_b = parse_gerber_layer(gbo_txt)
    fab_f = parse_gerber_layer(gdl_txt)

    # 4. Footprints (sorted cleanly by designator)
    comps = sorted(pcb["components"], key=lambda c: c["designator"])
    ref_to_idx: dict[str, int] = {}
    footprints: list[dict] = []
    for idx, c in enumerate(comps):
        ref = c["designator"]
        ref_to_idx[ref] = idx
        bb = c["bbox"]
        tl = mil_pt(bb["minX"], bb["maxY"])
        br = mil_pt(bb["maxX"], bb["minY"])
        pads = [convert_pad(p) for p in c["pads"]]
        footprints.append(
            {
                "ref": ref,
                "bbox": {
                    "pos": tl,
                    "relpos": [0, 0],
                    "size": [r4(br[0] - tl[0]), r4(br[1] - tl[1])],
                    "angle": 0,
                },
                "pads": pads,
                "drawings": [],
                "layer": "F" if c.get("layer", 1) == 1 else "B",
            }
        )

    # 5. Tracks, Vias, Zones, Nets
    tracks_f: list[dict] = []
    tracks_b: list[dict] = []
    nets_set: set[str] = {""}

    for fp in footprints:
        for p in fp["pads"]:
            nets_set.add(p["net"])

    for ln in pcb["copper"].get("lines", []):
        net = ln.get("net") or ""
        nets_set.add(net)
        tr = {
            "start": mil_pt(ln["startX"], ln["startY"]),
            "end": mil_pt(ln["endX"], ln["endY"]),
            "width": r4(ln["lineWidth"] * MIL_TO_MM),
            "net": net,
        }
        if ln["layer"] == 1:
            tracks_f.append(tr)
        else:
            tracks_b.append(tr)

    for v in pcb["copper"].get("vias", []):
        net = v.get("net") or ""
        nets_set.add(net)
        pt = mil_pt(v["x"], v["y"])
        tr = {
            "start": pt,
            "end": pt,
            "width": r4(v["diameter"] * MIL_TO_MM),
            "drillsize": r4(v["holeDiameter"] * MIL_TO_MM),
            "net": net,
        }
        tracks_f.append(tr)
        tracks_b.append(dict(tr))

    zones_f: list[dict] = []
    zones_b: list[dict] = []
    for p in pcb["copper"].get("poured", []):
        net = p.get("net") or ""
        nets_set.add(net)
        layer = p.get("layer", 1)
        for fl in p.get("fills", []):
            kind = fl.get("geometryKind")
            if kind == "filled-complex-polygon":
                polys = []
                for sp in fl.get("source", []):
                    poly = parse_poured_polygon(sp)
                    if len(poly) >= 3:
                        polys.append(poly)
                if polys:
                    z = {
                        "polygons": polys,
                        "width": 0,
                        "net": net,
                        "fillrule": "evenodd",
                    }
                    if layer == 1:
                        zones_f.append(z)
                    else:
                        zones_b.append(z)
            elif kind == "stroked-thermal-spoke-path":
                lw = r4(float(fl.get("lineWidth", 10)) * MIL_TO_MM)
                for sp in fl.get("source", []):
                    pts = parse_poured_polygon(sp)
                    for k in range(len(pts) - 1):
                        tr = {"start": pts[k], "end": pts[k + 1], "width": lw, "net": net}
                        if layer == 1:
                            tracks_f.append(tr)
                        else:
                            tracks_b.append(tr)

    # 6. BOM table from fab/TLSR_Flasher_BOM.csv
    bom_both: list[list] = []
    bom_f: list[list] = []
    VALUE_MAP = {
        "U1": "E180-Z6907A (TLSR8269)",
        "U2": "AP63203WU-7 (3.3V 2A Buck)",
        "L1": "3.9uH 3A",
        "Q1": "AO3401A (-30V PMOS)",
        "Q2": "S8050 (NPN BJT)",
        "D1": "SRV05-4 (USB ESD)",
        "F1": "1.5A 6V PTC",
        "USB1": "USB-C 16P Receptacle",
        "SW1": "TS-1088R Side Button",
        "LED1": "Red LED (+5V)",
        "LED2": "Green LED (PWR)",
        "C1,C7": "10uF 16V X5R",
        "C4,C5": "22uF 10V X5R",
        "C2,C3,C6,C8,C9,C10": "100nF 50V X7R",
        "R1,R2": "33 Ohm 1%",
        "R3,R4": "5.1k Ohm 1%",
        "R5": "4.7k Ohm 1%",
        "R6,R8": "10k Ohm 1%",
        "R7": "47k Ohm 1%",
        "R9": "100k Ohm 1%",
        "R10": "2.2k Ohm 1%",
        "H1": "1x5P 2.54mm (Target)",
        "H2": "1x4P 2.54mm (Self-Prog)",
    }

    def compact_status(s: str) -> str:
        m = re.match(r"Stocked \((\d+) pcs", s)
        if m:
            return f"Stock ({m.group(1)})"
        if "Sample Book" in s:
            return "Sample Book"
        if "Standard 2.54mm" in s:
            return "Stock (1x40P)"
        if "Order" in s:
            return "Order (LCSC)"
        return s

    bom_both: list[list] = []
    bom_f: list[list] = []
    bom_b: list[list] = []
    bom_fields: dict[str, list[str]] = {}

    with open(BOM_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            desig_key = row["Designators"].strip()
            refs = [r.strip() for r in desig_key.split(",") if r.strip()]
            val = VALUE_MAP.get(desig_key, row["Value_Description"].strip())
            mpn = row["ManufacturerPart"].strip()
            fp_name = row["Footprint"].strip()
            lcsc = row["LCSC_Part"].strip()
            status = compact_status(row["Source_Status"].strip())

            group_both = []
            group_f = []
            group_b = []
            for r in refs:
                idx = ref_to_idx[r]
                entry = [r, idx]
                group_both.append(entry)
                if footprints[idx]["layer"] == "F":
                    group_f.append(entry)
                else:
                    group_b.append(entry)
                bom_fields[str(idx)] = [val, fp_name, mpn, lcsc, status]

            if group_both:
                bom_both.append(group_both)
            if group_f:
                bom_f.append(group_f)
            if group_b:
                bom_b.append(group_b)

    pcbdata = {
        "edges_bbox": edges_bbox,
        "edges": edges,
        "drawings": {
            "silkscreen": {"F": silk_f, "B": silk_b},
            "fabrication": {"F": fab_f, "B": []},
        },
        "footprints": footprints,
        "metadata": {
            "title": "TLSR SWire Flasher",
            "revision": "V1.1",
            "company": "47x26mm | 2L | Top-Only SMD",
            "date": "2026-11-13",
        },
        "bom": {
            "both": bom_both,
            "skipped": [],
            "fields": bom_fields,
            "F": bom_f,
            "B": bom_b,
        },
        "font_data": {},
        "tracks": {"F": tracks_f, "B": tracks_b},
        "zones": {"F": zones_f, "B": zones_b},
        "nets": sorted(nets_set),
        "ibom_version": "v2.10.0",
    }

    config = {
        "dark_mode": True,
        "show_pads": True,
        "show_fabrication": False,
        "show_silkscreen": True,
        "highlight_pin1": "selected",
        "redraw_on_drag": True,
        "board_rotation": 0,
        "checkboxes": "Sourced,Placed",
        "bom_view": "left-right",
        "layer_view": "F",
        "offset_back_rotation": False,
        "kicad_text_formatting": True,
        "fields": ["Value", "Footprint", "MPN", "LCSC", "Status"],
    }

    with open(TEMPLATE_HTML, encoding="utf-8") as f:
        tpl = f.read()

    m_lz = re.search(r"var LZString=function\(\)\{[\s\S]*?\}\(\);", tpl)
    if not m_lz:
        raise RuntimeError("Could not locate LZString in template")

    pcbdata_json = json.dumps(pcbdata, separators=(",", ":"))
    compressed = lz_compress_to_base64(pcbdata_json)

    # Verify round-trip against the template's embedded LZString.decompressFromBase64
    with tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False, encoding="utf-8") as tf:
        tf.write(compressed)
        tmp_b64 = tf.name
    try:
        rt_len = int(
            subprocess.check_output(
                [
                    "node",
                    "-e",
                    f"const fs=require('fs');{m_lz.group(0)};"
                    f"const s=LZString.decompressFromBase64(fs.readFileSync({json.dumps(tmp_b64)},'utf8'));"
                    f"const obj=JSON.parse(s);console.log(s.length);",
                ],
                text=True,
            ).strip()
        )
        assert rt_len == len(pcbdata_json), f"LZString round-trip mismatch: {rt_len} != {len(pcbdata_json)}"
    finally:
        os.unlink(tmp_b64)

    # Inject config and pcbdata cleanly
    out = re.sub(
        r"var config = \{.*?\}",
        lambda _: "var config = " + json.dumps(config),
        tpl,
        count=1,
    )
    out = re.sub(
        r'var pcbdata = JSON\.parse\(LZString\.decompressFromBase64\("[^"]+"\)\)',
        lambda _: f'var pcbdata = JSON.parse(LZString.decompressFromBase64("{compressed}"))',
        out,
        count=1,
    )
    out = out.replace(
        "<title>Interactive BOM for KiCAD</title>",
        "<title>TLSR SWire Flasher — Interactive BOM</title>",
        1,
    )

    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(out)

    print(
        f"Generated {OUT_HTML} ({os.path.getsize(OUT_HTML)} bytes): "
        f"{len(footprints)} footprints, {len(bom_both)} BOM groups, "
        f"{len(edges)} edges, {len(silk_f)} F silk / {len(silk_b)} B silk, "
        f"{len(fab_f)} fab, {len(tracks_f)} F tracks / {len(tracks_b)} B tracks, "
        f"{len(zones_f)} F zones / {len(zones_b)} B zones, {len(pcbdata['nets'])} nets."
    )


if __name__ == "__main__":
    main()
