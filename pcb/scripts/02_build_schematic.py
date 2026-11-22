#!/usr/bin/env python3
"""Synthesize, compose, apply, and strictly gate-verify the complete schematic
for tlsr-flasher (33 components) in EasyEDA Pro project tlsr-flasher:
  - USB_ESD:    TYPE-C16PIN (USB1) + CC 5.1k (R3,R4) + SRV05-4 (D1) + 1.5A PTC (F1) + 33R (R1,R2) + 5V LED1/R5
  - BUCK_3V3:   AP63203WU-7 (U2) + 3.9uH SWPA4030 (L1) + C1,C2,C3,C4,C5,C6
  - TLSR_CORE:  E180-Z6907A (U1) + decoupling (C7,C8) + nRESET RC/SW1 (R6,C9,SW1)
  - PWR_SWITCH: AO3401A (Q1) + S8050 (Q2) + R7..R10, C10 + PWR LED2/R10
  - TARGET_HDR: 1x5P Target Header (H1: GND, PWR, 3V3, SWM, EXT_RST)
  - SELF_HDR:   1x4P Self-Prog Header (H2: GND, 3V3, SWS, RST)
"""
from __future__ import annotations
import copy
import json
import os
import subprocess

PROJECT = "f91760ddb2c7418299e7752f330a761d"
SCHEMATIC_UUID = "936a419812a202bd"
P1_UUID = "48f86e153a22ba1c"

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "design-data")
IMG_DIR = os.path.join(BASE_DIR, "images")
WORK_DIR = os.path.join(DATA_DIR, "sch-build")
os.makedirs(WORK_DIR, exist_ok=True)
os.makedirs(IMG_DIR, exist_ok=True)

# 33 designators -> (probe_sampleKey, role)
PART_TYPES: dict[str, tuple[str, str]] = {
    # USB-C, ESD, Polyfuse, Power LED
    "USB1": ("USBC",     "connector"),
    "R3":   ("R_5K1",    "resistor"),
    "R4":   ("R_5K1",    "resistor"),
    "D1":   ("SRV05",    "diode"),
    "F1":   ("PTC_1A5",  "fuse"),
    "R1":   ("R_33R",    "resistor"),
    "R2":   ("R_33R",    "resistor"),
    "LED1": ("LED_RED",  "led"),
    "R5":   ("R_4K7",    "resistor"),

    # AP63203WU-7 3.3V 2A Buck
    "U2":   ("AP63203",  "regulator"),
    "C1":   ("C_10U",    "capacitor"),
    "C2":   ("C_100N",   "capacitor"),
    "C3":   ("C_100N",   "capacitor"),
    "L1":   ("L_3U9",    "inductor"),
    "C4":   ("C_22U",    "capacitor"),
    "C5":   ("C_22U",    "capacitor"),
    "C6":   ("C_100N",   "capacitor"),

    # E180-Z6907A Core & Reset
    "U1":   ("E180",     "mcu"),
    "C7":   ("C_100N",   "capacitor"),  # 1uF? Wait: use C_100N + C_10U or C_100N; let's probe 1uF/100nF
    "C8":   ("C_100N",   "capacitor"),
    "R6":   ("R_10K",    "resistor"),
    "C9":   ("C_100N",   "capacitor"),
    "SW1":  ("SW_RST",   "switch"),

    # PWR High-Side Switch & Indicator
    "Q1":   ("AO3401A",  "mosfet"),
    "R7":   ("R_47K",    "resistor"),
    "C10":  ("C_100N",   "capacitor"),
    "Q2":   ("S8050",    "bjt"),
    "R8":   ("R_10K",    "resistor"),
    "R9":   ("R_100K",   "resistor"),
    "LED2": ("LED_GRN",  "led"),
    "R10":  ("R_2K2",    "resistor"),

    # Headers
    "H1":   ("HDR_5P",   "connector"),
    "H2":   ("HDR_4P",   "connector"),
}

# Wait: make C7 = 1uF? No, C_100N wasn't probed for 1uF's footprint, wait: 1uF (C48579283) IS in probe_bundle.json!
# Let's check: C7 -> C_10U or C_100N? In probe_bundle.json we already probed C_10U and C_100N!
# Let's add C_1U to probe_bundle? Actually C_10U (10uF) + C_100N (100nF) at U1.13 is even better than 1uF + 100nF,
# or 1uF was in inventory (100 pcs) and 10uF was in inventory (100 pcs)! Using C_10U (C7472959) + C_100N (C48579281)
# means zero extra unique C-numbers! Let's use C_10U for C7 (10uF local bulk at U1.13) + C_100N for C8!
PART_TYPES["C7"] = ("C_10U", "capacitor")

