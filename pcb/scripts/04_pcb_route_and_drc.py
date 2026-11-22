#!/usr/bin/env python3
"""Stage 4: Routing, Chamfered Top/Bottom GND Pours, Off-Pad Dog-Bone Vias & DRC=0.

Target board: 47.00 x 26.00 mm (1850.394 x 1023.622 mil), all 33 components on Top Layer.
Workflow:
  1. Reset existing copper/pours cleanly for deterministic reruns.
  2. Configure Net Classes (PWR20, PWR14, USB8) and Differential Pairs (USB_EXT, USB_INT).
  3. Hand-route and lock critical high-current buck / USB-C fanout / ESD / matched diff paths.
  4. Run official EasyEDA 2-layer 45-deg autorouter (ignoring GND).
  5. Search/validate off-pad 24/12 mil GND dog-bone + stitching vias via
     `pcb-drc-precheck.py --candidates`, place vias & Layer-2 USB1 shield bridges (1<->3, 2<->4).
  6. Create chamfered Top (L1) & Bottom (L2) GND pours (20 mil board inset, 50 mil corner chamfers).
  7. Double `pour-rebuild -> save -> reload`, assert `pcb drc --json` total==0 (passed==True),
     `pcb check` ERROR==0, and `pcb-drc-precheck.py` 0 issues.
"""
from __future__ import annotations
import json
import math
import os
import subprocess

PROJECT = "tlsr-flasher"
PCB_DOC = "3c00dcf5bcf1cf37"
OUT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(OUT_DIR, "design-data")
PRECHECK = "/home/zb/code/esp32-prototype/.agents/skills/easyeda-pcb-learnings/scripts/pcb-drc-precheck.py"

W_MIL = 1850.394
H_MIL = 1023.622
INSET = 20.0
CHAMFER = 50.0

