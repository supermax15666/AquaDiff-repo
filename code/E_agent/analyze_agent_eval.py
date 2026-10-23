# -*- coding: utf-8 -*-
"""E 臂 Agent 评测指标分析（方案 v2.15/v2.16 §4 精简指标集）。

用法：
    python analyze_agent_eval.py --run-dir <run目录> --set challenge|642|external

产出：run 目录内 metrics.json + metrics_summary.md。
指标：路由准确率 / 意图解析正确率(挑战集) / JSON 解析成功率 / 载荷忠实率 /
拒绝 precision-recall / Acc@10%（642/外部，gold 程序化、仅聚合输出）/ 延迟。
"""

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
from agent_core import Tools, route_condition  # noqa: E402

QPATH = {
    "642": os.path.join(ROOT, "02_数据", "02_基准题库与gold_642与240", "four_system_all_questions.jsonl"),
    "external": os.path.join(ROOT, "02_数据", "03_外部前瞻集_64题冻结", "frozen", "questions", "external_questions.jsonl"),
}
GPATH = {
    "642": os.path.join(ROOT, "02_数据", "02_基准题库与gold_642与240", "four_system_all_gold.evaluator.jsonl"),
    "external": os.path.join(ROOT, "02_数据", "03_外部前瞻集_64题冻结", "frozen", "gold", "external_gold.evaluator.jsonl"),
}


