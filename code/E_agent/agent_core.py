# -*- coding: utf-8 -*-
"""E 臂两段式受限 Agent 核心（方案 v2.15/v2.16 §3.E，工具契约见 工具契约.md）。

LLM 只做意图提取与终答誊写；校验/单位换算/饱和检查/路由/适用域/硬校验全部由本模块
的确定性宿主执行。路由总序（v2.16）：
  意图提取 → 宿主校验/换算 → DB(原始) ─命中→ 实测值+来源（超饱和附披露）
                                └未命中→ 饱和检查 ─超→ 明示+夹取 → 重入路由
                                                └未超→ 域盒 → ML / 域外拒绝
  → LLM 誊写 → 宿主硬校验。

依赖冻结产物：db/experimental_records.duckdb、frozen/solubility_frozen.json、
D 臂 registry（ffbc8b45…，joblib）。LLM 经 LM Studio OpenAI 兼容端点（锚点
Qwen3-4B-Instruct-2507，同 A/C 臂部署身份）；--mock 模式用确定性桩替代 LLM 供宿主测试。
"""

import json
import math
import os
import re
import time
from urllib import request as _urlreq, error as _urlerr

import duckdb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
DB_PATH = os.path.join(HERE, "db", "experimental_records.duckdb")
SAT_PATH = os.path.join(HERE, "frozen", "solubility_frozen.json")
REG_DIR = os.path.join(ROOT, "03_实验结果", "D臂_ML数值后端_冻结", "output", "registry",
                       "ffbc8b45278774e9317b8c53780753fd3a180f351dff7defed77d1bb4ce63ad6")
TAU = 0.01
SYSTEMS = {"NaCl-H2O": 58.44, "KCl-H2O": 74.55, "LiCl-H2O": 42.39, "CaCl2-H2O": 110.98}
UNIT_ANSWER_NOTE = ("Return the multiplier x where D = x * 10^-9 m^2/s. "
                    "The JSON numeric field must contain x only.")

INTENT_SYSTEM = (
    "You are a parameter extraction module for a diffusion-coefficient lookup system. "
    "Extract the solution system, temperature and concentration from the user question. "
    "Respond with a single JSON object only, no extra text.\n"
    'Schema: {"status": "ok|ambiguous|unsupported|missing_fields", '
    '"system": "NaCl-H2O|KCl-H2O|LiCl-H2O|CaCl2-H2O", '
    '"temperature": <number>, "temperature_unit": "K|C|F|unknown", '
    '"concentration": <number>, "concentration_unit": "mol/L|g/L|mmol/L|mol/kg|wt_percent|unknown", '
    '"issues": [<strings>]}\n'
    "HARD RULES (violations are errors):\n"
    "1. NEVER invent, estimate, or default any parameter. If temperature or concentration is not "
    "explicitly written as a number in the question, use missing_fields. Never substitute 298 K, "
    "25 C, 0, or any other default. Vague phrases like 'room temperature' or 'saturated "
    "concentration' or 'twice saturation' mean ambiguous (a number is required).\n"
    "2. Copy numbers and unit labels EXACTLY as written. Do NOT convert units yourself — the "
    "backend converts. '25 C' must be temperature=25, temperature_unit=C (NOT 298.15). "
    "'77 F' must be temperature=77, temperature_unit=F. A number with no unit at all → ambiguous.\n"
    "3. If the solution is not exactly one of the four supported aqueous systems (NaCl-H2O, "
    "KCl-H2O, LiCl-H2O, CaCl2-H2O), use status=unsupported and name it in issues. NEVER map a "
    "similar but different substance onto a supported system (e.g. KBr is NOT KCl-H2O; seawater, "
    "mixtures and non-aqueous solvents are unsupported).\n"
    "4. If the question asks about several conditions at once, a range, or a different property "
    "than the mutual diffusion coefficient of the binary solution, use ambiguous.\n"
    "5. status=ok only when one fully specified condition of a supported system with convertible "
    "units (mol/L, g/L, mmol/L, K, C, F) is present. mol/kg and wt_percent are valid to report "
    "as units but the backend will refuse them."
)