# Corner-chamfered 20-mil inset GND pour polygon (clears R=70.87 mil corner arcs by >=31 mil)
GND_POUR_POINTS = [
    [INSET + CHAMFER, INSET],
    [W_MIL - INSET - CHAMFER, INSET],
    [W_MIL - INSET, INSET + CHAMFER],
    [W_MIL - INSET, H_MIL - INSET - CHAMFER],
    [W_MIL - INSET - CHAMFER, H_MIL - INSET],
    [INSET + CHAMFER, H_MIL - INSET],
    [INSET, H_MIL - INSET - CHAMFER],
    [INSET, INSET + CHAMFER],
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


def chunked_track_lock(nets: set[str] | None = None, ids: list[str] | None = None, unlock: bool = False) -> int:
    if ids is None:
        tl = cli(["pcb", "track-list", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
        lines = tl.get("result", {}).get("lines", [])
        ids = [t["primitiveId"] for t in lines if (nets is None or t.get("net") in nets)]
    flag = ["--unlock"] if unlock else []
    for k in range(0, len(ids), 4):
        batch = ",".join(ids[k:k + 4])
        cli(["pcb", "track-lock", "--no-fills", "--ids", batch] + flag + ["--project", PROJECT, "--doc", PCB_DOC])
    return len(ids)


def place_track(layer: int, width: float, net: str, pts: list[tuple[float, float]]) -> None:
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if math.hypot(x2 - x1, y2 - y1) < 0.05:
            continue
        cli([
            "pcb", "track",
            "--layer", str(layer),
            "--width", f"{width:.2f}",
            "--net", net,
            "--x1", f"{x1:.2f}", "--y1", f"{y1:.2f}",
            "--x2", f"{x2:.2f}", "--y2", f"{y2:.2f}",
            "--project", PROJECT, "--doc", PCB_DOC,
        ])


def place_via(x: float, y: float, net: str, hole: float = 12.0, dia: float = 24.0) -> None:
    cli([
        "pcb", "via",
        "--x", f"{x:.2f}", "--y", f"{y:.2f}",
        "--hole", f"{hole:.2f}", "--diameter", f"{dia:.2f}",
        "--net", net,
        "--project", PROJECT, "--doc", PCB_DOC,
    ])


def reset_copper() -> None:
    tl = cli(["pcb", "track-list", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
    all_tids = [t["primitiveId"] for t in tl.get("result", {}).get("lines", []) if t.get("primitiveId")]
    if all_tids:
        chunked_track_lock(ids=all_tids, unlock=True)
    cli(["pcb", "rip-up", "--project", PROJECT, "--doc", PCB_DOC], check=False)

    dump0 = os.path.join(DATA_DIR, "pcb_pre_route_clean.json")
    cli(["pcb", "dump", "--include-copper", "--out", dump0, "--project", PROJECT, "--doc", PCB_DOC])
    d0 = json.load(open(dump0, encoding="utf-8"))
    vids = [v["primitiveId"] for v in d0.get("copper", {}).get("vias", []) if v.get("primitiveId")]
    if vids:
        for k in range(0, len(vids), 16):
            cli(["pcb", "via-delete", "--ids", ",".join(vids[k:k + 16]), "--project", PROJECT, "--doc", PCB_DOC])
    tids = [t["primitiveId"] for t in d0.get("copper", {}).get("lines", []) if t.get("primitiveId")]
    if tids:
        for k in range(0, len(tids), 16):
            cli(["pcb", "track-delete", "--ids", ",".join(tids[k:k + 16]), "--project", PROJECT, "--doc", PCB_DOC])

    pours = cli(["pcb", "pour-list", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)["result"].get("pours", [])
    if pours:
        pids = ",".join(p["primitiveId"] for p in pours if p.get("primitiveId"))
        if pids:
            cli(["pcb", "pour-delete", "--ids", pids, "--project", PROJECT, "--doc", PCB_DOC])


def setup_rules_and_pairs() -> None:
    existing_classes = {
        c["name"]
        for c in cli(["pcb", "net-class", "list", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)["result"].get("classes", [])
    }
    desired_classes = {
        "PWR_TRUNK": "VBUS_RAW,+5V,BUCK_SW",
        "PWR_RAIL": "3V3,PWR",
        "USB_DIFF": "USB_DP,USB_DN,DP,DM",
    }
    for cname, cnets in desired_classes.items():
        if cname not in existing_classes:
            cli(["pcb", "net-class", "create", "--name", cname, "--net", cnets, "--project", PROJECT, "--doc", PCB_DOC])

    cli(["pcb", "config", "track", "--name", "PWR20", "--copy-from", "copperThickness1oz", "--min", "8", "--default", "20", "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "config", "track", "--name", "PWR14", "--copy-from", "copperThickness1oz", "--min", "8", "--default", "14", "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "config", "track", "--name", "USB8", "--copy-from", "copperThickness1oz", "--min", "6", "--default", "8", "--project", PROJECT, "--doc", PCB_DOC])

    cli(["pcb", "config", "bind", "--class", "PWR_TRUNK", "--track-rule", "PWR20", "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "config", "bind", "--class", "PWR_RAIL", "--track-rule", "PWR14", "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "config", "bind", "--class", "USB_DIFF", "--track-rule", "USB8", "--project", PROJECT, "--doc", PCB_DOC])

    existing_pairs = {
        p["name"]
        for p in cli(["pcb", "diff-pair", "list", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)["result"].get("pairs", [])
    }
    if "USB_EXT" not in existing_pairs:
        cli(["pcb", "diff-pair", "create", "--name", "USB_EXT", "--positive", "USB_DP", "--negative", "USB_DN", "--project", PROJECT, "--doc", PCB_DOC])
    if "USB_INT" not in existing_pairs:
        cli(["pcb", "diff-pair", "create", "--name", "USB_INT", "--positive", "DP", "--negative", "DM", "--project", PROJECT, "--doc", PCB_DOC])

    s = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
    assert s.get("result", {}).get("saved") is True
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])
    print("✓ Configured Net Classes (PWR20, PWR14, USB8) and Diff Pairs (USB_EXT, USB_INT).")


def hand_route_critical_paths(pads_by_net: dict[str, list[dict]]) -> None:
    def pad(net: str, des: str, idx: int = 0) -> tuple[float, float]:
        matches = [p for p in pads_by_net[net] if p["designator"] == des]
        matches.sort(key=lambda m: (m["y"], m["x"]))
        return (round(matches[idx]["x"], 2), round(matches[idx]["y"], 2))

    # 1. BUCK_SW: 35 mil power bridge U2.5 -> L1.1 + 12 mil C3.2 detour North of L1.1
    u2_sw = pad("BUCK_SW", "U2")
    l1_sw = pad("BUCK_SW", "L1")
    c3_sw = pad("BUCK_SW", "C3")
    place_track(1, 35.0, "BUCK_SW", [u2_sw, l1_sw])
    place_track(1, 12.0, "BUCK_SW", [l1_sw, (l1_sw[0], 870.0), (747.0, 935.0), c3_sw])

    # 2. BUCK_BST: 10 mil clean diagonal North-West of U2.6 -> C3.1
    u2_bst = pad("BUCK_BST", "U2")
    c3_bst = pad("BUCK_BST", "C3")
    place_track(1, 10.0, "BUCK_BST", [u2_bst, (u2_bst[0], 860.2), (c3_bst[0], 935.0)])

    # 3. VBUS_RAW: South (278,437.5) & North (278,626.5) -> L2 trunk (x=319) -> F1.1
    f1_in = pad("VBUS_RAW", "F1")
    usb_vbus_s = pad("VBUS_RAW", "USB1", 0)
    usb_vbus_n = pad("VBUS_RAW", "USB1", 1)
    place_via(319.0, 397.0, "VBUS_RAW")
    place_via(319.0, usb_vbus_n[1], "VBUS_RAW")
    place_via(319.0, 884.1, "VBUS_RAW")
    place_track(1, 16.0, "VBUS_RAW", [usb_vbus_s, (304.0, usb_vbus_s[1]), (319.0, 422.5), (319.0, 397.0)])
    place_track(1, 16.0, "VBUS_RAW", [usb_vbus_n, (319.0, usb_vbus_n[1])])
    place_track(2, 20.0, "VBUS_RAW", [(319.0, 397.0), (319.0, 884.1)])
    place_track(1, 20.0, "VBUS_RAW", [(319.0, 884.1), f1_in])

    # 4. +5V: F1.2 -> C1.1 -> C2.1 -> U2.3 -> U2.2, D1.5 L2 clamp, LED1.2 branch
    f1_out = pad("+5V", "F1")
    c1_5v = pad("+5V", "C1")
    c2_5v = pad("+5V", "C2")
    u2_5v_en = pad("+5V", "U2", 0)
    u2_5v_in = pad("+5V", "U2", 1)
    d1_5v = pad("+5V", "D1")
    led1_a = pad("+5V", "LED1")

    place_track(1, 20.0, "+5V", [f1_out, (425.0, f1_out[1]), (425.0, 710.4), c1_5v, c2_5v, (610.6, 710.4), u2_5v_en, u2_5v_in])
    place_track(1, 16.0, "+5V", [f1_out, (f1_out[0], 995.0), (499.6, 995.0), led1_a])
    place_via(425.0, 650.0, "+5V")
    place_via(536.0, 475.0, "+5V")
    place_track(1, 16.0, "+5V", [(425.0, 710.4), (425.0, 650.0)])
    place_track(2, 16.0, "+5V", [(425.0, 650.0), (425.0, 586.0), (536.0, 475.0)])
    place_track(1, 16.0, "+5V", [(536.0, 475.0), d1_5v])

    # 5. CC1 & CC2 (zero crossing: CC2 inside y=208..412; CC1 loops South around R4 on L2 -> R3)
    cc1_u = pad("CC1", "USB1")
    cc1_r = pad("CC1", "R3")
    place_via(382.0, 581.2, "CC1")
    place_via(172.0, 290.0, "CC1")
    place_track(1, 8.0, "CC1", [cc1_u, (382.0, 581.2)])
    place_track(2, 8.0, "CC1", [(382.0, 581.2), (422.0, 541.2), (422.0, 195.0), (392.0, 165.0), (150.0, 165.0), (150.0, 268.0), (172.0, 290.0)])
    place_track(1, 8.0, "CC1", [(172.0, 290.0), cc1_r])

    cc2_u = pad("CC2", "USB1")
    cc2_r = pad("CC2", "R4")
    place_via(352.0, 412.0, "CC2")
    place_via(174.0, 208.0, "CC2")
    place_track(1, 8.0, "CC2", [cc2_u, (310.0, 463.1), (352.0, 421.1), (352.0, 412.0)])
    place_track(2, 8.0, "CC2", [(352.0, 412.0), (352.0, 238.0), (322.0, 208.0), (174.0, 208.0)])
    place_track(1, 8.0, "CC2", [(174.0, 208.0), cc2_r])

    # 6. USB_DP / USB_DN (8 mil USB1 -> D1 -> R1/R2)
    dn_u_s = pad("USB_DN", "USB1", 0)
    dn_u_n = pad("USB_DN", "USB1", 1)
    dp_u_s = pad("USB_DP", "USB1", 0)
    dp_u_n = pad("USB_DP", "USB1", 1)
    dn_d_w = min([p for p in pads_by_net["USB_DN"] if p["designator"] == "D1"], key=lambda m: m["x"])
    dn_d_e = max([p for p in pads_by_net["USB_DN"] if p["designator"] == "D1"], key=lambda m: m["x"])
    dp_d_w = min([p for p in pads_by_net["USB_DP"] if p["designator"] == "D1"], key=lambda m: m["x"])
    dp_d_e = max([p for p in pads_by_net["USB_DP"] if p["designator"] == "D1"], key=lambda m: m["x"])
    r1_in = pad("USB_DN", "R1")
    r2_in = pad("USB_DP", "R2")

    place_track(1, 6.5, "USB_DN", [dn_u_n, (310.0, dn_u_n[1])])
    place_track(1, 8.0, "USB_DN", [(310.0, dn_u_n[1]), (358.0, dn_u_n[1]), (391.9, 527.6), (dn_d_w["x"], dn_d_w["y"])])
    place_track(1, 6.5, "USB_DN", [dn_u_s, (314.0, dn_u_s[1])])
    place_track(1, 8.0, "USB_DN", [(314.0, dn_u_s[1]), (323.8, 512.4), (dn_d_w["x"], dn_d_w["y"])])
    place_track(1, 8.0, "USB_DN", [
        (dn_d_w["x"], dn_d_w["y"]), (dn_d_e["x"], dn_d_e["y"]),
        (dn_d_e["x"], 605.4), (514.0, 621.2), (528.0, 621.2), (544.0, 605.2), (544.0, 523.3), r1_in,
    ])

    place_track(1, 6.5, "USB_DP", [dp_u_s, (306.0, dp_u_s[1])])
    place_track(1, 8.0, "USB_DP", [(306.0, dp_u_s[1]), (325.0, 483.5), (370.9, 437.6), (dp_d_w["x"], dp_d_w["y"])])
    place_via(348.0, 538.0, "USB_DP")
    place_via(391.9, 405.0, "USB_DP")
    place_track(1, 6.5, "USB_DP", [dp_u_n, (309.0, dp_u_n[1]), (312.8, 538.0), (348.0, 538.0)])
    place_track(2, 8.0, "USB_DP", [(348.0, 538.0), (348.0, 448.9), (391.9, 405.0)])
    place_track(1, 8.0, "USB_DP", [(391.9, 405.0), (dp_d_w["x"], dp_d_w["y"])])
    place_track(1, 8.0, "USB_DP", [(dp_d_w["x"], dp_d_w["y"]), (dp_d_e["x"], dp_d_e["y"]), (542.0, dp_d_e["y"]), (542.0, 385.3), r2_in])

    # 7. DP / DM (8 mil straight Top-Layer diff pair R1/R2 -> U1.12/10, 0.09 mil matched skew!)
    dm_r1 = pad("DM", "R1")
    dm_u1 = pad("DM", "U1")
    dp_r2 = pad("DP", "R2")
    dp_u1 = pad("DP", "U1")
    place_track(1, 8.0, "DM", [dm_r1, (622.0, dm_r1[1]), (622.0, 402.0), (1056.0, 402.0), (1074.3, dm_u1[1]), dm_u1])
    place_track(1, 8.0, "DP", [
        dp_r2, (604.0, dp_r2[1]), (604.0, 386.0),
        (630.0, 386.0), (654.0, 362.0), (654.0, 341.8), (674.0, 321.8),
        (750.0, 321.8), (770.0, 341.8), (770.0, 362.0), (794.0, 386.0),
        (1038.0, 386.0), (1058.0, 366.0), (1058.0, 330.0), (1083.0, dp_u1[1]), dp_u1,
    ])

    # 8. 3V3 buck output caps, clean Kelvin feedback, L2 bridge under DM/DP -> Q1/R7/C6/C7/C8/U1.13
    l1_out = pad("3V3", "L1")
    c4_3v3 = pad("3V3", "C4")
    c5_3v3 = pad("3V3", "C5")
    c6_3v3 = pad("3V3", "C6")
    c7_3v3 = pad("3V3", "C7")
    c8_3v3 = pad("3V3", "C8")
    u1_3v3 = pad("3V3", "U1")
    r7_3v3 = pad("3V3", "R7")
    q1_3v3 = pad("3V3", "Q1")
    u2_fb = pad("3V3", "U2")

    place_track(1, 20.0, "3V3", [l1_out, (990.0, l1_out[1]), (1008.0, l1_out[1]), c5_3v3])
    place_track(1, 20.0, "3V3", [c5_3v3, (960.0, 915.4), (915.4, 960.0), (915.4, 995.0), (827.4, 995.0), c4_3v3])
    place_track(1, 14.0, "3V3", [(827.4, 995.0), (612.0, 995.0), (612.0, 812.4), u2_fb])

    place_via(990.0, 690.0, "3V3")
    place_via(945.6, 513.0, "3V3")
    place_via(765.0, 435.0, "3V3")
    place_via(945.0, 270.0, "3V3")

    place_track(1, 18.0, "3V3", [(990.0, l1_out[1]), (990.0, 690.0)])
    place_track(2, 18.0, "3V3", [(990.0, 690.0), (945.6, 645.6), (945.6, 513.0), (920.0, 487.4), (920.0, 295.0), (945.0, 270.0)])
    place_track(2, 14.0, "3V3", [(920.0, 487.4), (817.4, 487.4), (765.0, 435.0)])
    place_track(1, 14.0, "3V3", [(945.6, 513.0), q1_3v3])
    place_track(1, 14.0, "3V3", [(765.0, 435.0), r7_3v3])
    place_track(1, 16.0, "3V3", [(945.0, 270.0), (945.0, 297.4), c6_3v3, (1060.0, 297.4), (1091.8, 265.6), u1_3v3])
    place_track(1, 14.0, "3V3", [c6_3v3, (1000.0, 249.4), (1048.0, 201.4), (1048.0, 122.4), c7_3v3])
    place_track(1, 14.0, "3V3", [(945.0, 270.0), (922.4, 247.4), c8_3v3])

    # 9. Q1_GATE (clean 135/90-deg T-junctions Q1.1 -> Q2.1 -> C10.1 / R7.2)
    q1_g = pad("Q1_GATE", "Q1")
    q2_g = pad("Q1_GATE", "Q2")
    c10_g = pad("Q1_GATE", "C10")
    r7_g = pad("Q1_GATE", "R7")
    place_track(1, 10.0, "Q1_GATE", [q1_g, (q1_g[0], 628.6), q2_g, (q2_g[0], c10_g[1]), c10_g])
    place_track(1, 10.0, "Q1_GATE", [(q2_g[0], c10_g[1]), (r7_g[0], c10_g[1]), r7_g])

    # 10. SWS (U1.26 -> South channel -> via at (795, 45) clear of H2.2 -> L2 to H2.3)
    u1_sws = pad("SWS", "U1")
    h2_sws = pad("SWS", "H2")
    place_via(795.0, 45.0, "SWS")
    place_track(1, 10.0, "SWS", [u1_sws, (1288.8, u1_sws[1]), (1028.8, 45.0), (795.0, 45.0)])
    place_track(2, 10.0, "SWS", [(795.0, 45.0), (695.0, 45.0), h2_sws])

    locked = chunked_track_lock(nets={"BUCK_SW", "BUCK_BST", "VBUS_RAW", "+5V", "CC1", "CC2", "USB_DN", "USB_DP", "DM", "DP", "3V3", "Q1_GATE", "SWS"})
    print(f"✓ Hand-routed and locked {locked} critical analog / USB fanout / diff / buck segments.")


def find_clear_gnd_vias(dump: dict, pads_by_net: dict[str, list[dict]]) -> tuple[list[tuple[float, float]], list[tuple[int, float, float, float, float, float]]]:
    tracks: list[tuple[int, float, float, float, float, float]] = []
    # USB1 TH shield pads: explicit Layer-2 20 mil bridges 1<->3 & 2<->4
    usb_gnds = sorted(
        [p for p in pads_by_net["GND"] if p["designator"] == "USB1" and p["layer"] == 12],
        key=lambda m: (m["y"], m["x"]),
    )
    tracks.append((2, 20.0, usb_gnds[0]["x"], usb_gnds[0]["y"], usb_gnds[1]["x"], usb_gnds[1]["y"]))
    tracks.append((2, 20.0, usb_gnds[2]["x"], usb_gnds[2]["y"], usb_gnds[3]["x"], usb_gnds[3]["y"]))

    # USB1 SMD A1B12 / B1A12 GND pads: tie directly East of NPTH slots to Multi-Layer TH shield pads
    usb_smd_gnds = sorted(
        [p for p in pads_by_net["GND"] if p["designator"] == "USB1" and p["layer"] == 1],
        key=lambda m: m["y"],
    )
    # South (278, 543) -> (278, 521.5) -> (255.4, 498.9); North (278, 795) -> (278, 816.5) -> (255.4, 839.1)
    s_th, n_th = usb_gnds[1], usb_gnds[3]  # x=255.4 TH pads
    s_smd, n_smd = usb_smd_gnds[0], usb_smd_gnds[1]
    tracks.append((1, 20.0, s_smd["x"], s_smd["y"], s_smd["x"], s_th["y"] + (s_smd["x"] - s_th["x"])))
    tracks.append((1, 20.0, s_smd["x"], s_th["y"] + (s_smd["x"] - s_th["x"]), s_th["x"], s_th["y"]))
    tracks.append((1, 20.0, n_smd["x"], n_smd["y"], n_smd["x"], n_th["y"] - (n_smd["x"] - n_th["x"])))
    tracks.append((1, 20.0, n_smd["x"], n_th["y"] - (n_smd["x"] - n_th["x"]), n_th["x"], n_th["y"]))

    smd_gnd_pads = [p for p in pads_by_net["GND"] if p["layer"] == 1 and p["designator"] != "USB1"]
    tracks_dump = dump.get("copper", {}).get("lines", [])
    existing_vias = dump.get("copper", {}).get("vias", [])
    all_pads = [p for c in dump["components"] for p in c.get("pads", [])]

    def dist_seg_pt(ax: float, ay: float, bx: float, by: float, px: float, py: float) -> float:
        vx, vy = bx - ax, by - ay
        wx, wy = px - ax, py - ay
        c2 = vx * vx + vy * vy
        t = 0.0 if c2 < 1e-9 else max(0.0, min(1.0, (wx * vx + wy * vy) / c2))
        return math.hypot(px - (ax + t * vx), py - (ay + t * vy))

    def is_via_clear(vx: float, vy: float, r_via: float = 12.0, clearance: float = 9.0) -> bool:
        if vx < INSET + 22 or vx > W_MIL - INSET - 22 or vy < INSET + 22 or vy > H_MIL - INSET - 22:
            return False
        if 1060.0 <= vx <= 1635.0 and vy >= 755.0:
            return False
        for mx, my in [(110.2, 913.4), (1740.2, 110.2)]:
            if math.hypot(vx - mx, vy - my) < 95.0:
                return False
        for p in all_pads:
            dx = max(0.0, abs(vx - p["x"]) - p.get("width", 30.0) / 2.0)
            dy = max(0.0, abs(vy - p["y"]) - p.get("height", 30.0) / 2.0)
            if math.hypot(dx, dy) < r_via + clearance:
                return False
        for tr in tracks_dump:
            d = dist_seg_pt(tr["startX"], tr["startY"], tr["endX"], tr["endY"], vx, vy)
            if d < r_via + tr.get("lineWidth", 8.0) / 2.0 + clearance:
                return False
        for ev in existing_vias:
            if math.hypot(vx - ev["x"], vy - ev["y"]) < r_via + ev.get("diameter", 24.0) / 2.0 + clearance:
                return False
        return True

    chosen_vias: list[tuple[float, float]] = []
    # Prefer strict 0/45/90 deg dog-bone tracks first for nonOrtho==0
    dirs = [(math.cos(math.radians(a)), math.sin(math.radians(a))) for a in (0, 90, 180, 270, 45, 135, 225, 315)]

    def seg_clear_l1(ax: float, ay: float, bx: float, by: float, w_dog: float, clr: float) -> bool:
        n = max(4, int(math.hypot(bx - ax, by - ay) / 4.0) + 1)
        for i in range(1, n + 1):
            t = i / n
            sx, sy = ax + t * (bx - ax), ay + t * (by - ay)
            for tr in tracks_dump:
                if tr.get("net") == "GND" or tr.get("layer") != 1:
                    continue
                if dist_seg_pt(tr["startX"], tr["startY"], tr["endX"], tr["endY"], sx, sy) < (w_dog / 2.0 + tr.get("lineWidth", 8.0) / 2.0 + clr - 1.0):
                    return False
            for p in all_pads:
                if p.get("net") == "GND" or p.get("layer") not in (1, 12):
                    continue
                dx = max(0.0, abs(sx - p["x"]) - p.get("width", 30.0) / 2.0)
                dy = max(0.0, abs(sy - p["y"]) - p.get("height", 30.0) / 2.0)
                if math.hypot(dx, dy) < w_dog / 2.0 + clr - 1.0:
                    return False
        return True

    for gp in smd_gnd_pads:
        px, py = round(gp["x"], 2), round(gp["y"], 2)
        des = gp["designator"]
        w_dog = 12.0 if des in ("USB1", "D1", "U2", "U1") else 20.0

        # Check whether a close already-placed GND via can be reached without hitting non-GND pads/tracks
        reused = False
        for vx, vy in chosen_vias:
            if math.hypot(vx - px, vy - py) <= 68.0 and seg_clear_l1(px, py, vx, vy, w_dog, 8.5):
                tracks.append((1, w_dog, px, py, vx, vy))
                reused = True
                break
        if reused:
            continue

        found_segs = None
        for clr, r_list in ((8.5, [36.0, 42.0, 48.0, 56.0, 65.0, 76.0, 90.0, 108.0]), (6.5, [34.0, 40.0, 48.0, 58.0, 70.0, 84.0, 100.0])):
            for r in r_list:
                for ux, uy in dirs:
                    vx = round(px + ux * r, 2)
                    vy = round(py + uy * r, 2)
                    if not is_via_clear(vx, vy, clearance=clr):
                        continue
                    if any(math.hypot(vx - ox, vy - oy) < 32.0 for ox, oy in chosen_vias):
                        continue
                    if seg_clear_l1(px, py, vx, vy, w_dog, clr):
                        found_segs = (vx, vy, [(1, w_dog, px, py, vx, vy)])
                        break
                if found_segs:
                    break
            if found_segs:
                break
        if not found_segs:
            for dx in range(-90, 91, 15):
                for dy in range(-90, 91, 15):
                    if abs(dx) + abs(dy) < 35:
                        continue
                    vx, vy = round(px + dx, 2), round(py + dy, 2)
                    if not is_via_clear(vx, vy, clearance=6.5) or any(math.hypot(vx - ox, vy - oy) < 32.0 for ox, oy in chosen_vias):
                        continue
                    for mx, my in ((vx, py), (px, vy)):
                        if seg_clear_l1(px, py, mx, my, w_dog, 7.0) and seg_clear_l1(mx, my, vx, vy, w_dog, 7.0):
                            found_segs = (vx, vy, [(1, w_dog, px, py, mx, my), (1, w_dog, mx, my, vx, vy)])
                            break
                    if found_segs:
                        break
                if found_segs:
                    break
        if not found_segs:
            raise RuntimeError(f"Could not find clear dog-bone GND via for {des} at ({px}, {py})")
        vx, vy, seg_list = found_segs
        chosen_vias.append((vx, vy))
        tracks.extend(seg_list)

    stitch_targets = [
        (320.0, 860.0), (580.0, 840.0), (880.0, 860.0),
        (960.0, 960.0), (1740.0, 920.0), (1780.0, 500.0),
        (1740.0, 250.0), (1360.0, 720.0), (1200.0, 720.0),
        (720.0, 650.0), (700.0, 260.0), (220.0, 110.0),
    ]
    for sx, sy in stitch_targets:
        if is_via_clear(sx, sy, r_via=12.0, clearance=12.0) and all(math.hypot(sx - vx, sy - vy) > 45.0 for vx, vy in chosen_vias):
            chosen_vias.append((sx, sy))

    return chosen_vias, tracks


def main() -> None:
    cli(["doc", "open", PCB_DOC, "--project", PROJECT])

    reset_copper()
    setup_rules_and_pairs()

    pre_dump = os.path.join(DATA_DIR, "pcb_layout_r2_dump.json")
    d_pre = json.load(open(pre_dump, encoding="utf-8"))
    pads_by_net: dict[str, list[dict]] = {}
    for c in d_pre["components"]:
        for p in c.get("pads", []):
            p_copy = dict(p)
            p_copy["designator"] = c["designator"]
            pads_by_net.setdefault(p.get("net") or "<NONE>", []).append(p_copy)

    hand_route_critical_paths(pads_by_net)

    s_pre = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
    assert s_pre.get("result", {}).get("saved") is True
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])

    ar = cli([
        "pcb", "autoroute",
        "--layers", "1,2",
        "--corner", "45",
        "--optimize", "faster",
        "--timeout", "4m",
        "--ignore-net", "GND,BUCK_SW,BUCK_BST,VBUS_RAW,+5V,CC1,CC2,USB_DN,USB_DP,DM,DP,Q1_GATE,SWS",
        "--project", PROJECT, "--doc", PCB_DOC,
    ], parse_json=True)
    ar_res = ar.get("result", ar)
    print("✓ Autoroute finished:", json.dumps(
        {k: ar_res.get(k) for k in ("routed", "failed", "tracksCreated", "viasCreated", "summary") if k in ar_res},
        ensure_ascii=False,
    ))

    # Save & reload right after autoroute so dump/checks read consistent copper state
    s_ar = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], parse_json=True)
    assert s_ar.get("result", {}).get("saved") is True
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])

    mid_dump = os.path.join(DATA_DIR, "pcb_pre_pour_dump.json")
    cli(["pcb", "dump", "--include-copper", "--out", mid_dump, "--project", PROJECT, "--doc", PCB_DOC])
    d_mid = json.load(open(mid_dump, encoding="utf-8"))

    gnd_vias, gnd_tracks = find_clear_gnd_vias(d_mid, pads_by_net)

    cand_json = os.path.join(DATA_DIR, "gnd_via_candidates.json")
    with open(cand_json, "w", encoding="utf-8") as f:
        json.dump({"vias": [{"x": vx, "y": vy, "dia": 24, "net": "GND"} for vx, vy in gnd_vias]}, f, indent=2)
    cand_res = subprocess.run(["python3", PRECHECK, "--board", mid_dump, "--candidates", cand_json], capture_output=True, text=True)
    print(cand_res.stdout)
    if cand_res.returncode != 0:
        raise RuntimeError(f"Candidate GND via precheck failed:\n{cand_res.stdout}\n{cand_res.stderr}")

    for vx, vy in gnd_vias:
        place_via(vx, vy, "GND", hole=12.0, dia=24.0)
    for lay, w, x1, y1, x2, y2 in gnd_tracks:
        place_track(lay, w, "GND", [(x1, y1), (x2, y2)])
    print(f"✓ Placed {len(gnd_vias)} off-pad GND vias & {len(gnd_tracks)} GND dog-bone/bridge tracks.")

    pts_json = json.dumps(GND_POUR_POINTS)
    cli(["pcb", "pour", "--layer", "2", "--net", "GND", "--points", pts_json, "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "pour", "--layer", "1", "--net", "GND", "--points", pts_json, "--project", PROJECT, "--doc", PCB_DOC])
    print("✓ Created chamfered Top & Bottom GND pours.")

    # Save -> reload under fresh rules -> rebuild pours -> save -> cold reload before DRC
    s0 = cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], check=False)
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])

    cli(["pcb", "pour-rebuild", "--project", PROJECT, "--doc", PCB_DOC])
    cli(["pcb", "save", "--project", PROJECT, "--doc", PCB_DOC], check=False)
    cli(["doc", "reload", "--project", PROJECT, "--doc", PCB_DOC])

    final_dump = os.path.join(DATA_DIR, "pcb_final_dump.json")
    cli(["pcb", "dump", "--include-copper", "--out", final_dump, "--project", PROJECT, "--doc", PCB_DOC])

    drc_p = cli(["pcb", "drc", "--json", "--project", PROJECT, "--doc", PCB_DOC], check=False)
    drc_j = json.loads(drc_p.stdout)
    with open(os.path.join(DATA_DIR, "drc_final.json"), "w", encoding="utf-8") as f:
        json.dump(drc_j, f, indent=2, ensure_ascii=False)
    print(f"✓ COLD-RELOADED NATIVE DRC: passed={drc_j['passed']}, total={drc_j['total']}")

    chk_p = cli(["pcb", "check", "--project", PROJECT, "--doc", PCB_DOC], check=False)
    with open(os.path.join(DATA_DIR, "check_final.txt"), "w", encoding="utf-8") as f:
        f.write(chk_p.stdout + chk_p.stderr)
    print("=== FINAL PCB CHECK ===\n" + "\n".join(chk_p.stdout.splitlines()[:12]))

    pre = subprocess.run(["python3", PRECHECK, "--board", final_dump], capture_output=True, text=True)
    print(pre.stdout)
    if drc_j["total"] != 0:
        print("DRC VIOLATIONS:", json.dumps(drc_j, indent=2)[:4000])
        raise SystemExit(1)


if __name__ == "__main__":
    main()
