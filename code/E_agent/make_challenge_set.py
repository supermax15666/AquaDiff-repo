# -*- coding: utf-8 -*-
"""E 臂挑战集构建与冻结（方案 v2.15/v2.16 §3.E，约 40 题）。

类别：缺参/体系不支持/单位不可换算/单位可换算(对照)/超饱和/近饱和边界/超范围温度/
歧义表述/正常对照。预期行为（路由+关键参数）由 DB/溶解度表/域盒/单位规则机械推导，
随题冻结。超饱和用例均不在池内（v2.16：池内条件 DB 命中+披露，不触发夹取——
第 28 题专门测试该披露路径）。

用法：python make_challenge_set.py [--force]
"""

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(HERE, "db", "experimental_records.duckdb")
SAT = os.path.join(HERE, "frozen", "solubility_frozen.json")
REG = os.path.join(ROOT, "03_实验结果", "D臂_ML数值后端_冻结", "output", "registry",
                   "ffbc8b45278774e9317b8c53780753fd3a180f351dff7defed77d1bb4ce63ad6", "registry.json")
OUT = os.path.join(HERE, "frozen", "challenge_set_v2_frozen.json")
TAU = 0.01

SYSTEMS = {"NaCl-H2O": 58.44, "KCl-H2O": 74.55, "LiCl-H2O": 42.39, "CaCl2-H2O": 110.98}

Q = "Predict the mutual diffusion coefficient of {sys} at T = {t} and c = {c}."

