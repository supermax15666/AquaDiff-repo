# -*- coding: utf-8 -*-
"""外部前瞻集 Base→SFT 配对差：宏口径（macro-system）修正重算。

背景（v2 图片专项复查 P1）：Table 4 "External paired diff." 列与端点列不自洽。
根因：analyze_external_comparison.py 的配对差按 64 题等权（micro/全题口径）计算，
而端点列为四体系等权 macro-system 口径——同一张表混用两种口径。
本脚本：
  1) 原样复现原 micro 口径配对差（验证根因理解正确，应复现 +64.6/+71.9/+45.3/+43.8/+73.4）；
  2) 按共享评分器同款【体系分层 × 谱系聚类】bootstrap（fixed_strata=["system"]，
     seed 20260810，10,000 次）重算 macro 口径配对差与 CI、经验 p 值。
     点估计由线性性恒等于 macro 端点差（SFT−Base）。
输入：03_实验结果/外部前瞻集评测_64题_10场/逐场分析_10场/<run>/base_prompt_results.csv
输出：03_实验结果/外部前瞻集评测_64题_10场/宏口径配对修正_v1/
      external_comparison_macro_paired_v1.md / .csv（新目录，不覆盖历史产物）
"""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parents[2] / "03_实验结果" / "外部前瞻集评测_64题_10场"
ANA = BASE_DIR / "逐场分析_10场"
OUT = BASE_DIR / "宏口径配对修正_v1"
SEED = 20260810
N_REPS = 10000
SYSTEMS = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]

PAIRS = {
    "Qwen3-4B": ("qwen3_4b_base_external", "qwen3_4b_sft_external"),
    "Qwen3-8B": ("qwen3_8b_base_external", "qwen3_8b_sft_external"),
    "Qwen3.6-27B": ("qwen3_27b_base_external", "qwen3_27b_sft_external"),
    "Llama-3.1-8B": ("llama3_1_8b_base_external", "llama3_1_8b_sft_external"),
    "Gemma-2-9B": ("gemma2_9b_base_external", "gemma2_9b_sft_external"),
}

# 原 micro 口径表值（用于复现校验）：(配对差pp, CIlo, CIhi)
MICRO_REFERENCE = {
    "Qwen3-4B": (64.6, 40.8, 85.8),
    "Qwen3-8B": (71.9, 42.3, 100.0),
    "Qwen3.6-27B": (45.3, 28.6, 64.3),
    "Llama-3.1-8B": (43.8, 19.6, 79.6),
    "Gemma-2-9B": (73.4, 51.2, 90.1),
}


