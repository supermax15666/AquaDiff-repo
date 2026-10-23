# -*- coding: utf-8 -*-
"""E 臂宿主链确定性自测（mock LLM，2026-08-27 首次 45/45 通过）。

验证目标：agent_core 的确定性宿主在**完美意图提取 + 完美誊写**假设下的路由正确性——
包括 v2.16 路由顺序（DB 优先、饱和夹取仅限 ML 路径）、单位换算（°C/°F/g/L/mmol/L）、
夹取与亚稳披露标记、载荷忠实性校验。LLM 真实表现由 run_agent_eval.py 评测（非本脚本职责）。

用法：python test_host_routing.py     （退出码 0=全部通过）
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_core import Tools, LLMClient, process_question  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))

# 单位可换算题的"问题原文值 + 原始单位"（真实 LLM 的提取对象；冻结 expected_intent
# 存的是换算后期望条件，不能直接当桩用）
DIRECT_STUBS = {
    "D1": dict(status="ok", system="NaCl-H2O", temperature=25.0, temperature_unit="C",
               concentration=0.5, concentration_unit="mol/L"),
    "D2": dict(status="ok", system="KCl-H2O", temperature=77.0, temperature_unit="F",
               concentration=0.3, concentration_unit="mol/L"),
    "D3": dict(status="ok", system="NaCl-H2O", temperature=298.15, temperature_unit="K",
               concentration=58.44, concentration_unit="g/L"),
    "D4": dict(status="ok", system="KCl-H2O", temperature=298.15, temperature_unit="K",
               concentration=100.0, concentration_unit="mmol/L"),
    "C1": dict(status="ok", system="NaCl-H2O", temperature=298.15, temperature_unit="K",
               concentration=10.0, concentration_unit="wt_percent"),
    "C2": dict(status="ok", system="KCl-H2O", temperature=298.15, temperature_unit="K",
               concentration=0.5, concentration_unit="mol/kg"),
}


def make_stub(ei):
    if "system" in ei and "c" in ei:
        return dict(status="ok", system=ei["system"], temperature=ei["temperature"],
                    temperature_unit="K", concentration=ei["c"], concentration_unit="mol/L")
    if ei.get("status") == "unsupported":
        return dict(status="unsupported", issues=[ei.get("detected_system", "unsupported system")])
    return dict(status=ei.get("status", "ambiguous"), issues=["ambiguous"])


def main():
    tools = Tools()
    llm = LLMClient(mock=True)
    cs = json.load(open(os.path.join(HERE, "frozen", "challenge_set_frozen.json"), encoding="utf-8"))

    ok, fails = 0, []
    for item in cs["items"]:
        iid = item["item_id"]
        stub = DIRECT_STUBS[iid] if iid in DIRECT_STUBS else make_stub(item["expected_intent"])
        rec = process_question(tools, llm, item["prompt"], stub_intent=stub)
        rr = rec.get("route_result", {})
        got, exp = rr.get("route"), item["expected_route"]["route"]
        extra_ok = True
        if "saturation_clamp" in item["expected_route"]:
            extra_ok = "saturation_clamp" in rr
        if item["expected_route"].get("supersaturation_advisory"):
            extra_ok = extra_ok and rr.get("supersaturation_advisory") is True
        faith = rec.get("faithfulness", {}).get("faithful")
        if got == exp and extra_ok and faith:
            ok += 1
        else:
            fails.append((iid, exp, got, extra_ok, faith, rec.get("error")))

    print(f"挑战集 {len(cs['items'])} 题宿主自测（路由+夹取/披露标记+忠实性）：{ok}/{len(cs['items'])} 通过")
    for f in fails:
        print("  失败:", f)
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