PIN_NETS: dict[str, dict[str, str]] = {
    "USB1": {
        "A1B12": "GND", "B1A12": "GND",
        "1": "GND", "2": "GND", "3": "GND", "4": "GND",
        "A4B9": "VBUS_RAW", "B4A9": "VBUS_RAW",
        "A5": "CC1", "B5": "CC2",
        "A6": "USB_DP", "B6": "USB_DP",
        "A7": "USB_DN", "B7": "USB_DN",
        # A8 (SBU1), B8 (SBU2): NC
    },
    "R3":   {"1": "CC1", "2": "GND"},
    "R4":   {"1": "CC2", "2": "GND"},
    "F1":   {"1": "VBUS_RAW", "2": "+5V"},
    "D1":   {
        "1": "USB_DN", "6": "USB_DN",
        "3": "USB_DP", "4": "USB_DP",
        "2": "GND",    "5": "+5V",
    },
    "R1":   {"1": "USB_DN", "2": "DM"},
    "R2":   {"1": "USB_DP", "2": "DP"},
    "LED1": {"2": "+5V", "1": "LED1_K"},
    "R5":   {"1": "LED1_K", "2": "GND"},

    # Buck Converter
    "U2": {
        "1": "3V3",
        "2": "+5V",
        "3": "+5V",
        "4": "GND",
        "5": "BUCK_SW",
        "6": "BUCK_BST",
    },
    "C1":   {"1": "+5V",      "2": "GND"},
    "C2":   {"1": "+5V",      "2": "GND"},
    "C3":   {"1": "BUCK_BST", "2": "BUCK_SW"},
    "L1":   {"1": "BUCK_SW",  "2": "3V3"},
    "C4":   {"1": "3V3",      "2": "GND"},
    "C5":   {"1": "3V3",      "2": "GND"},
    "C6":   {"1": "3V3",      "2": "GND"},

    # E180-Z6907A Core (all other pins NC)
    "U1": {
        "2":  "GND",
        "4":  "PWR_EN",
        "10": "DM",
        "12": "DP",
        "13": "3V3",
        "14": "GND",
        "18": "SWM",
        "21": "EXT_RST",
        "26": "SWS",
        "36": "GND",
        "37": "RST",
    },
    "C7":   {"1": "3V3", "2": "GND"},
    "C8":   {"1": "3V3", "2": "GND"},
    "R6":   {"1": "3V3", "2": "RST"},
    "C9":   {"1": "RST", "2": "GND"},
    "SW1":  {"1": "RST", "2": "GND"},

    # PWR Switch & Indicator
    "Q1":   {"1": "Q1_GATE", "2": "3V3", "3": "PWR"},
    "R7":   {"1": "3V3",     "2": "Q1_GATE"},
    "C10":  {"1": "Q1_GATE", "2": "GND"},
    "Q2":   {"1": "Q2_BASE", "2": "GND", "3": "Q1_GATE"},
    "R8":   {"1": "PWR_EN",  "2": "Q2_BASE"},
    "R9":   {"1": "Q2_BASE", "2": "GND"},
    "LED2": {"2": "PWR",     "1": "LED2_K"},
    "R10":  {"1": "LED2_K",  "2": "GND"},

    # Headers
    "H1": {
        "1": "GND",
        "2": "PWR",
        "3": "3V3",
        "4": "SWM",
        "5": "EXT_RST",
    },
    "H2": {
        "1": "GND",
        "2": "3V3",
        "3": "SWS",
        "4": "RST",
    },
}

NET_POLICIES: dict[str, str] = {
    "GND":      "local_ground",
    "+5V":      "local_power",
    "3V3":      "local_power",
    "PWR":      "local_power",

    # Intra-zone direct nets
    "LED1_K":   "direct",
    "BUCK_SW":  "direct",
    "BUCK_BST": "direct",
    "Q1_GATE":  "direct",
    "Q2_BASE":  "direct",
    "LED2_K":   "direct",

    # Inter-zone ports
    "VBUS_RAW": "module_port",
    "CC1":      "module_port",
    "CC2":      "module_port",
    "USB_DN":   "module_port",
    "USB_DP":   "module_port",
    "DM":       "module_port",
    "DP":       "module_port",
    "PWR_EN":   "module_port",
    "SWM":      "module_port",
    "EXT_RST":  "module_port",
    "SWS":      "module_port",
    "RST":      "module_port",
}