def load_questions(dir_name: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with (ANA / dir_name / "base_prompt_results.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        for record in csv.DictReader(handle):
            rows[str(record["question_id"])] = record
    return rows


def percentile(sorted_vals: list[float], p: float) -> float:
    # 与原脚本一致：排序后取下标 int(p*N)
    return sorted_vals[int(p * len(sorted_vals))]


def micro_paired_bootstrap(diffs: dict[str, float], lineage: dict[str, str]):
    """原 analyze_external_comparison.py 的口径：12 谱系整体聚类重采样，64 题等权。"""
    rng = random.Random(SEED)
    clusters: dict[str, list[float]] = defaultdict(list)
    for q, d in diffs.items():
        clusters[lineage[q]].append(d)
    keys = sorted(clusters)
    means = []
    for _ in range(N_REPS):
        total, count = 0.0, 0
        for key in rng.choices(keys, k=len(keys)):
            vals = clusters[key]
            total += sum(vals)
            count += len(vals)
        means.append(total / count)
    means.sort()
    lo, hi = percentile(means, 0.025), percentile(means, 0.975)
    mean = sum(diffs.values()) / len(diffs)
    p = 2.0 * min(
        sum(1 for v in means if v <= 0) / N_REPS,
        sum(1 for v in means if v >= 0) / N_REPS,
    )
    return mean, lo, hi, p


def macro_paired_statistic(sampled: list[tuple[str, float]]) -> float:
    """四体系等权：每体系内取配对差均值，再对体系取均值。"""
    by_sys: dict[str, list[float]] = defaultdict(list)
    for sys_name, d in sampled:
        by_sys[sys_name].append(d)
    return sum(sum(v) / len(v) for v in by_sys.values()) / len(by_sys)


def macro_paired_bootstrap(diffs: dict[str, float], system: dict[str, str],
                           lineage: dict[str, str]):
    """共享评分器同款分层聚类 bootstrap：体系内重采样该体系的谱系（fixed_strata=system）。"""
    strata: dict[str, dict[str, list[tuple[str, float]]]] = defaultdict(
        lambda: defaultdict(list))
    for q, d in diffs.items():
        strata[system[q]][lineage[q]].append((system[q], d))
    rng = random.Random(SEED)
    estimates: list[float] = []
    for _ in range(N_REPS):
        sampled: list[tuple[str, float]] = []
        for sys_name in SYSTEMS:
            lineage_ids = sorted(strata[sys_name])
            for _ in range(len(lineage_ids)):
                sampled.extend(strata[sys_name][rng.choice(lineage_ids)])
        estimates.append(macro_paired_statistic(sampled))
    estimates.sort()
    observed = macro_paired_statistic(
        [(system[q], d) for q, d in diffs.items()])
    lo, hi = percentile(estimates, 0.025), percentile(estimates, 0.975)
    p = 2.0 * min(
        sum(1 for v in estimates if v <= 0) / N_REPS,
        sum(1 for v in estimates if v >= 0) / N_REPS,
    )
    return observed, lo, hi, p


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    add = lines.append
    add("# 外部前瞻集 Base→SFT 配对差：macro-system 口径修正（v1，2026-09-01）\n")
    add("口径：同题配对 SFT−Base；体系分层 × 谱系聚类 bootstrap 10,000 次"
        "（seed 20260810，与共享评分器 macro CI 同约定）；点估计恒等于 macro 端点差。\n")

    rows_out = []
    add("## 0. 外部集谱系分布\n")
    probe = load_questions(PAIRS["Qwen3-4B"][0])
    sys_lin: dict[str, set] = defaultdict(set)
    for q, r in probe.items():
        sys_lin[r["system"]].add(r["origin_lineage_id"])
    for s in SYSTEMS:
        n_q = sum(1 for r in probe.values() if r["system"] == s)
        add(f"- {s}: {n_q} 题 / {len(sys_lin[s])} 谱系")
    add("")

    add("## 1. micro 口径复现校验（应复现原表配对差）\n")
    add("| 模型 | 重算 micro 配对差 [CI] | 原表值 | 一致? |")
    add("|---|---|---|---|")
    micro_ok = True
    for label, (bd, sd) in PAIRS.items():
        bq, sq = load_questions(bd), load_questions(sd)
        assert set(bq) == set(sq), f"{label}: 题集不一致"
        diffs = {q: float(sq[q]["accuracy_10pct_fraction"])
                 - float(bq[q]["accuracy_10pct_fraction"]) for q in bq}
        lineage = {q: bq[q]["origin_lineage_id"] for q in bq}
        m, lo, hi, _ = micro_paired_bootstrap(diffs, lineage)
        ref = MICRO_REFERENCE[label]
        ok = (round(m * 100, 1) == ref[0] and round(lo * 100, 1) == ref[1]
              and round(hi * 100, 1) == ref[2])
        micro_ok = micro_ok and ok
        add(f"| {label} | {m*100:+.1f} [{lo*100:+.1f},{hi*100:+.1f}] "
            f"| +{ref[0]} [{ref[1]},{ref[2]}] | {'✓' if ok else '✗'} |")
    add("")

    add("## 2. macro 口径配对差（修正后权威值）\n")
    add("| 模型 | Base macro | SFT macro | 端点差 | 配对差 [CI95] | 双侧经验 p |")
    add("|---|---|---|---|---|---|")
    for label, (bd, sd) in PAIRS.items():
        bq, sq = load_questions(bd), load_questions(sd)
        diffs = {q: float(sq[q]["accuracy_10pct_fraction"])
                 - float(bq[q]["accuracy_10pct_fraction"]) for q in bq}
        system = {q: bq[q]["system"] for q in bq}
        lineage = {q: bq[q]["origin_lineage_id"] for q in bq}
        obs, lo, hi, p = macro_paired_bootstrap(diffs, system, lineage)
        # 端点 macro（逐题数据直算，与共享评分器口径一致）
        def macro_of(qs):
            return sum(
                sum(float(r["accuracy_10pct_fraction"]) for r in qs.values()
                    if r["system"] == s)
                / sum(1 for r in qs.values() if r["system"] == s)
                for s in SYSTEMS) / len(SYSTEMS)
        bmac, smac = macro_of(bq), macro_of(sq)
        gap = smac - bmac
        assert abs(obs - gap) < 1e-9, f"{label}: 配对差≠端点差（线性性被破坏）"
        add(f"| {label} | {bmac*100:.1f} | {smac*100:.1f} | {gap*100:+.1f} "
            f"| {obs*100:+.1f} [{lo*100:+.1f},{hi*100:+.1f}] | {p:.3f} |")
        rows_out.append({
            "模型": label,
            "Base外部macro%": f"{bmac*100:.1f}",
            "SFT外部macro%": f"{smac*100:.1f}",
            "外部配对差pp_macro口径": f"{obs*100:+.1f}",
            "外部差CI95_macro口径": f"[{lo*100:+.1f},{hi*100:+.1f}]",
            "p": f"{p:.3f}",
        })
    add("")
    add(f"micro 复现校验整体结果：{'全部一致 ✓' if micro_ok else '存在不一致 ✗'}")

    text = "\n".join(lines) + "\n"
    (OUT / "external_comparison_macro_paired_v1.md").write_text(
        text, encoding="utf-8")
    with (OUT / "external_comparison_macro_paired_v1.csv").open(
            "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_out[0].keys()))
        writer.writeheader()
        writer.writerows(rows_out)
    print(text)
    print("saved:", OUT)


if __name__ == "__main__":
    main()