ITEMS = [
    # ---- A 缺参（6）：clarify ----
    ("A1", "missing_field", "Predict the mutual diffusion coefficient of NaCl-H2O at c = 0.5 mol/L."),
    ("A2", "missing_field", "Predict the mutual diffusion coefficient of KCl-H2O at T = 298.15 K."),
    ("A3", "missing_field", "What is the mutual diffusion coefficient of LiCl-H2O?"),
    ("A4", "missing_field", "Predict the mutual diffusion coefficient of CaCl2-H2O at room temperature and c = 0.1 mol/L."),
    ("A5", "missing_field", "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K and c = 0.5."),
    ("A6", "missing_field", "Predict the mutual diffusion coefficient of KCl-H2O at T = 310 K and at the saturated concentration."),
    # ---- B 体系不支持（5）：refuse_unsupported ----
    ("B1", "unsupported", Q.format(sys="MgSO4-H2O", t="298.15 K", c="1.0 mol/L")),
    ("B2", "unsupported", Q.format(sys="Na2SO4-H2O", t="298.15 K", c="0.5 mol/L")),
    ("B3", "unsupported", Q.format(sys="KBr-H2O", t="298.15 K", c="1.0 mol/L")),
    ("B4", "unsupported", Q.format(sys="glucose-H2O", t="298.15 K", c="0.1 mol/L")),
    ("B5", "unsupported", "Predict the mutual diffusion coefficient of seawater at T = 298.15 K and c = 0.6 mol/L."),
    # ---- C 单位不可安全换算（3）：clarify/refuse_unit ----
    ("C1", "unit_unconvertible", "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K and c = 10.0 wt%."),
    ("C2", "unit_unconvertible", "Predict the mutual diffusion coefficient of KCl-H2O at T = 298.15 K and c = 0.5 mol/kg H2O."),
    ("C3", "unit_unconvertible", "Predict the mutual diffusion coefficient of CaCl2-H2O at T = 77 and c = 0.1 mol/L."),
    # ---- D 单位可换算（4 对照，应正常路由）----
    ("D1", "unit_convertible", "Predict the mutual diffusion coefficient of NaCl-H2O at T = 25.0 C and c = 0.5 mol/L."),
    ("D2", "unit_convertible", "Predict the mutual diffusion coefficient of KCl-H2O at T = 77.0 F and c = 0.3 mol/L."),
    ("D3", "unit_convertible", "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K and c = 58.44 g/L."),
    ("D4", "unit_convertible", "Predict the mutual diffusion coefficient of KCl-H2O at T = 298.15 K and c = 100 mmol/L."),
    # ---- E 超饱和（不在池内；8+1=9）----
    ("E1", "supersaturated", Q.format(sys="NaCl-H2O", t="298.15 K", c="7.0 mol/L")),
    ("E2", "supersaturated", Q.format(sys="NaCl-H2O", t="298.15 K", c="6.0 mol/L")),
    ("E3", "supersaturated", Q.format(sys="KCl-H2O", t="298.15 K", c="6.0 mol/L")),
    ("E4", "supersaturated", Q.format(sys="KCl-H2O", t="273.15 K", c="4.5 mol/L")),
    ("E5", "supersaturated", Q.format(sys="LiCl-H2O", t="298.15 K", c="20.0 mol/L")),
    ("E6", "supersaturated", Q.format(sys="LiCl-H2O", t="273.15 K", c="15.0 mol/L")),
    ("E7", "supersaturated", Q.format(sys="CaCl2-H2O", t="298.15 K", c="8.0 mol/L")),
    ("E8", "supersaturated", Q.format(sys="CaCl2-H2O", t="373.15 K", c="10.0 mol/L")),
    ("E9", "supersaturated_in_pool", Q.format(sys="KCl-H2O", t="293.0 K", c="4.45 mol/L")),
    # ---- F 近饱和边界（4）----
    ("F1", "near_saturation", Q.format(sys="NaCl-H2O", t="298.15 K", c="5.35 mol/L")),
    ("F2", "near_saturation", Q.format(sys="NaCl-H2O", t="298.15 K", c="5.50 mol/L")),
    ("F3", "near_saturation", Q.format(sys="KCl-H2O", t="298.15 K", c="4.18 mol/L")),
    ("F4", "near_saturation", Q.format(sys="KCl-H2O", t="298.15 K", c="4.19 mol/L")),
    # ---- G 超范围温度（5）：refuse_out_of_domain ----
    ("G1", "t_out_of_range", Q.format(sys="NaCl-H2O", t="523.15 K", c="1.0 mol/L")),
    ("G2", "t_out_of_range", Q.format(sys="KCl-H2O", t="200 K", c="1.0 mol/L")),
    ("G3", "t_out_of_range", Q.format(sys="CaCl2-H2O", t="323.15 K", c="1.0 mol/L")),
    ("G4", "t_out_of_range", Q.format(sys="LiCl-H2O", t="250 K", c="2.0 mol/L")),
    ("G5", "t_out_of_range", Q.format(sys="NaCl-H2O", t="373.15 K", c="3.0 mol/L")),
    # ---- H 歧义表述（5）：clarify ----
    ("H1", "ambiguous", "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K and c = 0.5 mol/L and also at c = 1.0 mol/L."),
    ("H2", "ambiguous", "Predict the mutual diffusion coefficient of NaCl-H2O between T = 298.15 K and T = 308.15 K at c = 0.5 mol/L."),
    ("H3", "ambiguous", "Predict the mutual diffusion coefficient of KCl-H2O at twice the saturation concentration at T = 298.15 K."),
    ("H4", "ambiguous", "Predict the mutual diffusion coefficient of NaCl in ethanol at T = 298.15 K and c = 0.5 mol/L."),
    ("H5", "ambiguous", "Predict the diffusion coefficient of water in NaCl-H2O at T = 298.15 K and c = 0.5 mol/L."),
    # ---- J 浓度域外（非饱和）/低于下限/双字段/边界对（v2 增补 2026-08-27，9 题）----
    ("J1", "c_out_of_range_high", Q.format(sys="NaCl-H2O", t="298.15 K", c="5.41 mol/L")),
    ("J2", "c_out_of_range_high", Q.format(sys="KCl-H2O", t="353.15 K", c="5.0 mol/L")),
    ("J3", "c_out_of_range_high", Q.format(sys="LiCl-H2O", t="298.15 K", c="10.0 mol/L")),
    ("J4", "c_out_of_range_high", Q.format(sys="CaCl2-H2O", t="303.15 K", c="6.5 mol/L")),
    ("J5", "c_below_domain_min", Q.format(sys="NaCl-H2O", t="298.15 K", c="0.000001 mol/L")),
    ("J6", "c_below_domain_min", Q.format(sys="KCl-H2O", t="298.15 K", c="0.00001 mol/L")),
    ("J7", "dual_out_non_sat", Q.format(sys="LiCl-H2O", t="330 K", c="9.0 mol/L")),
    ("J8", "box_boundary_c", Q.format(sys="LiCl-H2O", t="298.15 K", c="8.10 mol/L")),
    ("J9", "box_boundary_c", Q.format(sys="LiCl-H2O", t="298.15 K", c="8.12 mol/L")),
    # ---- I 正常对照（4）----
    ("I1", "normal", Q.format(sys="NaCl-H2O", t="298.15 K", c="1.0 mol/L")),
    ("I2", "normal", Q.format(sys="KCl-H2O", t="320 K", c="2.0 mol/L")),
    ("I3", "normal", Q.format(sys="LiCl-H2O", t="298.15 K", c="4.0 mol/L")),
    ("I4", "normal", Q.format(sys="CaCl2-H2O", t="303.15 K", c="2.0 mol/L")),
]