ZONES_BY_PAGE: list[tuple[str, str, list[dict]]] = [
    (
        "P1_USB_Input",
        "TLSR Flasher P1 - USB-C, CC, ESD & 1.5A Polyfuse",
        [
            {
                "id": "USB_ESD_DATA",
                "title": "USB ESD & 33R Series (D1)",
                "coreComponentId": "comp-D1",
                "componentIds": ["comp-D1", "comp-R1", "comp-R2"],
            },
            {
                "id": "USB_CONN",
                "title": "USB-C Receptacle (USB1)",
                "coreComponentId": "comp-USB1",
                "componentIds": ["comp-USB1"],
            },
            {
                "id": "LED_5V",
                "title": "+5V Power LED (LED1)",
                "coreComponentId": "comp-LED1",
                "componentIds": ["comp-LED1", "comp-R5"],
            },
            {
                "id": "CC1_PD",
                "title": "CC1 5.1k Pull-Down",
                "coreComponentId": "comp-R3",
                "componentIds": ["comp-R3"],
            },
            {
                "id": "CC2_PD",
                "title": "CC2 5.1k Pull-Down",
                "coreComponentId": "comp-R4",
                "componentIds": ["comp-R4"],
            },
            {
                "id": "VBUS_FUSE",
                "title": "1.5A Polyfuse (F1)",
                "coreComponentId": "comp-F1",
                "componentIds": ["comp-F1"],
            },
        ],
    ),
    (
        "P2_Power_Tree",
        "TLSR Flasher P2 - AP63203WU-7 3.3V Buck & Switched PWR",
        [
            {
                "id": "BUCK_3V3",
                "title": "AP63203WU-7 3.3V 2A Buck",
                "coreComponentId": "comp-U2",
                "componentIds": ["comp-U2", "comp-C1", "comp-C2", "comp-C3", "comp-L1", "comp-C4", "comp-C5", "comp-C6"],
            },
            {
                "id": "PWR_SWITCH",
                "title": "Switched Target PWR (AO3401A)",
                "coreComponentId": "comp-Q1",
                "componentIds": ["comp-Q1", "comp-R7", "comp-C10", "comp-Q2", "comp-R8", "comp-R9"],
            },
            {
                "id": "LED_PWR",
                "title": "Switched PWR LED (LED2)",
                "coreComponentId": "comp-LED2",
                "componentIds": ["comp-LED2", "comp-R10"],
            },
        ],
    ),
    (
        "P3_TLSR_Headers",
        "TLSR Flasher P3 - E180-Z6907A Core, Reset & SWire Headers",
        [
            {
                "id": "SELF_HDR",
                "title": "Self-Prog 1x4P (H2)",
                "coreComponentId": "comp-H2",
                "componentIds": ["comp-H2"],
            },
            {
                "id": "TLSR_CORE",
                "title": "E180-Z6907A Core & Reset",
                "coreComponentId": "comp-U1",
                "componentIds": ["comp-U1", "comp-C7", "comp-C8", "comp-R6", "comp-C9", "comp-SW1"],
            },
            {
                "id": "TARGET_HDR",
                "title": "Target SWire 1x5P (H1)",
                "coreComponentId": "comp-H1",
                "componentIds": ["comp-H1"],
            },
        ],
    ),
]

