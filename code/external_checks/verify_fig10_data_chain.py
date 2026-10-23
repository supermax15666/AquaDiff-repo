# -*- coding: utf-8 -*-
"""Figure 10 绘图数据链可靠性核查（2026-09-01）。

链路：图10(plot_v3.py) ← 表6_C臂SFT配对结果.csv
  ├─ Base 642 macro/CI  ← CET_all/03_各臂完整分析/A臂_本地五模型/A臂_五模型指标.csv
  ├─ SFT  642 macro/CI  ← CET_all/03_各臂完整分析/C臂_SFT掌握度/C臂_五模型指标合并.csv
  ├─ Base/SFT 外部 macro ← CET_all/03_各臂完整分析/外部集评测_三组对比/*_metrics.csv
  │     （与 03_实验结果/.../逐场分析_10场/<run>/manuscript_model_metrics.csv 逐字节一致?）
  └─ 外部配对差/CI/p    ← 宏口径配对修正_v1（逐题数据重算）

逐题层完整性：
  64 题/场、n_runs=3、10 场题集互相同、且 == 冻结前瞻集 questions_external_questions.jsonl；
  体系题量与谱系分布 == manifest；accuracy_10pct_fraction ∈ {0,1/3,2/3,1}。
"""
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
CET_ALL = ROOT / "CET_all"
RUNS = ROOT / "03_实验结果" / "外部前瞻集评测_64题_10场" / "逐场分析_10场"
OUTDIR = ROOT / "03_实验结果" / "外部前瞻集评测_64题_10场" / "宏口径配对修正_v1"

MODELS = ["Qwen3-4B", "Qwen3-8B", "Qwen3.6-27B", "Llama-3.1-8B", "Gemma-2-9B"]
A_KEY = {
    "Qwen3-4B": "qwen3_4b_instruct_2507_base_q4km",
    "Qwen3-8B": "qwen3_8b_instruct_base_q4km",
    "Qwen3.6-27B": "qwen3_6_27b_base_q4km",
    "Llama-3.1-8B": "llama3_1_8b_instruct_base_q4km",
    "Gemma-2-9B": "gemma2_9b_it_base_q4km",
}
C_KEY = {
    "Qwen3-4B": "qwen3_4b_instruct_2507_sft_q4km",
    "Qwen3-8B": "qwen3_8b_instruct_sft_q4km",
    "Qwen3.6-27B": "qwen3_6_27b_sft_q4km",
    "Llama-3.1-8B": "llama3_1_8b_instruct_sft_q4km",
    "Gemma-2-9B": "gemma2_9b_it_sft_q4km",
}
EXT_DIR = {
    "Qwen3-4B": ("qwen3_4b_base_external", "qwen3_4b_sft_external"),
    "Qwen3-8B": ("qwen3_8b_base_external", "qwen3_8b_sft_external"),
    "Qwen3.6-27B": ("qwen3_27b_base_external", "qwen3_27b_sft_external"),
    "Llama-3.1-8B": ("llama3_1_8b_base_external", "llama3_1_8b_sft_external"),
    "Gemma-2-9B": ("gemma2_9b_base_external", "gemma2_9b_sft_external"),
}

issues: list[str] = []
oks: list[str] = []


def ok(cond: bool, msg: str) -> None:
    (oks if cond else issues).append(("✓ " if cond else "✗ ") + msg)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as h:
        return list(csv.DictReader(h))


def primary(rows: list[dict]) -> dict:
    for r in rows:
        if r.get("analysis_set_role") == "primary":
            return r
    raise ValueError("no primary row")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def r1(x: float) -> float:
    # 与项目管线一致的舍入约定：Python format（round-half-even），
    # 如 6.25 → "6.2"（ analyze_external_comparison.py 的 f"{x:.1f}" 同款）
    return float(f"{x:.1f}")


def ci_text(lo: float, hi: float) -> str:
    return f"[{r1(lo):.1f},{r1(hi):.1f}]"


# ---------- 0. 读表6 ----------
t6 = {r["模型"]: r for r in read_csv(
    CET_ALL / "01_论文主表数字" / "表6_C臂SFT配对结果.csv")}

# ---------- 1. A 臂（Base 642） ----------
a_rows = {r["model_key"]: r for r in read_csv(
    CET_ALL / "03_各臂完整分析" / "A臂_本地五模型" / "A臂_五模型指标.csv")
    if r.get("analysis_set_role") == "primary"}
for m in MODELS:
    a = a_rows[A_KEY[m]]
    v = 100 * float(a["macro_system_accuracy_10pct"])
    lo = 100 * float(a["macro_system_accuracy_10pct_ci95_low"])
    hi = 100 * float(a["macro_system_accuracy_10pct_ci95_high"])
    ok(r1(v) == float(t6[m]["Base 642 macro%"]),
       f"{m} Base 642 macro {float(t6[m]['Base 642 macro%'])} == A臂权威值 {v:.4f} (±0.1)")
    ok(t6[m]["Base CI95"].replace(" ", "") == ci_text(lo, hi),
       f"{m} Base 642 CI {t6[m]['Base CI95']} == A臂 {ci_text(lo, hi)}")

# ---------- 2. C 臂（SFT 642） ----------
c_rows = {r["model_key"]: r for r in read_csv(
    CET_ALL / "03_各臂完整分析" / "C臂_SFT掌握度" / "C臂_五模型指标合并.csv")
    if r.get("analysis_set_role") == "primary"}