def derive_expected_routes(set_name):
    """机械推导每题期望路由（与冻结/宿主同口径：DB→饱和→域盒）。"""
    tools = Tools()
    exp = {}
    if set_name == "challenge":
        cs = json.load(open(os.path.join(HERE, "frozen", "challenge_set_v2_frozen.json"), encoding="utf-8"))
        for i in cs["items"]:
            exp[i["item_id"]] = i
        return exp
    for q in (json.loads(l) for l in open(QPATH[set_name], encoding="utf-8")):
        r = route_condition(tools, q["system"], float(q["temperature_K"]), float(q["concentration_mol_L"]))
        exp[q["question_id"]] = {"expected_route": {"route": r["route"]}, "system": q["system"]}
    return exp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-dir", required=True)
    ap.add_argument("--set", required=True, choices=["challenge", "642", "external"])
    args = ap.parse_args()

    expected = derive_expected_routes(args.set)
    gold = {}
    if args.set in GPATH:
        for l in open(GPATH[args.set], encoding="utf-8"):
            d = json.loads(l)
            gold[d["question_id"]] = float(d["diffusion_1e9_m2_s"])

    samples = [json.loads(l) for l in open(os.path.join(args.run_dir, "sample_results.jsonl"), encoding="utf-8")]
    n = len(samples)

    # ---- 1. 路由准确率 ----
    route_ok = route_n = 0
    confusion = {}
    for s in samples:
        e = expected.get(s["question_id"])
        if not e:
            continue
        route_n += 1
        er, rr = e["expected_route"], s.get("route_result", {})
        ok = rr.get("route") == er["route"]
        if ok and "saturation_clamp" in er:
            ok = "saturation_clamp" in rr
        if ok and er.get("supersaturation_advisory"):
            ok = rr.get("supersaturation_advisory") is True
        route_ok += int(ok)
        if not ok:
            k = f'{er["route"]}->{rr.get("route")}'
            confusion[k] = confusion.get(k, 0) + 1

    # ---- 2. 意图解析（挑战集逐题对照；全集报 JSON 解析成功率） ----
    intent_ok = intent_n = 0
    intent_fails = []
    if args.set == "challenge":
        for s in samples:
            e = expected[s["question_id"]]
            ei, it = e["expected_intent"], s.get("intent") or {}
            intent_n += 1
            if "system" in ei:
                good = (it.get("status") == "ok" and it.get("system") == ei["system"]
                        and abs((it.get("temperature") or -1e9) - ei["temperature"]) < 0.01
                        and abs((it.get("concentration") or -1e9) - ei["c"]) < 1e-6)
            else:
                want = ei.get("status")
                good = (it.get("status") == want) if want in ("unsupported",) else (
                    it.get("status") in ("ambiguous", "missing_fields"))
            intent_ok += int(good)
            if not good:
                intent_fails.append((s["question_id"], ei.get("status"), it.get("status"),
                                     it.get("temperature"), it.get("concentration"), it.get("concentration_unit")))
    parse_ok = sum(1 for s in samples if s.get("intent") is not None)

    # ---- 3. 载荷忠实率 ----
    faith_ok = faith_n = 0
    viol = {}
    for s in samples:
        fa = s.get("faithfulness")
        if fa and not fa.get("host_authored"):
            faith_n += 1
            faith_ok += int(fa["faithful"])
            for v in fa.get("violations", []):
                k = v.split("=")[0]
                viol[k] = viol.get(k, 0) + 1

    # ---- 4. 拒绝 precision / recall（题级；真值=机械推导的 refuse_out_of_domain） ----
    by_q = {}
    for s in samples:
        by_q.setdefault(s["question_id"], []).append(s)
    true_ref = agent_ref = both = 0
    for qid, ss in by_q.items():
        e = expected.get(qid)
        if not e:
            continue
        true = e["expected_route"]["route"].startswith("refuse")  # 域外/不支持/单位不可换算均属应拒绝
        refused = any(str(x.get("route_result", {}).get("route", "")).startswith("refuse")
                      or (x.get("final") or {}).get("answer_type") == "refusal" for x in ss)
        true_ref += int(true)
        agent_ref += int(refused)
        both += int(true and refused)
    precision = both / agent_ref if agent_ref else None
    recall = both / true_ref if true_ref else None

    # ---- 5. Acc@10%（题级：3 次中至少 1 次正确；拒绝/澄清/非数值计错） ----
    acc10 = acc10_strict = None
    per_sys = {}
    if gold:
        hits_any = hits_all = 0
        for qid, ss in by_q.items():
            g = gold.get(qid)
            if g is None:
                continue
            corr = sum(1 for x in ss
                       if (x.get("final") or {}).get("answer_type") == "value"
                       and isinstance((x.get("final") or {}).get("diffusion_1e9_m2_s"), (int, float))
                       and abs(x["final"]["diffusion_1e9_m2_s"] - g) / abs(g) <= 0.10)
            sysid = ss[0].get("route_result", {}).get("system") or _sys_of(expected, qid, args.set)
            a, b = per_sys.get(sysid, (0, 0))
            per_sys[sysid] = (a + int(corr > 0), b + 1)
            hits_any += int(corr > 0)
            hits_all += int(corr == len(ss))
        acc10 = hits_any / len(by_q)
        acc10_strict = hits_all / len(by_q)

    lat1 = [s["intent_latency_s"] for s in samples if s.get("intent_latency_s") is not None]
    lat2 = [s["final_latency_s"] for s in samples if s.get("final_latency_s") is not None]

    summary = {
        "set": args.set, "n_samples": n,
        "route_accuracy": round(route_ok / route_n, 4) if route_n else None,
        "route_confusion": confusion,
        "intent_accuracy": round(intent_ok / intent_n, 4) if intent_n else None,
        "intent_json_parse_success": round(parse_ok / n, 4),
        "faithfulness": round(faith_ok / faith_n, 4) if faith_n else None,
        "faithfulness_violations": viol,
        "refusal_precision": round(precision, 4) if precision is not None else None,
        "refusal_recall": round(recall, 4) if recall is not None else None,
        "refusal_counts": {"true_refusal_questions": true_ref, "agent_refusal_questions": agent_ref, "both": both},
        "acc10_any_repeat": round(acc10, 4) if acc10 is not None else None,
        "acc10_all_repeats": round(acc10_strict, 4) if acc10_strict is not None else None,
        "per_system_acc10": {k: f"{a}/{b}" for k, (a, b) in per_sys.items()},
        "latency_s": {"intent_mean": round(sum(lat1) / len(lat1), 2) if lat1 else None,
                      "final_mean": round(sum(lat2) / len(lat2), 2) if lat2 else None},
        "intent_fail_examples": intent_fails[:8],
    }
    json.dump(summary, open(os.path.join(args.run_dir, "metrics.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)

    lines = [f"# E 臂 Agent 评测指标 · {args.set}（{n} 样本）", ""]
    for k, v in summary.items():
        if k == "intent_fail_examples":
            lines.append(f"- {k}: {v}")
        else:
            lines.append(f"- {k}: {v}")
    open(os.path.join(args.run_dir, "metrics_summary.md"), "w", encoding="utf-8").write("\n".join(lines))
    print(json.dumps(summary, ensure_ascii=False, indent=1, default=str))


def _sys_of(expected, qid, set_name):
    e = expected.get(qid, {})
    if "system" in e:
        return e["system"]
    ei = e.get("expected_intent")
    if ei and "system" in ei:
        return ei["system"]
    return "?"


if __name__ == "__main__":
    main()