FINAL_SYSTEM = (
    "You are the answer-writer module of a diffusion-coefficient system. You receive a question and a "
    "TOOL RESULT block. Copy the numeric value and the source from the TOOL RESULT into your answer "
    "EXACTLY, digit for digit. Respond with a single JSON object only:\n"
    '{"answer_type": "value|refusal|clarify", "diffusion_1e9_m2_s": <number copied exactly>, '
    '"source_type": "experimental_record|specialized_model|none", '
    '"source_reference": "<copied from TOOL RESULT>", "notes": "<copy any required disclosure>"}\n'
    "Rules: (1) If the TOOL RESULT contains a value, answer_type MUST be \"value\" even when a NOTE is "
    "present (saturation or supersaturation notes belong in notes, they never change answer_type). "
    "(2) Copy the number with ALL digits shown; never round, recompute, or reformat it. "
    "(3) answer_type is \"refusal\" or \"clarify\" ONLY when the TOOL RESULT explicitly says NO VALUE "
    "or NO NUMERIC ANSWER; copy the given reason into notes and OMIT the numeric fields."
)


# ---------------------------------------------------------------- 工具层
class Tools:
    def __init__(self):
        self._con = duckdb.connect(DB_PATH, read_only=True)
        sat = json.load(open(SAT_PATH, encoding="utf-8"))
        self.sat_records = sat["records"]
        self.sat_content_sha = sat["records_content_sha256"]
        reg = json.load(open(os.path.join(REG_DIR, "registry.json"), encoding="utf-8"))
        self.domains = {s["system"]: s["applicability_domain"] for s in reg["systems"]}
        self.registry_fp = reg["protocol_fingerprint"]
        self._models = {}

    # -- 工具一：实验记录查询（精确匹配；多记录返回中位数+谱系，与 gold 策略一致）
    def query_experimental_records(self, system, T, c):
        rows = self._con.execute(
            "SELECT diffusion_1e9_m2_s, lineage_id, original_reference FROM experimental_records "
            "WHERE system=? AND temperature_K=? AND concentration_mol_L=?",
            [system, float(T), float(c)]).fetchall()
        if not rows:
            return {"hit": False}
        vals = sorted(r[0] for r in rows)
        n = len(vals)
        median = vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2
        return {"hit": True, "median_diffusion_1e9_m2_s": median, "n_records": n,
                "value_min_1e9_m2_s": vals[0], "value_max_1e9_m2_s": vals[-1],
                "lineage_ids": sorted({r[1] for r in rows}),
                "references": sorted({r[2] for r in rows})}

    # -- 工具三：饱和检查（冻结表线性插值；T 出表范围不检查）
    def check_saturation(self, system, T, c):
        pts = sorted((r["temperature_K"], r["c_sat_mol_L"]) for r in self.sat_records
                     if r["system_id"] == system)
        if not pts or T < pts[0][0] or T > pts[-1][0]:
            return {"checked": False, "exceeded": False}
        cs = None
        for (t1, c1), (t2, c2) in zip(pts, pts[1:]):
            if t1 <= T <= t2:
                cs = c1 + (c2 - c1) * (T - t1) / (t2 - t1)
                break
        if cs is None and T == pts[0][0]:
            cs = pts[0][1]
        return {"checked": True, "exceeded": c > cs * (1 + TAU), "c_sat_mol_L": cs,
                "ratio_to_saturation": c / cs if cs else None}

    # -- 工具二：专用模型预测（先矩形盒域检查；域外结构化拒绝）
    def predict_specialized_model(self, system, T, c):
        ad = self.domains[system]
        out_fields = []
        if not (ad["temperature_K"]["min"] <= T <= ad["temperature_K"]["max"]):
            out_fields.append("temperature_K")
        if not (ad["concentration_mol_L"]["min"] <= c <= ad["concentration_mol_L"]["max"]):
            out_fields.append("concentration_mol_L")
        if out_fields:
            return {"accepted": False, "out_of_domain_fields": out_fields, "domain": ad}
        if system not in self._models:
            import joblib
            self._models[system] = joblib.load(os.path.join(REG_DIR, f"{system}.joblib"))
        pred = float(self._models[system].predict([[float(T), float(c)]])[0])
        if not math.isfinite(pred):
            return {"accepted": False, "out_of_domain_fields": [], "domain": ad,
                    "refusal_reason": "model_output_not_finite"}
        return {"accepted": True, "prediction_1e9_m2_s": pred,
                "registry_fingerprint": self.registry_fp}


