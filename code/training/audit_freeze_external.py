# -*- coding: utf-8 -*-
"""External prospective test set: audit + freeze script (C arm, plan §17; v2.12 baseline = 642 questions).

职责（交接文档 §5 步骤 1）：
  1. 加载用户检索的候选记录（xlsx/csv，列契约见《外部前瞻集检索与冻结方案.md》第 6 节）；
  2. 与基线机械比对：
     a. 条件基线：四工作簿全部唯一条件（696 个）的 (system, T, c) 近重复检查；
     b. 谱系基线：四工作簿全部 45 个来源谱系（origin_lineage_id）撞名检查；
     c. 文献基线：642 题 gold 中全部 original_reference 归一化撞车检查（作者-年份碰撞只警告）；
  3. 按方案 §2 同一纳入/排除规则逐条判定（c=0、派生值、非实验、跨谱系冲突、物理硬界）；
  4. 同谱系同条件重复记录取中位数 consensus（与 642 完全同口径）；
  5. 按 642 题格式生成题库（家族 A 提示）与分离保存的 gold（SHA-256 留档），并密封。

安全纪律：本脚本与控制台输出**不打印任何 gold 数值**；审计日志 CSV 不含 D 列。
冻结后任何人不得查看 gold 文件（见 --freeze 时打印的 SEAL 通知）。
用法：
  python audit_freeze_external.py --precheck [--candidates PATH] [--sheet NAME]
  python audit_freeze_external.py --candidates PATH [--out-dir PATH] [--sheet NAME]
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "py" / "LLM_API_direct"))

from common import (  # noqa: E402
    SCHEMA_VERSION,
    TARGET_UNIT,
    canonical_json_bytes,
    sha256_bytes,
    sha256_file,
    stable_hash,
    safe_slug,
)
from prepare_questions import template_text  # noqa: E402

PLAN_VERSION = "2.14"
SYSTEMS = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]
SYSTEM_ORDER = {system: index for index, system in enumerate(SYSTEMS)}

DEFAULT_WORKBOOKS_DIR = ROOT / "分谱系数据"
DEFAULT_GOLD_642 = (
    ROOT / "py" / "LLM_API_direct" / "questions" / "four_system_all_gold.evaluator.jsonl"
)
DEFAULT_CANDIDATES_DIR = ROOT / "py" / "微调" / "external" / "candidates"
DEFAULT_OUT_DIR = ROOT / "py" / "微调" / "external"
SCOPE_DOC = ROOT / "py" / "微调" / "外部前瞻集检索与冻结方案.md"

# 近重复容差（冻结于《外部前瞻集检索与冻结方案.md》第 2.1 节）
T_TOLERANCE_K = 0.5
C_REL_TOLERANCE = 0.005
C_ABS_TOLERANCE = 0.0005
# 物理合理性硬界
T_MIN_K = 250.0
T_MAX_K = 380.0
C_MAX_MOL_L = 25.0
# 条数目标（检索方案第 5 节）
MIN_PER_SYSTEM = 10
TARGET_PER_SYSTEM = 20
MIN_TOTAL = 60
TARGET_TOTAL = 100

LINEAGE_PATTERN = re.compile(r"^[A-Z]{2,10}:[A-Z0-9_-]{2,12}:[A-Z0-9._-]{2,60}$")
YEAR_PATTERN = re.compile(r"\b(19\d{2}|20[0-2]\d)\b")

EVIDENCE_LEVEL = "prospective_external_frozen"
SPLIT_ROLE = "prospective_external_condition_consensus"
TEMPLATE_FAMILY_ID = "direct_internalized_numeric_en_v1"
QUESTION_ID_PREFIX = "external"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def norm_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", value.lower())


def reference_profile(reference: str) -> tuple[set[str], set[str]]:
    """返回 (作者词集合, 年份集合)，用于作者-年份碰撞预警。"""
    cleaned = str(reference or "")
    years = set(YEAR_PATTERN.findall(cleaned))
    first_year = min((match.start() for match in YEAR_PATTERN.finditer(cleaned)), default=-1)
    author_part = cleaned[:first_year] if first_year >= 0 else cleaned
    tokens = {
        token
        for token in re.split(r"[^A-Za-z]+", author_part)
        if len(token) > 2 and not token.isdigit()
    }
    return {token.lower() for token in tokens}, years


def load_workbook_rows(path: Path, sheet: str = "Confirmed_Records") -> list[dict[str, Any]]:
    from openpyxl import load_workbook

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet not in workbook.sheetnames:
            raise ValueError(f"Sheet {sheet!r} not found in {path.name}; sheets: {workbook.sheetnames}")
        worksheet = workbook[sheet]
        headers = [str(cell).strip() for cell in next(worksheet.iter_rows(min_row=1, max_row=1, values_only=True))]
        rows: list[dict[str, Any]] = []
        for values in worksheet.iter_rows(min_row=2, values_only=True):
            row = {headers[i]: values[i] for i in range(min(len(headers), len(values)))}
            if any(value not in (None, "") for value in row.values()):
                rows.append(row)
        return rows
    finally:
        workbook.close()


def load_candidate_rows(path: Path, sheet: str) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".xlsx":
        rows = load_workbook_rows(path, sheet)
    elif path.suffix.lower() == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            rows = [
                {str(key or "").strip(): value for key, value in row.items() if key is not None}
                for row in reader
            ]
    else:
        raise ValueError(f"Unsupported candidate file type: {path.name} (use .xlsx or .csv)")
    return [row for row in rows if any(value not in (None, "") for value in row.values())]


def finite_float(value: Any) -> float:
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("non-finite")
    return number


def condition_key(system: str, temperature: float, concentration: float) -> tuple[str, float, float]:
    return (system, float(temperature), float(concentration))


def is_near_duplicate(
    system: str, temperature: float, concentration: float,
    baseline: list[tuple[str, float, float]],
) -> tuple[bool, float | None, float | None]:
    best_dt: float | None = None
    best_dc: float | None = None
    for base_system, base_t, base_c in baseline:
        if base_system != system:
            continue
        dt = abs(temperature - base_t)
        if dt > T_TOLERANCE_K:
            continue
        dc = abs(concentration - base_c)
        if dc <= max(C_ABS_TOLERANCE, C_REL_TOLERANCE * max(concentration, base_c)):
            return True, dt, dc
        if best_dt is None or dt < best_dt:
            best_dt, best_dc = dt, dc
    return False, best_dt, best_dc


def load_baselines(workbooks_dir: Path, gold_642_path: Path) -> dict[str, Any]:
    workbook_conditions: list[tuple[str, float, float]] = []
    lineage_set: set[str] = set()
    source_assets: list[dict[str, Any]] = []
    for path in sorted(workbooks_dir.glob("*.xlsx")):
        rows = load_workbook_rows(path, "Confirmed_Records")
        for row in rows:
            system = str(row.get("system") or "").strip()
            if system not in SYSTEMS:
                continue
            try:
                temperature = finite_float(row.get("temperature_K"))
                concentration = finite_float(row.get("concentration_mol_L"))
            except (TypeError, ValueError):
                continue
            workbook_conditions.append(condition_key(system, temperature, concentration))
            lineage = str(row.get("model_group_id") or "").strip()
            if lineage:
                lineage_set.add(lineage)
        source_assets.append(
            {
                "filename": path.name,
                "path": str(path),
                "sha256": sha256_file(path),
                "sheet": "Confirmed_Records",
                "record_count": len(rows),
            }
        )
    workbook_unique = sorted(
        {(system, t, c) for (system, t, c) in workbook_conditions},
        key=lambda item: (SYSTEM_ORDER[item[0]], item[1], item[2]),
    )
    reference_norm_map: dict[str, str] = {}
    reference_profiles: list[tuple[set[str], set[str]]] = []
    question_conditions: list[tuple[str, float, float]] = []
    gold_642_sha256 = sha256_file(gold_642_path)
    with gold_642_path.open("r", encoding="utf-8-sig") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            gold = json.loads(line)
            system = str(gold.get("system") or "").strip()
            if system in SYSTEMS:
                question_conditions.append(
                    condition_key(
                        system,
                        float(gold["temperature_K"]),
                        float(gold["concentration_mol_L"]),
                    )
                )
            for source in gold.get("source_records", []):
                citation = str(source.get("original_reference") or "").strip()
                if not citation:
                    continue
                normalized = norm_text(citation)
                if normalized:
                    reference_norm_map[normalized] = citation
                reference_profiles.append(reference_profile(citation))
    # 近重复基线 = 642 题主集条件（方案 §3.C.4 / v2.12；执行件 2026-08-18 修正）。
    # 工作簿 696 唯一条件仅作参考留档，不参与硬排除。
    question_unique = sorted(
        set(question_conditions),
        key=lambda item: (SYSTEM_ORDER[item[0]], item[1], item[2]),
    )
    return {
        "conditions": question_unique,
        "lineage_set": lineage_set,
        "reference_norm_map": reference_norm_map,
        "reference_profiles": reference_profiles,
        "source_assets": source_assets,
        "gold_642_path": str(gold_642_path),
        "gold_642_sha256": gold_642_sha256,
        "question_set_condition_count": len(question_unique),
        "workbook_unique_condition_count": len(workbook_unique),
        "workbook_lineage_count": len(lineage_set),
    }


def validate_candidate(
    row: dict[str, Any], baselines: dict[str, Any]
) -> dict[str, Any]:
    """逐条判定候选记录；返回判定记录（不含 gold 数值）。"""
    required = [
        "system", "temperature_K", "concentration_mol_L",
        "diffusion_1e9_m2_s", "origin_lineage_id", "original_reference", "source_type",
    ]
    missing = [name for name in required if str(row.get(name) or "").strip() == ""]
    result: dict[str, Any] = {
        "system": str(row.get("system") or "").strip(),
        "temperature_K": str(row.get("temperature_K") or "").strip(),
        "concentration_mol_L": str(row.get("concentration_mol_L") or "").strip(),
        "origin_lineage_id": str(row.get("origin_lineage_id") or "").strip(),
        "source_type": str(row.get("source_type") or "").strip(),
        "disposition": None,
        "reason": None,
    }
    if missing:
        result["disposition"] = "excluded::invalid_schema"
        result["reason"] = f"missing_columns={','.join(missing)}"
        return result

    system = result["system"]
    if system not in SYSTEMS:
        result["disposition"] = "excluded::unknown_system"
        result["reason"] = f"system={system!r} not in {SYSTEMS}"
        return result

    try:
        temperature = finite_float(row["temperature_K"])
        concentration = finite_float(row["concentration_mol_L"])
        diffusion = finite_float(row["diffusion_1e9_m2_s"])
    except (TypeError, ValueError) as exc:
        result["disposition"] = "excluded::invalid_numeric"
        result["reason"] = f"numeric_error={exc}"
        return result

    if concentration <= 0:
        result["disposition"] = "excluded::nonpositive_concentration"
        result["reason"] = "c<=0"
        return result
    if diffusion <= 0:
        result["disposition"] = "excluded::nonpositive_diffusion"
        result["reason"] = "D<=0"
        return result
    if not (T_MIN_K <= temperature <= T_MAX_K):
        result["disposition"] = "excluded::implausible_temperature"
        result["reason"] = f"T={temperature} outside [{T_MIN_K}, {T_MAX_K}] K"
        return result
    if concentration > C_MAX_MOL_L:
        result["disposition"] = "excluded::implausible_concentration"
        result["reason"] = f"c={concentration} > {C_MAX_MOL_L} mol/L"
        return result

    lineage = result["origin_lineage_id"]
    if not LINEAGE_PATTERN.match(lineage):
        result["disposition"] = "excluded::lineage_id_format"
        result["reason"] = "lineage must match EXP:<SYS>:<NAME>_<YEAR> style"
        return result
    if lineage in baselines["lineage_set"]:
        result["disposition"] = "excluded::lineage_overlaps_workbook_pool"
        result["reason"] = "lineage already in the 45 workbook lineages"
        return result

    source_type = result["source_type"].lower()
    if source_type != "experimental":
        result["disposition"] = "excluded::non_experimental_source"
        result["reason"] = f"source_type={result['source_type']!r}"
        return result

    citation = str(row.get("original_reference") or "").strip()
    normalized = norm_text(citation)
    if normalized in baselines["reference_norm_map"]:
        result["disposition"] = "excluded::reference_overlaps_642_pool"
        result["reason"] = "citation matches: " + baselines["reference_norm_map"][normalized][:160]
        return result

    is_dup, nearest_dt, nearest_dc = is_near_duplicate(
        system, temperature, concentration, baselines["conditions"]
    )
    if is_dup:
        result["disposition"] = "excluded::near_duplicate_condition"
        result["reason"] = (
            f"nearest baseline condition within dT={nearest_dt:.4f} K, dc={nearest_dc:.6f} mol/L"
        )
        return result
    if nearest_dt is not None:
        result["nearest_baseline_dT"] = round(float(nearest_dt), 4)
        result["nearest_baseline_dc"] = round(float(nearest_dc), 6)

    warnings: list[str] = []
    tokens, years = reference_profile(citation)
    for base_tokens, base_years in baselines["reference_profiles"]:
        if tokens & base_tokens and years & base_years:
            warnings.append(
                "author-year collision with a 642-pool citation ("
                + " & ".join(sorted(tokens & base_tokens)) + " "
                + ", ".join(sorted(years & base_years)) + ")"
            )
            break
    if warnings:
        result["disposition"] = "included"
        result["warning"] = " | ".join(warnings)
    else:
        result["disposition"] = "included"

    result["_system"] = system
    result["_temperature"] = temperature
    result["_concentration"] = concentration
    result["_diffusion"] = diffusion
    result["_citation"] = citation
    result["_record_id"] = str(row.get("record_id") or "").strip()
    return result


def aggregate_included(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """按 (system, T, c) 聚合；跨谱系冲突排除；返回 (conditions, conflict_logs)。"""
    grouped: dict[tuple[str, float, float], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        grouped[condition_key(record["_system"], record["_temperature"], record["_concentration"])].append(record)
    conditions: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for (system, temperature, concentration), group in sorted(
        grouped.items(), key=lambda item: (SYSTEM_ORDER[item[0][0]], item[0][1], item[0][2])
    ):
        lineages = sorted({record["origin_lineage_id"] for record in group})
        values = sorted(float(record["_diffusion"]) for record in group)
        if len(lineages) > 1:
            for record in group:
                conflicts.append(
                    {
                        "system": system, "temperature_K": temperature,
                        "concentration_mol_L": concentration,
                        "origin_lineage_id": record["origin_lineage_id"],
                        "disposition": "excluded::within_pool_multilineage_conflict",
                        "reason": "same condition reported by multiple new lineages",
                    }
                )
            continue
        consensus = float(statistics.median(values))
        conditions.append(
            {
                "condition_id": stable_hash(
                    {"system": system, "temperature_K": temperature, "concentration_mol_L": concentration},
                    20,
                ),
                "system": system,
                "temperature_K": temperature,
                "concentration_mol_L": concentration,
                "diffusion_1e9_m2_s": consensus,
                "reference_value_policy": "median_across_same_condition_records",
                "reference_value_count": len(values),
                "reference_value_min_1e9_m2_s": min(values),
                "reference_value_max_1e9_m2_s": max(values),
                "reference_value_relative_range": (
                    (max(values) - min(values)) / abs(consensus) if consensus else None
                ),
                "origin_lineage_id": lineages[0],
                "origin_lineage_ids": lineages,
                "source_records": [
                    {
                        "record_id": record["_record_id"],
                        "origin_lineage_id": record["origin_lineage_id"],
                        "original_reference": record["_citation"],
                        "system": system,
                        "temperature_K": temperature,
                        "concentration_mol_L": concentration,
                    }
                    for record in group
                ],
                "warning": " | ".join(
                    sorted({record.get("warning") for record in group if record.get("warning")})
                ),
            }
        )
    return conditions, conflicts


def build_question_and_gold(condition: dict[str, Any], order: int) -> tuple[dict[str, Any], dict[str, Any]]:
    system = str(condition["system"])
    question_id = f"{QUESTION_ID_PREFIX}::{safe_slug(system).lower()}::{condition['condition_id']}"
    question: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "question_id": question_id,
        "question_order": order,
        "base_prompt_id": question_id,
        "template_family_id": TEMPLATE_FAMILY_ID,
        "knowledge_condition": "direct_closed_book",
        "language": "en",
        "task_type": "direct_internalized_knowledge_numeric",
        "route": "model_prediction",
        "system": system,
        "temperature_K": condition["temperature_K"],
        "concentration_mol_L": condition["concentration_mol_L"],
        "target_property": "binary_aqueous_mutual_diffusion_coefficient",
        "target_unit": TARGET_UNIT,
        "prompt": template_text(
            "en", system, float(condition["temperature_K"]), float(condition["concentration_mol_L"])
        ),
        "scoring": {
            "relative_error_thresholds": [0.05, 0.10],
            "parse_or_unit_failure_counts_as_incorrect": True,
            "missing_or_refusal_counts_as_incorrect": True,
        },
        "evidence_level": EVIDENCE_LEVEL,
    }
    question["question_sha256"] = stable_hash(question)

    gold: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "question_id": question_id,
        "base_prompt_id": question_id,
        "condition_id": condition["condition_id"],
        "diffusion_1e9_m2_s": condition["diffusion_1e9_m2_s"],
        "target_unit": TARGET_UNIT,
        "origin_lineage_id": condition["origin_lineage_id"],
        "origin_lineage_ids": condition["origin_lineage_ids"],
        "split_role": SPLIT_ROLE,
        "system": system,
        "temperature_K": condition["temperature_K"],
        "concentration_mol_L": condition["concentration_mol_L"],
        "reference_value_policy": condition["reference_value_policy"],
        "reference_value_count": condition["reference_value_count"],
        "reference_value_min_1e9_m2_s": condition["reference_value_min_1e9_m2_s"],
        "reference_value_max_1e9_m2_s": condition["reference_value_max_1e9_m2_s"],
        "reference_value_relative_range": condition["reference_value_relative_range"],
        "source_records": condition["source_records"],
        "evidence_level": EVIDENCE_LEVEL,
    }
    gold["gold_record_sha256"] = stable_hash(gold)
    return question, gold


def jsonl_sha256(records: list[dict[str, Any]]) -> str:
    lines = [canonical_json_bytes(record) for record in records]
    payload = b"\n".join(lines) + (b"\n" if lines else b"")
    return sha256_bytes(payload)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonical_json_bytes(record) for record in records]
    path.write_bytes(b"\n".join(lines) + (b"\n" if lines else b""))
    return sha256_file(path)


def audit_log_rows(
    judged: list[dict[str, Any]], conflicts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in judged:
        rows.append(
            {
                "system": record.get("system", ""),
                "temperature_K": record.get("temperature_K", ""),
                "concentration_mol_L": record.get("concentration_mol_L", ""),
                "origin_lineage_id": record.get("origin_lineage_id", ""),
                "source_type": record.get("source_type", ""),
                "disposition": record.get("disposition", ""),
                "reason": record.get("reason", ""),
                "warning": record.get("warning", ""),
                "nearest_baseline_dT": record.get("nearest_baseline_dT", ""),
                "nearest_baseline_dc": record.get("nearest_baseline_dc", ""),
            }
        )
    for conflict in conflicts:
        rows.append(
            {
                "system": conflict["system"],
                "temperature_K": conflict["temperature_K"],
                "concentration_mol_L": conflict["concentration_mol_L"],
                "origin_lineage_id": conflict["origin_lineage_id"],
                "source_type": "",
                "disposition": conflict["disposition"],
                "reason": conflict["reason"],
                "warning": "",
                "nearest_baseline_dT": "",
                "nearest_baseline_dc": "",
            }
        )
    return rows


def collect_candidates(path: Path, sheet: str) -> list[Path]:
    if path.is_dir():
        files = sorted(
            [p for p in path.iterdir() if p.suffix.lower() in (".xlsx", ".csv")]
        )
        if not files:
            raise ValueError(f"No .xlsx/.csv candidates found under {path}")
        return files
    if path.is_file():
        return [path]
    raise ValueError(f"candidates path not found: {path}")


def print_summary(
    judged: list[dict[str, Any]], conflicts: list[dict[str, Any]],
    conditions: list[dict[str, Any]] | None, header: str,
) -> None:
    print("=" * 72)
    print(header)
    print("=" * 72)
    dispositions = Counter(
        [record["disposition"] for record in judged]
        + [conflict["disposition"] for conflict in conflicts]
    )
    print("candidate record count:", len(judged))
    for disposition, count in sorted(dispositions.items()):
        print(f"  {count:5d}  {disposition}")
    if conditions is not None:
        by_system = Counter(str(condition["system"]) for condition in conditions)
        print("eligible unique conditions after audit:")
        for system in SYSTEMS:
            count = by_system.get(system, 0)
            status = "OK" if count >= MIN_PER_SYSTEM else "BELOW MIN"
            print(f"  {system:10s} {count:5d}  (min {MIN_PER_SYSTEM}, target {TARGET_PER_SYSTEM})  {status}")
        total = len(conditions)
        print(f"  {'TOTAL':10s} {total:5d}  (min {MIN_TOTAL}, target {TARGET_TOTAL})  "
              + ("OK" if total >= MIN_TOTAL else "BELOW MIN"))
    print()


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, default=DEFAULT_CANDIDATES_DIR)
    parser.add_argument("--sheet", default="Confirmed_Records")
    parser.add_argument("--workbooks-dir", type=Path, default=DEFAULT_WORKBOOKS_DIR)
    parser.add_argument("--gold-642", type=Path, default=DEFAULT_GOLD_642)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--precheck",
        action="store_true",
        help="Only audit and report; do not write any frozen artifacts.",
    )
    args = parser.parse_args()

    if not args.gold_642.is_file():
        raise FileNotFoundError(f"642 gold not found: {args.gold_642}")
    baselines = load_baselines(args.workbooks_dir, args.gold_642)
    print("baseline: 642-question conditions =", baselines["question_set_condition_count"])
    print("baseline: workbook lineages =", baselines["workbook_lineage_count"])
    print("baseline: workbook unique conditions (reference only) =", baselines["workbook_unique_condition_count"])
    print("baseline: 642 gold sha256 =", baselines["gold_642_sha256"])
    if SCOPE_DOC.is_file():
        print("scope doc sha256 =", sha256_file(SCOPE_DOC), f"({SCOPE_DOC.name})")
    print()

    judged: list[dict[str, Any]] = []
    candidate_assets: list[dict[str, Any]] = []
    for path in collect_candidates(args.candidates, args.sheet):
        rows = load_candidate_rows(path, args.sheet)
        candidate_assets.append(
            {
                "filename": path.name,
                "path": str(path),
                "sha256": sha256_file(path),
                "record_count": len(rows),
            }
        )
        for row in rows:
            judged.append(validate_candidate(row, baselines))
    print_summary(judged, [], None, f"AUDIT PRECHECK (candidates: {len(judged)} rows)")

    included = [record for record in judged if record["disposition"] == "included"]
    conditions, conflicts = aggregate_included(included)
    print_summary(judged, conflicts, conditions, "AUDIT SUMMARY (with within-pool conflicts)")

    if args.precheck:
        print("precheck finished; no frozen artifacts written.")
        return

    if len(conditions) == 0:
        print("no eligible conditions; nothing to freeze.")
        return

    out_dir = args.out_dir
    if any(out_dir.glob("*")):
        raise FileExistsError(
            f"output directory is not empty: {out_dir}\n"
            "freeze is one-shot; choose a fresh --out-dir (existing frozen artifacts are never overwritten)"
        )
    questions_path = out_dir / "questions" / "external_questions.jsonl"
    gold_path = out_dir / "gold" / "external_gold.evaluator.jsonl"
    manifest_path = out_dir / "manifest" / "external_manifest.json"
    audit_path = out_dir / "audit" / "external_audit_log.csv"
    seal_path = out_dir / "sealed" / "SEAL.md"

    questions: list[dict[str, Any]] = []
    gold_records: list[dict[str, Any]] = []
    for order, condition in enumerate(conditions, start=1):
        question, gold = build_question_and_gold(condition, order)
        questions.append(question)
        gold_records.append(gold)
    rendered_prompts = [str(record["prompt"]) for record in questions]
    if len(rendered_prompts) != len(set(rendered_prompts)):
        raise ValueError("different source conditions collapse to the same rendered prompt precision")

    question_set_sha256 = write_jsonl(questions_path, questions)
    gold_sha256 = write_jsonl(gold_path, gold_records)

    log_rows = audit_log_rows(judged, conflicts)
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_bytes(
        ("\ufeff" + "\r\n".join(
            [",".join(log_rows[0].keys())]
            + [",".join(str(row.get(key, "")) for key in log_rows[0]) for row in log_rows]
        ) + "\r\n"
        ).encode("utf-8")
    )
    audit_sha256 = sha256_file(audit_path)

    lineage_cluster_counts: dict[str, dict[str, int]] = {}
    system_counts: dict[str, int] = {}
    for condition in conditions:
        system_counts[str(condition["system"])] = system_counts.get(str(condition["system"]), 0) + 1
        lineage_cluster_counts.setdefault(str(condition["system"]), {})
        lineage_cluster_counts[str(condition["system"])][condition["origin_lineage_id"]] = (
            lineage_cluster_counts[str(condition["system"])].get(condition["origin_lineage_id"], 0) + 1
        )

    manifest: dict[str, Any] = {
        "artifact_type": "external_prospective_question_set_manifest",
        "schema_version": SCHEMA_VERSION,
        "research_plan_version": PLAN_VERSION,
        "created_at_utc": utc_now(),
        "evidence_level": EVIDENCE_LEVEL,
        "formal_confirmatory_use_allowed": False,
        "confirmatory_use_condition": (
            "plan_v2_10_section_17_all_conditions_met_at_evaluation_time"
        ),
        "sealed": True,
        "gold_present_in_question_set": False,
        "gold_sent_to_model": False,
        "gold_stored_separately": True,
        "language": "en",
        "template_family_id": TEMPLATE_FAMILY_ID,
        "question_count": len(questions),
        "selected_system_counts": system_counts,
        "selected_lineage_cluster_counts": lineage_cluster_counts,
        "question_set_path": str(questions_path),
        "question_set_sha256": question_set_sha256,
        "evaluator_gold_path": str(gold_path),
        "evaluator_gold_sha256": gold_sha256,
        "audit_log_path": str(audit_path),
        "audit_log_sha256": audit_sha256,
        "generator_path": str(Path(__file__)),
        "generator_sha256": sha256_file(Path(__file__)),
        "scope_document_path": str(SCOPE_DOC),
        "scope_document_sha256": sha256_file(SCOPE_DOC) if SCOPE_DOC.is_file() else None,
        "candidate_assets": candidate_assets,
        "baseline": {
            "near_duplicate_baseline": "642_primary_question_set",
            "question_set_condition_count": baselines["question_set_condition_count"],
            "workbook_unique_condition_count": baselines["workbook_unique_condition_count"],
            "workbook_unique_condition_role": "reference_only_not_exclusion",
            "workbook_lineage_count": baselines["workbook_lineage_count"],
            "gold_642_path": baselines["gold_642_path"],
            "gold_642_sha256": baselines["gold_642_sha256"],
            "near_duplicate_tolerances": {
                "temperature_K": T_TOLERANCE_K,
                "concentration_relative": C_REL_TOLERANCE,
                "concentration_absolute_mol_L": C_ABS_TOLERANCE,
            },
            "hard_bounds": {
                "temperature_K": [T_MIN_K, T_MAX_K],
                "concentration_mol_L_max": C_MAX_MOL_L,
            },
        },
        "audit": {
            "candidate_record_count": len(judged),
            "included_record_count": len(included),
            "excluded_record_count": len(judged) - len(included),
            "disposition_counts": dict(
                Counter(
                    [record["disposition"] for record in judged]
                    + [conflict["disposition"] for conflict in conflicts]
                )
            ),
        },
        "targets": {
            "min_per_system": MIN_PER_SYSTEM,
            "target_per_system": TARGET_PER_SYSTEM,
            "min_total": MIN_TOTAL,
            "target_total": TARGET_TOTAL,
        },
    }
    manifest_content_sha256 = sha256_bytes(canonical_json_bytes(manifest))
    manifest["manifest_content_sha256"] = manifest_content_sha256
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canonical_json_bytes(manifest))
    manifest_file_sha256 = sha256_file(manifest_path)

    seal_notice = (
        "# SEAL — external prospective test set is now FROZEN\n\n"
        "冻结时间（UTC）：" + manifest["created_at_utc"] + "\n\n"
        "**自此刻起至最终评估前（research_plan_simple.md v2.14 第 17 条；v2.13 时序口径：训练后、任何评估前冻结）：**\n\n"
        "1. 任何人（含用户与助手）不得查看 gold 文件内容；\n"
        "2. 任何模型不得在外部集上运行（含 A 臂 Base 五模型）；\n"
        "3. 不得根据外部集结果回改训练、提示、选模或超参；\n"
        "4. 违规 → 前瞻性作废，外部集只能按回顾性报告。\n\n"
        "## 哈希清单（核验用，无任何真值）\n\n"
        "| 产物 | SHA-256 |\n|---|---|\n"
        "| questions | " + question_set_sha256 + " |\n"
        "| gold | " + gold_sha256 + " |\n"
        "| manifest content | " + manifest_content_sha256 + " |\n"
        "| manifest file | " + manifest_file_sha256 + " |\n"
        "| audit log | " + audit_sha256 + " |\n"
        "| scope doc | " + str(manifest["scope_document_sha256"]) + " |\n"
        "| generator | " + manifest["generator_sha256"] + " |\n\n"
        "题数：" + str(len(questions)) + "；逐体系：" + json.dumps(system_counts, ensure_ascii=False) + "\n"
    )
    seal_path.parent.mkdir(parents=True, exist_ok=True)
    seal_path.write_text(seal_notice, encoding="utf-8")

    print("=" * 72)
    print("FROZEN. External prospective test set artifacts written (gold sealed).")
    print("=" * 72)
    print("questions:", questions_path)
    print("gold     :", gold_path)
    print("manifest :", manifest_path)
    print("audit    :", audit_path)
    print("seal     :", seal_path)
    print("question_set_sha256:", question_set_sha256)
    print("evaluator_gold_sha256:", gold_sha256)
    print("manifest_content_sha256:", manifest_content_sha256)
    print("manifest_file_sha256:", manifest_file_sha256)
    print()
    print(seal_notice)


if __name__ == "__main__":
    main()