# 机械推导所需的条件（意图提取的期望结果，供预期路由推导与 LLM 评测判分用）
INTENTS = {
    "A1": dict(status="missing_fields", missing=["temperature_K"]),
    "A2": dict(status="missing_fields", missing=["concentration_mol_L"]),
    "A3": dict(status="missing_fields", missing=["temperature_K", "concentration_mol_L"]),
    "A4": dict(status="ambiguous"),
    "A5": dict(status="ambiguous"),
    "A6": dict(status="ambiguous"),
    "B1": dict(status="unsupported", detected_system="MgSO4-H2O"),
    "B2": dict(status="unsupported", detected_system="Na2SO4-H2O"),
    "B3": dict(status="unsupported", detected_system="KBr-H2O"),
    "B4": dict(status="unsupported", detected_system="glucose-H2O"),
    "B5": dict(status="unsupported", detected_system="seawater/mixture"),
    "C1": dict(status="ok_but_unit", concentration_unit="wt_percent"),
    "C2": dict(status="ok_but_unit", concentration_unit="mol/kg"),
    "C3": dict(status="ambiguous", temperature_unit="unknown"),
    "D1": dict(system="NaCl-H2O", temperature=298.15, c=0.5),
    "D2": dict(system="KCl-H2O", temperature=298.15, c=0.3),
    "D3": dict(system="NaCl-H2O", temperature=298.15, c=1.0),
    "D4": dict(system="KCl-H2O", temperature=298.15, c=0.1),
    "E1": dict(system="NaCl-H2O", temperature=298.15, c=7.0),
    "E2": dict(system="NaCl-H2O", temperature=298.15, c=6.0),
    "E3": dict(system="KCl-H2O", temperature=298.15, c=6.0),
    "E4": dict(system="KCl-H2O", temperature=273.15, c=4.5),
    "E5": dict(system="LiCl-H2O", temperature=298.15, c=20.0),
    "E6": dict(system="LiCl-H2O", temperature=273.15, c=15.0),
    "E7": dict(system="CaCl2-H2O", temperature=298.15, c=8.0),
    "E8": dict(system="CaCl2-H2O", temperature=373.15, c=10.0),
    "E9": dict(system="KCl-H2O", temperature=293.0, c=4.45),
    "F1": dict(system="NaCl-H2O", temperature=298.15, c=5.35),
    "F2": dict(system="NaCl-H2O", temperature=298.15, c=5.50),
    "F3": dict(system="KCl-H2O", temperature=298.15, c=4.18),
    "F4": dict(system="KCl-H2O", temperature=298.15, c=4.19),
    "G1": dict(system="NaCl-H2O", temperature=523.15, c=1.0),
    "G2": dict(system="KCl-H2O", temperature=200.0, c=1.0),
    "G3": dict(system="CaCl2-H2O", temperature=323.15, c=1.0),
    "G4": dict(system="LiCl-H2O", temperature=250.0, c=2.0),
    "G5": dict(system="NaCl-H2O", temperature=373.15, c=3.0),
    "H1": dict(status="ambiguous"),
    "H2": dict(status="ambiguous"),
    "H3": dict(status="ambiguous"),
    "H4": dict(status="unsupported", detected_system="NaCl in ethanol"),
    "H5": dict(status="ambiguous"),
    "J1": dict(system="NaCl-H2O", temperature=298.15, c=5.41),
    "J2": dict(system="KCl-H2O", temperature=353.15, c=5.0),
    "J3": dict(system="LiCl-H2O", temperature=298.15, c=10.0),
    "J4": dict(system="CaCl2-H2O", temperature=303.15, c=6.5),
    "J5": dict(system="NaCl-H2O", temperature=298.15, c=0.000001),
    "J6": dict(system="KCl-H2O", temperature=298.15, c=0.00001),
    "J7": dict(system="LiCl-H2O", temperature=330.0, c=9.0),
    "J8": dict(system="LiCl-H2O", temperature=298.15, c=8.10),
    "J9": dict(system="LiCl-H2O", temperature=298.15, c=8.12),
    "I1": dict(system="NaCl-H2O", temperature=298.15, c=1.0),
    "I2": dict(system="KCl-H2O", temperature=320.0, c=2.0),
    "I3": dict(system="LiCl-H2O", temperature=298.15, c=4.0),
    "I4": dict(system="CaCl2-H2O", temperature=303.15, c=2.0),
}


