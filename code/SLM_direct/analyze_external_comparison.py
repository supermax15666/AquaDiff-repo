# -*- coding: utf-8 -*-
"""外部前瞻集最终对比：Base vs SFT（macro Acc@10% + 谱系聚类配对 bootstrap）。

输入：protocol_v2_2/_analysis/<model>_external/ 下的 base_prompt_results.csv
（逐题 accuracy_10pct_fraction，含 origin_lineage_id）与 manuscript_model_metrics.csv
（共享评分器的 macro_system_accuracy_10pct 与 CI）。
输出：控制台表格 + `_analysis/external_comparison_summary.md`。

口径：题目为 64 个外部条件（各 3 次重复）；配对 = 同题 SFT−Base 差值；
bootstrap 以 origin_lineage_id 聚类重采样 10,000 次（seed 20260810）。
"""
from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "results" / "SLM_direct" / "protocol_v2_2"
ANA = ROOT / "_analysis"
SEED = 20260810
N_REPS = 10000

PAIRS = {
    "Qwen3-4B": ("qwen3_4b_base_external", "qwen3_4b_sft_external"),
    "Qwen3-8B": ("qwen3_8b_base_external", "qwen3_8b_sft_external"),
    "Qwen3.6-27B": ("qwen3_27b_base_external", "qwen3_27b_sft_external"),
    "Llama-3.1-8B": ("llama3_1_8b_base_external", "llama3_1_8b_sft_external"),
    "Gemma-2-9B": ("gemma2_9b_base_external", "gemma2_9b_sft_external"),
}