ATTACHMENTS = [
    # USB_ESD_DATA & LED_5V
    {"componentId": "comp-R1",   "pinNumber": "1", "attachTo": {"componentId": "comp-D1",   "pinNumber": "6"}},
    {"componentId": "comp-R2",   "pinNumber": "1", "attachTo": {"componentId": "comp-D1",   "pinNumber": "4"}},
    {"componentId": "comp-R5",   "pinNumber": "1", "attachTo": {"componentId": "comp-LED1", "pinNumber": "1"}},

    # BUCK_3V3
    {"componentId": "comp-C1",   "pinNumber": "1", "attachTo": {"componentId": "comp-U2",   "pinNumber": "3"}},
    {"componentId": "comp-C2",   "pinNumber": "1", "attachTo": {"componentId": "comp-U2",   "pinNumber": "3"}},
    {"componentId": "comp-C3",   "pinNumber": "1", "attachTo": {"componentId": "comp-U2",   "pinNumber": "6"}},
    {"componentId": "comp-L1",   "pinNumber": "1", "attachTo": {"componentId": "comp-U2",   "pinNumber": "5"}},
    {"componentId": "comp-C4",   "pinNumber": "1", "attachTo": {"componentId": "comp-L1",   "pinNumber": "2"}},
    {"componentId": "comp-C5",   "pinNumber": "1", "attachTo": {"componentId": "comp-L1",   "pinNumber": "2"}},
    {"componentId": "comp-C6",   "pinNumber": "1", "attachTo": {"componentId": "comp-L1",   "pinNumber": "2"}},

    # TLSR_CORE
    {"componentId": "comp-C7",   "pinNumber": "1", "attachTo": {"componentId": "comp-U1",   "pinNumber": "13"}},
    {"componentId": "comp-C8",   "pinNumber": "1", "attachTo": {"componentId": "comp-U1",   "pinNumber": "13"}},
    {"componentId": "comp-R6",   "pinNumber": "2", "attachTo": {"componentId": "comp-U1",   "pinNumber": "37"}},
    {"componentId": "comp-C9",   "pinNumber": "1", "attachTo": {"componentId": "comp-U1",   "pinNumber": "37"}},
    {"componentId": "comp-SW1",  "pinNumber": "1", "attachTo": {"componentId": "comp-U1",   "pinNumber": "37"}},

    # PWR_SWITCH & LED_PWR
    {"componentId": "comp-R7",   "pinNumber": "2", "attachTo": {"componentId": "comp-Q1",   "pinNumber": "1"}},
    {"componentId": "comp-C10",  "pinNumber": "1", "attachTo": {"componentId": "comp-Q1",   "pinNumber": "1"}},
    {"componentId": "comp-Q2",   "pinNumber": "3", "attachTo": {"componentId": "comp-Q1",   "pinNumber": "1"}},
    {"componentId": "comp-R8",   "pinNumber": "2", "attachTo": {"componentId": "comp-Q2",   "pinNumber": "1"}},
    {"componentId": "comp-R9",   "pinNumber": "1", "attachTo": {"componentId": "comp-Q2",   "pinNumber": "1"}},
    {"componentId": "comp-R10",  "pinNumber": "1", "attachTo": {"componentId": "comp-LED2", "pinNumber": "1"}},
]


def cli(args: list[str], parse_json: bool = False):
    p = subprocess.run(["easyeda"] + args, capture_output=True, text=True)
    if p.returncode != 0:
        raise RuntimeError(f"Command failed ({p.returncode}): {' '.join(args)}\nSTDOUT:\n{p.stdout}\nSTDERR:\n{p.stderr}")
    return json.loads(p.stdout) if parse_json else p.stdout


def net_scope_and_role(net_name: str) -> tuple[str, str]:
    pol = NET_POLICIES[net_name]
    if pol == "local_ground":
        return ("global", "ground")
    if pol == "local_power":
        return ("global", "power")
    if pol == "module_port":
        return ("global", "signal")
    return ("local", "signal")


def build_synthetic_unwired(bundle: dict) -> tuple[dict[str, dict], dict[str, list[dict]]]:
    pmap = bundle["probeMap"]
    des_by_pid: dict[str, list[dict]] = {}
    for item in bundle["designators"].get("designators", []):
        des_by_pid.setdefault(item["parentId"], []).append(item["bbox"])

    tmpl_by_key: dict[str, tuple[dict, list[dict], str]] = {}
    for c in bundle["schList"]["components"]:
        if c.get("componentType") == "sheet":
            continue
        info = pmap[c["designator"]]
        tmpl_by_key[info["sampleKey"]] = (c, des_by_pid.get(c["primitiveId"], []), info["libraryUuid"])

    unwired_by_ref: dict[str, dict] = {}
    des_by_ref: dict[str, list[dict]] = {}
    for ref, (skey, role) in PART_TYPES.items():
        tmpl, tbboxes, lib_uuid = tmpl_by_key[skey]
        inst = copy.deepcopy(tmpl)
        inst["designator"] = ref
        inst["primitiveId"] = f"synth-{ref}"
        inst.setdefault("otherProperty", {})
        inst["otherProperty"]["EasyEDA Agent Component ID"] = f"comp-{ref}"
        inst["otherProperty"]["EasyEDA Agent Role"] = role
        inst["_libraryUuid"] = lib_uuid
        unwired_by_ref[ref] = inst
        des_by_ref[ref] = copy.deepcopy(tbboxes)
    return unwired_by_ref, des_by_ref