# ---------------------------------------------------------------- LLM 客户端
class LLMClient:
    def __init__(self, base_url="http://127.0.0.1:1234/v1", model=None, mock=False,
                 api_key=None, extra_body=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.mock = mock
        # 云端 OpenAI 兼容端点鉴权：显式参数优先，其次环境变量 AQUADIFF_API_KEY；
        # 均未设置时不发 Authorization（本地 LM Studio 无需鉴权，行为与旧版逐位一致）。
        self.api_key = api_key or os.environ.get("AQUADIFF_API_KEY") or None
        # 供应商专属请求字段（如 DeepSeek/智谱/豆包的 thinking 开关、通义的
        # enable_thinking）：显式参数优先，其次环境变量 AQUADIFF_LLM_EXTRA（JSON 字符串）。
        # 不设置则不合并——本地 LM Studio 与旧版行为逐位一致。
        if extra_body is None:
            raw = os.environ.get("AQUADIFF_LLM_EXTRA")
            extra_body = json.loads(raw) if raw else None
        self.extra_body = dict(extra_body) if extra_body else None

    def chat_json(self, system, user, max_tokens=512, temperature=0.0,
                  retries=5, backoff_base=15, backoff_max=60):
        """返回 (dict|None, raw_text, latency_s)。基础设施类失败自动重试（退避）。

        retries/backoff_* 仅是调用方可选的演示档位；默认值（5 次、15/30/45/60 s）
        与评测运行行为逐位一致。"""
        t0 = time.time()
        if self.mock:
            obj, raw = self._mock_response(system, user)
            return obj, raw, time.time() - t0
        body = {"model": self.model, "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}]}
        if self.extra_body:
            body.update(self.extra_body)
        payload = json.dumps(body).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = "Bearer " + self.api_key
        last_err = None
        for attempt in range(1, retries + 1):
            req = _urlreq.Request(self.base_url + "/chat/completions", data=payload,
                                  headers=headers, method="POST")
            try:
                with _urlreq.urlopen(req, timeout=120) as resp:
                    out = json.loads(resp.read().decode("utf-8"))
                raw = out["choices"][0]["message"]["content"]
                return _extract_json(raw), raw, time.time() - t0
            except Exception as e:  # 网络/HTTP/断线：退避重试（模型掉线常为瞬时）
                last_err = e
                if attempt < retries:
                    time.sleep(min(backoff_base * attempt, backoff_max))
        raise RuntimeError(f"LLM call failed after {retries} attempts: {last_err}") from last_err

    def _mock_response(self, system, user):
        """确定性桩：由用户消息中携带的桩标记决定返回（仅测试宿主逻辑）。"""
        if system is INTENT_SYSTEM:
            stub = json.loads(user.split("STUB-INTENT:", 1)[1].split("\n", 1)[0])
            return stub, json.dumps(stub, ensure_ascii=False)
        stub = json.loads(user.split("STUB-FINAL:", 1)[1].split("\n", 1)[0])
        return stub, json.dumps(stub, ensure_ascii=False)


def _extract_json(text):
    m = re.search(r"\{[^{}]*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


# ---------------------------------------------------------------- 宿主路由
def _fmt(x):
    """数值规范化字符串（忠实性逐字比较用：去除浮点表示差异）。"""
    if x is None:
        return ""
    if isinstance(x, float) and x == int(x) and abs(x) < 1e15:
        return str(int(x))
    return repr(x)


def route_condition(tools, system, T, c):
    """v2.16 路由：DB(原始) → 饱和检查/夹取 → 重入 → 域盒 → ML/拒绝。返回工具结果块。"""
    trace = []
    db = tools.query_experimental_records(system, T, c)
    if db["hit"]:
        sat = tools.check_saturation(system, T, c)
        advisory = sat.get("checked") and sat.get("exceeded")
        trace.append("db_hit")
        return {"route": "db_hit", "db": db, "supersaturation_advisory": bool(advisory),
                "saturation": sat, "trace": trace}
    trace.append("db_miss")
    sat = tools.check_saturation(system, T, c)
    clamped = None
    c_eff = c
    if sat.get("checked") and sat.get("exceeded"):
        clamped = sat["c_sat_mol_L"]
        c_eff = clamped
        trace.append(f"saturation_clamp({c}->{clamped})")
        db2 = tools.query_experimental_records(system, T, c_eff)
        if db2["hit"]:
            trace.append("db_hit_after_clamp")
            return {"route": "db_hit_after_clamp", "db": db2, "saturation": sat,
                    "saturation_clamp": {"input_c": c, "c_sat_mol_L": clamped}, "trace": trace}
        trace.append("db_miss_after_clamp")
    ml = tools.predict_specialized_model(system, T, c_eff)
    if ml["accepted"]:
        trace.append("ml")
        result = {"route": "ml", "ml": ml, "saturation": sat, "trace": trace}
    else:
        trace.append("refuse_out_of_domain")
        result = {"route": "refuse_out_of_domain", "ml": ml, "saturation": sat, "trace": trace}
    if clamped is not None:
        result["saturation_clamp"] = {"input_c": c, "c_sat_mol_L": clamped}
    return result


def host_validate(intent):
    """宿主对 LLM 意图的最终裁决与单位换算。返回 (ok, condition|None, decision|None)。"""
    if not isinstance(intent, dict):
        return False, None, {"route": "clarify", "reason": "intent_parse_failed"}
    status = intent.get("status")
    if status == "unsupported":
        return False, None, {"route": "refuse_unsupported",
                             "reason": f"不支持的水溶液体系：{intent.get('issues')}"}
    if status in ("ambiguous", "missing_fields"):
        return False, None, {"route": "clarify",
                             "reason": f"问题不完整或存在歧义：{intent.get('issues')}"}
    if status != "ok":
        return False, None, {"route": "clarify", "reason": f"无法解析：{intent.get('issues')}"}
    system = intent.get("system")
    if system not in SYSTEMS:
        return False, None, {"route": "refuse_unsupported", "reason": f"体系不支持：{system}"}
    tu = (intent.get("temperature_unit") or "unknown").lower()
    cu = (intent.get("concentration_unit") or "mol/L").lower()
    T, c = intent.get("temperature"), intent.get("concentration")
    if not isinstance(T, (int, float)) or not isinstance(c, (int, float)):
        return False, None, {"route": "clarify", "reason": "温度/浓度缺失或非数值"}
    # 温度换算（精确）
    if tu in ("k", ""):
        pass
    elif tu in ("c", "celsius", "°c"):
        T = T + 273.15
    elif tu in ("f", "fahrenheit", "°f"):
        T = (T - 32.0) * 5.0 / 9.0 + 273.15
    else:
        return False, None, {"route": "clarify", "reason": "温度单位未知/不可安全换算"}
    # 浓度换算（仅质量浓度→摩尔浓度；molality/wt% 需密度，拒绝）
    if cu in ("mol/l", "m", ""):
        pass
    elif cu == "g/l":
        c = c / SYSTEMS[system]
    elif cu in ("mmol/l", "mmol/l"):
        c = c / 1000.0
    elif cu in ("mol/kg", "molality") or "wt" in cu or "%" in cu:
        return False, None, {"route": "refuse_unit_unconvertible",
                             "reason": f"浓度单位 {cu} 需溶液密度，无法安全换算为 mol/L"}
    else:
        return False, None, {"route": "clarify", "reason": f"浓度单位未知：{cu}"}
    return True, {"system": system, "temperature_K": float(T), "concentration_mol_L": float(c)}, None


def build_tool_block(question, decision_or_route, condition=None):
    """构造给 LLM 阶段二的工具结果块文本（宿主注入，LLM 只誊写）。"""
    if condition is None:
        return (f"QUESTION: {question}\nTOOL RESULT: NO NUMERIC ANSWER. "
                f"Decision: {decision_or_route.get('route')}. Reason: {decision_or_route.get('reason')}. "
                "Ask the user to clarify or state refusal accordingly.")
    r = decision_or_route
    lines = [f"QUESTION: {question}", "TOOL RESULT:"]
    sat_note = ""
    if r.get("saturation_clamp"):
        sc = r["saturation_clamp"]
        sat_note = (f"NOTE: input concentration {sc['input_c']} mol/L exceeds the saturation "
                    f"concentration {sc['c_sat_mol_L']:.6g} mol/L at this temperature; the value below "
                    f"is given AT SATURATION.")
        lines.append(sat_note)
    if r["route"].startswith("db_hit"):
        db = r["db"]
        src = "; ".join(db["references"][:3]) + ("; ..." if len(db["references"]) > 3 else "")
        lines.append(f"value: D = {db['median_diffusion_1e9_m2_s']} * 10^-9 m^2/s "
                     f"(x = {db['median_diffusion_1e9_m2_s']})")
        lines.append(f"source_type: experimental_record ({db['n_records']} records, "
                     f"lineages: {', '.join(db['lineage_ids'][:3])})")
        lines.append(f"source_reference: {src}")
        if r.get("supersaturation_advisory"):
            lines.append("NOTE: this concentration exceeds the equilibrium saturation concentration; "
                         "the returned value is a measured record (possibly a metastable "
                         "supersaturated solution).")
    elif r["route"] == "ml":
        ml = r["ml"]
        cv = canonical_ml_value(ml["prediction_1e9_m2_s"])
        lines.append(f"value: D = {cv} * 10^-9 m^2/s (x = {cv})")
        lines.append("source_type: specialized_model (frozen registry ffbc8b45, "
                     f"{condition['system']})")
        lines.append("source_reference: frozen specialized numerical model (registry ffbc8b45)")
    else:  # refuse_out_of_domain
        ml = r["ml"]
        ad = ml.get("domain", {})
        rng_t = ad.get("temperature_K", {})
        rng_c = ad.get("concentration_mol_L", {})
        lines.append("NO VALUE: out of applicability domain "
                     f"(fields: {', '.join(ml.get('out_of_domain_fields', []))}; "
                     f"valid T [{rng_t.get('min')}, {rng_t.get('max')}] K, "
                     f"c [{rng_c.get('min')}, {rng_c.get('max')}] mol/L).")
        if r.get("saturation_clamp"):
            lines.append("The input was supersaturated; even at the saturation concentration the "
                         "condition remains outside the model domain.")
        lines.append("answer_type must be refusal with this reason in notes.")
    return "\n".join(lines)


def canonical_ml_value(v):
    """ML 预测的规范输出值：6 位有效数字（工具块显示、忠实性校验与判分共用同一口径）。"""
    return float(f"{float(v):.6g}")


def check_faithfulness(route_result, final_json):
    """宿主硬校验：数值与来源逐字一致（忠实率分项）。"""
    if not isinstance(final_json, dict):
        return {"faithful": False, "violations": ["final_parse_failed"]}
    v = []
    at = final_json.get("answer_type")
    expected_at = {"db_hit": "value", "db_hit_after_clamp": "value", "ml": "value"}.get(
        route_result["route"], "refusal" if route_result["route"] == "refuse_out_of_domain" else "clarify")
    if at != expected_at:
        v.append(f"answer_type={at} expected={expected_at}")
    if expected_at == "value":
        expected_val = (route_result["db"]["median_diffusion_1e9_m2_s"]
                        if route_result["route"].startswith("db_hit")
                        else canonical_ml_value(route_result["ml"]["prediction_1e9_m2_s"]))
        got = final_json.get("diffusion_1e9_m2_s")
        if not isinstance(got, (int, float)) or abs(float(got) - float(expected_val)) > 1e-9 * max(1.0, abs(expected_val)):
            v.append(f"value={got!r} expected={expected_val!r}")
        st = final_json.get("source_type")
        exp_st = "experimental_record" if route_result["route"].startswith("db_hit") else "specialized_model"
        if st != exp_st:
            v.append(f"source_type={st} expected={exp_st}")
        if route_result.get("saturation_clamp") or route_result.get("supersaturation_advisory"):
            notes = str(final_json.get("notes", ""))
            if "saturat" not in notes.lower():
                v.append("missing saturation disclosure in notes")
    return {"faithful": not v, "violations": v}


# ---------------------------------------------------------------- 主流程
def process_question(tools, llm, question, stub_intent=None, stub_final=None):
    """处理单个问题，返回完整记录（评测与指标计算用）。"""
    rec = {"question": question, "events": []}
    # 阶段一：意图提取
    intent_user = question if stub_intent is None else f"{question}\nSTUB-INTENT:{json.dumps(stub_intent, ensure_ascii=False)}"
    try:
        intent, raw1, lat1 = llm.chat_json(INTENT_SYSTEM, intent_user)
        rec["intent_raw"] = raw1
        rec["intent_latency_s"] = round(lat1, 4)
    except RuntimeError as e:
        rec.update(stage="intent", error=str(e))
        return rec
    rec["intent"] = intent
    if intent is None:
        # 意图 JSON 解析失败 → 宿主降级为澄清请求（确定性直出，计解析失败、不计错误）
        rec.update(stage="complete",
                   route_result={"route": "clarify", "reason": "intent_json_parse_failed"},
                   final={"answer_type": "clarify", "source_type": "none",
                          "notes": "无法从问题中解析出可靠的结构化条件，请补充完整条件后重试"},
                   faithfulness={"faithful": True, "violations": [], "host_authored": True})
        return rec
    # 宿主裁决与换算
    ok, condition, decision = host_validate(intent)
    rec["condition"] = condition
    if not ok:
        rec["route_result"] = decision
        # 澄清/体系不支持/单位不可换算：终答由宿主确定性直出（不经 LLM 誊写，零转写风险）
        rec["final"] = {"answer_type": "clarify" if decision["route"] == "clarify" else "refusal",
                        "source_type": "none",
                        "notes": decision.get("reason", "")}
        rec["faithfulness"] = {"faithful": True, "violations": [], "host_authored": True}
        rec["stage"] = "complete"
        return rec
    # 确定性路由
    route_result = route_condition(tools, condition["system"],
                                   condition["temperature_K"], condition["concentration_mol_L"])
    rec["route_result"] = {k: route_result[k] for k in
                           ("route", "trace", "supersaturation_advisory", "saturation_clamp")
                           if k in route_result}
    # 阶段二：誊写
    block = build_tool_block(question, route_result, condition)
    if route_result["route"].startswith("db_hit"):
        expected_val = route_result["db"]["median_diffusion_1e9_m2_s"]
        stub2 = {"answer_type": "value", "diffusion_1e9_m2_s": expected_val,
                 "source_type": "experimental_record"}
    elif route_result["route"] == "ml":
        stub2 = {"answer_type": "value",
                 "diffusion_1e9_m2_s": canonical_ml_value(route_result["ml"]["prediction_1e9_m2_s"]),
                 "source_type": "specialized_model"}
    else:
        stub2 = {"answer_type": "refusal", "notes": "out of domain"}
    if route_result.get("saturation_clamp") or route_result.get("supersaturation_advisory"):
        stub2 = dict(stub2, notes=(str(stub2.get("notes", "")) +
                    " The input concentration exceeds the saturation concentration at this temperature."
                    ).strip())
    if stub_final is None and getattr(llm, "mock", False):
        stub_final = stub2  # mock 模式默认用完美誊写桩（宿主逻辑测试用）
    final_user = block if stub_final is None else f"{block}\nSTUB-FINAL:{json.dumps(stub2 if stub_final=='auto' else stub_final, ensure_ascii=False)}"
    try:
        final, raw2, lat2 = llm.chat_json(FINAL_SYSTEM, final_user)
        rec["final_raw"] = raw2
        rec["final_latency_s"] = round(lat2, 4)
    except RuntimeError as e:
        rec["stage"] = "final"
        rec["error"] = str(e)
        rec["tool_block"] = block
        return rec
    rec["final"] = final
    rec["tool_block"] = block
    rec["faithfulness"] = check_faithfulness(route_result, final)
    rec["stage"] = "complete"
    return rec
