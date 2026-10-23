# -*- coding: utf-8 -*-
"""agent_web v2 流式端点确定性自测（不依赖网络与 LLM 服务）。

验证：① /api/ask_stream NDJSON 逐行实时到达（stage 行先于 final 行 ≥0.3 s）；
② stage 字段齐备（n/role/tool/route）；③ 终止块正确（不悬挂）；④ /api/ask 兼容；
⑤ 拒绝路径的 _meta 结构化字段。
"""
import http.client
import json
import threading
import time
from http.server import ThreadingHTTPServer

import agent_web
from agent_core import Tools, INTENT_SYSTEM

PORT = 8319


class StubLLM:
    """确定性桩：意图/誊写两阶段各延迟 0.5 s。"""

    def chat_json(self, system, user, max_tokens=512, temperature=0.0, **kw):
        time.sleep(0.5)
        if system == INTENT_SYSTEM:
            obj = {"status": "ok", "system": "NaCl-H2O", "temperature": 25,
                   "temperature_unit": "C", "concentration": 1.0,
                   "concentration_unit": "mol/L", "issues": []}
        else:
            obj = {"answer_type": "value", "diffusion_1e9_m2_s": 1.483,
                   "source_type": "experimental_record",
                   "source_reference": "stub", "notes": ""}
        return obj, json.dumps(obj, ensure_ascii=False), 0.5


class RefuseStubLLM(StubLLM):
    def chat_json(self, system, user, max_tokens=512, temperature=0.0, **kw):
        time.sleep(0.5)
        if system == INTENT_SYSTEM:
            obj = {"status": "ok", "system": "LiCl-H2O", "temperature": 250,
                   "temperature_unit": "K", "concentration": 2.0,
                   "concentration_unit": "mol/L", "issues": []}
        else:
            obj = {"answer_type": "refusal", "notes": "out of applicability domain"}
        return obj, json.dumps(obj, ensure_ascii=False), 0.5


def run_stream(question):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
    t0 = time.time()
    conn.request("POST", "/api/ask_stream", body=json.dumps({"question": question}),
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    assert resp.status == 200, resp.status
    events = []
    for raw in resp:
        line = raw.decode("utf-8").strip()
        if line:
            events.append((round(time.time() - t0, 2), json.loads(line)))
    conn.close()
    return events


def main():
    agent_web.TOOLS = Tools()
    agent_web.LLM = StubLLM()
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), agent_web.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        # 页面
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=10)
        conn.request("GET", "/")
        r = conn.getresponse(); body = r.read().decode("utf-8"); conn.close()
        assert r.status == 200 and "pipeflow" in body and "ask_stream" in body, "page broken"
        print("page ok")

        # 流式：命中路径
        ev = run_stream("25°C、1.0 mol/L 氯化钠溶液的互扩散系数是多少？")
        kinds = [e["type"] for _, e in ev]
        assert kinds == ["stage"] * 5 + ["final"], kinds
        stages = [e["stage"] for _, e in ev if e["type"] == "stage"]
        assert [s["n"] for s in stages] == [1, 2, 3, 4, 5]
        assert [s["role"] for s in stages] == ["llm", "host", "host", "host", "llm"]
        assert stages[3].get("tool"), "stage4 缺工具全文"
        assert stages[2].get("route", "").startswith("db_hit"), stages[2].get("route")
        fin = [e for _, e in ev if e["type"] == "final"][0]
        assert fin["final"]["answer_type"] == "value"
        assert fin["final"]["_meta"]["kind"] == "db_hit"
        t_stage1 = ev[0][0]
        t_final = ev[-1][0]
        assert t_final - t_stage1 >= 0.7, (t_stage1, t_final, "流式未逐行到达（被整体缓冲）")
        print(f"stream(db_hit) ok: stage1@{t_stage1}s final@{t_final}s "
              f"meta={fin['final']['_meta']['kind']} faithful={fin['faithfulness']['faithful']}")

        # 流式：拒绝路径
        agent_web.LLM = RefuseStubLLM()
        ev2 = run_stream("LiCl 250 K 2.0 mol/L")
        kinds2 = [e["type"] for _, e in ev2]
        assert kinds2 == ["stage"] * 5 + ["final"], kinds2
        fin2 = [e for _, e in ev2 if e["type"] == "final"][0]
        m = fin2["final"]["_meta"]
        assert fin2["final"]["answer_type"] == "refusal" and m["kind"] == "refuse"
        assert m["out_fields"] and len(m["valid_T"]) == 2, m
        assert fin2["final"]["_meta"]["valid_T"][0] == 273.15, m["valid_T"]
        print(f"stream(refuse) ok: out_fields={m['out_fields']} valid_T={m['valid_T']}")

        # 兼容端点
        conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=30)
        conn.request("POST", "/api/ask", body=json.dumps({"question": "25°C、1.0 mol/L 氯化钠溶液的互扩散系数是多少？"}),
                     headers={"Content-Type": "application/json"})
        r = conn.getresponse(); d = json.loads(r.read().decode("utf-8")); conn.close()
        assert r.status == 200 and len(d["stages"]) == 5 and "final" in d and "faithfulness" in d
        print("legacy /api/ask ok")
        print("\n全部通过 ✅")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
