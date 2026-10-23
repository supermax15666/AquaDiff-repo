# -*- coding: utf-8 -*-
"""Figure 12(a) 面板 8 个数字的真实值核验（2026-09-14）。

核验对象：figure/图12_统一性能/data/fig12_panel_data.csv
核验链：
  1/2. Closed-book、SFT 全题均值  ← 表6 外部 macro 五模型均值（表6 已过 123 项数据链核查）
  3/4. Closed-book、SFT 域内均值  ← 逐题数据 + ML 域标记复算（复现已发布 21.1/93.3）
  5/6. Frozen ML 域内 97.9 / 全题 71.9 ← E 臂 per-system 计数 + 拒绝计数反推
       （NaCl 12/12、KCl 11/15 含 3 拒、LiCl 20/27 含 7 拒、CaCl2 4/10 含 6 拒
         → 域内 (12+11+20+4)/48 = 47/48 = 97.92%；全题 macro = 四体系等权 = 71.87%）
  7/8. AquaDiff 同值 ← E臂_external_metrics.json（与 D 臂逐位一致：接口损失 0）
"""
from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(r"C:\Users\AS\Desktop\CET")
RUNS = ROOT / "03_实验结果" / "外部前瞻集评测_64题_10场" / "逐场分析_10场"
T6 = ROOT / "CET_all" / "01_论文主表数字" / "表6_C臂SFT配对结果.csv"
DOM_CSV = ROOT / "03_实验结果" / "D臂_ML数值后端_冻结" / "外部集64题预测_20260825" / "predictions.csv"
E_JSON = ROOT / "CET_all" / "03_各臂完整分析" / "E臂_Agent" / "E臂_external_metrics.json"
PANEL = ROOT / "figure" / "图12_统一性能" / "data" / "fig12_panel_data.csv"

PAIRS = {
    "Qwen3-4B": ("qwen3_4b_base_external", "qwen3_4b_sft_external"),
    "Qwen3-8B": ("qwen3_8b_base_external", "qwen3_8b_sft_external"),
    "Qwen3.6-27B": ("qwen3_27b_base_external", "qwen3_27b_sft_external"),
    "Llama-3.1-8B": ("llama3_1_8b_base_external", "llama3_1_8b_sft_external"),
    "Gemma-2-9B": ("gemma2_9b_base_external", "gemma2_9b_sft_external"),
}

results = []


def chk(name: str, fig_val: float, true_val: float, src: str, tol: float = 0.051):
    ok = abs(fig_val - true_val) <= tol
    results.append((ok, name, fig_val, true_val, src))


# ---- 读图值 ----
fig_vals = {}
with PANEL.open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        fig_vals[r["path"]] = (float(r["in_domain_48q_pct"]),
                               float(r["full_set_64q_pct"]))

# ---- 1/2. 全题均值（表6） ----
t6 = {}
with T6.open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        t6[r["模型"]] = (float(r["Base外部macro%"]), float(r["SFT外部macro%"]))
base_full = statistics.mean(v[0] for v in t6.values())
sft_full = statistics.mean(v[1] for v in t6.values())
chk("Closed-book full-set", fig_vals["Closed-book (5 models)"][1], base_full,
    "表6 Base外部macro% 五模型均值")
chk("SFT full-set", fig_vals["SFT (5 models)"][1], sft_full,
    "表6 SFT外部macro% 五模型均值")

# ---- 3/4. 域内均值（逐题 + 域标记） ----
dom = {}
with DOM_CSV.open(encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        dom[r["question_id"]] = (r["in_domain"] == "True")
assert len(dom) == 64 and sum(dom.values()) == 48


def load(d):
    with (RUNS / d / "base_prompt_results.csv").open(encoding="utf-8-sig") as f:
        return {r["question_id"]: float(r["accuracy_10pct_fraction"])
                for r in csv.DictReader(f)}


base_ind, sft_ind = [], []
for m, (bd, sd) in PAIRS.items():
    bq, sq = load(bd), load(sd)
    assert set(bq) == set(sq) == set(dom)
    base_ind.append(100 * statistics.mean(v for q, v in bq.items() if dom[q]))
    sft_ind.append(100 * statistics.mean(v for q, v in sq.items() if dom[q]))
chk("Closed-book in-domain", fig_vals["Closed-book (5 models)"][0],
    statistics.mean(base_ind), "逐题+ML域标记复算（五模型均值）")
chk("SFT in-domain", fig_vals["SFT (5 models)"][0],
    statistics.mean(sft_ind), "逐题+ML域标记复算（五模型均值）")

# ---- 5/6/7/8. ML 与 AquaDiff（E 臂计数反推 + 逐位一致） ----
ej = json.loads(E_JSON.read_text(encoding="utf-8"))
per_sys = ej["per_system_acc10"]
refusals_by_sys = {"NaCl-H2O": 0, "KCl-H2O": 3, "LiCl-H2O": 7, "CaCl2-H2O": 6}
assert ej["refusal_counts"]["both"] == 16
ind_correct = 0
ind_errors = 0
macro_terms = []
for sys_name, frac in per_sys.items():
    num, den = (int(x) for x in frac.split("/"))
    ind_correct += num
    # 全题计数中的"错误" = 域外拒绝 + 域内错误；域内错误只允许是 KCl 的 1 个（47/48 的由来）
    ind_errors += den - num - refusals_by_sys[sys_name]
    macro_terms.append(100.0 * num / den)
assert ind_correct == 47 and ind_errors == 1, (ind_correct, ind_errors)
ml_indom = 100.0 * ind_correct / 48.0
ml_full = statistics.mean(macro_terms)
chk("Frozen ML in-domain", fig_vals["Frozen ML"][0], ml_indom,
    "E臂 per-system 计数+16拒绝反推 47/48")
chk("Frozen ML full-set", fig_vals["Frozen ML"][1], ml_full,
    "E臂 per-system 四体系等权 macro")
chk("AquaDiff in-domain", fig_vals["AquaDiff (4B)"][0], ml_indom,
    "与冻结 ML 逐位一致（E臂接口损失 0）")
chk("AquaDiff full-set", fig_vals["AquaDiff (4B)"][1], ml_full,
    "与冻结 ML 逐位一致（E臂接口损失 0）")
assert abs(ej["acc10_all_repeats"] * 100 - 73.4) < 0.05  # micro 73.4% 一致性

# ---- 汇总 ----
print("=" * 74)
print(f"{'核验项':<26}{'图值':>7}{'真实值':>9}  结果")
print("-" * 74)
bad = 0
for ok, name, fv, tv, src in results:
    bad += 0 if ok else 1
    print(f"{name:<26}{fv:>7.1f}{tv:>9.2f}  {'✓' if ok else '✗'}  ({src})")
print("=" * 74)
print(f"通过 {len(results) - bad}/{len(results)}" + ("，全部正确真实 ✓" if bad == 0 else f"，{bad} 项不符 ✗"))