for m in MODELS:
    c = c_rows[C_KEY[m]]
    v = 100 * float(c["macro_system_accuracy_10pct"])
    lo = 100 * float(c["macro_system_accuracy_10pct_ci95_low"])
    hi = 100 * float(c["macro_system_accuracy_10pct_ci95_high"])
    ok(r1(v) == float(t6[m]["SFT 642 macro%"]),
       f"{m} SFT 642 macro {float(t6[m]['SFT 642 macro%'])} == C臂权威值 {v:.4f} (±0.1)")
    ok(t6[m]["SFT CI95"].replace(" ", "") == ci_text(lo, hi),
       f"{m} SFT 642 CI {t6[m]['SFT CI95']} == C臂 {ci_text(lo, hi)}")

# ---------- 3. 642 增益（未舍入宏观差） ----------
for m in MODELS:
    a = a_rows[A_KEY[m]]; c = c_rows[C_KEY[m]]
    gap = 100 * (float(c["macro_system_accuracy_10pct"])
                 - float(a["macro_system_accuracy_10pct"]))
    ok(r1(gap) == float(t6[m]["642增益pp"].lstrip("+")),
       f"{m} 642增益 {t6[m]['642增益pp']} == 未舍入差 {gap:.4f} (±0.1)")

# ---------- 4. 外部 macro（CET_all 指标表）+ 与实验结果目录逐字节一致 ----------
ext_all = CET_ALL / "03_各臂完整分析" / "外部集评测_三组对比"
for m in MODELS:
    bd, sd = EXT_DIR[m]
    for role, d in (("Base", bd), ("SFT", sd)):
        cet_csv = ext_all / f"{d}_metrics.csv"
        arc_csv = RUNS / d / "manuscript_model_metrics.csv"
        ok(sha256(cet_csv) == sha256(arc_csv),
           f"{m} {role} 外部指标：CET_all 副本 == 03_实验结果 权威副本（SHA-256 一致）")
        p = primary(read_csv(cet_csv))
        v = 100 * float(p["macro_system_accuracy_10pct"])
        key = f"{role}外部macro%"
        ok(r1(v) == float(t6[m][key]),
           f"{m} {role} 外部 macro {float(t6[m][key])} == 指标表 {v:.4f} (±0.1)")

# ---------- 5. 外部配对差/CI/p == 宏口径重算产物 ----------
macro_rows = {r["模型"]: r for r in read_csv(
    OUTDIR / "external_comparison_macro_paired_v1.csv")}
for m in MODELS:
    r = macro_rows[m]
    ok(t6[m]["外部配对差pp"] == r["外部配对差pp_macro口径"],
       f"{m} 外部配对差 {t6[m]['外部配对差pp']} == 重算 {r['外部配对差pp_macro口径']}")
    ok(t6[m]["外部差CI95"].replace(" ", "") == r["外部差CI95_macro口径"].replace(" ", ""),
       f"{m} 外部差CI {t6[m]['外部差CI95']} == 重算 {r['外部差CI95_macro口径']}")
    ok(t6[m]["p"] == "p<0.001" and float(r["p"]) < 0.001,
       f"{m} p 一致（重算 p={r['p']}）")

# ---------- 6. 逐题层完整性 ----------
frozen_ids = set()
frozen_sys = Counter()
with (CET_ALL / "04_基准与数据集" / "外部前瞻集" /
      "questions_external_questions.jsonl").open(encoding="utf-8") as h:
    for line in h:
        rec = json.loads(line)
        frozen_ids.add(rec["question_id"])
        frozen_sys[rec["system"]] += 1
ok(len(frozen_ids) == 64, f"冻结前瞻集题量 == 64（实际 {len(frozen_ids)}）")

manifest = json.loads((CET_ALL / "04_基准与数据集" / "外部前瞻集" /
                       "manifest_external_manifest.json").read_text(encoding="utf-8"))
ok(dict(frozen_sys) == manifest["selected_system_counts"],
   f"题集体系分布 {dict(frozen_sys)} == manifest {manifest['selected_system_counts']}")

qid_sets = []
for m in MODELS:
    for role, d in (("Base", EXT_DIR[m][0]), ("SFT", EXT_DIR[m][1])):
        rows = read_csv(RUNS / d / "base_prompt_results.csv")
        qids = {r["question_id"] for r in rows}
        qid_sets.append((m, role, qids))
        ok(len(qids) == 64 and len(rows) == 64,
           f"{m} {role} 逐题 64 行/64 唯一题（实际 {len(rows)}/{len(qids)}）")
        ok(all(r["n_runs"] == "3" for r in rows),
           f"{m} {role} 全部 n_runs=3")
        ok(all(abs(float(r["accuracy_10pct_fraction"]) * 3
                   - round(float(r["accuracy_10pct_fraction"]) * 3)) < 1e-9
               for r in rows),
           f"{m} {role} accuracy_10pct_fraction ∈ {{0,1/3,2/3,1}}")
        ok(qids == frozen_ids, f"{m} {role} 题集 == 冻结前瞻集")
        sys_lin: dict[str, Counter] = {}
        lin_counter: dict[str, Counter] = {}
        sc = Counter()
        lc: dict[str, Counter] = {}
        for r in rows:
            sc[r["system"]] += 1
            lc.setdefault(r["system"], Counter())[r["origin_lineage_id"]] += 1
        ok(dict(sc) == manifest["selected_system_counts"],
           f"{m} {role} 体系题量 == manifest")
        ok({s: dict(c) for s, c in lc.items()} ==
           manifest["selected_lineage_cluster_counts"],
           f"{m} {role} 谱系分布 == manifest")

first = qid_sets[0][2]
ok(all(s == first for _, _, s in qid_sets[1:]),
   "10 场逐题数据题集两两相同")

# ---------- 汇总 ----------
print("=" * 72)
print(f"通过 {len(oks)} 项 / 问题 {len(issues)} 项")
print("=" * 72)
for s in oks:
    print(s)
if issues:
    print("-" * 72)
    for s in issues:
        print(s)
