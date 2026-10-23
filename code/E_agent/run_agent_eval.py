# -*- coding: utf-8 -*-
"""E 臂 Agent 评测 runner（方案 v2.15/v2.16 §3.E；结果归档 03_实验结果/E臂_*）。

用法（在有 LM Studio + Qwen3-4B-Instruct-2507 的机器上）：
    python run_agent_eval.py --set smoke  --base-url http://127.0.0.1:1234/v1
    python run_agent_eval.py --set challenge --repeats 3
    python run_agent_eval.py --set 642      --repeats 3
    python run_agent_eval.py --set external --repeats 3

每题独立会话、temperature=0、每题 repeats 次（默认 3，与 A/C 臂对齐）。
产物：新 run 目录（sample_results.jsonl + run_manifest.json + metrics_summary.md）。
指标：路由准确率 / 解析成功 / 载荷忠实率 / 拒绝 P-R（外部集与挑战集）+ Acc@10%（642/外部，gold 程序化）。
"""

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_core import Tools, LLMClient, process_question, UNIT_ANSWER_NOTE  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SET_PATHS = {
    "642": os.path.join(ROOT, "02_数据", "02_基准题库与gold_642与240", "four_system_all_questions.jsonl"),
    "external": os.path.join(ROOT, "02_数据", "03_外部前瞻集_64题冻结", "frozen", "questions", "external_questions.jsonl"),
    "challenge": os.path.join(HERE, "frozen", "challenge_set_v2_frozen.json"),
}
GOLD_PATHS = {
    "642": os.path.join(ROOT, "02_数据", "02_基准题库与gold_642与240", "four_system_all_gold.evaluator.jsonl"),
    "external": os.path.join(ROOT, "02_数据", "03_外部前瞻集_64题冻结", "frozen", "gold", "external_gold.evaluator.jsonl"),
}


def load_set(name):
    if name == "challenge":
        cs = json.load(open(SET_PATHS[name], encoding="utf-8"))
        return [{"question_id": i["item_id"], "prompt": i["prompt"],
                 "system": i["expected_intent"].get("system"),
                 "expected_route": i["expected_route"]} for i in cs["items"]]
    return [json.loads(l) for l in open(SET_PATHS[name], encoding="utf-8")]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", required=True, choices=list(SET_PATHS) + ["smoke"])
    ap.add_argument("--repeats", type=int, default=3)
    ap.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    ap.add_argument("--model", default="cet-gguf/qwen3-4b-instruct-2507@q4_k_m")
    ap.add_argument("--out-root", default=os.path.join(ROOT, "03_实验结果", "E臂_受限Agent评测"))
    ap.add_argument("--retry-failed-from", default=None,
                    help="断点续跑：仅重跑该 run 目录中 stage 错误的 (question, repeat) 样本，"
                         "成功样本原样并入新 run（原 run 不动，manifest 记录来源）")
    args = ap.parse_args()

    tools = Tools()
    llm = LLMClient(base_url=args.base_url, model=args.model)
    items = load_set("challenge" if args.set == "smoke" else args.set)
    if args.set == "smoke":
        # 代表性 3 题：正常查库（含誊写链）/ 超饱和夹取→ML / 域外拒绝
        wanted = ["I1", "E3", "G3"]
        items = [i for i in items if i["question_id"] in wanted]

    work = [(it, rep + 1) for it in items for rep in range(args.repeats)]
    carried = []
    if args.retry_failed_from:
        old = [json.loads(l) for l in open(os.path.join(args.retry_failed_from, "sample_results.jsonl"),
                                           encoding="utf-8")]
        failed = {(s["question_id"], s["repeat"]) for s in old if s.get("stage") != "complete"}
        carried = [s for s in old if (s["question_id"], s["repeat"]) not in failed]
        work = [(it, rep) for (it, rep) in work if (it["question_id"], rep) in failed]
        print(f"断点续跑：原 run {len(old)} 样本，携带完好 {len(carried)}，重跑 {len(work)}")

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run_dir = os.path.join(args.out_root, f"agent_{args.set}__{ts}")
    os.makedirs(run_dir, exist_ok=False)

    n_ok = n_err = 0
    samples = list(carried)
    n_ok = sum(1 for s in samples if s.get("stage") == "complete")
    for item, rep in work:
        rec = process_question(tools, llm, item["prompt"])
        rec["question_id"] = item["question_id"]
        rec["repeat"] = rep
        samples.append(rec)
        n_ok += int(rec.get("stage") == "complete")
        n_err += int(rec.get("stage") != "complete")
        print(f"[{n_ok + n_err}/{len(samples)}] {item['question_id']} r{rep} "
              f"route={rec.get('route_result', {}).get('route', rec.get('stage'))}", flush=True)

    with open(os.path.join(run_dir, "sample_results.jsonl"), "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False, default=str) + "\n")

    def sha(p):
        h = hashlib.sha256()
        with open(p, "rb") as fh:
            for c in iter(lambda: fh.read(1 << 20), b""):
                h.update(c)
        return h.hexdigest()

    manifest = {
        "artifact_type": "e_arm_agent_eval_run",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_version": "2.16",
        "set": args.set, "n_items": len(items), "repeats": args.repeats,
        "completed": n_ok, "errors": n_err,
        "llm": {"base_url": args.base_url, "model": args.model, "temperature": 0.0},
        "dependencies": {
            "duckdb_sha256": json.load(open(os.path.join(HERE, "db", "build_manifest.json"), encoding="utf-8"))["db_sha256"],
            "solubility_records_sha256": tools.sat_content_sha,
            "registry_fingerprint": tools.registry_fp,
        },
        "agent_core_sha256": sha(os.path.join(HERE, "agent_core.py")),
        "retry_provenance": ({"resumed_from": os.path.abspath(args.retry_failed_from),
                              "carried_complete_samples": len(carried), "rerun_samples": len(work)}
                             if args.retry_failed_from else None),
    }
    with open(os.path.join(run_dir, "run_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print(f"\nrun 目录：{run_dir}")
    print(f"完成 {n_ok} / 错误 {n_err}（分析用 analyze 脚本另行生成指标汇总）")


if __name__ == "__main__":
    main()