def load_questions(dir_name: str) -> dict[str, dict]:
    rows: dict[str, dict] = {}
    with (ANA / dir_name / "base_prompt_results.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        for record in csv.DictReader(handle):
            rows[str(record["question_id"])] = record
    return rows


def macro_metrics(dir_name: str) -> dict:
    with (ANA / dir_name / "manuscript_model_metrics.csv").open(
        encoding="utf-8-sig", newline=""
    ) as handle:
        for record in csv.DictReader(handle):
            if record.get("analysis_set_role") == "primary":
                return record
    raise ValueError(f"no primary metrics row in {dir_name}")


def cluster_bootstrap(
    diff_by_question: dict[str, float], lineage_by_question: dict[str, str]
) -> tuple[float, float, float, float]:
    """返回 (均值差, CI95 下, CI95 上, 双侧经验 p)。"""
    rng = random.Random(SEED)
    clusters: dict[str, list[float]] = defaultdict(list)
    for question_id, diff in diff_by_question.items():
        clusters[lineage_by_question[question_id]].append(diff)
    cluster_keys = sorted(clusters)
    means: list[float] = []
    for _ in range(N_REPS):
        total = 0.0
        count = 0
        for key in rng.choices(cluster_keys, k=len(cluster_keys)):
            values = clusters[key]
            total += sum(values)
            count += len(values)
        means.append(total / count)
    means.sort()
    lo = means[int(0.025 * N_REPS)]
    hi = means[int(0.975 * N_REPS)]
    mean = sum(diff_by_question.values()) / len(diff_by_question)
    p_two_sided = 2.0 * min(
        sum(1 for value in means if value <= 0) / N_REPS,
        sum(1 for value in means if value >= 0) / N_REPS,
    )
    return mean, lo, hi, p_two_sided


def main() -> None:
    lines: list[str] = []
    add = lines.append
    add("# 外部前瞻集最终对比：Base vs SFT（64 题，各 3 次重复）\n")
    add("## 1. macro Acc@10%（共享评分器口径，CI95）\n")
    add("| 模型 | Base | SFT | Δ |")
    add("|---|---|---|---|")
    metrics_by_pair = {}
    pair_rows = []
    for label, (base_dir, sft_dir) in PAIRS.items():
        base = macro_metrics(base_dir)
        sft = macro_metrics(sft_dir)
        b = float(base["macro_system_accuracy_10pct"])
        s = float(sft["macro_system_accuracy_10pct"])
        blo = float(base["macro_system_accuracy_10pct_ci95_low"])
        bhi = float(base["macro_system_accuracy_10pct_ci95_high"])
        slo = float(sft["macro_system_accuracy_10pct_ci95_low"])
        shi = float(sft["macro_system_accuracy_10pct_ci95_high"])
        metrics_by_pair[label] = (b, s, blo, bhi, slo, shi)
        add(
            f"| {label} | {b*100:.1f}% [{blo*100:.1f},{bhi*100:.1f}] "
            f"| {s*100:.1f}% [{slo*100:.1f},{shi*100:.1f}] | {(s-b)*100:+.1f}pp |"
        )
        pair_rows.append((label, b, s, blo, bhi, slo, shi))

    add("\n## 2. SFT−Base 配对差（同题配对，谱系聚类 bootstrap 10,000 次，CI95）\n")
    add("| 模型 | 配对均值差 | CI95 | 双侧经验 p |")
    add("|---|---|---|---|")
    stats_rows = []
    for label, (base_dir, sft_dir) in PAIRS.items():
        base_q = load_questions(base_dir)
        sft_q = load_questions(sft_dir)
        if set(base_q) != set(sft_q):
            raise ValueError(f"{label}: question id sets differ")
        diff_by_question = {
            q: float(sft_q[q]["accuracy_10pct_fraction"])
            - float(base_q[q]["accuracy_10pct_fraction"])
            for q in base_q
        }
        lineage_by_question = {q: base_q[q]["origin_lineage_id"] for q in base_q}
        mean, lo, hi, p = cluster_bootstrap(diff_by_question, lineage_by_question)
        add(f"| {label} | {mean*100:+.1f}pp | [{lo*100:+.1f},{hi*100:+.1f}] | {p:.3f} |")
        stats_rows.append((label, mean, lo, hi, p))

    add("\n## 3. 分体系 Acc@10%（题均，各 3 次重复）\n")
    add("| 体系 | Base（5 模型范围） | SFT（5 模型范围） |")
    add("|---|---|---|")
    systems = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]
    base_qs = {label: load_questions(PAIRS[label][0]) for label in PAIRS}
    sft_qs = {label: load_questions(PAIRS[label][1]) for label in PAIRS}
    for system in systems:
        b_values, s_values = [], []
        for label in PAIRS:
            b_rows = [r for r in base_qs[label].values() if r["system"] == system]
            s_rows = [r for r in sft_qs[label].values() if r["system"] == system]
            b_values.append(
                sum(float(r["accuracy_10pct_fraction"]) for r in b_rows) / len(b_rows)
            )
            s_values.append(
                sum(float(r["accuracy_10pct_fraction"]) for r in s_rows) / len(s_rows)
            )
        add(
            f"| {system} | {min(b_values)*100:.1f}–{max(b_values)*100:.1f}% "
            f"| {min(s_values)*100:.1f}–{max(s_values)*100:.1f}% |"
        )

    add("\n## 4. 逐模型分体系 Acc@10%\n")
    add("| 模型/臂 | NaCl | KCl | LiCl | CaCl₂ | macro |")
    add("|---|---|---|---|---|---|")
    for label in PAIRS:
        for role, qs in (("Base", base_qs), ("SFT", sft_qs)):
            per = {}
            for system in systems:
                rows = [r for r in qs[label].values() if r["system"] == system]
                per[system] = (
                    sum(float(r["accuracy_10pct_fraction"]) for r in rows) / len(rows)
                )
            add(
                f"| {label} {role} | {per['NaCl-H2O']*100:.1f}% | {per['KCl-H2O']*100:.1f}% "
                f"| {per['LiCl-H2O']*100:.1f}% | {per['CaCl2-H2O']*100:.1f}% "
                f"| {metrics_by_pair[label][0 if role=='Base' else 1]*100:.1f}% |"
            )

    text = "\n".join(lines) + "\n"
    (ANA / "external_comparison_summary.md").write_text(text, encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()
