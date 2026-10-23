# -*- coding: utf-8 -*-
"""从 CRC Handbook 92nd ed. 提取四体系溶解度，生成 E 臂饱和安全层录入表。

数据源（主源，唯一采信）：
    CRC Handbook of Chemistry and Physics, 92nd Edition (2011-2012),
    Section 5, "Aqueous Solubility of Inorganic Compounds at Various Temperatures",
    书页 5-190 至 5-195（本 PDF 0 起页索引 1066-1071）。
    原始单位：溶质质量百分数 (100·w2)；固相转变以星号标注在相邻两温度列。
    行引文献：NaCl/KCl/LiCl -> IUPAC Solubility Data Series Vol. 47（表中 ref 1:47）；
              CaCl2 -> Potter & Clynne 1978 (J. Res. USGS 6, 701) /
                        Clynne & Potter 1979 (J. Chem. Eng. Data 24, 338)（表中 ref 8）。

提取值已于 2026-08-25 用以下独立口径核对（详见 溶解度收集日志.md）：
    - CRC 5-199 "Solubility of Common Salts at Ambient Temperatures"（Apelblat molality）
    - Perry's 8th ed. Table 2-1 无机物表 0/100 °C 溶解度锚点
    - 段内平滑性与文献常识量级

用法：
    python extract_solubility_crc.py                     # 生成草稿（无密度，c_sat 留空）
    python extract_solubility_crc.py --density 密度表.csv  # 密度补齐后生成完整表
    （密度表 CSV 列：system_id,temperature_K,density_g_cm3,density_source；
      每体系须单一密度来源；temperature_K 必须与本表 48 个原生温度点一致）

输出（均在 py/E_Agent/）：
    --out 指定文件名，默认 溶解度录入_CRC92_v1_草稿.xlsx（同时写同列 CSV）
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

E_AGENT = Path(__file__).resolve().parent
TEMPLATE = E_AGENT / "饱和度录入模板.xlsx"
ACCESSED = "2026-08-25"
M2 = {"NaCl-H2O": 58.44, "KCl-H2O": 74.55, "LiCl-H2O": 42.39, "CaCl2-H2O": 110.98}

# CRC 5-190 表 12 个原生温度列（°C）
TEMPS_C = [0, 10, 20, 25, 30, 40, 50, 60, 70, 80, 90, 100]

# 四体系原始行：wt% 值与星号位置（True = 该列数值带 *，与其相邻星号列共同括住一次固相转变）。
# 提取自 PDF 页索引 1067 (CaCl2) / 1068 (KCl, LiCl) / 1070 (NaCl)。
CRC_ROWS: dict[str, tuple[str, list[tuple[float, bool]], str]] = {
    "NaCl-H2O": (
        "NaCl: 26.28 26.32 26.41 26.45 26.52 26.67 26.84 27.03 27.25 27.50 27.78 28.05 (无星号)",
        [(26.28, False), (26.32, False), (26.41, False), (26.45, False), (26.52, False),
         (26.67, False), (26.84, False), (27.03, False), (27.25, False), (27.50, False),
         (27.78, False), (28.05, False)],
        "CRC 92nd ed.(2011) 表 5-190–5-195 (PDF p.1070); 行引 IUPAC SDS Vol.47",
    ),
    "KCl-H2O": (
        "KCl: 21.74 23.61 25.39 26.22 27.04 28.59 30.04 31.40 32.66 33.86 34.99 36.05 (无星号)",
        [(21.74, False), (23.61, False), (25.39, False), (26.22, False), (27.04, False),
         (28.59, False), (30.04, False), (31.40, False), (32.66, False), (33.86, False),
         (34.99, False), (36.05, False)],
        "CRC 92nd ed.(2011) 表 5-190–5-195 (PDF p.1068); 行引 IUPAC SDS Vol.47",
    ),
    "LiCl-H2O": (
        "LiCl: 40.45 42.46* 45.29* 45.81 46.25 47.30 48.47 49.78 51.27 52.98 54.98* 56.34* "
        "(星号对: 10-20 °C、90-100 °C)",
        [(40.45, False), (42.46, True), (45.29, True), (45.81, False), (46.25, False),
         (47.30, False), (48.47, False), (49.78, False), (51.27, False), (52.98, False),
         (54.98, True), (56.34, True)],
        "CRC 92nd ed.(2011) 表 5-190–5-195 (PDF p.1068); 行引 IUPAC SDS Vol.47",
    ),
    "CaCl2-H2O": (
        "CaCl2: 36.70 39.19 42.13 44.83* 49.12* 52.85* 56.05* 56.73 57.44 58.21 59.04 59.94 "
        "(星号对: 25-30 °C、40-50 °C)",
        [(36.70, False), (39.19, False), (42.13, False), (44.83, True), (49.12, True),
         (52.85, True), (56.05, True), (56.73, False), (57.44, False), (58.21, False),
         (59.04, False), (59.94, False)],
        "CRC 92nd ed.(2011) 表 5-190–5-195 (PDF p.1067); 行引 Potter & Clynne 1978/1979 (ref 8)",
    ),
}

# 固相分段（依据 CRC 星号对 + Clynne & Potter 1979 实测相变温度佐证；完整论证见收集日志）
SOLID_PHASES: dict[str, list[str]] = {
    "NaCl-H2O": ["anhydrous"] * 12,
    "KCl-H2O": ["anhydrous"] * 12,
    # 0,10 °C -> LiCl·2H2O; 20-90 °C -> LiCl·H2O; 100 °C -> 无水
    # （C&P 1979: 2H2O->H2O 转变 19.73±0.13 °C@45.29 wt%，H2O->无水 95.6±0.3 °C@55.85 wt%；
    #  相变液组成富水侧判据验证分段；2026-08-26 依 C&P 修正，此前 3H2O/2H2O/H2O 分段有误）
    "LiCl-H2O": ["LiCl·2H2O", "LiCl·2H2O"] + ["LiCl·H2O"] * 9 + ["anhydrous"],
    # 0-25 °C -> CaCl2·6H2O; 30,40 °C -> CaCl2·4H2O; 50-100 °C -> CaCl2·2H2O
    # （C&P 1979: 4H2O->2H2O 转变 45.19±0.07 °C@55.73 wt%，与 CRC 曲线外推 55.72 吻合）
    "CaCl2-H2O": ["CaCl2·6H2O"] * 4 + ["CaCl2·4H2O"] * 2 + ["CaCl2·2H2O"] * 6,
}

# CRC 5-199 "Solubility of Common Salts at Ambient Temperatures"（Apelblat，molality，mol/kg）
APELBLAT = {
    "NaCl-H2O": {10: 6.110, 15: 6.121, 20: 6.136, 25: 6.153, 30: 6.174, 35: 6.197, 40: 6.222},
    "LiCl-H2O": {10: 19.296, 15: 19.456, 20: 19.670, 25: 19.935},
}

# Perry's 8th ed. Table 2-1 无机物表溶解度锚点（g/100 g H2O，无水基）
PERRYS_ANCHORS = {
    "NaCl-H2O": {0: 35.7, 100: 39.8},
    "KCl-H2O": {0: 27.6, 100: 56.7},
    "LiCl-H2O": {0: 67.0, 100: 127.5},
}

PHASE_NOTES = {
    "NaCl-H2O": "全程无星号，固相无水 NaCl",
    "KCl-H2O": "全程无星号，固相无水 KCl",
    "LiCl-H2O": "星号对(10,20)=LiCl·2H2O→LiCl·H2O 转变（C&P 1979 实测 19.73±0.13 °C@45.29 wt%，"
                "恰为 CRC 20 °C 值）；星号对(90,100)=LiCl·H2O→无水 LiCl（C&P 1979: 95.6±0.3 °C@55.85 wt%；"
                "CRC 4-1: LiCl·H2O dec 98 °C 一致；相变液组成富水判据验证分段）",
    "CaCl2-H2O": "星号对(25,30)=CaCl2·6H2O→CaCl2·4H2O（CRC 4-1: 6H2O dec 30 °C）；"
                 "星号对(40,50)=CaCl2·4H2O→CaCl2·2H2O（C&P 1979 实测 45.19±0.07 °C@55.73 wt%，"
                 "与 CRC 曲线外推 55.72 吻合；4-1: 2H2O dec 175 °C，50–100 °C 段一致）",
}


def wt_to_molality(wt: float, m2: float) -> float:
    return 1000.0 * (wt / 100.0) / (m2 * (1.0 - wt / 100.0))


def wt_to_g_per_100g(wt: float) -> float:
    return 100.0 * (wt / 100.0) / (1.0 - wt / 100.0)


def report_checks() -> list[str]:
    """结构自检：覆盖、段内单调、平滑性、交叉核对。返回人类可读报告行。"""
    lines = []
    ok = True
    for sys_id, (raw_desc, vals, _cite) in CRC_ROWS.items():
        m2 = M2[sys_id]
        # 覆盖：每 20 K 至少一点（0-100 °C 原生网格远超要求）
        gaps = []
        for lo in range(0, 100, 20):
            if not any(lo <= t < lo + 20 for t in TEMPS_C):
                gaps.append(lo)
        if gaps:
            ok = False
            lines.append(f"[失败] {sys_id}: 20 K 网格覆盖缺口 {gaps}")
        # 段内单调（wt% 空间；mol/L 空间留待密度补齐后由 precheck 复核）
        phases = SOLID_PHASES[sys_id]
        for i in range(1, 12):
            if phases[i] == phases[i - 1] and vals[i][0] < vals[i - 1][0]:
                ok = False
                lines.append(f"[失败] {sys_id}: 固相 {phases[i]} 段内 {TEMPS_C[i-1]}→{TEMPS_C[i]} °C wt% 下降")
        # 交叉核对：Apelblat molality
        for t_c, m_ref in APELBLAT.get(sys_id, {}).items():
            if t_c not in TEMPS_C:
                continue
            wt = vals[TEMPS_C.index(t_c)][0]
            m_der = wt_to_molality(wt, m2)
            dev = (m_der - m_ref) / m_ref * 100.0
            flag = "OK" if abs(dev) <= 0.5 else ("分歧(已记录)" if abs(dev) <= 1.0 else "大分歧(已记录)")
            lines.append(f"[核对] {sys_id} {t_c} °C: molality {m_der:.3f} vs Apelblat {m_ref} "
                         f"({dev:+.2f}%) {flag}")
        # 交叉核对：Perry's 锚点（g/100g H2O）
        for t_c, g_ref in PERRYS_ANCHORS.get(sys_id, {}).items():
            wt = vals[TEMPS_C.index(t_c)][0]
            g_der = wt_to_g_per_100g(wt)
            dev = (g_der - g_ref) / g_ref * 100.0
            lines.append(f"[锚点] {sys_id} {t_c} °C: {g_der:.2f} vs Perry's {g_ref} "
                         f"g/100g ({dev:+.2f}%)")
    lines.insert(0, f"[{'全部通过' if ok else '存在失败项'}] 结构自检（覆盖/段内单调/交叉核对）")
    return lines


def build_rows(density: dict[tuple[str, float], tuple[float, str]] | None):
    """生成模板行。density: {(system_id, T_K): (rho, source)}；无则 c_sat 留空。"""
    rows = []
    for sys_id in ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]:
        raw_desc, vals, cite = CRC_ROWS[sys_id]
        phases = SOLID_PHASES[sys_id]
        m2 = M2[sys_id]
        for i, (wt, starred) in enumerate(vals):
            t_c = TEMPS_C[i]
            t_k = round(t_c + 273.15, 2)
            molality = wt_to_molality(wt, m2)
            g100 = wt_to_g_per_100g(wt)
            notes = [f"CRC 原生温度点 {t_c} °C；wt%→molality={molality:.4f} mol/kg；"
                     f"g/100g H2O={g100:.3f}（精确单位换算，无需求密度）"]
            if starred:
                notes.append("本列数值带 CRC 星号（与相邻星号列共同括住一次固相转变）")
            if i == 0:
                notes.append(PHASE_NOTES[sys_id])
            if density is not None:
                key = (sys_id, t_k)
                if key in density:
                    rho, dsrc = density[key]
                    c_sat = 1000.0 * rho * (wt / 100.0) / m2
                    conv = f"ρ={rho} g/cm³（{dsrc}）; c=1000·ρ·w2/M2, M2={m2} g/mol"
                    notes.append(f"饱和密度 ρ={rho} g/cm³ @ {t_c} °C")
                else:
                    c_sat, conv = None, ""
                    notes.append("!! 密度表缺本点")
            else:
                c_sat, conv = None, ""
                notes.append("c_sat 待密度源（见 溶解度密度需求清单.md）")
            rows.append({
                "system_id": sys_id,
                "temperature_K": t_k,
                "c_sat_mol_L": c_sat,
                "original_value": wt,
                "original_basis": "mass_percent_of_solute (100·w2, CRC 5-190 表定义)",
                "conversion_basis": conv,
                "solid_phase": phases[i],
                "source_citation": cite,
                "accessed_date": ACCESSED,
                "notes": "；".join(notes),
            })
    return rows


def write_outputs(rows, out_xlsx: Path):
    import openpyxl

    wb = openpyxl.load_workbook(TEMPLATE)
    ws = wb["Solubility_Records"]
    header = [c.value for c in ws[1]]
    for r in rows:
        ws.append([r.get(h) for h in header])
    wb.save(out_xlsx)
    out_csv = out_xlsx.with_suffix(".csv")
    with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=header)
        w.writeheader()
        for r in rows:
            w.writerow({h: ("" if r.get(h) is None else r.get(h)) for h in header})
    return out_csv


def load_density(path: Path) -> dict[tuple[str, float], tuple[float, str]]:
    out = {}
    with path.open(encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            if not row.get("density_g_cm3", "").strip():
                continue  # 待补行（如 CaCl2 密度源未到位）
            key = (row["system_id"].strip(), round(float(row["temperature_K"]), 2))
            out[key] = (float(row["density_g_cm3"]), row["density_source"].strip())
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--density", type=Path, default=None,
                    help="密度表 CSV（system_id,temperature_K,density_g_cm3,density_source）")
    ap.add_argument("--out", type=Path, default=None, help="输出 xlsx 路径")
    args = ap.parse_args()

    for line in report_checks():
        print(line)

    density = load_density(args.density) if args.density else None
    if density is not None:
        need = {(s, round(t + 273.15, 2)) for s in CRC_ROWS for t in TEMPS_C}
        missing = sorted(need - set(density))
        extra = sorted(set(density) - need)
        if missing:
            print(f"[警告] 密度表缺 {len(missing)} 点: {missing[:8]}{'...' if len(missing) > 8 else ''}")
        if extra:
            print(f"[警告] 密度表多出 {len(extra)} 点（忽略）")

    out = args.out or (E_AGENT / ("溶解度录入_CRC92_v2.xlsx" if density else "溶解度录入_CRC92_v1_草稿.xlsx"))
    rows = build_rows(density)
    out_csv = write_outputs(rows, out)
    n_done = sum(1 for r in rows if r["c_sat_mol_L"] is not None)
    print(f"\n已写入 {out}（48 行，c_sat 已填 {n_done}/48）")
    print(f"已写入 {out_csv}")
    if n_done < 48:
        print("提示：c_sat_mol_L 与 conversion_basis 留空的行需密度源补齐后重跑本脚本（--density）。")
        print("注意：precheck_solubility.py 在 c_sat 为空时会中断，请待密度补齐后再运行 precheck。")


if __name__ == "__main__":
    main()