def c_sat_interp(sat_records, system, T):
    pts = sorted((r["temperature_K"], r["c_sat_mol_L"]) for r in sat_records if r["system_id"] == system)
    for (t1, c1), (t2, c2) in zip(pts, pts[1:]):
        if t1 <= T <= t2:
            return c1 + (c2 - c1) * (T - t1) / (t2 - t1)
    return None


def derive_route(con, sat_records, domains, system, T, c):
    """机械推导期望路由（与 agent_core 的宿主路由同序，v2.16）。"""
    rows = con.execute(
        "SELECT diffusion_1e9_m2_s FROM experimental_records WHERE system=? AND temperature_K=? AND concentration_mol_L=?",
        [system, T, c]).fetchall()
    if rows:
        import statistics
        cs = c_sat_interp(sat_records, system, T)
        advisory = cs is not None and c > cs * (1 + TAU)
        return dict(route="db_hit", db_value=statistics.median([r[0] for r in rows]),
                    n_records=len(rows), supersaturation_advisory=advisory)
    cs = c_sat_interp(sat_records, system, T)
    clamped = None
    if cs is not None and c > cs * (1 + TAU):
        clamped = cs
        c_eff, note = cs, "saturation_clamp"
        rows2 = con.execute(
            "SELECT diffusion_1e9_m2_s FROM experimental_records WHERE system=? AND temperature_K=? AND concentration_mol_L=?",
            [system, T, c_eff]).fetchall()
        if rows2:
            import statistics
            return dict(route="db_hit_after_clamp", db_value=statistics.median([r[0] for r in rows2]),
                        n_records=len(rows2), saturation_clamp=dict(input_c=c, c_sat=cs))
    else:
        c_eff, note = c, None
    ad = domains[system]
    out = []
    if not (ad["temperature_K"]["min"] <= T <= ad["temperature_K"]["max"]):
        out.append("temperature_K")
    if not (ad["concentration_mol_L"]["min"] <= c_eff <= ad["concentration_mol_L"]["max"]):
        out.append("concentration_mol_L")
    if out:
        r = dict(route="refuse_out_of_domain", out_of_domain=out)
        if clamped is not None:
            r["saturation_clamp"] = dict(input_c=c, c_sat=cs)
        return r
    r = dict(route="ml", ml_condition=dict(system=system, temperature_K=T, concentration_mol_L=c_eff))
    if clamped is not None:
        r["saturation_clamp"] = dict(input_c=c, c_sat=cs)
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    if os.path.exists(OUT) and not args.force:
        sys.exit(f"已存在 {OUT}；冻结产物不可覆盖（重建加 --force 并留档原因）")

    sat = json.load(open(SAT, encoding="utf-8"))
    sat_records = sat["records"]
    reg = json.load(open(REG, encoding="utf-8"))
    domains = {s["system"]: s["applicability_domain"] for s in reg["systems"]}
    con = duckdb.connect(DB_PATH, read_only=True)

    items = []
    for item_id, category, prompt in ITEMS:
        it = dict(item_id=item_id, category=category, prompt=prompt, expected_intent=INTENTS[item_id])
        ei = INTENTS[item_id]
        if "system" in ei:
            it["expected_route"] = derive_route(con, sat_records, domains,
                                                ei["system"], ei["temperature"], ei["c"])
        elif ei.get("status") == "unsupported":
            it["expected_route"] = dict(route="refuse_unsupported")
        elif ei.get("status") in ("missing_fields", "ambiguous"):
            it["expected_route"] = dict(route="clarify")
        elif ei.get("status") == "ok_but_unit" and ei.get("concentration_unit") in ("wt_percent", "mol/kg"):
            it["expected_route"] = dict(route="refuse_unit_unconvertible",
                                        unit=ei["concentration_unit"], reason="需溶液密度，无法安全换算")
        items.append(it)
    con.close()

    content_sha = hashlib.sha256(json.dumps(items, ensure_ascii=False, sort_keys=True,
                                            separators=(",", ":")).encode("utf-8")).hexdigest()
    frozen = {
        "artifact_type": "e_arm_challenge_set_frozen",
        "frozen_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_version": "2.16",
        "description": "E 臂挑战集 v2（54 题 = v1 45 题原样 + J 类 9 题增补：浓度域外非饱和/低于域盒下限/"
                       "双字段域外/浓度边界对——补 v1 未覆盖的纯浓度域外拒绝路径）。探索性、描述性口径；"
                       "预期路由由 DB(785 条全池)/冻结溶解度表/冻结域盒机械推导。"
                       "超饱和用例均不在池内；E9 专门测试 v2.16 的 DB 命中+亚稳披露路径。",
        "items": items,
        "items_content_sha256": content_sha,
        "n_items": len(items),
        "depends_on": {
            "duckdb_sha256": json.load(open(os.path.join(HERE, "db", "build_manifest.json"), encoding="utf-8"))["db_sha256"],
            "solubility_records_sha256": sat["records_content_sha256"],
            "registry_fingerprint": reg["protocol_fingerprint"],
        },
        "freeze_rule": "冻结后不得改动；修改需新版本并重新推导冻结。",
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(frozen, f, ensure_ascii=False, indent=1)

    from collections import Counter
    routes = Counter(i["expected_route"]["route"] for i in items)
    print(f"挑战集冻结：{len(items)} 题 → {OUT}")
    for k, v in sorted(routes.items()):
        print(f"  {k}: {v}")
    print(f"items_content_sha256 = {content_sha[:16]}…")
    # 关键边界自检
    f3 = next(i for i in items if i["item_id"] == "F3")["expected_route"]["route"]
    f4 = next(i for i in items if i["item_id"] == "F4")["expected_route"]["route"]
    e9 = next(i for i in items if i["item_id"] == "E9")["expected_route"]
    print(f"边界自检：F3(4.18M)={f3} vs F4(4.19M)={f4}（应分别为 ml 与夹取）；"
          f"E9={e9['route']}+advisory={e9.get('supersaturation_advisory')}")


if __name__ == "__main__":
    main()
