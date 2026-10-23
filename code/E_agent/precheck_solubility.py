# -*- coding: utf-8 -*-
"""溶解度录入表 precheck（E 臂饱和安全层，方案 v2.15）。

用法：
    python precheck_solubility.py --input <填好的xlsx或csv>

检查项：
  1. 列完整性与取值域（system_id 白名单、T/c 数值范围）
  2. 每体系温度覆盖：273.15–373.15 K、每 20 K 至少 1 点
  3. 同固相分段内 c_sat 随 T 单调（相变拐点处跳变允许）
  4. 固相栏必填
  5. 交叉核对（警告级）：池内最大浓度对应温度下的 c_sat 量级合理性
  6. 换算依据非空

退出码 0 = 全部通过；1 = 存在错误（警告不阻断但需人工确认）。
"""

import argparse
import csv
import sys

SYSTEMS = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]
REQUIRED = ["system_id", "temperature_K", "c_sat_mol_L", "original_value",
            "original_basis", "conversion_basis", "solid_phase",
            "source_citation", "accessed_date", "notes"]
T_MIN, T_MAX = 273.15, 373.15
GRID = 20.0
# 池内（642 训练池）各体系最大浓度 mol/L，用于交叉核对（D 臂 registry 冻结域）
POOL_MAX = {"NaCl-H2O": 5.4, "KCl-H2O": 4.45, "LiCl-H2O": 8.1108, "CaCl2-H2O": 6.004}


def load_rows(path):
    if path.lower().endswith(".csv"):
        with open(path, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))
    import openpyxl
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["Solubility_Records"]
    rows = []
    it = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(it)]
    for vals in it:
        if vals is None or all(v is None or str(v).strip() == "" for v in vals):
            continue
        rows.append({h: ("" if v is None else v) for h, v in zip(header, vals)})
    wb.close()
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True)
    args = ap.parse_args()

    rows = load_rows(args.input)
    errors, warnings = [], []
    if not rows:
        sys.exit("错误：没有数据行")

    for i, r in enumerate(rows, start=2):
        for col in REQUIRED:
            if col not in r or str(r.get(col, "")).strip() == "":
                if col in ("notes",):  # notes 允许为空
                    continue
                errors.append(f"行{i}: 缺少 {col}")
        sys_id = str(r.get("system_id", "")).strip()
        if sys_id and sys_id not in SYSTEMS:
            errors.append(f"行{i}: system_id 非法（{sys_id}）")
        try:
            t = float(r["temperature_K"])
            if not (T_MIN - 0.01 <= t <= T_MAX + 0.01):
                errors.append(f"行{i}: temperature_K={t} 超出 [{T_MIN},{T_MAX}]")
        except (KeyError, ValueError, TypeError):
            t = None
        try:
            c = float(r["c_sat_mol_L"])
            if not (0.01 <= c <= 30):
                errors.append(f"行{i}: c_sat_mol_L={c} 量级可疑（0.01–30 之外）")
        except (KeyError, ValueError, TypeError):
            c = None

    # 温度覆盖与分段单调性
    for s in SYSTEMS:
        pts = sorted(
            (float(r["temperature_K"]), float(r["c_sat_mol_L"]), str(r.get("solid_phase", "")).strip(), r)
            for r in rows if str(r.get("system_id", "")).strip() == s
        )
        if not pts:
            errors.append(f"{s}: 无数据行")
            continue
        # 覆盖：每 GRID K 至少一点（按区间中点近似）
        edges = [T_MIN + i * GRID for i in range(int((T_MAX - T_MIN) // GRID) + 1)]
        for lo in edges:
            hi = min(lo + GRID, T_MAX)
            if not any(lo - 0.01 <= t < hi + 0.01 for t, c, ph, r in pts):
                warnings.append(f"{s}: [{lo:.0f},{hi:.0f}] K 无数据点（建议补充）")
        # 同固相分段内单调递增
        for (t1, c1, ph1, _), (t2, c2, ph2, _) in zip(pts, pts[1:]):
            if ph1 == ph2 and t2 > t1 and c2 < c1 - 1e-9:
                warnings.append(f"{s}: 固相 {ph1} 段内 T={t1}→{t2} 时 c_sat 下降（{c1}→{c2}），请核对")
        # 交叉核对：池内最大浓度不应超过表内全域最大饱和浓度（超 5% 警告；
        # 池内最大值可能来自高温行，故与全域最大值而非近室温值比较）
        c_max_table = max(c for _, c, _, _ in pts)
        if POOL_MAX[s] > c_max_table * 1.05:
            warnings.append(
                f"{s}: 池内最大浓度 {POOL_MAX[s]} M 超过表内最大饱和浓度 {c_max_table:.3f} M 的 5%"
                "——池内数据不应明显超过溶解度，请核对换算或温度覆盖"
            )

    print(f"共 {len(rows)} 行")
    for e in errors:
        print(f"[错误] {e}")
    for w in warnings:
        print(f"[警告] {w}")
    if errors:
        print(f"\n结果：{len(errors)} 个错误，{len(warnings)} 个警告 —— 需修正后重跑")
        sys.exit(1)
    print(f"\n结果：0 个错误，{len(warnings)} 个警告 —— {'警告请人工确认后' if warnings else ''}可通知助手冻结")
    sys.exit(0)


if __name__ == "__main__":
    main()
