# -*- coding: utf-8 -*-
"""期中检查：27B SFT（进行中）vs 27B Base 在同一批已完成题目上的 Acc@10%。

输出：两者在已完成的同题子集上的总体/逐体系 Acc@10%（题内 3 次重复取均值，
体系间等权 macro）。
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(r"E:\Desktop\CET_docment\CET_docment")
GOLD = ROOT / "py" / "LLM_API_direct" / "questions" / "four_system_all_gold.evaluator.jsonl"
SFT_RUN = next(
    (ROOT / "py" / "results" / "SLM_direct" / "protocol_v2_2" / "lm_studio__qwen3_6_27b_sft_q4km__qwen3.6-27b-lora-r64" / "runs").glob("*/sample_results.jsonl")
)
BASE_RUN = (
    ROOT / "py" / "results" / "SLM_direct" / "protocol_v2_2"
    / "lm_studio__qwen3_6_27b_base_q4km__qwen3.6-27b_q4_k_m" / "runs"
    / "qwen3_6_27b_base_primary_q4km_v1__20260816T042130039240Z_ed529b63e1" / "sample_results.jsonl"
)


def load_gold() -> dict[str, tuple[str, float]]:
    gold: dict[str, tuple[str, float]] = {}
    for line in GOLD.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        gold[str(row["question_id"])] = (str(row["system"]), float(row["diffusion_1e9_m2_s"]))
    return gold


def load_samples(path: Path) -> list[dict]:
    samples = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if row.get("infrastructure_failure"):
            continue
        pred = row.get("parsed_answer") or {}
        value = pred.get("diffusion_1e9_m2_s") if isinstance(pred, dict) else None
        if value is None:
            continue
        samples.append(
            {
                "question_id": str(row["question_id"]),
                "value": float(value),
            }
        )
    return samples


def accuracy(samples: list[dict], gold: dict) -> dict:
    per_question: dict[str, list[float]] = defaultdict(list)
    for s in samples:
        qid = s["question_id"]
        if qid not in gold:
            continue
        system, g = gold[qid]
        ok = 1.0 if abs(s["value"] - g) / g <= 0.10 else 0.0
        per_question[(system, qid)].append(ok)
    per_system: dict[str, list[float]] = defaultdict(list)
    for (system, _), oks in per_question.items():
        per_system[system].append(sum(oks) / len(oks))
    overall = [v for oks in per_question.values() for v in [sum(oks) / len(oks)]]
    macro = sum(sum(v) / len(v) for v in per_system.values()) / len(per_system) if per_system else 0.0
    return {
        "questions": len(per_question),
        "samples": len(samples),
        "overall_question_mean": sum(overall) / len(overall) if overall else 0.0,
        "macro_system": macro,
        "per_system": {s: sum(v) / len(v) for s, v in sorted(per_system.items())},
    }


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    gold = load_gold()
    sft = load_samples(SFT_RUN)
    base = load_samples(BASE_RUN)
    sft_qids = {s["question_id"] for s in sft}
    base_matched = [s for s in base if s["question_id"] in sft_qids]
    print("SFT run file:", SFT_RUN.name)
    print("Base run file:", BASE_RUN.name)
    print("=" * 60)
    a_sft = accuracy(sft, gold)
    a_base = accuracy(base_matched, gold)
    print(f"SFT  已完成题目: {a_sft['questions']}（样本 {a_sft['samples']}）")
    print(f"Base 同题子集  : {a_base['questions']}（样本 {a_base['samples']}）")
    print("-" * 60)
    print(f"{'指标':<22}{'Base 27B':>12}{'SFT 27B':>12}{'变化':>10}")
    print(f"{'Acc@10% 题均(全部)':<22}{a_base['overall_question_mean']*100:>11.1f}%{a_sft['overall_question_mean']*100:>11.1f}%{a_sft['overall_question_mean']-a_base['overall_question_mean']:>+10.1f}pp")
    print(f"{'Acc@10% macro-system':<22}{a_base['macro_system']*100:>11.1f}%{a_sft['macro_system']*100:>11.1f}%{a_sft['macro_system']-a_base['macro_system']:>+10.1f}pp")
    for system in sorted(set(a_base['per_system']) | set(a_sft['per_system'])):
        b = a_base['per_system'].get(system, 0.0) * 100
        s = a_sft['per_system'].get(system, 0.0) * 100
        print(f"{system:<22}{b:>11.1f}%{s:>11.1f}%{s-b:>+10.1f}pp")


if __name__ == "__main__":
    main()
