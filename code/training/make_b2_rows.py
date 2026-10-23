# -*- coding: utf-8 -*-
"""读取填好密度的 B2 查值清单，换算 mol/kg→mol/L 并生成候选行 CSV。

换算（v2.12 冻结）：c = 1000·ρ·m / (1000 + m·M2)，M2(KCl) = 74.5513 g/mol。
输入：external/draft/b2_密度查值清单.csv（density_g_cm3 列已填）
输出：external/draft/b2_rows.csv（与 candidates_draft_v1.csv 同列契约）
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DRAFT = ROOT / "py" / "微调" / "external" / "draft"
IN_PATH = DRAFT / "b2_密度查值清单.csv"
OUT_PATH = DRAFT / "b2_rows.csv"

M2 = 74.5513
REF = (
    "Catinca Secuianu, Geoffrey C. Maitland, J. P. Martin Trusler, William A. Wakeham, "
    "J. Chem. Eng. Data, 56 (2011) 4840-4848, DOI: 10.1021/je200808q"
)
HEADERS = [
    "system", "temperature_K", "concentration_mol_L", "diffusion_1e9_m2_s",
    "origin_lineage_id", "original_reference", "source_type", "record_id",
    "retrieval_date", "notes",
]


def main() -> None:
    with IN_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    out_rows: list[dict[str, str]] = []
    problems: list[str] = []
    for row in rows:
        density_text = (row.get("density_g_cm3") or "").strip()
        if not density_text or density_text.upper() == "N/A":
            problems.append(f"T={row['T_K']} m={row['molality_mol_kg']}: density missing")
            continue
        try:
            rho = float(density_text)
            t = float(row["T_K"])
            m = float(row["molality_mol_kg"])
            d = float(row["D_1e9_m2_s"])
            p = float(row["p_MPa"])
        except ValueError as exc:
            problems.append(f"T={row['T_K']} m={row['molality_mol_kg']}: bad value ({exc})")
            continue
        if rho <= 0.5 or rho >= 2.0:
            problems.append(f"T={t} m={m}: implausible density {rho}")
            continue
        c = 1000.0 * rho * m / (1000.0 + m * M2)
        source = (row.get("密度出处") or "").strip() or "density source not recorded"
        out_rows.append(
            {
                "system": "KCl-H2O",
                "temperature_K": f"{t:.2f}",
                "concentration_mol_L": f"{c:.6f}",
                "diffusion_1e9_m2_s": f"{d:.3f}",
                "origin_lineage_id": "EXP:KCL:SECUIANU_2011",
                "original_reference": REF,
                "source_type": "experimental",
                "record_id": f"secuianu2011::table1-p{p:.2f}-m{m:.1f}",
                "retrieval_date": "2026-08-18",
                "notes": (
                    f"B2 Table 1, p<1 MPa (p={p:.2f} MPa), molality m={m:.1f} mol/kg; "
                    f"density {rho:.4f} g/cm3 used for c conversion; density source: {source}; "
                    "T<=380 K, m>0 per v2.12"
                ),
            }
        )
    if problems:
        print("problems (rows skipped):")
        for problem in problems:
            print("  -", problem)
    if not out_rows:
        raise SystemExit("no rows generated; fill density_g_cm3 first")
    with OUT_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADERS)
        writer.writeheader()
        for row in out_rows:
            writer.writerow(row)
    print(f"written {len(out_rows)} rows -> {OUT_PATH}")
    for row in out_rows:
        print(f"  T={row['temperature_K']} c={row['concentration_mol_L']} D={row['diffusion_1e9_m2_s']}")


if __name__ == "__main__":
    main()