def ensure_sheet_titleblock(puuid: str, ptitle: str) -> None:
    cli(["doc", "open", puuid, "--project", PROJECT])
    tb_patch = {
        "Name": {"value": ptitle, "showTitle": False, "showValue": True},
        "Description": {"value": "TLSR SWire Flasher (E180-Z6907A + USB-C + AP63203WU-7)", "showTitle": False, "showValue": True},
        "Drawed": {"value": "Antigravity", "showTitle": False, "showValue": True},
    }
    cli(["sch", "titleblock", "--project", PROJECT, "--doc", puuid, "--data", json.dumps(tb_patch, ensure_ascii=False)])
    d = cli(["sch", "list", "--project", PROJECT, "--doc", puuid, "--include-page-primitives"], parse_json=True)["result"]
    sheet = [c for c in d["components"] if c.get("componentType") == "sheet"][0]
    spid = sheet["primitiveId"]
    attrs = {a["Key"]: a for a in d["pagePrimitives"]["attributes"] if a.get("ParentPrimitiveId") == spid}
    for key, tx, ty in [("Name", 685, 114), ("Description", 685, 76), ("Drawed", 572, 76)]:
        if key not in attrs:
            continue
        rec = attrs[key]
        if rec.get("X") == tx and rec.get("Y") == ty:
            continue
        mpath = os.path.join(WORK_DIR, f"move-tb-{key}.json")
        with open(mpath, "w", encoding="utf-8") as f:
            json.dump({
                "projectUuid": PROJECT,
                "documentUuid": puuid,
                "primitiveId": rec["primitiveId"],
                "ownerType": "sheet",
                "x": tx,
                "y": ty,
                "expected": rec,
            }, f, ensure_ascii=False, indent=2)
        cli(["sch", "attribute-move", "--from", mpath, "--project", PROJECT, "--doc", puuid])


