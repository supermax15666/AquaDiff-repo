# -*- coding: utf-8 -*-
"""修订 R2：E 臂 Agent 核心——修复来源元数据校验与输出。

变更内容（历史系统与修订系统严格区分；本文件为 r2 版本，历史 run 结果不得沿用）：
  1. check_faithfulness() 新增 source_reference 字段逐字比对：
     - 期望值由宿主从同一 route_result 重新构造（与 build_tool_block 使用同一函数），
       而不是从 LLM 已生成的 tool_block 文本反解，避免"拿 LLM 读到的文本自证"。
     - 失败计入 violations（source_reference=... expected=...）。
  2. build_source_reference(route_result, condition) 抽出为独立函数，供
     build_tool_block() 与 check_faithfulness() 共用，保证"注入"与"校验"同源。
  3. 新增宿主直出模式（host_direct_payload=True）：数值与来源字段由宿主写入最终回答，
     LLM 只允许补充 notes 中的解释性文字；用于 D01 对照（LLM 解析＋宿主输出 vs
     LLM 解析＋LLM 转写）。
  4. process_question() 在 host_direct_payload 模式下跳过第二阶段模型调用，
     记录 final_host_authored=True，并单独统计第二阶段的转写失败与回退次数。

用法（不改动历史run）：
    from agent_core_r2 import Tools, LLMClient, process_question
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
MODEL_SOURCE_STEM = "frozen specialized numerical model (registry {fp})"


# ---------------------------------------------------------------- 工具层（与历史版一致）
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


# ---------------------------------------------------------------- LLM 客户端（历史版一致）
class LLMClient:
    def __init__(self, base_url="http://127.0.0.1:1234/v1", model=None, mock=False,
                 api_key=None, extra_body=None):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.mock = mock
        self.api_key = api_key or os.environ.get("AQUADIFF_API_KEY") or None
        if extra_body is None:
            raw = os.environ.get("AQUADIFF_LLM_EXTRA")
            extra_body = json.loads(raw) if raw else None
        self.extra_body = dict(extra_body) if extra_body else None

    def chat_json(self, system, user, max_tokens=512, temperature=0.0,
                  retries=5, backoff_base=15, backoff_max=60):
        t0 = time.time()
        if self.mock:
            obj, raw = self._mock_response(system, user)
            return obj, raw, time.time() - t0
        body = {"model": self.model, "temperature": temperature, "max_tokens": max_tokens,
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
            except Exception as e:
                last_err = e
                if attempt < retries:
                    time.sleep(min(backoff_base * attempt, backoff_max))
        raise RuntimeError(f"LLM call failed after {retries} attempts: {last_err}") from last_err

    def _mock_response(self, system, user):
        if "parameter extraction module" in system:
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


# ---------------------------------------------------------------- 路由（历史版一致）
def route_condition(tools, system, T, c):
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
    if tu in ("k", ""):
        pass
    elif tu in ("c", "celsius", "°c"):
        T = T + 273.15
    elif tu in ("f", "fahrenheit", "°f"):
        T = (T - 32.0) * 5.0 / 9.0 + 273.15
    else:
        return False, None, {"route": "clarify", "reason": "温度单位未知/不可安全换算"}
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


def canonical_ml_value(v):
    """ML 预测的规范输出值：6 位有效数字（工具块显示、来源元数据与判分共用同一口径）。"""
    return float(f"{float(v):.6g}")


# ---------------------------------------------------------------- 【R2 新增】同源来源元数据
def build_source_metadata(route_result, condition=None):
    """由宿主从 route_result 直接构造 (source_type, source_reference, value)。

    build_tool_block() 与 check_faithfulness() 共用本函数，使"注入给 LLM 的来源"
    与"校验 LLM 誊写的来源"来自同一真值，而不是从 LLM 看到的文本反解。
    返回 (source_type, source_reference, canonical_value 或 None)。
    """
    r = route_result
    route = r.get("route")
    if route and route.startswith("db_hit"):
        db = r["db"]
        refs = db["references"]
        src = "; ".join(refs[:3]) + ("; ..." if len(refs) > 3 else "")
        return "experimental_record", src, db["median_diffusion_1e9_m2_s"]
    if route == "ml":
        fp = r["ml"].get("registry_fingerprint")
        if not fp:
            raise KeyError("route_result.ml.registry_fingerprint missing: cannot build source metadata")
        # 校验/注入统一使用短标识（与稿件 registry ffbc8b45… 一致）
        ref = MODEL_SOURCE_STEM.format(fp=fp[:8])
        return "specialized_model", ref, canonical_ml_value(r["ml"]["prediction_1e9_m2_s"])
    return "none", "", None


def build_tool_block(question, decision_or_route, condition=None):
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
        _st, ref, cv = build_source_metadata(r, condition)
        lines.append(f"value: D = {cv} * 10^-9 m^2/s (x = {cv})")
        lines.append(f"source_type: specialized_model (frozen registry {r['ml']['registry_fingerprint'][:8]}, "
                     f"{condition['system']})")
        lines.append(f"source_reference: {ref}")
    else:
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


# ---------------------------------------------------------------- 【R2 修复】硬校验
def check_faithfulness(route_result, final_json):
    """宿主硬校验（R2）：分项评价 answer_type / 数值 / source_type / source_reference / 披露。

    与历史版的差别：新增 source_reference 逐字比对（历史版未检查该字段，
    因此历史 run 的 faithful=True 不能理解为"来源逐字一致"）。
    """
    if not isinstance(final_json, dict):
        return {"faithful": False, "violations": ["final_parse_failed"],
                "checks": {}, "host_authored": False}
    v = []
    checks = {}
    at = final_json.get("answer_type")
    expected_at = {"db_hit": "value", "db_hit_after_clamp": "value", "ml": "value"}.get(
        route_result["route"],
        "refusal" if route_result["route"] == "refuse_out_of_domain" else "clarify")
    checks["answer_type"] = (at == expected_at)
    if not checks["answer_type"]:
        v.append(f"answer_type={at} expected={expected_at}")
    if expected_at == "value":
        exp_st, exp_ref, exp_val = build_source_metadata(route_result)
        got = final_json.get("diffusion_1e9_m2_s")
        ok_val = (isinstance(got, (int, float))
                  and abs(float(got) - float(exp_val)) <= 1e-9 * max(1.0, abs(float(exp_val))))
        checks["value"] = ok_val
        if not ok_val:
            v.append(f"value={got!r} expected={exp_val!r}")
        st = final_json.get("source_type")
        checks["source_type"] = (st == exp_st)
        if not checks["source_type"]:
            v.append(f"source_type={st} expected={exp_st}")
        # --- R2 新增：来源引用逐字比对 ---
        ref = final_json.get("source_reference")
        checks["source_reference"] = (ref == exp_ref)
        if not checks["source_reference"]:
            v.append(f"source_reference={ref!r} expected={exp_ref!r}")
        if route_result.get("saturation_clamp") or route_result.get("supersaturation_advisory"):
            notes = str(final_json.get("notes", ""))
            checks["disclosure"] = ("saturat" in notes.lower())
            if not checks["disclosure"]:
                v.append("missing saturation disclosure in notes")
    return {"faithful": not v, "violations": v, "checks": checks, "host_authored": False}


def host_direct_final(route_result, condition=None):
    """【R2 新增】宿主直出模式：数值与来源字段由宿主写入最终回答。

    返回 (final_json, faithfulness)。LLM 在该模式下不参与数值/来源字段的生成，
    因此 faithfulness 中的 host_authored=True（与"转写成功"不是同一指标）。
    """
    route = route_result["route"]
    if route.startswith("db_hit") or route == "ml":
        st, ref, val = build_source_metadata(route_result, condition)
        notes = ""
        if route_result.get("saturation_clamp") or route_result.get("supersaturation_advisory"):
            notes = ("The input concentration exceeds the saturation concentration at this "
                     "temperature; the value is given at the stated condition.")
        final = {"answer_type": "value", "diffusion_1e9_m2_s": val, "source_type": st,
                 "source_reference": ref, "notes": notes}
        return final, {"faithful": True, "violations": [], "checks": {"host_direct": True},
                       "host_authored": True}
    ml = route_result.get("ml", {})
    ad = ml.get("domain", {})
    reason = ("out of applicability domain (fields: %s; valid T [%s, %s] K, c [%s, %s] mol/L)"
              % (", ".join(ml.get("out_of_domain_fields", [])),
                 ad.get("temperature_K", {}).get("min"), ad.get("temperature_K", {}).get("max"),
                 ad.get("concentration_mol_L", {}).get("min"),
                 ad.get("concentration_mol_L", {}).get("max")))
    final = {"answer_type": "refusal", "source_type": "none", "notes": reason}
    return final, {"faithful": True, "violations": [], "checks": {"host_direct": True},
                   "host_authored": True}


def process_question(tools, llm, question, stub_intent=None, stub_final=None,
                     host_direct_payload=False):
    """处理单个问题。host_direct_payload=True 时数值/来源由宿主直出（D01 对照）。"""
    rec = {"question": question, "events": []}
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
        rec.update(stage="complete",
                   route_result={"route": "clarify", "reason": "intent_json_parse_failed"},
                   final={"answer_type": "clarify", "source_type": "none",
                          "notes": "无法从问题中解析出可靠的结构化条件，请补充完整条件后重试"},
                   faithfulness={"faithful": True, "violations": [], "checks": {},
                                 "host_authored": True})
        return rec
    ok, condition, decision = host_validate(intent)
    rec["condition"] = condition
    if not ok:
        rec["route_result"] = decision
        rec["final"] = {"answer_type": "clarify" if decision["route"] == "clarify" else "refusal",
                        "source_type": "none",
                        "notes": decision.get("reason", "")}
        rec["faithfulness"] = {"faithful": True, "violations": [], "checks": {},
                               "host_authored": True}
        rec["stage"] = "complete"
        return rec
    route_result = route_condition(tools, condition["system"],
                                   condition["temperature_K"], condition["concentration_mol_L"])
    rec["route_result"] = {k: route_result[k] for k in
                           ("route", "trace", "supersaturation_advisory", "saturation_clamp")
                           if k in route_result}
    block = build_tool_block(question, route_result, condition)
    rec["tool_block"] = block

    # --- R2：宿主直出模式，不调用第二阶段 LLM ---
    if host_direct_payload:
        final, faith = host_direct_final(route_result, condition)
        rec["final"] = final
        rec["faithfulness"] = faith
        rec["final_host_authored"] = True
        rec["stage"] = "complete"
        return rec

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
        stub_final = stub2
    final_user = block if stub_final is None else f"{block}\nSTUB-FINAL:{json.dumps(stub2 if stub_final=='auto' else stub_final, ensure_ascii=False)}"
    try:
        final, raw2, lat2 = llm.chat_json(FINAL_SYSTEM, final_user)
        rec["final_raw"] = raw2
        rec["final_latency_s"] = round(lat2, 4)
    except RuntimeError as e:
        rec["stage"] = "final"
        rec["error"] = str(e)
        return rec
    rec["final"] = final
    rec["faithfulness"] = check_faithfulness(route_result, final)
    rec["final_host_authored"] = False
    rec["stage"] = "complete"
    return rec


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
    "EXACTLY, digit for digit, including the source_reference string. Respond with a single JSON object only:\n"
    '{"answer_type": "value|refusal|clarify", "diffusion_1e9_m2_s": <number copied exactly>, '
    '"source_type": "experimental_record|specialized_model|none", '
    '"source_reference": "<copied from TOOL RESULT, character for character>", '
    '"notes": "<copy any required disclosure>"}\n'
    "Rules: (1) If the TOOL RESULT contains a value, answer_type MUST be \"value\" even when a NOTE is "
    "present (saturation or supersaturation notes belong in notes, they never change answer_type). "
    "(2) Copy the number with ALL digits shown; never round, recompute, or reformat it. "
    "(3) Copy source_reference character for character, including registry identifiers, DOIs and "
    "author names; never abbreviate, translate or \"correct\" it. "
    "(4) answer_type is \"refusal\" or \"clarify\" ONLY when the TOOL RESULT explicitly says NO VALUE "
    "or NO NUMERIC ANSWER; copy the given reason into notes and OMIT the numeric fields."
)
