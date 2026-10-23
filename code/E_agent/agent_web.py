# -*- coding: utf-8 -*-
"""E 臂 Agent 网页演示界面 v2（零依赖：仅 Python 标准库 + agent_core）。

设计要点（2026-09-07 改版）：
  - 双角色视觉语言：大模型环节=聊天气泡卡（蓝、圆角）；后台程序环节=控制台卡（青绿、方角、
    等宽字体）；④ 工具结果块为深色终端卡——"两段式"一眼可辨；
  - 顶部常驻流水线：①意图→②审核→③路由→④工具→⑤誊写→答案，逐环点亮并标耗时，
    提问期间可看到大模型环节慢思考、后台程序环节毫秒级闪过（节奏即架构）；
  - 流式推送：POST /api/ask_stream 以 NDJSON 逐阶段返回（Transfer-Encoding: chunked），
    前端边收边渲染；/api/ask 保留为一次性 JSON（调试用）；
  - 配色与汇报 PPT 统一：实测值=青绿 / 模型预测=蓝 / 拒绝=红 / 澄清·披露=琥珀。
  - 云端 API 支持：--base-url/--model/--api-key/--extra-body（或环境变量
    AQUADIFF_API_KEY / AQUADIFF_LLM_EXTRA，见 agent_web_cloud.bat）。

用法：
    python agent_web.py            # 启动后自动打开浏览器 http://127.0.0.1:8317
    python agent_web.py --port 8317 --no-browser
    双击 agent_web.bat（本地 LM Studio）或 agent_web_cloud.bat（云端 API）亦可。
"""

import argparse
import json
import os
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from agent_core import (Tools, LLMClient, INTENT_SYSTEM, FINAL_SYSTEM,  # noqa: E402
                        host_validate, route_condition, build_tool_block,
                        check_faithfulness, canonical_ml_value, REG_DIR)

TOOLS = None
LLM = None

_REG_INFO = None


def reg_info():
    """registry.json 逐体系信息（冻结模型名等；只读冻结产物，缓存一次）。"""
    global _REG_INFO
    if _REG_INFO is None:
        reg = json.load(open(os.path.join(REG_DIR, "registry.json"), encoding="utf-8"))
        _REG_INFO = {s["system"]: s for s in reg["systems"]}
    return _REG_INFO


def _llm_label_row():
    """阶段①显示的当前大模型标识：模型名 @ 端点主机（本地/云端一眼可辨）。"""
    model = getattr(LLM, "model", None) or "未知模型"
    base = getattr(LLM, "base_url", "") or ""
    try:
        host = base.split("//", 1)[-1].split("/", 1)[0]
    except Exception:  # noqa: BLE001
        host = ""
    return ["模型", f"{model} @ {host}" if host else model]

PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<title>AquaDiff · 扩散系数受限智能体演示</title>
<style>
  :root { --bg:#f3f7f6; --card:#fff; --ink:#1f2937; --sub:#64748b; --line:#e2e8f0;
          --llm:#075985; --llm-tint:#eaf2f9; --llm-line:#bfd8ea;
          --host:#0f766e; --host-tint:#e7f3f0; --host-line:#bcd9d3;
          --bad:#c0392b; --bad-tint:#fbecea;
          --warn:#b45309; --warn-tint:#fdf3e3;
          --dark:#0b3640;
          --mono:"Cascadia Mono",Consolas,"Courier New",monospace; }
  * { box-sizing:border-box; }
  body { margin:0; background:var(--bg); color:var(--ink);
         font-family:"Microsoft YaHei","PingFang SC",system-ui,sans-serif; }
  .wrap { max-width:1120px; margin:0 auto; padding:18px 16px 90px; }

  /* ---- 头部 ---- */
  .banner { background:linear-gradient(120deg,#0b3640,#0f4c52); color:#fff; border-radius:14px;
            padding:16px 22px; margin-bottom:14px; display:flex; align-items:center; gap:14px; flex-wrap:wrap; }
  .banner h1 { margin:0; font-size:21px; letter-spacing:.5px; }
  .banner .sub { color:#9fc0bb; font-size:12.5px; margin-top:4px; }
  .banner .tags { margin-left:auto; display:flex; gap:8px; }
  .banner .tag { border:1px solid rgba(255,255,255,.35); color:#dcecea; border-radius:14px;
                 padding:4px 12px; font-size:12px; }

  /* ---- 顶部分支决策图（左：SVG 路线树；右：图例列） ---- */
  .pipe { background:var(--card); border:1px solid var(--line); border-radius:14px;
          padding:14px 18px 10px; margin-bottom:14px; display:flex; gap:16px; align-items:stretch; }
  .pipeflow { flex:1; min-width:0; }
  .pipeflow svg { width:100%; height:auto; display:block; }
  .pipecap { font-size:10px; color:#8fa19c; margin-top:3px; line-height:1.5; }
  .te { stroke:#d3deda; stroke-width:1.6; fill:none; transition:stroke .25s, stroke-width .25s; }
  .te.on.llmc { stroke:var(--llm); stroke-width:2.6; }
  .te.on.hostc { stroke:var(--host); stroke-width:2.6; }
  .tel { font-size:8.5px; fill:#93a5a0; }
  .tn .tb { fill:#f0f4f2; stroke:var(--line); stroke-width:1.2; transition:fill .25s; }
  .tn .tt { fill:#7b8b86; font-size:10px; font-weight:600; text-anchor:middle; }
  .tn.on .tb { stroke:none; }
  .tn.on .tt { fill:#fff; font-weight:700; }
  .tn.llm.on .tb { fill:var(--llm); }
  .tn.host.on .tb { fill:var(--host); }
  .tn.db.on .tb { fill:var(--host); }
  .tn.ml.on .tb { fill:var(--llm); }
  .tn.ref.on .tb { fill:var(--bad); }
  .tn.warn.on .tb { fill:var(--warn); }
  .tn.skip .tb { fill:#fff; stroke:#b9c6c2; stroke-dasharray:3 2.5; }
  .tn.skip .tt { fill:#a9b8b3; font-weight:400; }
  .tn.active .tb { animation:tpulse 1.1s ease-in-out infinite; stroke-width:2.6; }
  @keyframes tpulse { 0%,100%{opacity:1;} 50%{opacity:.4;} }
  .tsub { font-size:8.5px; fill:#8fa19c; text-anchor:middle; }
  .tval { font-size:9.5px; font-weight:700; text-anchor:middle; fill:var(--ink); }
  .pipeleg { flex:0 0 215px; border-left:1px solid var(--line); padding-left:16px;
             display:flex; flex-direction:column; justify-content:center; gap:7px;
             font-size:11.5px; color:var(--sub); }
  .pipeleg .lrow { display:flex; align-items:center; gap:7px; }
  .pipeleg .lgrp { font-size:10.5px; color:#8fa19c; margin-top:3px; letter-spacing:1px; }
  .anscolors { display:grid; grid-template-columns:1fr 1fr; gap:5px 10px; }
  @media (max-width:1000px){
    .pipe { flex-direction:column; gap:10px; }
    .pipeleg { border-left:none; padding-left:0; border-top:1px solid var(--line); padding-top:10px; }
  }
  .sw { display:inline-block; width:10px; height:10px; border-radius:3px; margin-right:5px; vertical-align:-1px; }

  /* ---- 示例与输入 ---- */
  .chips { display:flex; flex-wrap:wrap; gap:8px; margin:12px 0; }
  .chipgroups { display:flex; flex-wrap:wrap; gap:10px 20px; margin:12px 0 14px; }
  .chipgroup { display:flex; flex-direction:column; gap:6px; }
  .grouplab { font-size:11px; color:var(--sub); display:flex; align-items:center; gap:6px; }
  .grouplab .sw { margin:0; }
  .chiprow { display:flex; flex-wrap:wrap; gap:6px; max-width:560px; }
  .chip { background:var(--card); border:1px solid var(--line); border-radius:16px;
          padding:6px 13px; font-size:12.5px; cursor:pointer; color:#44506b; }
  .chip:hover { border-color:var(--host); color:var(--host); }
  .ask { display:flex; gap:8px; margin:10px 0 20px; }
  .ask input { flex:1; border:1px solid var(--line); border-radius:10px; padding:12px 15px;
               font-size:15px; outline:none; background:var(--card); }
  .ask input:focus { border-color:var(--host); box-shadow:0 0 0 3px rgba(15,118,110,.12); }
  .ask button { border:none; border-radius:10px; background:var(--host); color:#fff;
                padding:0 26px; font-size:15px; font-weight:600; cursor:pointer; }
  .ask button:hover { background:#0c625b; }
  .ask button:disabled { background:#9dbfb9; cursor:default; }

  /* ---- 对话轮 ---- */
  .turn { margin-bottom:30px; }
  .q { display:flex; justify-content:flex-end; }
  .q .bubble { background:var(--dark); color:#fff; border-radius:14px 14px 3px 14px;
               padding:10px 15px; max-width:78%; font-size:14.5px; }
  .statusline { color:var(--sub); font-size:13px; padding:10px 4px 0; }
  .statusline.err { color:var(--bad); }
  .stages { position:relative; display:flex; flex-direction:column; gap:10px; padding-left:4px; }
  .stages::before { content:""; position:absolute; left:38px; top:18px; bottom:18px; width:2px;
                    background:var(--line); }
  .stage { position:relative; display:flex; gap:12px; animation:pop .28s ease; }
  @keyframes pop { from{opacity:0; transform:translateY(6px);} to{opacity:1; transform:none;} }
  .rolebadge { flex:0 0 68px; display:flex; align-items:center; justify-content:center; z-index:1; }
  .rolebadge span { font-size:11.5px; font-weight:700; padding:4px 9px; border-radius:13px;
                    background:var(--card); border:1px solid var(--line); color:var(--sub); }
  .stage.role-llm .rolebadge span { background:var(--llm); border-color:var(--llm); color:#fff; }
  .stage.role-host .rolebadge span { background:var(--host); border-color:var(--host); color:#fff; }
  .card { flex:1; padding:12px 15px; min-width:0; }
  .stage.role-llm .card { background:var(--llm-tint); border:1px solid var(--llm-line); border-radius:16px; }
  .stage.role-host .card { background:var(--host-tint); border:1px solid var(--host-line); border-radius:9px; }
  .stage .t { display:flex; align-items:center; gap:8px; font-weight:700; font-size:15px; }
  .stage .t.fail { color:var(--bad); }
  .stage .lat { margin-left:auto; color:var(--sub); font-weight:400; font-size:12px; font-family:var(--mono); }
  .kv { margin-top:8px; display:grid; grid-template-columns:110px 1fr; gap:4px 10px; font-size:13.5px; }
  .kv .k { color:var(--sub); }
  .stage.role-host .kv .v { font-family:var(--mono); font-size:12.8px; }
  .kv .v { font-weight:500; word-break:break-all; }
  .trace { margin-top:9px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
  .trace .tl { font-size:11.5px; color:var(--sub); margin-right:2px; }
  .step { background:#dcebe8; color:#0c5a54; border-radius:6px; padding:2px 9px; font-size:12px;
          font-family:var(--mono); }
  .step.bad { background:var(--bad-tint); color:var(--bad); }
  .fork { margin-top:10px; display:flex; flex-wrap:wrap; gap:6px; align-items:center; }
  .exit { border-radius:8px; padding:4px 12px; font-size:12.5px; font-weight:600;
          border:1.5px solid var(--line); color:#96a5a1; background:transparent; }
  .exit.on.db { background:var(--host); border-color:var(--host); color:#fff; }
  .exit.on.ml { background:var(--llm); border-color:var(--llm); color:#fff; }
  .exit.on.refuse { background:var(--bad); border-color:var(--bad); color:#fff; }
  .exit.on::after { content:" ◀ 本次路径"; font-weight:400; font-size:11px; opacity:.85; }
  .farrow { color:#b6c6c1; font-size:12px; }
  details { margin-top:8px; } summary { color:var(--sub); cursor:pointer; font-size:12px; }
  pre { background:var(--card); border:1px solid var(--line); border-radius:8px; padding:10px;
        font-size:12px; white-space:pre-wrap; word-break:break-all; margin:6px 0 0; }
  .stage.console .card { background:var(--dark); border-color:#12424d; color:#d7e9e6; border-radius:9px; }
  .stage.console .t { color:#9fd8cf; font-size:13.5px; }
  .chead { font-family:var(--mono); font-size:11px; letter-spacing:.5px; color:#7fb5ac; margin-bottom:6px; }
  .toolpre { background:transparent; border:none; color:#e3f2ef; font-family:var(--mono);
             font-size:12.8px; line-height:1.55; margin:0; }

  /* ---- 最终答案 ---- */
  .final { border-radius:16px; padding:16px 20px; margin-top:14px; color:#fff;
           animation:pop .35s ease; box-shadow:0 6px 22px rgba(11,54,64,.18); }
  .final.db { background:linear-gradient(120deg,#0f766e,#0b5d57); }
  .final.ml { background:linear-gradient(120deg,#075985,#0a4a6e); }
  .final.refusal { background:linear-gradient(120deg,#c0392b,#a93226); }
  .final.clarify { background:linear-gradient(120deg,#b45309,#96450a); }
  .fhead { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
  .fbadge { background:rgba(255,255,255,.2); border-radius:14px; padding:3px 12px;
            font-size:12.5px; font-weight:700; }
  .fsub { font-size:12px; opacity:.85; }
  .final .num { font-size:40px; font-weight:700; margin:8px 0 2px; font-family:var(--mono); }
  .final .num .unit { font-size:17px; font-weight:600; margin-left:8px; opacity:.9; font-family:var(--mono); }
  .final .reason { font-size:15px; line-height:1.6; margin-top:6px; }
  .refbox { background:rgba(255,255,255,.14); border-radius:10px; padding:10px 14px;
            margin-top:10px; font-size:12.5px; line-height:1.6; }
  .refbox .rtitle { font-weight:700; margin-bottom:4px; opacity:.9; }
  .refbox ol { margin:0; padding-left:20px; }
  .refbox li { margin:2px 0; word-break:break-all; }
  .rtab { display:grid; grid-template-columns:110px 1fr; gap:3px 10px; font-size:13px; margin-top:8px; }
  .rtab .k { opacity:.8; } .rtab .v { font-family:var(--mono); font-weight:600; }
  .note { background:rgba(255,255,255,.18); border-radius:9px; padding:9px 12px;
          margin-top:9px; font-size:12.5px; line-height:1.55; }
  .faith { margin-top:10px; font-size:13px; color:var(--sub);
           background:var(--card); border:1px solid var(--line); border-radius:10px;
           padding:9px 14px; }
  .faith b.ok { color:var(--host); } .faith b.no { color:var(--bad); }
  @media (max-width:820px) {
    .stages::before { display:none; } .rolebadge { flex:0 0 auto; align-items:flex-start; padding-top:10px; }
    .pipeflow { flex-wrap:wrap; gap:8px; } .pconn { display:none; }
  }

  /* ---- 布局：侧栏（历史会话） + 主区 ---- */
  .app { display:flex; align-items:stretch; min-height:100vh; }
  .side { flex:0 0 250px; background:#ecf2f0; border-right:1px solid var(--line);
          padding:14px 10px; position:sticky; top:0; height:100vh; display:flex; flex-direction:column; }
  .newchat { border:none; border-radius:10px; background:var(--host); color:#fff; font-size:14px;
             font-weight:600; padding:10px 12px; cursor:pointer; }
  .newchat:hover { background:#0c625b; }
  .histhead { font-size:11.5px; color:var(--sub); margin:16px 6px 6px; letter-spacing:1px; }
  .histlist { flex:1; overflow-y:auto; display:flex; flex-direction:column; gap:4px; }
  .hitem { position:relative; border-radius:9px; padding:8px 26px 8px 10px; cursor:pointer;
           border:1px solid transparent; }
  .hitem:hover { background:#e0eae7; }
  .hitem.on { background:#fff; border-color:var(--host-line); }
  .hitem .htitle { font-size:12.5px; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
  .hitem .hsub { font-size:10.5px; color:var(--sub); margin-top:2px; }
  .hdel { position:absolute; right:6px; top:8px; border:none; background:transparent; color:#9fb0ac;
          font-size:14px; cursor:pointer; line-height:1; padding:2px 4px; border-radius:5px; }
  .hdel:hover { color:var(--bad); background:var(--bad-tint); }
  .hempty { font-size:12px; color:var(--sub); padding:10px; }
  .sidefoot { font-size:10.5px; color:#8fa19c; padding:8px 6px 0; line-height:1.5;
              border-top:1px solid #dbe5e2; margin-top:8px; }
  .main { flex:1; min-width:0; }
  @media (max-width:880px){ .side { display:none; } }

  /* ---- 数据与判断机制面板 ---- */
  .mech { border:1px solid rgba(255,255,255,.45); color:#dcecea; background:rgba(255,255,255,.08);
          border-radius:14px; padding:4px 12px; font-size:12px; cursor:pointer; }
  .mech:hover { background:rgba(255,255,255,.18); }
  .modalbg { position:fixed; inset:0; background:rgba(11,54,64,.5); z-index:50;
             display:flex; align-items:center; justify-content:center; padding:20px; }
  .modalbg[hidden] { display:none; }
  .modal { background:#fff; border-radius:16px; max-width:1060px; width:100%; max-height:88vh;
           overflow-y:auto; padding:22px 26px; box-shadow:0 20px 60px rgba(11,54,64,.35); }
  .mhead { display:flex; align-items:flex-start; gap:12px; margin-bottom:12px; }
  .mtitle { font-size:19px; font-weight:700; }
  .msub { font-size:12.5px; color:var(--sub); margin-top:3px; }
  .mclose { margin-left:auto; border:none; background:#f1f5f4; color:var(--sub); width:32px; height:32px;
            border-radius:50%; font-size:16px; cursor:pointer; flex:0 0 auto; }
  .mclose:hover { background:var(--bad-tint); color:var(--bad); }
  .mintro { background:var(--host-tint); border:1px solid var(--host-line); border-radius:12px;
            padding:12px 16px; font-size:13px; line-height:1.8; margin-bottom:12px; }
  .mintro b { color:var(--host); }
  .mstats { display:flex; gap:20px; flex-wrap:wrap; font-size:12.5px; color:var(--sub); margin-bottom:14px; }
  .mstats b { color:var(--ink); font-size:15px; }
  .mgrid { display:grid; grid-template-columns:1fr 1fr; gap:14px; }
  @media (max-width:880px){ .mgrid { grid-template-columns:1fr; } }
  .scard { border:1px solid var(--line); border-radius:12px; padding:14px 16px; background:#fcfefd; }
  .scard h3 { margin:0; font-size:15.5px; }
  .scard .srow { font-size:12px; color:var(--sub); margin-top:6px; line-height:1.65; }
  .scard .srow b { color:var(--ink); font-weight:600; }
  .lins { margin-top:8px; display:flex; flex-wrap:wrap; gap:4px; max-height:60px; overflow-y:auto; }
  .lin { font-family:var(--mono); font-size:10.5px; background:#eef4f2; border:1px solid var(--line);
         border-radius:5px; padding:1px 6px; color:#44615c; cursor:help; }
  .satwrap { margin-top:10px; }
  .satlab { font-size:11px; color:var(--sub); margin-top:4px; line-height:1.5; }
  svg text { font-family:var(--mono); }
  .axg { stroke:#e5edea; stroke-width:1; }
  .axl { stroke:#c3d2ce; stroke-width:1.2; }
  .axt { font-size:9px; fill:#7d8f8a; }
  .satline { fill:none; stroke:var(--host); stroke-width:2.2; }
  .satdot { fill:var(--host); }
  .domline { stroke:var(--llm); stroke-width:1.4; stroke-dasharray:5 4; }
  .domfill { fill:rgba(192,57,43,.06); }
</style>
</head>
<body>
<div class="app">
  <aside class="side">
    <button class="newchat" id="newchat">＋ 新对话</button>
    <div class="histhead">历史会话</div>
    <div class="histlist" id="histlist"></div>
    <div class="sidefoot">会话记录保存在本机浏览器中，<br>关闭页面后仍可回看。</div>
  </aside>
  <main class="main">
    <div class="wrap">
  <div class="banner">
    <div>
      <h1>AquaDiff · 扩散系数受限智能体</h1>
      <div class="sub">两段式：大模型只做意图提取与终答誊写 · 校验 / 查库 / 路由 / 拒绝全部由确定性后台程序执行（方案 v2.16）</div>
    </div>
    <div class="tags"><button class="mech" onclick="openMeta()">数据与判断机制</button><span class="tag">可追溯</span><span class="tag">会拒绝</span><span class="tag">全本地部署</span></div>
  </div>

  <div class="pipe">
    <div class="pipeflow" id="pipe">
      <svg id="tree" viewBox="0 0 850 196" xmlns="http://www.w3.org/2000/svg">
        <path id="e_q1"  class="te" d="M102,106 L136,106"/>
        <path id="e_12"  class="te" d="M220,106 L258,106"/>
        <path id="e_23"  class="te" d="M342,106 L380,106"/>
        <path id="e_2cl" class="te" d="M300,93 L300,26 L490,26"/>
        <path id="e_3db" class="te" d="M422,93 L422,60 L720,60"/>
        <path id="e_3sat" class="te" d="M422,119 L422,156 L490,156"/>
        <path id="e_sat_dom" class="te" d="M532,143 L532,106 L604,106"/>
        <path id="e_sat_clamp" class="te" d="M532,169 L532,182 L650,182 L650,119"/>
        <path id="e_dom_ml" class="te" d="M692,106 L720,106"/>
        <path id="e_dom_ref" class="te" d="M650,119 L650,156 L720,156"/>
        <text class="tel" x="361" y="101" text-anchor="middle">通过</text>
        <text class="tel" x="307" y="60">不通过</text>
        <text class="tel" x="429" y="80">命中</text>
        <text class="tel" x="429" y="142">未命中</text>
        <text class="tel" x="568" y="99" text-anchor="middle">未超过</text>
        <text class="tel" x="591" y="177" text-anchor="middle">超过·夹取后重入</text>
        <text class="tel" x="706" y="99" text-anchor="middle">域内</text>
        <text class="tel" x="657" y="142">域外</text>
        <g id="n_q" class="tn"><rect class="tb" x="18" y="93" width="84" height="26" rx="8"/><text class="tt" x="60" y="109.5">提问</text></g>
        <g id="n_1" class="tn llm"><rect class="tb" x="136" y="93" width="84" height="26" rx="8"/><text class="tt" x="178" y="109.5">意图提取</text></g>
        <text id="n1_model" class="tsub" x="178" y="133">大模型</text>
        <g id="n_2" class="tn host"><rect class="tb" x="258" y="93" width="84" height="26" rx="8"/><text class="tt" x="300" y="109.5">校验·换算</text></g>
        <g id="n_3" class="tn host"><rect class="tb" x="380" y="93" width="84" height="26" rx="8"/><text class="tt" x="422" y="109.5">查库 DuckDB</text></g>
        <g id="n_sat" class="tn host"><rect class="tb" x="490" y="143" width="84" height="26" rx="8"/><text class="tt" x="532" y="159.5">饱和检查</text></g>
        <g id="n_dom" class="tn host"><rect class="tb" x="608" y="93" width="84" height="26" rx="8"/><text class="tt" x="650" y="109.5">域盒检查</text></g>
        <g id="x_cl" class="tn warn"><rect class="tb" x="490" y="13" width="84" height="26" rx="8"/><text class="tt" x="532" y="29.5">澄清 / 拒绝</text></g>
        <g id="x_db" class="tn db"><rect class="tb" x="720" y="47" width="84" height="26" rx="8"/><text class="tt" x="762" y="63.5">实测值+文献</text></g>
        <g id="x_ml" class="tn ml"><rect class="tb" x="720" y="93" width="84" height="26" rx="8"/><text class="tt" x="762" y="109.5">ML 模型预测</text></g>
        <g id="x_ref" class="tn ref"><rect class="tb" x="720" y="143" width="84" height="26" rx="8"/><text class="tt" x="762" y="159.5">结构化拒绝</text></g>
        <text id="t_val" class="tval" x="762" y="42" visibility="hidden"></text>
      </svg>
      <div class="pipecap">查库 / 饱和 / 域盒同属阶段③确定性路由 · 命中 / ML / 域外出口经 ⑤ 大模型誊写+硬校验输出 · 澄清·拒绝由后台程序直出 · 超饱和实测命中附亚稳披露</div>
    </div>
    <div class="pipeleg">
      <div class="lrow"><span class="sw" style="background:var(--llm)"></span>大模型环节（语言理解 / 誊写）</div>
      <div class="lrow"><span class="sw" style="background:var(--host)"></span>后台程序（确定性，毫秒级）</div>
      <div class="lgrp">答案色</div>
      <div class="anscolors">
        <div class="lrow"><span class="sw" style="background:var(--host)"></span>实测值</div>
        <div class="lrow"><span class="sw" style="background:var(--llm)"></span>模型预测</div>
        <div class="lrow"><span class="sw" style="background:var(--bad)"></span>拒绝</div>
        <div class="lrow"><span class="sw" style="background:var(--warn)"></span>澄清 / 披露</div>
      </div>
    </div>
  </div>

  <div class="chipgroups" id="chips"></div>
  <div class="ask">
    <input id="q" placeholder="输入问题，例如：25°C、1.0 mol/L 氯化钠溶液的互扩散系数是多少？" />
    <button id="go" onclick="ask()">提问</button>
  </div>
  <div id="turns"></div>
    </div>
  </main>
</div>

<div class="modalbg" id="metabg" hidden>
  <div class="modal">
    <div class="mhead">
      <div>
        <div class="mtitle">数据与判断机制</div>
        <div class="msub">谱系覆盖 · 饱和曲线 · 适用域盒 —— 全部读自冻结产物（DuckDB 实验库 / 溶解度表 / 模型 registry）</div>
      </div>
      <button class="mclose" id="mclose">×</button>
    </div>
    <div id="metabody">加载中……</div>
  </div>
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
/* 示例按预期路由分块（编号保持 EXAMPLES 原始序号，与演示脚本引用一致；
   分组依据 = 后台路由逻辑实跑核证：例2/4 为饱和夹取后走 ML，例5 为库内亚稳披露命中） */
const CHIP_GROUPS = [
  {label:'实测值 · 库内命中', color:'var(--host)', idx:[0, 4]},
  {label:'模型预测 · 含饱和夹取', color:'var(--llm)', idx:[1, 3]},
  {label:'结构化拒绝', color:'var(--bad)', idx:[2, 5, 6]},
  {label:'请求澄清', color:'var(--warn)', idx:[7]},
];
CHIP_GROUPS.forEach(g=>{
  const grp = document.createElement('div'); grp.className = 'chipgroup';
  grp.innerHTML = `<div class="grouplab"><span class="sw" style="background:${g.color}"></span>${g.label}</div>`;
  const row = document.createElement('div'); row.className = 'chiprow';
  g.idx.forEach(i=>{
    const c = document.createElement('div'); c.className = 'chip';
    c.textContent = (i+1)+'. '+EXAMPLES[i].slice(0,34)+(EXAMPLES[i].length>34?'…':'');
    c.onclick = ()=>{ document.getElementById('q').value = EXAMPLES[i]; ask(); };
    row.appendChild(c);
  });
  grp.appendChild(row); chips.appendChild(grp);
});
function esc(s){ return String(s??'').replace(/[&<>"]/g,m=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[m])); }
function kv(rows){ if(!rows||!rows.length) return '';
  return '<div class="kv">'+rows.map(r=>`<div class="k">${esc(r[0])}</div><div class="v">${esc(r[1])}</div>`).join('')+'</div>'; }

/* ---------- 顶部流水线 ---------- */
const NODE_NAMES = {1:'① 大模型 · 意图提取中……',2:'② 后台 · 审核换算中……',3:'③ 后台 · 确定性路由中……',
                    4:'④ 后台 · 工具执行中……',5:'⑤ 大模型 · 终答誊写中……'};
const CFG = { model: null };
function shortModel(m){
  if(!m) return '';
  m = String(m).split('/').pop();
  return m.length > 17 ? m.slice(0,16)+'…' : m;
}
const EXIT_POS = { x_db:[762,42], x_ml:[762,134], x_ref:[762,184], x_cl:[532,50] };
let lastExit = null;
function elById(id){ return document.getElementById(id); }
function nodeOn(id, kind){
  const e = elById(id); if(!e) return;
  e.classList.add('on'); if(kind) e.classList.add(kind);
}
function nodeSkip(id){
  const e = elById(id); if(!e) return;
  e.classList.add('skip');
  const t = e.querySelector('.tt'); if(t) t.textContent = '饱和·跳过';
}
function edgeOn(id, colorc){
  const e = elById(id); if(!e) return;
  e.classList.add('on', colorc);
}
function treeSetActive(id){
  document.querySelectorAll('#tree .tn.active').forEach(e=>e.classList.remove('active'));
  const e = elById(id); if(e) e.classList.add('active');
}
function setStatus(n, statusEl){
  if(statusEl && NODE_NAMES[n]) statusEl.textContent = NODE_NAMES[n];
}
function treeReset(){
  document.querySelectorAll('#tree .tn').forEach(e=>{
    e.classList.remove('on','active','skip','llm','host','db','ml','ref','warn');
  });
  document.querySelectorAll('#tree .te').forEach(e=>e.classList.remove('on','llmc','hostc'));
  const sat = elById('n_sat');
  if(sat){ const t = sat.querySelector('.tt'); if(t) t.textContent = '饱和检查'; }
  const st = elById('n1_model'); if(st) st.textContent = shortModel(CFG.model) || '大模型';
  const tv = elById('t_val'); if(tv) tv.setAttribute('visibility','hidden');
  lastExit = null;
}
function treeStage(s){
  if(s.n===1){
    edgeOn('e_q1','llmc'); nodeOn('n_1','llm');
    if(s.status==='fail'){ lastExit='x_cl'; nodeOn('x_cl','warn'); }
    return;
  }
  if(s.n===2){
    edgeOn('e_12','hostc'); nodeOn('n_2','host');
    if(s.status==='fail'){ edgeOn('e_2cl','hostc'); lastExit='x_cl'; nodeOn('x_cl','warn'); }
    else edgeOn('e_23','hostc');
    return;
  }
  if(s.n===3){
    nodeOn('n_3','host');
    const r = s.route || '';
    if(r.startsWith('db_hit')){
      edgeOn('e_3db','hostc'); lastExit='x_db'; nodeOn('x_db','db');
    } else {
      edgeOn('e_3sat','hostc');
      const ss = s.sat_state ||
        (String((s.trace||[]).join(' ')).includes('saturation_clamp') ? 'clamped' : 'ok');
      if(ss==='skipped') nodeSkip('n_sat'); else nodeOn('n_sat','host');
      edgeOn(ss==='clamped' ? 'e_sat_clamp' : 'e_sat_dom', 'hostc');
      nodeOn('n_dom','host');
      if(r==='ml'){ edgeOn('e_dom_ml','hostc'); lastExit='x_ml'; nodeOn('x_ml','ml'); }
      else { edgeOn('e_dom_ref','hostc'); lastExit='x_ref'; nodeOn('x_ref','ref'); }
    }
    return;
  }
  if(s.n===4 && lastExit){ treeSetActive(lastExit); }
}
function treeFinal(f){
  document.querySelectorAll('#tree .tn.active').forEach(e=>e.classList.remove('active'));
  const tv = elById('t_val');
  if(!tv || !lastExit) return;
  const pos = EXIT_POS[lastExit]; if(!pos) return;
  let txt = '';
  if(f.answer_type==='value') txt = 'D = ' + f.diffusion_1e9_m2_s;
  else if(f.answer_type==='refusal') txt = '无值·拒绝';
  else txt = '请补充信息';
  tv.textContent = txt;
  tv.setAttribute('x', pos[0]); tv.setAttribute('y', pos[1]);
  tv.setAttribute('visibility','visible');
}
fetch('/api/config').then(r=>r.json()).then(c=>{
  CFG.model = c.model || null;
  const st = elById('n1_model');
  if(st){ st.textContent = shortModel(CFG.model) || '大模型'; st.setAttribute('title', c.model||''); }
}).catch(()=>{});

/* ---------- 阶段卡片 ---------- */
function forkHtml(route){
  if(!route) return '';
  const taken = route.startsWith('db_hit') ? 'db' : (route==='ml' ? 'ml' : 'refuse');
  const exits = [['db','实验实测值 + 来源'],['ml','冻结模型预测'],['refuse','结构化拒绝']];
  return '<div class="fork">' + exits.map(e=>
    `<div class="exit ${e[0]} ${taken===e[0]?'on '+e[0]:''}">${e[1]}</div>`).join('<div class="farrow">▸</div>') + '</div>';
}
function stageHtml(s){
  const role = s.role || (s.title.indexOf('前台')>=0 ? 'llm' : 'host');
  const isConsole = s.tool != null;
  let cls = 'stage role-'+role + (isConsole ? ' console' : '');
  let h = `<div class="${cls}"><div class="rolebadge"><span>${role==='llm'?'大模型':'后台程序'}</span></div><div class="card">`;
  h += `<div class="t ${s.status==='fail'?'fail':''}">${esc(s.title)}${s.lat!=null?`<span class="lat">${esc(s.lat)}</span>`:''}</div>`;
  if(isConsole){
    h += `<div class="chead">TOOL RESULT · 后台工具输出（非大模型生成）</div><pre class="toolpre">${esc(s.tool)}</pre>`;
  } else {
    h += kv(s.rows);
  }
  if(s.route) h += forkHtml(s.route);
  if(s.trace && s.trace.length)
    h += '<div class="trace"><span class="tl">路径轨迹</span>'+s.trace.map(t=>`<span class="step${/refuse|miss/.test(t)?' bad':''}">${esc(t)}</span>`).join('')+'</div>';
  if(s.raw) h += '<details><summary>模型原始输出</summary><pre>'+esc(s.raw)+'</pre></details>';
  return h + '</div></div>';
}

/* ---------- 最终答案 ---------- */
/* 冻结模型参考精度（口径：D 臂冻结评价，谱系分组交叉验证宏 MdAPE %；
   外部前瞻集域内 ±10% 容差正确率 97.9% = 47/48）——冻结产物不含逐条件预测区间，
   故以历史评测真实精度代替，不编造区间 */
const ML_PRECISION = {'NaCl-H2O':2.13, 'KCl-H2O':2.70, 'LiCl-H2O':4.68, 'CaCl2-H2O':4.52};
const EXT_ACC = '外部新文献题域内 ±10% 容差正确率 97.9%（47/48）';
function finalHtml(f, fa){
  const m = f._meta || {};
  let h = '';
  if(f.answer_type==='value'){
    const isDb = m.kind==='db_hit';
    h += `<div class="final ${isDb?'db':'ml'}"><div class="fhead"><span class="fbadge">${isDb?'实验实测值 · 文献可溯源':'专用模型预测 · 适用域内'}</span>`;
    if(isDb) h += `<span class="fsub">DuckDB 精确命中 ${m.n_records??'?'} 条记录 · 中位数</span>`;
    else h += `<span class="fsub">专用模型 ${esc(m.model || '')} · registry ffbc8b45</span>`;
    h += `</div><div class="num">${esc(f.diffusion_1e9_m2_s)}<span class="unit">× 10⁻⁹ m²/s</span></div>`;
    if(isDb && m.n_records > 1 && m.value_min != null){
      h += `<div class="accnote">${m.n_records} 条实测记录取值 ${(+m.value_min).toFixed(3)} – ${(+m.value_max).toFixed(3)}，返回中位数</div>`;
    }
    if(!isDb){
      const prec = ML_PRECISION[m.system] != null ? '≈'+ML_PRECISION[m.system]+'%' : '见机制面板';
      h += `<div class="accnote">参考精度：谱系交叉验证中位相对误差 ${prec}；${EXT_ACC}</div>`;
    }
    if(isDb && m.references && m.references.length){
      h += `<div class="refbox"><div class="rtitle">文献来源（${m.n_records} 条记录，前 ${m.references.length} 条）</div><ol>` +
           m.references.map(r=>`<li>${esc(r)}</li>`).join('') + '</ol></div>';
    }
    if(f.notes) h += `<div class="note">⚠ ${esc(f.notes)}</div>`;
    h += '</div>';
  } else if(f.answer_type==='refusal'){
    h += `<div class="final refusal"><div class="fhead"><span class="fbadge">结构化拒绝</span><span class="fsub">宁可拒绝，绝不编造数值</span></div>`;
    h += `<div class="reason">${esc(f.notes||'')}</div>`;
    if(m.out_fields){
      h += `<div class="rtab"><div class="k">出域字段</div><div class="v">${esc((m.out_fields||[]).join('、'))}</div>` +
           `<div class="k">有效温度范围</div><div class="v">${esc(String(m.valid_T?.[0]))} – ${esc(String(m.valid_T?.[1]))} K</div>` +
           `<div class="k">有效浓度范围</div><div class="v">${esc(String(m.valid_c?.[0]))} – ${esc(String(m.valid_c?.[1]))} mol/L</div></div>`;
    }
    h += '</div>';
  } else {
    h += `<div class="final clarify"><div class="fhead"><span class="fbadge">请求澄清</span></div>` +
         `<div class="reason">${esc(f.notes||'')}</div></div>`;
  }
  if(fa) h += `<div class="faith">载荷硬校验：${fa.faithful?'<b class="ok">✓ 终答数值与来源和工具输出逐字一致</b>':'<b class="no">✗ 不一致：'+esc(JSON.stringify(fa.violations))+'</b>'}</div>`;
  return h;
}

/* ---------- 流式提问 ---------- */
async function ask(){
  const q = document.getElementById('q').value.trim(); if(!q) return;
  const box = document.getElementById('turns');
  const turn = document.createElement('div'); turn.className='turn';
  turn.innerHTML = `<div class="q"><div class="bubble">${esc(q)}</div></div><div class="statusline">连接中……</div><div class="stages"></div>`;
  box.prepend(turn);
  const statusEl = turn.querySelector('.statusline');
  const stagesEl = turn.querySelector('.stages');
  document.getElementById('go').disabled = true;
  treeReset();
  treeSetActive('n_1');
  setStatus(1, statusEl);
  const turnData = { question: q, stages: [], final: null, faithfulness: null };
  try{
    const resp = await fetch('/api/ask_stream',{method:'POST',headers:{'Content-Type':'application/json'},
                                     body:JSON.stringify({question:q})});
    if(!resp.ok || !resp.body) throw new Error('HTTP '+resp.status);
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = '', gotFinal = false;
    while(true){
      const {done, value} = await reader.read();
      if(done) break;
      buf += dec.decode(value,{stream:true});
      let i;
      while((i = buf.indexOf('\n')) >= 0){
        const line = buf.slice(0,i).trim(); buf = buf.slice(i+1);
        if(!line) continue;
        let ev; try{ ev = JSON.parse(line); }catch(e){ continue; }
        if(ev.type==='stage'){
          const s = ev.stage;
          stagesEl.insertAdjacentHTML('beforeend', stageHtml(s));
          treeStage(s);
          if(s.n < 5) setStatus(s.n+1, statusEl);
          turnData.stages.push(s);
        } else if(ev.type==='final'){
          gotFinal = true;
          statusEl.remove();
          const f = ev.final || {};
          treeFinal(f);
          stagesEl.insertAdjacentHTML('beforeend', finalHtml(f, ev.faithfulness));
          turnData.final = ev.final;
          turnData.faithfulness = ev.faithfulness;
          commitTurn(turnData);
        } else if(ev.type==='error'){
          throw new Error(ev.error || '服务端错误');
        }
      }
    }
    if(!gotFinal){ statusEl.textContent='响应中断（未收到最终答案）'; statusEl.classList.add('err'); }
  }catch(e){
    statusEl.textContent = '请求失败：'+e+'（请确认 agent_web.py 仍在运行、模型端点可达）';
    statusEl.classList.add('err');
  }
  document.getElementById('go').disabled = false;
}
/* ---------- 历史会话（localStorage，GPT 式） ---------- */
const LS_KEY = 'aquadiff_sessions_v1';
function lsLoad(){
  try { return JSON.parse(localStorage.getItem(LS_KEY)) || {sessions: []}; }
  catch(e){ return {sessions: []}; }
}
function lsSave(db){
  try { localStorage.setItem(LS_KEY, JSON.stringify(db)); }
  catch(e){ db.sessions.shift(); try { localStorage.setItem(LS_KEY, JSON.stringify(db)); } catch(e2){} }
}
let curSession = null;
function fmtTime(ts){
  const d = new Date(ts);
  return (d.getMonth()+1)+'/'+d.getDate()+' '+String(d.getHours()).padStart(2,'0')+':'+String(d.getMinutes()).padStart(2,'0');
}
function renderHist(){
  const db = lsLoad();
  const box = document.getElementById('histlist');
  box.innerHTML = db.sessions.map(s =>
    `<div class="hitem ${s.id===curSession?'on':''}" data-id="${s.id}">
       <div class="htitle">${esc(s.title)}</div>
       <div class="hsub">${fmtTime(s.created)} · ${s.turns.length} 问</div>
       <button class="hdel" title="删除该会话">×</button>
     </div>`).join('') || '<div class="hempty">暂无历史会话<br>提问后自动保存</div>';
  box.querySelectorAll('.hitem').forEach(el=>{
    el.onclick = (e)=>{ if(e.target.classList.contains('hdel')) return; loadSession(el.dataset.id); };
    const del = el.querySelector('.hdel');
    del.onclick = (e)=>{ e.stopPropagation(); deleteSession(el.dataset.id); };
  });
}
function commitTurn(td){
  const db = lsLoad();
  let s = db.sessions.find(x=>x.id===curSession);
  if (!s){
    curSession = 's' + Date.now() + Math.floor(Math.random()*1000);
    s = { id: curSession, title: td.question.slice(0, 26), created: Date.now(), turns: [] };
    db.sessions.unshift(s);
  }
  s.turns.push(td);
  if (db.sessions.length > 100) db.sessions.pop();
  lsSave(db); renderHist();
}
function turnHtml(td){
  let h = `<div class="q"><div class="bubble">${esc(td.question)}</div></div><div class="stages">`;
  (td.stages||[]).forEach(s=>{ h += stageHtml(s); });
  h += '</div>' + finalHtml(td.final || {answer_type:'clarify', notes:'(该轮未完成)'}, td.faithfulness);
  return `<div class="turn">${h}</div>`;
}
function loadSession(id){
  const db = lsLoad();
  const s = db.sessions.find(x=>x.id===id);
  if (!s) return;
  curSession = id;
  document.getElementById('turns').innerHTML = s.turns.map(turnHtml).join('');
  treeReset();
  const last = s.turns[s.turns.length-1];
  if (last){
    (last.stages||[]).forEach(st=>treeStage(st));
    treeFinal(last.final || {answer_type:'clarify'});
  }
  renderHist();
}
function deleteSession(id){
  const db = lsLoad();
  db.sessions = db.sessions.filter(x=>x.id!==id);
  lsSave(db);
  if (curSession===id){
    curSession = null;
    document.getElementById('turns').innerHTML = '';
    treeReset();
  }
  renderHist();
}
document.getElementById('newchat').onclick = ()=>{
  curSession = null;
  document.getElementById('turns').innerHTML = '';
  treeReset();
  renderHist();
  document.getElementById('q').focus();
};
renderHist();

/* ---------- 数据与判断机制面板 ---------- */
let metaCache = null;
async function openMeta(){
  const bg = document.getElementById('metabg');
  const body = document.getElementById('metabody');
  bg.hidden = false;
  if (!metaCache){
    body.textContent = '加载中……';
    try { metaCache = await (await fetch('/api/meta')).json(); }
    catch(e){ body.textContent = '加载失败：' + e; return; }
  }
  const m = metaCache;
  const cards = m.systems.map(s=>{
    const name = s.system.replace('CaCl2', 'CaCl₂').replace('-H2O', '–H₂O');
    const lins = s.lineages.map(l=>
      `<span class="lin" title="${esc(l.ref||'')}">${esc(l.short)} ×${l.n}</span>`).join('');
    return `<div class="scard">
      <h3>${name}</h3>
      <div class="srow">实测记录 <b>${s.n_records}</b> 条 · 来源谱系 <b>${s.n_lineages}</b> 个 ·
        数据覆盖 T <b>${s.data_T[0]}–${s.data_T[1]}</b> K · c <b>${s.data_c[0]}–${s.data_c[1]}</b> mol/L</div>
      <div class="srow">适用域盒：T <b>${s.domain_T[0]}–${s.domain_T[1]}</b> K · c <b>${s.domain_c[0]}–${s.domain_c[1]}</b> mol/L（超出 → 结构化拒绝）</div>
      <div class="srow">冻结模型：<b>${esc(s.model || '')}</b></div>
      <div class="srow">ML 参考精度：谱系交叉验证中位相对误差 <b>≈${ML_PRECISION[s.system] != null ? ML_PRECISION[s.system] : '?'}%</b>；${EXT_ACC}</div>
      <div class="lins">${lins}</div>
      <div class="satwrap">${satSvg(s)}
        <div class="satlab">饱和浓度 c<sub>sat</sub>(T)：冻结表 ${s.sat_points.length} 点线性插值；
          库未命中且 c &gt; c<sub>sat</sub>×1.01 → 明示并按饱和点夹取；
          蓝虚线 = 域盒温度上界，浅红区 = 超出域盒（拒绝）</div>
      </div>
    </div>`;
  }).join('');
  body.innerHTML = `
    <div class="mintro"><b>判断顺序 —— 每次提问都走同一条确定性路径</b><br>
      ① <b>查库优先</b>：命中文献实测记录 → 返回实测值与来源（同条件多谱系取中位数、来源全列；超饱和的实测记录照常返回并附亚稳披露，<b>不夹取</b>）<br>
      ② <b>饱和检查</b>（仅库未命中）：浓度超过该温度平衡溶解度 c<sub>sat</sub>(T) 的 1.01 倍 → 明示后按饱和点夹取，重新进入路由<br>
      ③ <b>适用域盒</b>：温度 / 浓度超出冻结模型适用域 → 结构化拒绝（指明出域字段与有效范围）<br>
      ④ <b>域内预测</b>：调用该体系的冻结专用数值模型（registry ${esc(m.registry_fp)}）</div>
    <div class="mstats">
      <span>实测记录合计 <b>${m.total_records}</b> 条</span>
      <span>来源谱系 <b>${m.total_lineages}</b> 个</span>
      <span>溶解度表 273.15–373.15 K · 48 点</span>
      <span>夹取容差 τ = 1%</span>
    </div>
    <div class="mgrid">${cards}</div>`;
}
function satSvg(s){
  const W=380, H=155, L=48, R=10, T=10, B=26;
  const pts = s.sat_points;
  if (!pts || pts.length < 2) return '';
  const tMin = 273.15, tMax = 373.15;
  const cData = Math.max(...pts.map(p=>p[1]));
  const cMax = cData * 1.12;
  const x = t => L + (t - tMin) / (tMax - tMin) * (W - L - R);
  const y = c => H - B - c / cMax * (H - T - B);
  let g = '';
  const dT = s.domain_T[1];
  if (dT && dT < tMax - 1)
    g += `<rect x="${x(dT).toFixed(1)}" y="${T}" width="${(W-R-x(dT)).toFixed(1)}" height="${H-B-T}" class="domfill"/>`;
  [0, 25, 50, 75, 100].forEach(tc => {
    const t = 273.15 + tc;
    g += `<line x1="${x(t).toFixed(1)}" y1="${T}" x2="${x(t).toFixed(1)}" y2="${H-B}" class="axg"/>` +
         `<text x="${x(t).toFixed(1)}" y="${H-8}" text-anchor="middle" class="axt">${tc}°C</text>`;
  });
  [0, 0.5, 1].forEach(f => {
    const c = cData * f;
    g += `<line x1="${L}" y1="${y(c).toFixed(1)}" x2="${W-R}" y2="${y(c).toFixed(1)}" class="axg"/>` +
         `<text x="${L-4}" y="${(y(c)+3).toFixed(1)}" text-anchor="end" class="axt">${+c.toFixed(1)}</text>`;
  });
  g += `<line x1="${L}" y1="${H-B}" x2="${W-R}" y2="${H-B}" class="axl"/>` +
       `<line x1="${L}" y1="${T}" x2="${L}" y2="${H-B}" class="axl"/>` +
       `<text x="${W-R}" y="${H-8}" text-anchor="end" class="axt">T</text>` +
       `<text x="${L-4}" y="${T+9}" text-anchor="end" class="axt">mol/L</text>`;
  if (dT && dT < tMax - 1)
    g += `<line x1="${x(dT).toFixed(1)}" y1="${T}" x2="${x(dT).toFixed(1)}" y2="${H-B}" class="domline"/>`;
  g += `<polyline points="${pts.map(p=>x(p[0]).toFixed(1)+','+y(p[1]).toFixed(1)).join(' ')}" class="satline"/>`;
  pts.forEach(p=>{ g += `<circle cx="${x(p[0]).toFixed(1)}" cy="${y(p[1]).toFixed(1)}" r="2.4" class="satdot"/>`; });
  return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:auto">${g}</svg>`;
}
document.getElementById('mclose').onclick = ()=>{ document.getElementById('metabg').hidden = true; };
document.getElementById('metabg').addEventListener('click', e=>{ if(e.target.id==='metabg') e.target.hidden = true; });

document.getElementById('q').addEventListener('keydown', e=>{ if(e.key==='Enter') ask(); });
</script>
</body>
</html>"""


def process_stages(question, on_stage=None):
    """完整管线；on_stage(stage_dict) 在每个阶段完成时回调（流式用）。返回完整结果 dict。"""
    stages = []

    def emit(s):
        stages.append(s)
        if on_stage:
            on_stage(s)

    # ① 意图提取（大模型）
    s1 = {"n": 1, "role": "llm", "title": "① 大模型 · 意图提取", "status": "", "raw": None, "lat": None}
    try:
        intent, raw1, lat1 = LLM.chat_json(INTENT_SYSTEM, question, max_tokens=1024, retries=3, backoff_base=2, backoff_max=8)
        if intent is None:  # 云端偶发空回复：重试一次
            intent, raw1, lat1 = LLM.chat_json(INTENT_SYSTEM, question, max_tokens=1024, retries=3, backoff_base=2, backoff_max=8)
    except RuntimeError as e:
        emit({"n": 1, "role": "llm", "title": "① 大模型 · 意图提取", "status": "fail",
              "rows": [_llm_label_row(), ["结果", f"模型调用失败：{e}"]]})
        return {"question": question, "stages": stages,
                "final": {"answer_type": "clarify", "notes": f"模型调用失败：{e}", "_meta": {"kind": "other"}},
                "faithfulness": None}
    s1.update(raw=raw1, lat=round(lat1, 1), status="ok" if intent else "fail")
    if intent is None:
        s1["rows"] = [_llm_label_row(), ["结果", "JSON 解析失败，转入澄清"]]
        emit(s1)
        return {"question": question, "stages": stages,
                "final": {"answer_type": "clarify", "notes": "无法从问题中解析出结构化条件", "_meta": {"kind": "other"}},
                "faithfulness": None}
    s1["rows"] = [_llm_label_row(),
                  ["体系", intent.get("system", "?")],
                  ["温度", f"{intent.get('temperature')} {intent.get('temperature_unit','')}".strip()],
                  ["浓度", f"{intent.get('concentration')} {intent.get('concentration_unit','')}".strip()]]
    emit(s1)

    # ② 后台审核
    t2 = time.time()
    ok, condition, decision = host_validate(intent)
    if not ok:
        emit({"n": 2, "role": "host", "title": "② 后台 · 审核与换算", "status": "fail",
              "rows": [["判定", "不通过"], ["原因", decision.get("reason", "")]]})
        return {"question": question, "stages": stages,
                "final": {"answer_type": "clarify" if decision["route"] == "clarify" else "refusal",
                          "notes": decision.get("reason", ""), "_meta": {"kind": "other"}},
                "faithfulness": None}
    conv = []
    if abs(condition["temperature_K"] - (intent.get("temperature") or 0)) > 1e-9:
        conv.append(f"温度 {intent['temperature']}{intent['temperature_unit']} → {condition['temperature_K']} K")
    if abs(condition["concentration_mol_L"] - (intent.get("concentration") or 0)) > 1e-9:
        conv.append(f"浓度 {intent['concentration']} {intent['concentration_unit']} → {condition['concentration_mol_L']} mol/L")
    emit({"n": 2, "role": "host", "title": "② 后台 · 审核与换算", "status": "ok", "lat": round(time.time() - t2, 3),
          "rows": [["有效条件", f"{condition['system']} · T={condition['temperature_K']} K · c={condition['concentration_mol_L']} mol/L"],
                   ["单位换算", "; ".join(conv) if conv else "无需换算"]]})

    # ③ 确定性路由 + ④ 工具结果（后台）
    sysid, T, c = condition["system"], condition["temperature_K"], condition["concentration_mol_L"]
    t3 = time.time()
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
        rows3.append(["实验库", "未命中（该条件无实测记录）→ 进入安全检查"])
        sat = r.get("saturation", {})
        if sat.get("checked"):
            rows3.append(["饱和检查", f"c_sat({T:.2f} K) = {sat['c_sat_mol_L']:.4f} mol/L，输入 {c} mol/L（比值 {sat['ratio_to_saturation']:.3f}）"
                          + (" → 超过，按饱和浓度夹取" if sat.get("exceeded") else " → 未超过")])
        else:
            rows3.append(["饱和检查", f"T={T} K 超出溶解度表范围 [273.15, 373.15] K，跳过"])
        if r["route"] == "ml":
            dom = TOOLS.domains.get(sysid, {})
            dt, dc = dom.get("temperature_K", {}), dom.get("concentration_mol_L", {})
            mname = reg_info().get(sysid, {}).get("registered_model_display", "专用数值模型")
            rows3.append(["域盒检查", f"域内：T [{dt.get('min'):g}, {dt.get('max'):g}] K · "
                          f"c [{dc.get('min'):g}, {dc.get('max'):g}] mol/L → 调用专用模型"])
            rows3.append(["ML 预测", f"{mname}：D = {canonical_ml_value(r['ml']['prediction_1e9_m2_s'])} × 10⁻⁹ m²/s"])
        else:
            ad = r["ml"].get("domain", {})
            rng_t, rng_c = ad.get("temperature_K", {}), ad.get("concentration_mol_L", {})
            rows3.append(["域盒检查", f"出域字段：{'、'.join(r['ml'].get('out_of_domain_fields', []))}；"
                          f"有效范围 T [{rng_t.get('min')}, {rng_t.get('max')}] K，c [{rng_c.get('min')}, {rng_c.get('max')}] mol/L"])
    sat_info = r.get("saturation", {})
    sat_state = None
    if not r["route"].startswith("db_hit"):
        sat_state = ("clamped" if sat_info.get("exceeded") else "ok") if sat_info.get("checked") else "skipped"
    emit({"n": 3, "role": "host", "title": "③ 后台 · 确定性路由",
          "status": "fail" if r["route"] == "refuse_out_of_domain" else "ok",
          "rows": rows3, "trace": r["trace"], "route": r["route"], "sat_state": sat_state,
          "lat": round(time.time() - t3, 3)})
    t4 = time.time()
    block = build_tool_block(question, r, condition)
    emit({"n": 4, "role": "host", "title": "④ 后台 · 工具结果块", "status": "", "tool": block,
          "lat": round(time.time() - t4, 3)})

    # 结构化答案元数据（前端证据卡用）
    meta = {"kind": "other"}
    if r["route"].startswith("db_hit"):
        db = r["db"]
        meta = {"kind": "db_hit", "n_records": db["n_records"],
                "references": db["references"][:4], "median": db["median_diffusion_1e9_m2_s"],
                "value_min": db.get("value_min_1e9_m2_s"), "value_max": db.get("value_max_1e9_m2_s")}
    elif r["route"] == "ml":
        meta = {"kind": "ml", "prediction": canonical_ml_value(r["ml"]["prediction_1e9_m2_s"]), "system": sysid,
                "model": reg_info().get(sysid, {}).get("registered_model_display")}
    else:
        ad = r["ml"].get("domain", {})
        rng_t, rng_c = ad.get("temperature_K", {}), ad.get("concentration_mol_L", {})
        meta = {"kind": "refuse", "out_fields": r["ml"].get("out_of_domain_fields", []),
                "valid_T": [rng_t.get("min"), rng_t.get("max")],
                "valid_c": [rng_c.get("min"), rng_c.get("max")]}

    # ⑤ 誊写（大模型）
    try:
        final, raw2, lat2 = LLM.chat_json(FINAL_SYSTEM, block, max_tokens=2048, retries=3, backoff_base=2, backoff_max=8)
        if final is None:  # 云端偶发空回复：重试一次
            final, raw2, lat2 = LLM.chat_json(FINAL_SYSTEM, block, max_tokens=2048, retries=3, backoff_base=2, backoff_max=8)
    except RuntimeError as e:
        emit({"n": 5, "role": "llm", "title": "⑤ 大模型 · 终答誊写", "status": "fail",
              "rows": [["结果", f"模型调用失败：{e}"]]})
        return {"question": question, "stages": stages,
                "final": {"answer_type": "clarify", "notes": f"誊写阶段模型调用失败：{e}", "_meta": {"kind": "other"}},
                "faithfulness": None}
    emit({"n": 5, "role": "llm", "title": "⑤ 大模型 · 终答誊写",
          "status": "ok" if final else "fail", "raw": raw2, "lat": round(lat2, 1)})
    if final is None:
        final = {"answer_type": "clarify", "notes": "誊写 JSON 解析失败（计为忠实性失败）"}
    final["_meta"] = meta
    fa = check_faithfulness(r, final)
    return {"question": question, "stages": stages, "final": final, "faithfulness": fa}


def process_for_ui(question):
    """一次性完整结果（/api/ask 调试端点用）。"""
    return process_stages(question, None)


_META_CACHE = None


def build_meta():
    """机制面板数据：谱系覆盖 / 饱和曲线 / 适用域盒（全部读自冻结产物，首次计算后缓存）。"""
    global _META_CACHE
    if _META_CACHE is not None:
        return _META_CACHE
    systems = []
    for sysid in ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]:
        n_rec, n_lin, tmin, tmax, cmin, cmax = TOOLS._con.execute(
            "SELECT count(*), count(distinct lineage_id), min(temperature_K), max(temperature_K), "
            "min(concentration_mol_L), max(concentration_mol_L) FROM experimental_records WHERE system = ?",
            [sysid]).fetchone()
        lins = [{"short": r[0].split(":")[-1], "n": r[1], "ref": r[2]}
                for r in TOOLS._con.execute(
                    "SELECT lineage_id, count(*), min(original_reference) FROM experimental_records "
                    "WHERE system = ? GROUP BY lineage_id ORDER BY 2 DESC", [sysid]).fetchall()]
        dom = TOOLS.domains.get(sysid, {})
        dt, dc = dom.get("temperature_K", {}), dom.get("concentration_mol_L", {})
        sat = sorted((r["temperature_K"], r["c_sat_mol_L"])
                     for r in getattr(TOOLS, "sat_records", []) if r["system_id"] == sysid)
        systems.append({
            "system": sysid, "n_records": n_rec, "n_lineages": n_lin,
            "data_T": [tmin, tmax], "data_c": [round(cmin, 4), round(cmax, 4)],
            "domain_T": [dt.get("min"), dt.get("max")], "domain_c": [dc.get("min"), dc.get("max")],
            "model": reg_info().get(sysid, {}).get("registered_model_display"),
            "lineages": lins, "sat_points": [[round(t, 2), round(c, 4)] for t, c in sat],
        })
    _META_CACHE = {
        "tau_percent": 1.0, "sat_range_K": [273.15, 373.15],
        "registry_fp": TOOLS.registry_fp[:12],
        "total_records": sum(s["n_records"] for s in systems),
        "total_lineages": sum(s["n_lineages"] for s in systems),
        "systems": systems,
    }
    return _META_CACHE


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_question(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = raw.decode("gbk", errors="replace")
        return json.loads(text).get("question", "").strip()

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, PAGE.encode("utf-8"), "text/html; charset=utf-8")
        elif self.path == "/api/config":
            self._send(200, json.dumps({"model": getattr(LLM, "model", None),
                                        "base_url": getattr(LLM, "base_url", "")},
                                       ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        elif self.path == "/api/meta":
            self._send(200, json.dumps(build_meta(), ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")
        else:
            self._send(404, b"not found", "text/plain")

    def do_POST(self):
        if self.path == "/api/ask":
            try:
                result = process_for_ui(self._read_question())
                self._send(200, json.dumps(result, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
            return
        if self.path == "/api/ask_stream":
            try:
                question = self._read_question()
            except Exception as e:  # noqa: BLE001
                self._send(400, json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")
                return
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Transfer-Encoding", "chunked")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            alive = {"ok": True}

            def send_line(obj):
                if not alive["ok"]:
                    return
                try:
                    data = (json.dumps(obj, ensure_ascii=False) + "\n").encode("utf-8")
                    self.wfile.write(f"{len(data):X}\r\n".encode("ascii") + data + b"\r\n")
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    alive["ok"] = False

            def on_stage(st):
                send_line({"type": "stage", "stage": st})
            try:
                result = process_stages(question, on_stage)
                send_line({"type": "final", "final": result["final"], "faithfulness": result["faithfulness"]})
            except Exception as e:  # noqa: BLE001
                send_line({"type": "error", "error": str(e)})
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            return
        self._send(404, b"not found", "text/plain")


def main():
    global TOOLS, LLM
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8317)
    ap.add_argument("--base-url", default=os.environ.get("AQUADIFF_BASE_URL", "http://127.0.0.1:1234/v1"))
    ap.add_argument("--model", default=os.environ.get("AQUADIFF_MODEL", "cet-gguf/qwen3-4b-instruct-2507@q4_k_m"))
    ap.add_argument("--api-key", default=None, help="云端 API 密钥（缺省读环境变量 AQUADIFF_API_KEY；本地 LM Studio 无需）")
    ap.add_argument("--extra-body", default=None, help="供应商专属请求字段 JSON（如 '{\"thinking\":{\"type\":\"disabled\"}}'；缺省读环境变量 AQUADIFF_LLM_EXTRA）")
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    TOOLS = Tools()
    LLM = LLMClient(base_url=args.base_url, model=args.model, api_key=args.api_key,
                    extra_body=json.loads(args.extra_body) if args.extra_body else None)
    srv = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    url = f"http://127.0.0.1:{args.port}"
    print(f"✅ AquaDiff 网页演示已启动：{url}  （LLM: {args.model} @ {args.base_url}）")
    print("   浏览器未自动打开时请手动访问上面的地址；Ctrl+C 退出。")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")


if __name__ == "__main__":
    main()
