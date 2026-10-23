# -*- coding: utf-8 -*-
"""D 臂冻结模型在外部前瞻集 64 题上的预测与评分（06_未完成事项 P0-1，方案 §3.D/§18 预注册比较）。

纪律：
- 密封 gold 只在本脚本内程序化读取用于评分；任何输出文件/控制台不包含 gold 值，
  也不包含可反推 gold 的逐题误差列（predictions.csv 只含模型侧输出）。
- 只读冻结产物（registry + joblib + 外部集 questions/gold），先校验 SHA-256 再加载。
- 结果写入全新目录，不覆盖任何历史产物；聚系模型为每体系入选的 specialized 模型
  （Agent 后端口径），pooled 对照不在本任务范围。

用法：
    python predict_external.py --registry <registry目录> --questions <external_questions.jsonl>
        --gold <external_gold.evaluator.jsonl> --out <输出目录>
"""

import argparse
import hashlib
import json
import math
import os
import sys
from datetime import datetime, timezone

import joblib
import numpy as np
import sklearn


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--registry", required=True, help="冻结 registry 目录（含 registry.json 与 joblib）")
    ap.add_argument("--questions", required=True, help="外部集 questions jsonl")
    ap.add_argument("--gold", required=True, help="外部集密封 gold jsonl（仅程序内使用）")
    ap.add_argument("--out", required=True, help="输出目录（须为不存在的新目录）")
    args = ap.parse_args()

    if os.path.exists(args.out):
        sys.exit(f"输出目录已存在，禁止覆盖：{args.out}")
    os.makedirs(args.out)

    # ---------- 1. 冻结产物完整性校验 ----------
    registry_path = os.path.join(args.registry, "registry.json")
    registry = json.load(open(registry_path, encoding="utf-8"))
    fingerprint = registry["protocol_fingerprint"]
    sys_entries = {s["system"]: s for s in registry["systems"]}

    questions_sha = sha256_of(args.questions)
    gold_sha = sha256_of(args.gold)

    # ---------- 2. 加载外部集题目 ----------
    questions = [json.loads(l) for l in open(args.questions, encoding="utf-8")]
    assert len(questions) == 64, f"外部集应为 64 题，实际 {len(questions)}"

    # ---------- 3. 逐体系加载模型并预测（含适用域结构化拒绝） ----------
    rows = []
    for q in questions:
        system = q["system"]
        entry = sys_entries[system]
        ad = entry["applicability_domain"]
        T = float(q["temperature_K"])
        c = float(q["concentration_mol_L"])

        reasons = []
        if not (ad["temperature_K"]["min"] <= T <= ad["temperature_K"]["max"]):
            reasons.append(
                f"temperature_K={T} 出域 [{ad['temperature_K']['min']},{ad['temperature_K']['max']}]"
            )
        if not (ad["concentration_mol_L"]["min"] <= c <= ad["concentration_mol_L"]["max"]):
            reasons.append(
                f"concentration_mol_L={c} 出域 [{ad['concentration_mol_L']['min']},{ad['concentration_mol_L']['max']}]"
            )

        pred = None
        if not reasons:
            model_path = os.path.join(args.registry, f"{system}.joblib")
            actual = sha256_of(model_path)
            expected = entry["artifact"]["sha256"]
            assert actual == expected, f"{system} joblib 哈希不一致：{actual} != {expected}"
            model = joblib.load(model_path)
            X = np.array([[T, c]], dtype=float)
            y = float(model.predict(X)[0])
            if math.isfinite(y):
                pred = y
            else:
                reasons.append("model_output_not_finite")

        rows.append({
            "question_id": q["question_id"],
            "system": system,
            "temperature_K": T,
            "concentration_mol_L": c,
            "in_domain": pred is not None,
            "predicted_diffusion_1e9_m2_s": pred,
            "refusal_reason": "; ".join(reasons) if reasons else "",
            "_registered_model": entry["registered_model_key"],
        })

    # ---------- 4. 程序化评分（gold 不落盘、不打印；仅聚合输出） ----------
    gold = {}
    for l in open(args.gold, encoding="utf-8"):
        d = json.loads(l)
        gold[d["question_id"]] = float(d["diffusion_1e9_m2_s"])
    assert len(gold) == 64

    per_system = {}
    for system in ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]:
        srows = [r for r in rows if r["system"] == system]
        n = len(srows)
        refused = sum(1 for r in srows if not r["in_domain"])
        valid = [r for r in srows if r["in_domain"]]
        acc5 = acc10 = 0
        apes, abs_errs, signed_errs = [], [], []
        for r in srows:
            g = gold[r["question_id"]]
            if r["in_domain"]:
                ape = abs(r["predicted_diffusion_1e9_m2_s"] - g) / abs(g) * 100.0
                apes.append(ape)
                abs_errs.append(abs(r["predicted_diffusion_1e9_m2_s"] - g))
                signed_errs.append(r["predicted_diffusion_1e9_m2_s"] - g)
                if ape <= 5.0:
                    acc5 += 1
                if ape <= 10.0:
                    acc10 += 1
        per_system[system] = {
            "n_questions": n,
            "n_refused_out_of_domain": refused,
            "n_predicted": len(valid),
            "accuracy_5pct_all_question_denominator": acc5 / n,
            "accuracy_10pct_all_question_denominator": acc10 / n,
            "accuracy_10pct_in_domain_denominator": (acc10 / len(valid)) if valid else None,
            "mae_1e9_m2_s": float(np.mean(abs_errs)) if abs_errs else None,
            "rmse_1e9_m2_s": float(np.sqrt(np.mean(np.square(abs_errs)))) if abs_errs else None,
            "mdape_percent": float(np.median(apes)) if apes else None,
            "p95_ape_percent": float(np.percentile(apes, 95)) if apes else None,
            "bias_1e9_m2_s": float(np.mean(signed_errs)) if signed_errs else None,
        }

    n_all = len(rows)
    acc10_micro = sum(
        1 for r in rows
        if r["in_domain"] and abs(r["predicted_diffusion_1e9_m2_s"] - gold[r["question_id"]]) / abs(gold[r["question_id"]]) <= 0.10
    ) / n_all
    acc5_micro = sum(
        1 for r in rows
        if r["in_domain"] and abs(r["predicted_diffusion_1e9_m2_s"] - gold[r["question_id"]]) / abs(gold[r["question_id"]]) <= 0.05
    ) / n_all
    acc10_macro = float(np.mean([per_system[s]["accuracy_10pct_all_question_denominator"] for s in per_system]))
    acc5_macro = float(np.mean([per_system[s]["accuracy_5pct_all_question_denominator"] for s in per_system]))

    overall = {
        "n_questions": n_all,
        "n_refused_out_of_domain": sum(1 for r in rows if not r["in_domain"]),
        "accuracy_5pct_micro": acc5_micro,
        "accuracy_10pct_micro": acc10_micro,
        "accuracy_5pct_macro_system": acc5_macro,
        "accuracy_10pct_macro_system": acc10_macro,
    }

    # ---------- 5. 落盘（预测侧 + 聚合指标；无 gold、无逐题误差） ----------
    import csv
    pred_csv = os.path.join(args.out, "predictions.csv")
    with open(pred_csv, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=[
            "question_id", "system", "temperature_K", "concentration_mol_L",
            "in_domain", "predicted_diffusion_1e9_m2_s", "refusal_reason", "registered_model",
        ])
        w.writeheader()
        for r in rows:
            w.writerow({
                "question_id": r["question_id"], "system": r["system"],
                "temperature_K": r["temperature_K"], "concentration_mol_L": r["concentration_mol_L"],
                "in_domain": r["in_domain"], "predicted_diffusion_1e9_m2_s": r["predicted_diffusion_1e9_m2_s"],
                "refusal_reason": r["refusal_reason"], "registered_model": r["_registered_model"],
            })

    metrics = {
        "artifact_type": "ml_backend_d_external_prediction",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "registry_protocol_fingerprint": fingerprint,
        "registered_models": {s: e["registered_model_key"] for s, e in sys_entries.items()},
        "questions_file_sha256": questions_sha,
        "gold_file_sha256": gold_sha,
        "gold_handling": "密封 gold 仅在脚本内程序化评分；输出仅含聚合指标与模型侧预测，无 gold 值、无逐题误差列。",
        "accuracy_denominator": "全题口径（域外拒绝计错，与 LLM 各臂拒答计错一致）；另报域内口径与拒绝数。",
        "per_system": per_system,
        "overall": overall,
    }
    json.dump(metrics, open(os.path.join(args.out, "metrics.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    script_sha = sha256_of(os.path.abspath(__file__))
    manifest = {
        "artifact_type": "ml_backend_d_external_prediction_run",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "task": "06_未完成事项 P0-1：D 臂冻结 ML 模型在外部前瞻集 64 题上的预测（方案 §3.D/§18 预注册比较）",
        "registry_dir": os.path.abspath(args.registry),
        "registry_protocol_fingerprint": fingerprint,
        "questions_file": os.path.abspath(args.questions),
        "questions_file_sha256": questions_sha,
        "gold_file": os.path.abspath(args.gold),
        "gold_file_sha256": gold_sha,
        "script": os.path.abspath(__file__),
        "script_sha256": script_sha,
        "python": sys.version.split()[0],
        "scikit_learn": sklearn.__version__,
        "joblib": joblib.__version__,
        "numpy": np.__version__,
        "output_files": ["predictions.csv", "metrics.json", "metrics_summary.md", "run_manifest.json"],
        "notes": "pooled 对照模型未在本任务范围（P0-1 为 Base/SFT/ML(专用) 三组比较）；如需可另开 run。",
    }
    json.dump(manifest, open(os.path.join(args.out, "run_manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # ---------- 6. 人类可读汇总（仅聚合） ----------
    lines = [
        "# D 臂冻结 ML 模型 · 外部前瞻集 64 题预测（三组比较之 ML 组）",
        "",
        f"- registry 冻结指纹：`{fingerprint[:16]}…`（2026-08-15 冻结，protocol_frozen=true）",
        f"- 模型：{metrics['registered_models']}",
        f"- 逐体系入选算法：NaCl=GP / KCl=Ridge / LiCl=GB / CaCl₂=GB（谱系分组 5 折 CV 选模）",
        f"- 适用域：矩形盒（T、c 各体系训练范围），域外结构化拒绝（方案 §3.D）",
        f"- Acc 分母 = 该体系全部题（域外拒绝计错，与 LLM 臂口径一致）；环境 sklearn {sklearn.__version__}",
        "",
        "| 体系 | 题数 | 域外拒绝 | Acc@5%（全题） | Acc@10%（全题） | Acc@10%（域内） | MAE | RMSE | MdAPE | P95 APE | bias |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for s, m in per_system.items():
        lines.append(
            f"| {s} | {m['n_questions']} | {m['n_refused_out_of_domain']} | "
            f"{m['accuracy_5pct_all_question_denominator']*100:.1f}% | "
            f"{m['accuracy_10pct_all_question_denominator']*100:.1f}% | "
            f"{(m['accuracy_10pct_in_domain_denominator']*100 if m['accuracy_10pct_in_domain_denominator'] is not None else float('nan')):.1f}% | "
            f"{m['mae_1e9_m2_s']:.4f} | {m['rmse_1e9_m2_s']:.4f} | "
            f"{m['mdape_percent']:.2f}% | {m['p95_ape_percent']:.2f}% | {m['bias_1e9_m2_s']:+.4f} |"
        )
    lines += [
        "",
        f"**micro Acc@10%（64 题全分母）：{overall['accuracy_10pct_micro']*100:.1f}%；"
        f"macro-system Acc@10%（四体系等权）：{overall['accuracy_10pct_macro_system']*100:.1f}%；"
        f"Acc@5%：micro {overall['accuracy_5pct_micro']*100:.1f}% / macro {overall['accuracy_5pct_macro_system']*100:.1f}%；"
        f"域外拒绝 {overall['n_refused_out_of_domain']}/{overall['n_questions']}**",
        "",
        "> 误差指标（MAE/RMSE/MdAPE/P95/bias）仅基于域内有效预测；域外拒绝行为是后端设计要求（§3.D），",
        "> 在全题 Acc 中计错以与 Base/SFT 臂可比。本文件不含 gold 值与逐题误差（gold 密封纪律）。",
    ]
    open(os.path.join(args.out, "metrics_summary.md"), "w", encoding="utf-8").write("\n".join(lines))

    # ---------- 7. 控制台仅打印聚合 ----------
    print("\n".join(lines))
    print(f"\n输出目录：{args.out}")


if __name__ == "__main__":
    main()
