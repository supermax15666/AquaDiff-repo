# -*- coding: utf-8 -*-
"""E 臂 Agent 网页演示界面（零依赖：仅 Python 标准库 + agent_core）。

用法：
    python agent_web.py            # 启动后自动打开浏览器 http://127.0.0.1:8317
    python agent_web.py --port 8317 --no-browser
    双击 agent_web.bat 亦可。
"""

import argparse
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_core import (Tools, LLMClient, INTENT_SYSTEM, FINAL_SYSTEM,  # noqa: E402
                        host_validate, route_condition, build_tool_block,
                        check_faithfulness, canonical_ml_value)

TOOLS = None
LLM = None

PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>扩散系数受限 Agent · 演示</title>
<style>
  :root { --bg:#f5f6fa; --card:#fff; --ink:#2b2f3a; --sub:#7a8194; --line:#e6e8ef;
          --blue:#3b6fd4; --green:#1e9e63; --red:#c94a3d; --amber:#b8860b; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif; }
  .wrap { max-width:900px; margin:0 auto; padding:24px 16px 80px; }
  h1 { font-size:20px; } .sub { color:var(--sub); font-size:13px; margin-top:4px; }
  .banner { background:linear-gradient(135deg,#20304f,#3b6fd4); color:#fff; border-radius:14px;
            padding:18px 22px; margin-bottom:16px; }
  .banner h1 { margin:0 0 4px; color:#fff; } .banner .sub { color:#c9d6f2; }
  .chips { display:flex; flex-wrap:wrap; gap:8px; margin:14px 0; }
  .chip { background:var(--card); border:1px solid var(--line); border-radius:16px;
          padding:5px 12px; font-size:12px; cursor:pointer; color:#44506b; }
  .chip:hover { border-color:var(--blue); color:var(--blue); }
  .ask { display:flex; gap:8px; margin:10px 0 20px; }
  .ask input { flex:1; border:1px solid var(--line); border-radius:10px; padding:11px 14px;
               font-size:14px; outline:none; background:var(--card); }
  .ask input:focus { border-color:var(--blue); }
  .ask button { border:none; border-radius:10px; background:var(--blue); color:#fff;
                padding:0 22px; font-size:14px; cursor:pointer; }
  .ask button:disabled { background:#9db3dd; }
  .turn { margin-bottom:28px; }
  .q { display:flex; justify-content:flex-end; }
  .q .bubble { background:var(--blue); color:#fff; border-radius:14px 14px 2px 14px;
               padding:10px 14px; max-width:80%; font-size:14px; }
  .stage { background:var(--card); border:1px solid var(--line); border-radius:12px;
           padding:12px 14px; margin-top:10px; font-size:13px; }
  .stage .t { display:flex; align-items:center; gap:8px; font-weight:600; }
  .stage .dot { width:9px; height:9px; border-radius:50%; background:var(--blue); }
  .stage.ok .dot { background:var(--green); } .stage.warn .dot { background:var(--amber); }
  .stage.fail .dot { background:var(--red); }
  .stage .lat { margin-left:auto; color:var(--sub); font-weight:400; font-size:12px; }
  .kv { margin-top:8px; display:grid; grid-template-columns:130px 1fr; gap:3px 10px; }
  .kv .k { color:var(--sub); } .kv .v { font-weight:500; word-break:break-all; }
  .trace { margin-top:8px; display:flex; flex-wrap:wrap; gap:6px; }
  .step { background:#eef2fb; color:#33508f; border-radius:6px; padding:2px 8px; font-size:12px; }
  .step.bad { background:#fbeeee; color:#a24036; }
  details { margin-top:8px; } summary { color:var(--sub); cursor:pointer; font-size:12px; }
  pre { background:#f2f3f8; border-radius:8px; padding:10px; font-size:12px;
        white-space:pre-wrap; word-break:break-all; margin:6px 0 0; }
  .final { border-radius:12px; padding:14px 16px; margin-top:12px; color:#fff; }
  .final.value { background:var(--green); } .final.refusal { background:var(--red); }
  .final.clarify { background:var(--amber); }
  .final .lab { font-size:12px; opacity:.85; }
  .final .num { font-size:30px; font-weight:700; margin:4px 0; }
  .final .src { font-size:12px; opacity:.9; }
  .final .note { background:rgba(255,255,255,.18); border-radius:8px; padding:8px 10px;
                 margin-top:8px; font-size:12px; }
  .faith { margin-top:8px; font-size:12px; color:var(--sub); }
  .faith b.ok { color:var(--green); } .faith b.no { color:var(--red); }
  .thinking { color:var(--sub); font-size:13px; padding:10px 4px; }
</style>
</head>
<body>
<div class="wrap">
  <div class="banner">
    <h1>扩散系数受限 Agent</h1>
    <div class="sub">两段式：Qwen3-4B 只做意图提取与誊写 · 查库 / 饱和检查 / 冻结模型 / 拒绝全部由确定性后台执行（方案 v2.16）</div>
  </div>
  <div class="chips" id="chips"></div>
  <div class="ask">
    <input id="q" placeholder="输入问题，例如：25°C、1.0 mol/L 氯化钠溶液的互扩散系数是多少？" />
    <button id="go" onclick="ask()">提问</button>
  </div>
  <div id="turns"></div>
</div>
<script>
const EXAMPLES = [
  "25°C、1.0 mol/L 氯化钠溶液的互扩散系数是多少？",
  "Predict the mutual diffusion coefficient of KCl-H2O at T = 298.15 K and c = 6.0 mol/L.",
  "Predict the mutual diffusion coefficient of LiCl-H2O at T = 250 K and c = 2.0 mol/L.",
  "氯化钾在 273.15 K、4.5 mol/L 时的扩散系数",
  "293.0 K、4.45 mol/L 的 KCl 溶液扩散系数是多少？",
  "硫酸镁溶液在 298.15 K、1.0 mol/L 的扩散系数",
  "氯化钠溶液 298.15 K、10 wt% 的扩散系数",
  "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K.",
];
const chips = document.getElementById('chips');
EXAMPLES.forEach((e,i)=>{ const c=document.createElement('div'); c.className='chip';
  c.textContent=(i+1)+'. '+e.slice(0,40)+(e.length>40?'…':''); c.onclick=()=>{document.getElementById('q').value=e;ask();};
  chips.appendChild(c); });
function esc(s){ return String(s??'').replace(/[&<>]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[m])); }
function kv(rows){ if(!rows||!rows.length) return '';
  return '<div class="kv">'+rows.map(r=>`<div class="k">${esc(r[0])}</div><div class="v">${esc(r[1])}</div>`).join('')+'</div>'; }
function stageHtml(s){
  const cls = s.status||'';
  let inner = `<div class="t"><span class="dot"></span>${esc(s.title)}<span class="lat">${s.lat??''}</span></div>`;
  inner += kv(s.rows);
  if(s.trace) inner += '<div class="trace">'+s.trace.map(t=>`<span class="step${/refuse|miss/.test(t)?' bad':''}">${esc(t)}</span>`).join('')+'</div>';
  if(s.raw) inner += `<details><summary>模型原始输出</summary><pre>${esc(s.raw)}</pre></details>`;
  return `<div class="stage ${cls}">${inner}</div>`;
}
async function ask(){
  const q = document.getElementById('q').value.trim(); if(!q) return;
  const box = document.getElementById('turns');
  const turn = document.createElement('div'); turn.className='turn';
  turn.innerHTML = `<div class="q"><div class="bubble">${esc(q)}</div></div><div class="thinking">Agent 处理中……</div>`;
  box.prepend(turn);
  document.getElementById('go').disabled = true;
  try{
    const r = await fetch('/api/ask',{method:'POST',headers:{'Content-Type':'application/json'},
                                     body:JSON.stringify({question:q})});
    const d = await r.json();
    turn.querySelector('.thinking').remove();
    render(turn, d);
  }catch(e){
    turn.querySelector('.thinking').textContent = '请求失败：'+e+'（请确认 agent_web.py 仍在运行）';
  }
  document.getElementById('go').disabled = false;
}
function render(turn, d){
  let h = '';
  (d.stages||[]).forEach(s=>{ h += stageHtml(s); });
  const f = d.final||{};
  if(f.answer_type==='value'){
    h += `<div class="final value"><div class="lab">最终答案</div>
          <div class="num">D = ${esc(f.diffusion_1e9_m2_s)} × 10⁻⁹ m²/s</div>
          <div class="src">来源：${f.source_type==='experimental_record'?'实验记录（DuckDB 精确命中）':'冻结专用数值模型（registry ffbc8b45）'}</div>
          ${f.notes?`<div class="note">${esc(f.notes)}</div>`:''}</div>`;
  } else if(f.answer_type==='refusal'){
    h += `<div class="final refusal"><div class="lab">结构化拒绝</div>
          <div style="font-size:15px;margin-top:4px">${esc(f.notes||'')}</div></div>`;
  } else {
    h += `<div class="final clarify"><div class="lab">请求澄清</div>
          <div style="font-size:15px;margin-top:4px">${esc(f.notes||'')}</div></div>`;
  }
  const fa = d.faithfulness;
  if(fa) h += `<div class="faith">载荷硬校验：${fa.faithful?'<b class="ok">✓ 数值与来源和工具输出逐字一致</b>':'<b class="no">✗ 不一致：'+esc(JSON.stringify(fa.violations))+'</b>'}</div>`;
  turn.innerHTML = `<div class="q"><div class="bubble">${esc(d.question)}</div></div>` + h;
}
document.getElementById('q').addEventListener('keydown', e=>{ if(e.key==='Enter') ask(); });
</script>
</body>
</html>"""


def process_for_ui(question):
    """运行完整管线，返回结构化阶段（供前端渲染）。"""
    stages, err = [], None
    # ① 意图提取
    try:
        intent, raw1, lat1 = LLM.chat_json(INTENT_SYSTEM, question, max_tokens=1024)
        if intent is None:  # 云端偶发空回复：重试一次
            intent, raw1, lat1 = LLM.chat_json(INTENT_SYSTEM, question, max_tokens=1024)
    except RuntimeError as e:
        return {"question": question, "stages": stages, "final":
                {"answer_type": "clarify", "notes": f"模型调用失败：{e}"}, "faithfulness": None}
    s1 = {"title": "① 前台（Qwen3-4B）· 意图提取", "lat": f"{lat1:.1f}s", "raw": raw1}
    if intent is None:
        s1["status"], s1["rows"] = "fail", [["结果", "JSON 解析失败，转入澄清"]]
        stages.append(s1)
        return {"question": question, "stages": stages,
                "final": {"answer_type": "clarify", "notes": "无法从问题中解析出结构化条件"}, "faithfulness": None}
    s1["status"] = "ok"
    s1["rows"] = [["体系", intent.get("system", "?")],
                  ["温度", f"{intent.get('temperature')} {intent.get('temperature_unit','')}".strip()],
                  ["浓度", f"{intent.get('concentration')} {intent.get('concentration_unit','')}".strip()]]
    stages.append(s1)
    # ② 宿主审核
    ok, condition, decision = host_validate(intent)
    if not ok:
        s2 = {"title": "② 后台 · 审核与换算", "status": "fail",
              "rows": [["判定", "不通过"], ["原因", decision.get("reason", "")]]}
        stages.append(s2)
        return {"question": question, "stages": stages,
                "final": {"answer_type": "clarify" if decision["route"] == "clarify" else "refusal",
                          "notes": decision.get("reason", "")}, "faithfulness": None}
    conv = []
    if abs(condition["temperature_K"] - (intent.get("temperature") or 0)) > 1e-9:
        conv.append(f"温度 {intent['temperature']}{intent['temperature_unit']} → {condition['temperature_K']} K")
    if abs(condition["concentration_mol_L"] - (intent.get("concentration") or 0)) > 1e-9:
        conv.append(f"浓度 {intent['concentration']} {intent['concentration_unit']} → {condition['concentration_mol_L']} mol/L")
    stages.append({"title": "② 后台 · 审核与换算", "status": "ok",
                   "rows": [["有效条件", f"{condition['system']} · T={condition['temperature_K']} K · c={condition['concentration_mol_L']} mol/L"],
                            ["单位换算", "; ".join(conv) if conv else "无需换算"]]})
    # ③ 路由
    sysid, T, c = condition["system"], condition["temperature_K"], condition["concentration_mol_L"]
    r = route_condition(TOOLS, sysid, T, c)
    rows3 = []
    if r["route"].startswith("db_hit"):
        db = r["db"]
        rows3 = [["实验库", f"命中 {db['n_records']} 条记录（中位数 D={db['median_diffusion_1e9_m2_s']}）"],
                 ["谱系", "、".join(db["lineage_ids"][:4]) + ("…" if len(db["lineage_ids"]) > 4 else "")],
                 ["文献", "；".join(db["references"][:2]) + ("…" if len(db["references"]) > 2 else "")]]
        if r.get("supersaturation_advisory"):
            rows3.append(["⚠ 披露", "该浓度超过平衡溶解度：返回值为实测记录（可能为亚稳过饱和测量）"])
    else:
        sat = r.get("saturation", {})
        if sat.get("checked"):
            rows3.append(["饱和检查", f"c_sat({T:.2f} K) = {sat['c_sat_mol_L']:.4f} mol/L，输入 {c} mol/L（比值 {sat['ratio_to_saturation']:.3f}）"
                          + (" → 超过，按饱和浓度夹取" if sat.get("exceeded") else " → 未超过")])
        else:
            rows3.append(["饱和检查", f"T={T} K 超出溶解度表范围 [273.15, 373.15] K，跳过"])
        if r["route"] == "ml":
            rows3.append(["域盒检查", "在适用域内 → 调用冻结专用模型"])
            rows3.append(["ML 预测", f"D = {canonical_ml_value(r['ml']['prediction_1e9_m2_s'])} × 10⁻⁹ m²/s"])
        else:
            ad = r["ml"].get("domain", {})
            rng_t, rng_c = ad.get("temperature_K", {}), ad.get("concentration_mol_L", {})
            rows3.append(["域盒检查", f"出域字段：{'、'.join(r['ml'].get('out_of_domain_fields', []))}；"
                          f"有效范围 T [{rng_t.get('min')}, {rng_t.get('max')}] K，c [{rng_c.get('min')}, {rng_c.get('max')}] mol/L"])
    st3 = {"title": "③ 后台 · 确定性路由", "status": "fail" if r["route"] == "refuse_out_of_domain" else "ok",
           "rows": rows3, "trace": r["trace"]}
    stages.append(st3)
    # ④⑤ 誊写
    block = build_tool_block(question, r, condition)
    stages.append({"title": "④ 工具结果块（交给前台誊写）", "status": "",
                   "rows": [["内容", block.split("TOOL RESULT:", 1)[-1].strip().replace("\n", " ⏎ ")[:300]]]})
    try:
        final, raw2, lat2 = LLM.chat_json(FINAL_SYSTEM, block, max_tokens=2048)
        if final is None:  # 云端偶发空回复：重试一次
            final, raw2, lat2 = LLM.chat_json(FINAL_SYSTEM, block, max_tokens=2048)
    except RuntimeError as e:
        return {"question": question, "stages": stages,
                "final": {"answer_type": "clarify", "notes": f"誊写阶段模型调用失败：{e}"}, "faithfulness": None}
    stages.append({"title": "⑤ 前台（Qwen3-4B）· 终答誊写", "lat": f"{lat2:.1f}s", "raw": raw2,
                   "status": "ok" if final else "fail"})
    if final is None:
        final = {"answer_type": "clarify", "notes": "誊写 JSON 解析失败（计为忠实性失败）"}
    fa = check_faithfulness(r, final)
    return {"question": question, "stages": stages, "final": final, "faithfulness": fa}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path != "/api/ask":
            self._send(404, b"not found", "text/plain")
            return
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", errors="replace")
        try:
            body = json.loads(text)
            result = process_for_ui(body.get("question", "").strip())
            self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        except Exception as e:
            self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")


def main():
    global TOOLS, LLM
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8317)
    ap.add_argument("--base-url", default="http://127.0.0.1:1234/v1")
    ap.add_argument("--model", default="cet-gguf/qwen3-4b-instruct-2507@q4_k_m")
    ap.add_argument("--api-key", default=None, help="云端 API 密钥（缺省读环境变量 AQUADIFF_API_KEY；本地 LM Studio 无需）")
    ap.add_argument("--extra-body", default=None, help="供应商专属请求字段 JSON（如 '{\"thinking\":{\"type\":\"disabled\"}}'；缺省读环境变量 AQUADIFF_LLM_EXTRA）")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    TOOLS = Tools()
    LLM = LLMClient(base_url=args.base_url, model=args.model, api_key=args.api_key,
                    extra_body=json.loads(args.extra_body) if args.extra_body else None)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"✅ Agent 网页演示已启动：{url}  （LLM: {args.model} @ {args.base_url}）")
    print("   浏览器未自动打开时请手动访问上面的地址；Ctrl+C 退出。")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