def main() -> None:
    assert set(PART_TYPES.keys()) == set(PIN_NETS.keys())
    bundle = json.load(open(os.path.join(DATA_DIR, "probe_bundle.json"), encoding="utf-8"))
    unwired_by_ref, des_by_ref = build_synthetic_unwired(bundle)

    comp_entries = []
    for ref in PART_TYPES:
        c = unwired_by_ref[ref]
        cid = f"comp-{ref}"
        rmap = PIN_NETS[ref]
        pins_out = []
        pin_states = {}
        for p in c["pins"]:
            pnum = str(p["pinNumber"])
            pname = str(p["pinName"])
            net = rmap.get(pnum, "")
            if not net:
                pin_states[pnum] = "nc"
            pins_out.append({
                "number": pnum,
                "name": pname,
                "net": net,
                "x": p["x"],
                "y": p["y"],
                "rotation": p.get("rotation", 0),
            })
        entry: dict = {
            "id": cid,
            "measurement": {
                "designator": ref,
                "x": c["x"],
                "y": c["y"],
                "rotation": c.get("rotation", 0),
                "mirror": bool(c.get("mirror", False)),
                "bbox": c["bbox"],
                "pins": pins_out,
                "textBboxes": des_by_ref[ref],
            },
            "allowedRotations": [0],
        }
        if pin_states:
            entry["pinStates"] = pin_states
        comp_entries.append(entry)

    all_zones = [z for _, _, zs in ZONES_BY_PAGE for z in zs]
    zones_in_path = os.path.join(WORK_DIR, "zones-in.json")
    zones_geom_path = os.path.join(WORK_DIR, "zones-geom.json")
    zones_rep_path = os.path.join(WORK_DIR, "zones-report.json")
    with open(zones_in_path, "w", encoding="utf-8") as f:
        json.dump({
            "schemaVersion": 1,
            "spacing": 10,
            "maxCandidates": 200000,
            "components": comp_entries,
            "netPolicies": NET_POLICIES,
            "attachments": ATTACHMENTS,
            "zones": all_zones,
        }, f, ensure_ascii=False, indent=2)

    cli(["sch", "layout-plan", "--zones", "--from", zones_in_path, "--out", zones_geom_path, "--report", zones_rep_path])
    print(f"✓ Offline layout-plan solved all {len(all_zones)} zones!", flush=True)

    solved_by_id = {z["id"]: z for z in json.load(open(zones_geom_path, encoding="utf-8"))["zones"]}
    sh = bundle["sheetExact"]["sheet"]

    # Ensure 3 schematic pages exist and have clean names
    pages_res = cli(["sch", "pages", "--project", PROJECT], parse_json=True)["result"]["pages"]
    page_uuid_by_name: dict[str, str] = {}
    for idx, (pname, ptitle, _) in enumerate(ZONES_BY_PAGE):
        if idx < len(pages_res):
            puuid = pages_res[idx]["uuid"]
            if pages_res[idx]["name"] != pname:
                cli(["sch", "page-rename", "--project", PROJECT, "--page", puuid, "--name", pname])
        else:
            known = {p["uuid"] for p in pages_res}
            cli(["sch", "page-new", "--project", PROJECT, "--schematic", SCHEMATIC_UUID])
            pages_res = cli(["sch", "pages", "--project", PROJECT], parse_json=True)["result"]["pages"]
            puuid = [p["uuid"] for p in pages_res if p["uuid"] not in known][0]
            cli(["sch", "page-rename", "--project", PROJECT, "--page", puuid, "--name", pname])
        page_uuid_by_name[pname] = puuid

    win = cli(["project", "info", "--project", PROJECT], parse_json=True)["windowId"]

    for page_idx, (pname, ptitle, pzones) in enumerate(ZONES_BY_PAGE, start=1):
        puuid = page_uuid_by_name[pname]
        z_list = [solved_by_id[z["id"]] for z in pzones]
        sheet_in_path = os.path.join(WORK_DIR, f"sheet-in-p{page_idx}.json")
        sheet_out_path = os.path.join(WORK_DIR, f"sheet-out-p{page_idx}.json")
        with open(sheet_in_path, "w", encoding="utf-8") as f:
            json.dump({
                "schemaVersion": 1,
                "spacing": 10,
                "zones": z_list,
                "sheet": {
                    "bounds": sh["bbox"],
                    "border": sh["innerBBox"],
                    "keepouts": [{"minX": 468, "minY": 0, "maxX": 1170, "maxY": 198}],
                    "padding": 10,
                    "gap": 10,
                    "flow": "z",
                },
            }, f, ensure_ascii=False, indent=2)

        cli(["sch", "layout-sheet-plan", "--flow", "z", "--from", sheet_in_path, "--out", sheet_out_path])
        out_doc = json.load(open(sheet_out_path, encoding="utf-8"))
        print(f"  {pname}: blockedZones={out_doc.get('blockedZones')} pages={len(out_doc['pages'])}", flush=True)
        assert not out_doc.get("blockedZones"), f"{pname} blockedZones: {out_doc.get('blockedZones')}"
        assert len(out_doc["pages"]) == 1, f"{pname}: Expected 1 page, got {len(out_doc['pages'])}!"

        pobj = out_doc["pages"][0]
        page_path = os.path.join(WORK_DIR, f"selected-page-{page_idx}.json")
        with open(page_path, "w", encoding="utf-8") as f:
            json.dump(pobj, f, ensure_ascii=False, indent=2)

        # Build composition doc for this page
        comp_ir_list = []
        connections_ir = []
        nets_seen: dict[str, dict] = {}
        conn_modules_ir = []
        geom_modules_ir = []
        for z in pobj["zones"]:
            zid = z["id"]
            ztitle = z["title"]
            layout = z["layout"]
            core_id = z["coreComponentId"]
            periph_ids = []
            internal_nets = set()
            port_nets: dict[str, list[str]] = {}
            for pl in layout["placements"]:
                ref = pl["designator"]
                orig = unwired_by_ref[ref]
                cid = orig["otherProperty"]["EasyEDA Agent Component ID"]
                role = orig["otherProperty"]["EasyEDA Agent Role"]
                dev_uuid = orig["device"]["uuid"]
                lib_uuid = orig["_libraryUuid"]
                if cid != core_id:
                    periph_ids.append(cid)
                ir_pins = []
                for p in pl["pins"]:
                    pnum = str(p["number"])
                    pname_pin = str(p["name"])
                    net_name = p.get("net", "")
                    ir_pins.append({
                        "number": pnum,
                        "name": pname_pin,
                        "noConnected": (net_name == ""),
                        "x": p["x"],
                        "y": p["y"],
                    })
                    if net_name:
                        net_id = f"net-{net_name}"
                        if net_name not in nets_seen:
                            sc, rl = net_scope_and_role(net_name)
                            nets_seen[net_name] = {"id": net_id, "name": net_name, "scope": sc, "role": rl}
                        connections_ir.append({
                            "componentId": cid,
                            "pinNumber": pnum,
                            "netId": net_id,
                            "kind": "netlist",
                        })
                        pol = NET_POLICIES[net_name]
                        if pol == "direct":
                            internal_nets.add(net_id)
                        elif pol == "module_port":
                            port_nets.setdefault(net_name, []).append(f"{cid}:{pnum}")
                comp_ir_list.append({
                    "id": cid,
                    "ref": ref,
                    "role": role,
                    "pageId": puuid,
                    "pageName": pname,
                    "device": {
                        "libraryUuid": lib_uuid,
                        "deviceUuid": dev_uuid,
                        "name": orig.get("manufacturerId") or orig["component"]["name"],
                    },
                    "footprint": orig["footprint"]["name"],
                    "placement": {
                        "x": pl["x"],
                        "y": pl["y"],
                        "rotation": pl["rotation"],
                        "mirror": bool(pl["mirror"]),
                        "bbox": pl["bbox"],
                    },
                    "pins": ir_pins,
                })
            ports_ir = [
                {"id": f"port-{zid}-{nname}", "name": nname, "netId": f"net-{nname}", "pinRefs": prefs}
                for nname, prefs in sorted(port_nets.items())
            ]
            conn_modules_ir.append({
                "id": zid,
                "name": ztitle,
                "coreComponents": [core_id] if core_id else [],
                "peripheralComponents": periph_ids,
                "internalNets": sorted(internal_nets),
                "ports": ports_ir,
            })
            geom_modules_ir.append({
                "id": zid,
                "title": ztitle,
                "placements": layout["placements"],
                "wires": layout["wires"],
                "flags": layout["flags"],
            })

        sheet_meta = pobj["sheet"]
        comp_doc = {
            "schemaVersion": 1,
            "connectivity": {
                "schemaVersion": "1.4",
                "projectId": PROJECT,
                "documentId": puuid,
                "components": comp_ir_list,
                "nets": list(nets_seen.values()),
                "connections": connections_ir,
                "modules": conn_modules_ir,
            },
            "sheet": sheet_meta["bounds"],
            "sheetBorder": sheet_meta["border"],
            "keepouts": sheet_meta["keepouts"],
            "titleBlock": {
                "Name": {"value": ptitle, "showTitle": False, "showValue": True},
                "Description": {"value": "TLSR SWire Flasher (E180-Z6907A + USB-C + AP63203WU-7)", "showTitle": False, "showValue": True},
                "Drawed": {"value": "Antigravity", "showTitle": False, "showValue": True},
            },
            "modules": geom_modules_ir,
        }
        comp_path = os.path.join(WORK_DIR, f"composition-p{page_idx}.json")
        with open(comp_path, "w", encoding="utf-8") as f:
            json.dump(comp_doc, f, ensure_ascii=False, indent=2)

        # Apply to live page (sch compose --replace compares against before_fresh and resets only if differing)
        cli(["doc", "open", puuid, "--project", PROJECT])
        ensure_sheet_titleblock(puuid, ptitle)

        before_fp = os.path.join(WORK_DIR, f"before-p{page_idx}.json")
        before_fresh = cli([
            "sch", "list", "--project", PROJECT, "--doc", puuid,
            "--include-device-identity", "--include-pins", "--include-bbox",
            "--include-wires", "--include-page-primitives",
        ], parse_json=True)
        with open(before_fp, "w", encoding="utf-8") as f:
            json.dump(before_fresh, f, ensure_ascii=False, indent=2)

        # Skip destructive re-apply if the exact expected components & wires already exist on this page
        bf_res = before_fresh.get("result", before_fresh)
        exp_refs = sorted(c["ref"] for c in comp_ir_list)
        got_refs = sorted(c["designator"] for c in bf_res.get("components", []) if c.get("designator") and c.get("componentType") != "sheet")
        if exp_refs == got_refs and page_idx < len(ZONES_BY_PAGE) and len(bf_res.get("wires", [])) > 0:
            print(f"  ✓ {pname}: already matches {len(exp_refs)} components, skipping re-apply", flush=True)
        else:
            plan_fp = os.path.join(WORK_DIR, f"plan-p{page_idx}.json")
            play_fp = os.path.join(WORK_DIR, f"apply-p{page_idx}.json")
            cli([
                "sch", "compose",
                "--from", comp_path, "--layout-page", page_path,
                "--out", plan_fp, "--before", before_fp,
                "--replace", "--preserve-instances", "--playbook", play_fp,
            ])
            # Cross-page module_port nets look 1-pin until the final page exists; relax --strict on intermediate pages only
            if page_idx < len(ZONES_BY_PAGE):
                pdata = json.load(open(play_fp, encoding="utf-8"))
                for st in pdata.get("steps", []):
                    if st.get("id") == "strict-schematic-gate" and "flags" in st:
                        st["flags"]["strict"] = False
                with open(play_fp, "w", encoding="utf-8") as f:
                    json.dump(pdata, f, ensure_ascii=False, indent=2)
            cli(["sch", "apply", play_fp, "--dry-run"])
            cli(["sch", "apply", play_fp, "--yes"])
            ensure_sheet_titleblock(puuid, ptitle)

        sv = cli(["sch", "save", "--project", PROJECT, "--doc", puuid], parse_json=True)
        assert sv.get("result", {}).get("saved") is True, f"{pname} save failed: {sv}"

    # Phase 2: Cold-reload, run STRICT gate (now that all 3 pages are present), and export images for ALL pages
    for page_idx, (pname, ptitle, _) in enumerate(ZONES_BY_PAGE, start=1):
        puuid = page_uuid_by_name[pname]
        cli(["doc", "open", puuid, "--project", PROJECT])
        cli(["doc", "reload", "--project", PROJECT, "--doc", puuid])

        gate_out = cli(["sch", "gate", "--strict", "--project", PROJECT, "--doc", puuid])
        with open(os.path.join(DATA_DIR, f"sch_gate_p{page_idx}.txt"), "w", encoding="utf-8") as f:
            f.write(gate_out)
        print(f"=== {pname} sch gate --strict ===\n" + gate_out.strip(), flush=True)

        cli(["sch", "export-image", "--scope", "page", "--format", "png", "--project", PROJECT, "--doc", puuid, "--window", win,
             "--out", os.path.join(IMG_DIR, f"sch_p{page_idx}.png")])
        cli(["sch", "export-image", "--scope", "page", "--format", "svg", "--project", PROJECT, "--doc", puuid, "--window", win,
             "--out", os.path.join(IMG_DIR, f"sch_p{page_idx}.svg")])

    nets_audit = cli(["sch", "nets", "--project", PROJECT])
    with open(os.path.join(DATA_DIR, "sch_nets_audit.txt"), "w", encoding="utf-8") as f:
        f.write(nets_audit)
    print("=== Cross-page sch nets audit ===\n" + nets_audit.strip(), flush=True)

    conn_all = cli(["sch", "connectivity", "--all-pages", "--project", PROJECT], parse_json=True)
    with open(os.path.join(DATA_DIR, "sch_connectivity_all.json"), "w", encoding="utf-8") as f:
        json.dump(conn_all, f, ensure_ascii=False, indent=2)

    res = conn_all.get("result", conn_all)
    comps = [c for c in res.get("components", []) if c.get("ref")]
    assert len(comps) == len(PART_TYPES), f"Expected {len(PART_TYPES)} components, got {len(comps)}"
    by_ref = {c["ref"]: c for c in comps}
    nets_by_id = {n["id"]: n["name"] for n in res.get("nets", [])}
    cid_to_ref = {c["id"]: c["ref"] for c in comps}
    actual_pin_net = {}
    for cn in res.get("connections", []):
        r = cid_to_ref.get(cn["componentId"])
        if r:
            actual_pin_net[(r, str(cn["pinNumber"]))] = nets_by_id[cn["netId"]]

    for ref, exp_map in PIN_NETS.items():
        c = by_ref[ref]
        for p in c["pins"]:
            pnum = str(p["number"])
            exp_net = exp_map.get(pnum, "")
            got_net = actual_pin_net.get((ref, pnum), "")
            nc_flag = p.get("noConnected", False)
            if exp_net == "":
                assert nc_flag and got_net == "", f"{ref}.{pnum}: expected NC, got {got_net!r} nc={nc_flag}"
            else:
                assert got_net == exp_net, f"{ref}.{pnum}: expected {exp_net!r}, got {got_net!r}"

    print(f"✓ SCHEMATIC APPLIED, SAVED, RELOADED, STRICT-GATED & {len(PART_TYPES)}/{len(PART_TYPES)} PIN-VERIFIED!")


if __name__ == "__main__":
    main()
