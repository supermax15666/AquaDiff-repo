# -*- coding: utf-8 -*-
"""E 臂 Agent 交互演示（真实 Qwen3-4B，逐步展示两段式内部过程）。

用法：
    python agent_demo.py                 # 交互模式（输入问题或示例编号）
    python agent_demo.py --once "问题"   # 单题模式（冒烟/演示）
    python agent_demo.py --base-url http://127.0.0.1:1234/v1 --model cet-gguf/qwen3-4b-instruct-2507@q4_k_m
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_core import (Tools, LLMClient, INTENT_SYSTEM, FINAL_SYSTEM,  # noqa: E402
                        host_validate, route_condition, build_tool_block, check_faithfulness)

EXAMPLES = [
    "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K and c = 1.0 mol/L. Return the multiplier x where D = x * 10^-9 m^2/s.",
    "Predict the mutual diffusion coefficient of KCl-H2O at T = 298.15 K and c = 6.0 mol/L. Return the multiplier x where D = x * 10^-9 m^2/s.",
    "Predict the mutual diffusion coefficient of NaCl-H2O at T = 25.0 C and c = 58.44 g/L.",
    "Predict the mutual diffusion coefficient of LiCl-H2O at T = 250 K and c = 2.0 mol/L.",
    "Predict the mutual diffusion coefficient of KCl-H2O at T = 293.0 K and c = 4.45 mol/L.",
    "Predict the mutual diffusion coefficient of NaCl-H2O at c = 0.5 mol/L.",
    "Predict the mutual diffusion coefficient of MgSO4-H2O at T = 298.15 K and c = 1.0 mol/L.",
    "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K and c = 10.0 wt%.",
]


def run_once(tools, llm, question, show=True):
    def out(s=""):
        if show:
            print(s)

    out("=" * 78)
    out(f"【问题】{question}")
    out("=" * 78)

    # ---- 阶段一：LLM 意图提取 ----
    out("\n① 前台（Qwen3-4B）意图提取……")
    try:
        intent, raw1, lat1 = llm.chat_json(INTENT_SYSTEM, question, max_tokens=1024)
        if intent is None:  # 云端偶发空回复：重试一次
            intent, raw1, lat1 = llm.chat_json(INTENT_SYSTEM, question, max_tokens=1024)
    except RuntimeError as e:
        out(f"   ✗ LLM 调用失败：{e}")
        return None
    out(f"   原始输出（{lat1:.1f}s）: {raw1.strip()[:200]}")
    if intent is None:
        out("   → JSON 解析失败：转入澄清")
        out("\n★ 最终答案：请补充信息（系统无法从问题中解析出完整条件）")
        return None
    out(f"   解析意图: {json.dumps(intent, ensure_ascii=False)}")

    # ---- 宿主裁决与换算 ----
    ok, condition, decision = host_validate(intent)
    if not ok:
        out(f"\n② 后台审核：✗ {decision['reason']}")
        at = "澄清请求" if decision["route"] == "clarify" else "拒绝"
        out(f"\n★ 最终答案（{at}，由后台确定性直出）: {decision['reason']}")
        return None
    out(f"\n② 后台审核：✓ 有效条件 → {json.dumps(condition, ensure_ascii=False)}")

    # ---- 确定性路由 ----
    out("\n③ 后台路由（按 v2.16 顺序）：")
    sysid, T, c = condition["system"], condition["temperature_K"], condition["concentration_mol_L"]
    db = tools.query_experimental_records(sysid, T, c)
    if db["hit"]:
        out(f"   3a. 查实验库：命中 {db['n_records']} 条记录（中位 D={db['median_diffusion_1e9_m2_s']}，"
            f"谱系 {', '.join(db['lineage_ids'][:2])}{'…' if len(db['lineage_ids'])>2 else ''}）")
    else:
        out("   3a. 查实验库：未命中")
        sat = tools.check_saturation(sysid, T, c)
        if sat.get("checked"):
            tag = "超过！" if sat["exceeded"] else "未超过"
            out(f"   3b. 饱和检查：c_sat({T:.2f}K)={sat['c_sat_mol_L']:.4f} M，"
                f"输入 {c} M → {tag}（比值 {sat['ratio_to_saturation']:.3f}）")
        else:
            out(f"   3b. 饱和检查：T={T} 超出溶解度表范围 [273.15,373.15] K，跳过")
    r = route_condition(tools, sysid, T, c)
    out(f"   3c. 路径轨迹: {' → '.join(r['trace'])}")
    if r["route"].startswith("db_hit"):
        out(f"   3d. 路由结果: 返回实测记录" + ("（附亚稳过饱和披露）" if r.get("supersaturation_advisory") else ""))
    elif r["route"] == "ml":
        out(f"   3d. 路由结果: 冻结 ML 预测 D={r['ml']['prediction_1e9_m2_s']:.6g}")
    else:
        out(f"   3d. 路由结果: 结构化拒绝（出域字段: {', '.join(r['ml'].get('out_of_domain_fields', []))}）")

    # ---- 阶段二：誊写 ----
    block = build_tool_block(question, r, condition)
    out("\n④ 交给前台誊写的工具结果块：")
    for line in block.splitlines()[1:]:
        out(f"   {line}")
    out("\n⑤ 前台（Qwen3-4B）誊写……")
    try:
        final, raw2, lat2 = llm.chat_json(FINAL_SYSTEM, block, max_tokens=2048)
        if final is None:  # 云端偶发空回复：重试一次
            final, raw2, lat2 = llm.chat_json(FINAL_SYSTEM, block, max_tokens=2048)
    except RuntimeError as e:
        out(f"   ✗ LLM 调用失败：{e}")
        return None
    out(f"   原始输出（{lat2:.1f}s）: {raw2.strip()[:200]}")

    # ---- 硬校验 ----
    f = check_faithfulness(r, final)
    out(f"\n⑥ 后台硬校验（数值/来源逐字核对）: {'✓ 通过' if f['faithful'] else '✗ 不一致 ' + str(f['violations'])}")

    # ---- 最终答案 ----
    out("\n" + "★" * 39)
    if final and final.get("answer_type") == "value":
        out(f"★ 最终答案: D = {final.get('diffusion_1e9_m2_s')} × 10⁻⁹ m²/s"
            f"（来源: {final.get('source_type')}）")
        notes = str(final.get("notes", "")).strip()
        if notes:
            out(f"★ 说明: {notes[:150]}")
    else:
        out(f"★ 最终答案: {json.dumps(final, ensure_ascii=False)[:200]}")
    out("★" * 39)
    return {"condition": condition, "route": r, "final": final, "faithfulness": f}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", default=None, help="单题模式：直接运行该问题")
    ap.add_argument("--base-url", default=os.environ.get("AQUADIFF_BASE_URL", "http://127.0.0.1:1234/v1"))
    ap.add_argument("--model", default=os.environ.get("AQUADIFF_MODEL", "cet-gguf/qwen3-4b-instruct-2507@q4_k_m"))
    ap.add_argument("--api-key", default=None, help="云端 API 密钥（缺省读环境变量 AQUADIFF_API_KEY；本地 LM Studio 无需）")
    ap.add_argument("--extra-body", default=None, help="供应商专属请求字段 JSON（如 '{\"thinking\":{\"type\":\"disabled\"}}'；缺省读环境变量 AQUADIFF_LLM_EXTRA）")
    args = ap.parse_args()

    tools = Tools()
    llm = LLMClient(base_url=args.base_url, model=args.model, api_key=args.api_key,
                    extra_body=json.loads(args.extra_body) if args.extra_body else None)

    if args.once:
        run_once(tools, llm, args.once)
        return

    print("=" * 78)
    print(" E 臂受限 Agent 交互演示（两段式：Qwen3-4B 前台 + 确定性后台）")
    print(f" LLM: {args.model} @ {args.base_url}")
    print(" 输入问题直接运行；输入示例编号运行示例；q 退出")
    print("=" * 78)
    print("示例题目：")
    for i, e in enumerate(EXAMPLES, 1):
        print(f"  [{i}] {e[:72]}{'…' if len(e) > 72 else ''}")
    while True:
        try:
            q = input("\n你的问题> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not q:
            continue
        if q.lower() in ("q", "quit", "exit"):
            break
        if q.isdigit() and 1 <= int(q) <= len(EXAMPLES):
            q = EXAMPLES[int(q) - 1]
        run_once(tools, llm, q)
    print("再见。")


if __name__ == "__main__":
    main()
