from __future__ import annotations

import argparse
import csv
import json
import math
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Callable, Iterable

from common import (
    SCHEMA_VERSION,
    TARGET_UNIT,
    atomic_write_csv,
    atomic_write_json,
    atomic_write_text,
    iter_jsonl,
    read_json,
    resolve_path,
    safe_slug,
    sha256_file,
    stable_hash,
    utc_now,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Score completed API runs and export manuscript-ready JSON/CSV tables."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config.json",
    )
    parser.add_argument("--run-dir", type=Path, action="append")
    parser.add_argument("--analysis-id")
    parser.add_argument("--bootstrap-replicates", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260810)
    parser.add_argument(
        "--allow-partial-question-set",
        action="store_true",
        help="Allow development runs created with run_benchmark.py --limit.",
    )
    return parser.parse_args()


def mean(values: Iterable[float]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.fmean(clean) if clean else None


def median(values: Iterable[float]) -> float | None:
    clean = [float(value) for value in values if value is not None and math.isfinite(float(value))]
    return statistics.median(clean) if clean else None


def percentile(values: Iterable[float], probability: float) -> float | None:
    clean = sorted(float(value) for value in values if value is not None and math.isfinite(float(value)))
    if not clean:
        return None
    if len(clean) == 1:
        return clean[0]
    position = (len(clean) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[lower]
    weight = position - lower
    return clean[lower] * (1 - weight) + clean[upper] * weight


def sample_score(sample: dict[str, Any], gold: dict[str, Any]) -> dict[str, Any]:
    quality = sample.get("response_quality") or {}
    prediction = quality.get("parsed_prediction_1e9_m2_s")
    valid_numeric = bool(quality.get("valid_numeric_response"))
    observed = float(gold["diffusion_1e9_m2_s"])
    numeric = (
        valid_numeric
        and isinstance(prediction, (int, float))
        and not isinstance(prediction, bool)
        and math.isfinite(float(prediction))
    )
    relative_error = abs(float(prediction) - observed) / abs(observed) if numeric and observed != 0 else None
    score = {
        "run_id": sample["run_id"],
        "task_id": sample["task_id"],
        "question_id": sample["question_id"],
        "base_prompt_id": sample["base_prompt_id"],
        "template_family_id": sample["template_family_id"],
        "sample_index": int(sample["sample_index"]),
        "model_key": sample["model_key"],
        "provider": sample.get("provider"),
        "requested_model_id": sample.get("requested_model_id"),
        "returned_model_id": (sample.get("response_metadata") or {}).get("returned_model_id"),
        "system_fingerprint": (sample.get("response_metadata") or {}).get("system_fingerprint"),
        "system": gold["system"],
        "temperature_K": float(gold["temperature_K"]),
        "concentration_mol_L": float(gold["concentration_mol_L"]),
        "origin_lineage_id": gold["origin_lineage_id"],
        "split_role": gold.get("split_role"),
        "evidence_level": gold.get("evidence_level"),
        "request_success": bool(sample.get("request_success")),
        "infrastructure_failure": bool(sample.get("infrastructure_failure")),
        "answer_schema_valid": bool(quality.get("answer_schema_valid")),
        "canonical_unit": quality.get("canonical_unit", TARGET_UNIT),
        "unit_source": quality.get("unit_source", "benchmark_fixed"),
        "unit_correct": bool(quality.get("unit_correct")),
        "valid_numeric_response": numeric,
        "observed_diffusion_1e9_m2_s": observed,
        "predicted_diffusion_1e9_m2_s": float(prediction) if numeric else None,
        "signed_error_1e9_m2_s": float(prediction) - observed if numeric else None,
        "absolute_error_1e9_m2_s": abs(float(prediction) - observed) if numeric else None,
        "relative_error": relative_error,
        "absolute_percentage_error": relative_error * 100.0 if relative_error is not None else None,
        "within_5pct": bool(relative_error is not None and relative_error <= 0.05),
        "within_10pct": bool(relative_error is not None and relative_error <= 0.10),
        "positive_prediction": bool(numeric and float(prediction) > 0),
        "attempt_count": int(sample.get("attempt_count", 0)),
        "latency_seconds_final_attempt": sample.get("latency_seconds_final_attempt"),
        "accepted_response_path": sample.get("accepted_response_path"),
        "accepted_response_sha256": sample.get("accepted_response_sha256"),
    }
    return score


def group_samples(samples: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in samples:
        grouped[str(sample["base_prompt_id"])].append(sample)
    return grouped


def prompt_rows(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for base_prompt_id, group in sorted(group_samples(samples).items()):
        first = group[0]
        numeric = [row for row in group if row["valid_numeric_response"]]
        output.append(
            {
                "run_id": first["run_id"],
                "model_key": first["model_key"],
                "provider": first["provider"],
                "requested_model_id": first["requested_model_id"],
                "base_prompt_id": base_prompt_id,
                "question_id": first["question_id"],
                "template_family_id": first["template_family_id"],
                "system": first["system"],
                "origin_lineage_id": first["origin_lineage_id"],
                "split_role": first["split_role"],
                "evidence_level": first["evidence_level"],
                "temperature_K": first["temperature_K"],
                "concentration_mol_L": first["concentration_mol_L"],
                "observed_diffusion_1e9_m2_s": first["observed_diffusion_1e9_m2_s"],
                "n_runs": len(group),
                "request_success_fraction": mean(float(row["request_success"]) for row in group),
                "valid_numeric_fraction": mean(float(row["valid_numeric_response"]) for row in group),
                "accuracy_5pct_fraction": mean(float(row["within_5pct"]) for row in group),
                "accuracy_10pct_fraction": mean(float(row["within_10pct"]) for row in group),
                "predicted_median_1e9_m2_s": median(
                    row["predicted_diffusion_1e9_m2_s"] for row in numeric
                ),
                "predicted_range_1e9_m2_s": (
                    max(row["predicted_diffusion_1e9_m2_s"] for row in numeric)
                    - min(row["predicted_diffusion_1e9_m2_s"] for row in numeric)
                    if numeric
                    else None
                ),
                "absolute_percentage_error_median": median(
                    row["absolute_percentage_error"] for row in numeric
                ),
                "infrastructure_failure_fraction": mean(
                    float(row["infrastructure_failure"]) for row in group
                ),
            }
        )
    return output


def metric_block(samples: list[dict[str, Any]]) -> dict[str, Any]:
    prompts = prompt_rows(samples)
    numeric = [row for row in samples if row["valid_numeric_response"]]
    if not samples:
        return {"n_base_prompts": 0, "n_sample_runs": 0}
    observed = [row["observed_diffusion_1e9_m2_s"] for row in numeric]
    predicted = [row["predicted_diffusion_1e9_m2_s"] for row in numeric]
    errors = [row["absolute_error_1e9_m2_s"] for row in numeric]
    squared = [(prediction - truth) ** 2 for prediction, truth in zip(predicted, observed)]
    aps = [row["absolute_percentage_error"] for row in numeric]
    bias = [row["signed_error_1e9_m2_s"] for row in numeric]
    observed_mean = mean(observed)
    total_sum_squares = (
        sum((value - float(observed_mean)) ** 2 for value in observed)
        if observed_mean is not None
        else 0.0
    )
    r_squared = (
        1.0 - sum(squared) / total_sum_squares
        if len(numeric) >= 2 and total_sum_squares > 0
        else None
    )
    lineage_apes: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in numeric:
        lineage_apes[(str(row["system"]), str(row["origin_lineage_id"]))].append(
            float(row["absolute_percentage_error"])
        )
    system_lineage_mdapes: dict[str, list[float]] = defaultdict(list)
    for (system, _lineage), values in lineage_apes.items():
        if values:
            system_lineage_mdapes[system].append(statistics.median(values))
    system_macro_mdapes = [
        statistics.fmean(values) for values in system_lineage_mdapes.values() if values
    ]
    system_prompt_accuracy_5: dict[str, list[float]] = defaultdict(list)
    system_prompt_accuracy_10: dict[str, list[float]] = defaultdict(list)
    for prompt in prompts:
        system = str(prompt["system"])
        system_prompt_accuracy_5[system].append(float(prompt["accuracy_5pct_fraction"]))
        system_prompt_accuracy_10[system].append(float(prompt["accuracy_10pct_fraction"]))
    macro_system_accuracy_5 = mean(
        statistics.fmean(values)
        for values in system_prompt_accuracy_5.values()
        if values
    )
    macro_system_accuracy_10 = mean(
        statistics.fmean(values)
        for values in system_prompt_accuracy_10.values()
        if values
    )
    return {
        "n_base_prompts": len(prompts),
        "n_sample_runs": len(samples),
        "n_valid_numeric_runs": len(numeric),
        "request_success_rate": mean(float(row["request_success"]) for row in samples),
        "infrastructure_failure_rate": mean(float(row["infrastructure_failure"]) for row in samples),
        "schema_valid_rate": mean(float(row["answer_schema_valid"]) for row in samples),
        "valid_numeric_coverage": mean(float(row["valid_numeric_response"]) for row in samples),
        "full_question_accuracy_5pct": mean(float(row["within_5pct"]) for row in samples),
        "full_question_accuracy_10pct": mean(float(row["within_10pct"]) for row in samples),
        "base_prompt_accuracy_5pct_mean": mean(row["accuracy_5pct_fraction"] for row in prompts),
        "base_prompt_accuracy_10pct_mean": mean(row["accuracy_10pct_fraction"] for row in prompts),
        "macro_system_accuracy_5pct": macro_system_accuracy_5,
        "macro_system_accuracy_10pct": macro_system_accuracy_10,
        "mae_valid_numeric_1e9_m2_s": mean(errors),
        "rmse_valid_numeric_1e9_m2_s": math.sqrt(mean(squared)) if squared else None,
        "r_squared_valid_numeric": r_squared,
        "bias_valid_numeric_1e9_m2_s": mean(bias),
        "mape_valid_numeric_percent": mean(aps),
        "mdape_valid_numeric_percent": median(aps),
        "macro_system_lineage_mdape_valid_numeric_percent": mean(system_macro_mdapes),
        "p95_ape_valid_numeric_percent": percentile(aps, 0.95),
        "max_ape_valid_numeric_percent": max(aps) if aps else None,
        "positive_rate_among_valid_numeric": mean(float(row["positive_prediction"]) for row in numeric),
        "mean_final_attempt_latency_seconds": mean(
            row["latency_seconds_final_attempt"] for row in samples
        ),
        "mean_attempt_count": mean(row["attempt_count"] for row in samples),
    }


def prompt_accuracy(prompt: dict[str, Any], threshold: str) -> float:
    return float(prompt[threshold])


def stratified_bootstrap(
    prompts: list[dict[str, Any]],
    statistic: Callable[[list[dict[str, Any]]], float | None],
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    strata: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for prompt in prompts:
        strata[str(prompt["system"])][str(prompt["origin_lineage_id"])].append(prompt)
    observed = statistic(prompts)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        sampled: list[dict[str, Any]] = []
        for lineages in strata.values():
            lineage_ids = sorted(lineages)
            for _ in range(len(lineage_ids)):
                selected_lineage = rng.choice(lineage_ids)
                sampled.extend(lineages[selected_lineage])
        value = statistic(sampled)
        if value is not None and math.isfinite(value):
            estimates.append(float(value))
    return {
        "estimate": observed,
        "ci95_low": percentile(estimates, 0.025),
        "ci95_high": percentile(estimates, 0.975),
        "bootstrap_replicates_requested": replicates,
        "bootstrap_replicates_valid": len(estimates),
        "bootstrap_seed": seed,
        "cluster_unit": "origin_lineage_id",
        "nested_unit": "base_prompt_id",
        "fixed_strata": ["system"],
    }


def macro_system_prompt_accuracy(
    prompts: list[dict[str, Any]], threshold: str
) -> float | None:
    by_system: dict[str, list[float]] = defaultdict(list)
    for prompt in prompts:
        by_system[str(prompt["system"])].append(float(prompt[threshold]))
    return mean(statistics.fmean(values) for values in by_system.values() if values)


def bootstrap_samples_by_lineage(
    samples: list[dict[str, Any]],
    statistic: Callable[[list[dict[str, Any]]], float | None],
    replicates: int,
    seed: int,
) -> dict[str, Any]:
    strata: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for sample in samples:
        strata[str(sample["system"])][str(sample["origin_lineage_id"])].append(sample)
    observed = statistic(samples)
    rng = random.Random(seed)
    estimates: list[float] = []
    for _ in range(replicates):
        sampled: list[dict[str, Any]] = []
        for lineages in strata.values():
            lineage_ids = sorted(lineages)
            for _ in range(len(lineage_ids)):
                sampled.extend(lineages[rng.choice(lineage_ids)])
        value = statistic(sampled)
        if value is not None and math.isfinite(value):
            estimates.append(float(value))
    return {
        "estimate": observed,
        "ci95_low": percentile(estimates, 0.025),
        "ci95_high": percentile(estimates, 0.975),
        "bootstrap_replicates_requested": replicates,
        "bootstrap_replicates_valid": len(estimates),
        "bootstrap_seed": seed,
        "cluster_unit": "origin_lineage_id",
        "nested_units": ["base_prompt_id", "sample_index"],
        "fixed_strata": ["system"],
    }


def mae_valid_numeric_statistic(rows: list[dict[str, Any]]) -> float | None:
    values = [
        float(row["absolute_error_1e9_m2_s"])
        for row in rows
        if row["valid_numeric_response"]
        and row["absolute_error_1e9_m2_s"] is not None
        and math.isfinite(float(row["absolute_error_1e9_m2_s"]))
    ]
    return statistics.fmean(values) if values else None


def macro_system_lineage_mdape_statistic(
    rows: list[dict[str, Any]],
) -> float | None:
    lineage_apes: dict[tuple[str, str], list[float]] = defaultdict(list)
    for row in rows:
        if not row["valid_numeric_response"]:
            continue
        ape = row["absolute_percentage_error"]
        if ape is not None and math.isfinite(float(ape)):
            lineage_apes[(str(row["system"]), str(row["origin_lineage_id"]))].append(
                float(ape)
            )
    if not lineage_apes:
        return None
    system_lineage_mdapes: dict[str, list[float]] = defaultdict(list)
    for (system, _lineage), values in lineage_apes.items():
        system_lineage_mdapes[system].append(statistics.median(values))
    system_means = [
        statistics.fmean(values) for values in system_lineage_mdapes.values() if values
    ]
    return statistics.fmean(system_means) if system_means else None


def discover_runs(
    output_root: Path,
    expected_question_sha256: str,
    expected_question_count: int,
) -> list[Path]:
    compatible: list[Path] = []
    for path in output_root.glob("*/runs/*/run_manifest.json"):
        manifest = read_json(path)
        question_set = manifest.get("question_set", {})
        if (
            manifest.get("status") == "completed"
            and question_set.get("sha256") == expected_question_sha256
            and int(question_set.get("count", -1)) == expected_question_count
        ):
            compatible.append(path.parent)
    return sorted(compatible)


def load_gold(path: Path) -> dict[str, dict[str, Any]]:
    result = {}
    for record in iter_jsonl(path):
        question_id = str(record["question_id"])
        if question_id in result:
            raise ValueError(f"Duplicate evaluator gold question_id: {question_id}")
        result[question_id] = record
    return result


def load_analysis_sets(
    path: Path,
    expected_question_ids: set[str],
    expected_questions: list[dict[str, Any]],
    expected_gold_path: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    payload = read_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("sets"), list):
        raise ValueError("analysis_sets_file must contain a JSON object with a 'sets' array")
    recorded_content_hash = payload.get("analysis_sets_content_sha256")
    if recorded_content_hash:
        unhashed = {
            key: value
            for key, value in payload.items()
            if key != "analysis_sets_content_sha256"
        }
        if recorded_content_hash != stable_hash(unhashed):
            raise ValueError("Analysis-set manifest content hash mismatch")
    if payload.get("response_reuse") is not True:
        raise ValueError("Analysis-set manifest must declare response_reuse=true")
    if int(payload.get("additional_api_calls_for_sensitivity_subset", -1)) != 0:
        raise ValueError("Sensitivity analysis must require zero additional API calls")
    recorded_primary_path = Path(str(payload["primary_question_file"]))
    if not recorded_primary_path.is_absolute():
        recorded_primary_path = (path.parent / recorded_primary_path).resolve()
    if payload.get("primary_question_file_sha256") != sha256_file(recorded_primary_path):
        raise ValueError("Primary question-file hash mismatch in analysis-set manifest")
    recorded_gold_path = Path(str(payload["evaluator_gold_file"]))
    if not recorded_gold_path.is_absolute():
        recorded_gold_path = (path.parent / recorded_gold_path).resolve()
    if recorded_gold_path.resolve() != expected_gold_path.resolve():
        raise ValueError("Analysis-set manifest points to a different evaluator gold file")
    if payload.get("evaluator_gold_file_sha256") != sha256_file(expected_gold_path):
        raise ValueError("Evaluator gold hash mismatch in analysis-set manifest")

    question_system = {
        str(record["question_id"]): str(record["system"])
        for record in expected_questions
    }
    seen_set_ids: set[str] = set()
    sets: list[dict[str, Any]] = []
    primary_ids: set[str] | None = None
    sensitivity_ids: set[str] | None = None
    for record in payload["sets"]:
        if not isinstance(record, dict):
            raise ValueError("Each analysis-set entry must be an object")
        set_id = str(record.get("analysis_set_id", "")).strip()
        role = str(record.get("role", "")).strip()
        raw_ids = record.get("question_ids")
        if not set_id or set_id in seen_set_ids or role not in {"primary", "sensitivity"}:
            raise ValueError("Analysis-set IDs must be unique and roles must be primary/sensitivity")
        if not isinstance(raw_ids, list):
            raise ValueError(f"Analysis set {set_id!r} is missing question_ids")
        ids = [str(value) for value in raw_ids]
        if len(ids) != len(set(ids)):
            raise ValueError(f"Analysis set {set_id!r} contains duplicate question IDs")
        if int(record.get("question_count", -1)) != len(ids):
            raise ValueError(f"Analysis set {set_id!r} count does not match its members")
        if record.get("question_ids_sha256") != stable_hash(sorted(ids)):
            raise ValueError(f"Analysis set {set_id!r} member hash mismatch")
        id_set = set(ids)
        if not id_set.issubset(expected_question_ids):
            raise ValueError(f"Analysis set {set_id!r} contains unknown question IDs")
        actual_counts = Counter(question_system[question_id] for question_id in ids)
        recorded_counts = {
            str(key): int(value)
            for key, value in dict(record.get("system_counts", {})).items()
        }
        if dict(sorted(actual_counts.items())) != dict(sorted(recorded_counts.items())):
            raise ValueError(f"Analysis set {set_id!r} system counts do not match members")
        normalized = {**record, "question_ids": ids}
        sets.append(normalized)
        seen_set_ids.add(set_id)
        if role == "primary":
            if primary_ids is not None:
                raise ValueError("Exactly one primary analysis set is required")
            primary_ids = id_set
        else:
            if sensitivity_ids is not None:
                raise ValueError("Exactly one sensitivity analysis set is required")
            sensitivity_ids = id_set
    if primary_ids != expected_question_ids:
        raise ValueError("Primary analysis set must equal the configured full question set")
    if sensitivity_ids is None or not sensitivity_ids < primary_ids:
        raise ValueError("Sensitivity analysis set must be a strict subset of the primary set")
    return sets, payload


SAMPLE_FIELDS = [
    "run_id", "task_id", "question_id", "base_prompt_id", "template_family_id",
    "sample_index", "model_key", "provider", "requested_model_id", "returned_model_id",
    "system_fingerprint", "system", "temperature_K", "concentration_mol_L",
    "origin_lineage_id", "split_role", "evidence_level", "request_success",
    "infrastructure_failure", "answer_schema_valid", "canonical_unit", "unit_source",
    "unit_correct",
    "valid_numeric_response", "observed_diffusion_1e9_m2_s",
    "predicted_diffusion_1e9_m2_s", "signed_error_1e9_m2_s",
    "absolute_error_1e9_m2_s", "relative_error", "absolute_percentage_error",
    "within_5pct", "within_10pct", "positive_prediction",
    "attempt_count", "latency_seconds_final_attempt", "accepted_response_path",
    "accepted_response_sha256",
]

PROMPT_FIELDS = [
    "run_id", "model_key", "provider", "requested_model_id", "base_prompt_id",
    "question_id", "template_family_id", "system", "origin_lineage_id", "split_role",
    "evidence_level", "temperature_K", "concentration_mol_L",
    "observed_diffusion_1e9_m2_s", "n_runs", "request_success_fraction",
    "valid_numeric_fraction", "accuracy_5pct_fraction", "accuracy_10pct_fraction",
    "predicted_median_1e9_m2_s", "predicted_range_1e9_m2_s",
    "absolute_percentage_error_median",
    "infrastructure_failure_fraction",
]


def main() -> int:
    args = parse_args()
    if args.bootstrap_replicates <= 0:
        raise ValueError("--bootstrap-replicates must be positive")
    config_path = args.config.resolve()
    config = read_json(config_path)
    base_dir = config_path.parent
    output_root = resolve_path(base_dir, config["output_root"])
    gold_path = resolve_path(base_dir, config["evaluator_gold_file"])
    gold = load_gold(gold_path)
    question_path = resolve_path(base_dir, config["question_file"])
    expected_questions = list(iter_jsonl(question_path))
    expected_question_ids = {str(record["question_id"]) for record in expected_questions}
    if len(expected_question_ids) != len(expected_questions):
        raise ValueError("Configured question file contains duplicate question IDs")
    if set(gold) != expected_question_ids:
        raise ValueError("Evaluator gold IDs must exactly match the configured question set")
    analysis_sets_path = resolve_path(base_dir, config["analysis_sets_file"])
    analysis_sets, analysis_sets_manifest = load_analysis_sets(
        analysis_sets_path, expected_question_ids, expected_questions, gold_path
    )
    question_sha256 = sha256_file(question_path)
    run_dirs = (
        [path.resolve() for path in args.run_dir]
        if args.run_dir
        else discover_runs(output_root, question_sha256, len(expected_questions))
    )
    if not run_dirs:
        raise ValueError("No completed run directories found")
    analysis_id = args.analysis_id or utc_now().replace(":", "").replace("-", "").split(".")[0] + "Z"
    analysis_dir = output_root / "_analysis" / safe_slug(analysis_id)
    analysis_dir.mkdir(parents=True, exist_ok=False)

    all_samples: list[dict[str, Any]] = []
    run_inventory = []
    for run_dir in run_dirs:
        manifest_path = run_dir / "run_manifest.json"
        results_path = run_dir / "sample_results.jsonl"
        manifest = read_json(manifest_path)
        if manifest.get("status") != "completed":
            raise ValueError(f"Run is not completed: {run_dir}")
        if manifest.get("protocol_pause_triggered"):
            raise ValueError(
                f"Run exceeds the 5% infrastructure-failure threshold and must be rerun "
                f"as a whole after remediation: {run_dir}"
            )
        if manifest["question_set"]["sha256"] != question_sha256:
            raise ValueError(f"Question set hash mismatch for run: {run_dir}")
        selected_count = int(manifest["question_set"].get("count", 0))
        if selected_count != len(expected_questions) and not args.allow_partial_question_set:
            raise ValueError(
                f"Partial development run ({selected_count}/{len(expected_questions)} questions): "
                f"{run_dir}. Pass --allow-partial-question-set only for pipeline testing."
            )
        samples = list(iter_jsonl(results_path))
        repetitions = int(manifest.get("repetitions_per_base_prompt", 0))
        scheduled_pairs = [
            (str(sample["question_id"]), int(sample["sample_index"])) for sample in samples
        ]
        if len(scheduled_pairs) != len(set(scheduled_pairs)):
            raise ValueError(f"Duplicate question/sample_index pair in run: {run_dir}")
        sample_indexes: dict[str, set[int]] = defaultdict(set)
        for question_id, sample_index in scheduled_pairs:
            sample_indexes[question_id].add(sample_index)
        expected_indexes = set(range(1, repetitions + 1))
        incomplete = sorted(
            question_id
            for question_id, indexes in sample_indexes.items()
            if indexes != expected_indexes
        )
        if incomplete:
            raise ValueError(
                f"Incomplete repetition indexes in run {run_dir}: {incomplete[:5]}"
            )
        sampled_question_ids = {str(sample["question_id"]) for sample in samples}
        if not sampled_question_ids.issubset(expected_question_ids):
            raise ValueError(f"Run contains questions outside the configured set: {run_dir}")
        expected_sample_count = selected_count * repetitions
        if len(samples) != expected_sample_count:
            raise ValueError(
                f"Run has {len(samples)} samples, expected {expected_sample_count}: {run_dir}"
            )
        if selected_count == len(expected_questions) and sampled_question_ids != expected_question_ids:
            missing_ids = sorted(expected_question_ids - sampled_question_ids)
            raise ValueError(f"Run is missing configured questions: {missing_ids[:5]}")
        for sample in samples:
            question_id = str(sample["question_id"])
            if question_id not in gold:
                raise ValueError(f"Evaluator gold missing question {question_id!r}")
            all_samples.append(sample_score(sample, gold[question_id]))
        run_inventory.append(
            {
                "run_dir": str(run_dir),
                "run_manifest_sha256": sha256_file(manifest_path),
                "sample_results_sha256": sha256_file(results_path),
                "run_id": manifest["run_id"],
                "model_key": manifest["model_key"],
                "provider": manifest.get("provider"),
                "requested_model_id": manifest["requested_model_id"],
                "returned_model_ids": manifest.get("returned_model_ids", []),
                "snapshot_confirmed": manifest.get("snapshot_confirmed", False),
                "evidence_level": manifest.get("evidence_level"),
                "repetitions": repetitions,
            }
        )

    by_run: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for sample in all_samples:
        by_run[str(sample["run_id"])].append(sample)
    sensitivity_ids = set(
        next(
            record["question_ids"]
            for record in analysis_sets
            if record["role"] == "sensitivity"
        )
    )
    for sample in all_samples:
        sample["in_sensitivity_balanced_240"] = sample["question_id"] in sensitivity_ids
    all_prompts = [row for samples in by_run.values() for row in prompt_rows(samples)]
    for prompt in all_prompts:
        prompt["in_sensitivity_balanced_240"] = prompt["question_id"] in sensitivity_ids
    sample_fields = [*SAMPLE_FIELDS, "in_sensitivity_balanced_240"]
    prompt_fields = [*PROMPT_FIELDS, "in_sensitivity_balanced_240"]
    atomic_write_csv(analysis_dir / "sample_level_results.csv", all_samples, sample_fields)
    atomic_write_csv(analysis_dir / "base_prompt_results.csv", all_prompts, prompt_fields)

    metrics = []
    summaries: dict[str, Any] = {}
    for run_id, run_samples, analysis_set in (
        (run_id, run_samples, analysis_set)
        for run_id, run_samples in sorted(by_run.items())
        for analysis_set in analysis_sets
    ):
        analysis_set_id = str(analysis_set["analysis_set_id"])
        member_ids = set(str(value) for value in analysis_set["question_ids"])
        samples = [
            sample for sample in run_samples if str(sample["question_id"]) in member_ids
        ]
        if len(samples) != len(member_ids) * int(
            next(
                inventory["repetitions"]
                for inventory in run_inventory
                if inventory["run_id"] == run_id
            )
        ):
            if args.allow_partial_question_set:
                print(
                    f"NOTE: skipping incomplete analysis set {analysis_set_id!r} "
                    f"for run {run_id!r} (partial-run mode)"
                )
                continue
            raise ValueError(
                f"Analysis set {analysis_set_id!r} is incomplete in run {run_id!r}"
            )
        overall = metric_block(samples)
        prompts = prompt_rows(samples)
        ci5 = stratified_bootstrap(
            prompts,
            lambda rows: mean(row["accuracy_5pct_fraction"] for row in rows),
            args.bootstrap_replicates,
            args.bootstrap_seed,
        )
        ci10 = stratified_bootstrap(
            prompts,
            lambda rows: mean(row["accuracy_10pct_fraction"] for row in rows),
            args.bootstrap_replicates,
            args.bootstrap_seed + 1,
        )
        ci_macro5 = stratified_bootstrap(
            prompts,
            lambda rows: macro_system_prompt_accuracy(rows, "accuracy_5pct_fraction"),
            args.bootstrap_replicates,
            args.bootstrap_seed + 4,
        )
        ci_macro10 = stratified_bootstrap(
            prompts,
            lambda rows: macro_system_prompt_accuracy(rows, "accuracy_10pct_fraction"),
            args.bootstrap_replicates,
            args.bootstrap_seed + 5,
        )
        ci_mae = bootstrap_samples_by_lineage(
            samples,
            mae_valid_numeric_statistic,
            args.bootstrap_replicates,
            args.bootstrap_seed + 2,
        )
        ci_macro_mdape = bootstrap_samples_by_lineage(
            samples,
            macro_system_lineage_mdape_statistic,
            args.bootstrap_replicates,
            args.bootstrap_seed + 3,
        )
        first = samples[0]
        summary = {
            "run_id": run_id,
            "analysis_set_id": analysis_set_id,
            "analysis_set_role": analysis_set["role"],
            "model_key": first["model_key"],
            "provider": first["provider"],
            "requested_model_id": first["requested_model_id"],
            "overall": overall,
            "confidence_intervals": {
                "base_prompt_accuracy_5pct_mean": ci5,
                "base_prompt_accuracy_10pct_mean": ci10,
                "macro_system_accuracy_5pct": ci_macro5,
                "macro_system_accuracy_10pct": ci_macro10,
                "mae_valid_numeric_1e9_m2_s": ci_mae,
                "macro_system_lineage_mdape_valid_numeric_percent": ci_macro_mdape,
            },
            "by_system": {},
            "by_lineage": {},
            "by_split_role": {},
        }
        for system in sorted(set(row["system"] for row in samples)):
            summary["by_system"][system] = metric_block(
                [row for row in samples if row["system"] == system]
            )
        for lineage in sorted(set(row["origin_lineage_id"] for row in samples)):
            summary["by_lineage"][lineage] = metric_block(
                [row for row in samples if row["origin_lineage_id"] == lineage]
            )
        for role in sorted(set(str(row["split_role"]) for row in samples)):
            summary["by_split_role"][role] = metric_block(
                [row for row in samples if str(row["split_role"]) == role]
            )
        summaries[f"{run_id}::{analysis_set_id}"] = summary
        metrics.append(
            {
                "run_id": run_id,
                "analysis_set_id": analysis_set_id,
                "analysis_set_role": analysis_set["role"],
                "model_key": first["model_key"],
                "provider": first["provider"],
                "requested_model_id": first["requested_model_id"],
                **overall,
                "accuracy_5pct_ci95_low": ci5["ci95_low"],
                "accuracy_5pct_ci95_high": ci5["ci95_high"],
                "accuracy_10pct_ci95_low": ci10["ci95_low"],
                "accuracy_10pct_ci95_high": ci10["ci95_high"],
                "macro_system_accuracy_5pct_ci95_low": ci_macro5["ci95_low"],
                "macro_system_accuracy_5pct_ci95_high": ci_macro5["ci95_high"],
                "macro_system_accuracy_10pct_ci95_low": ci_macro10["ci95_low"],
                "macro_system_accuracy_10pct_ci95_high": ci_macro10["ci95_high"],
                "mae_valid_ci95_low": ci_mae["ci95_low"],
                "mae_valid_ci95_high": ci_mae["ci95_high"],
                "macro_lineage_mdape_valid_ci95_low": ci_macro_mdape["ci95_low"],
                "macro_lineage_mdape_valid_ci95_high": ci_macro_mdape["ci95_high"],
            }
        )

    metric_fields = list(dict.fromkeys(key for row in metrics for key in row))
    atomic_write_csv(analysis_dir / "manuscript_model_metrics.csv", metrics, metric_fields)
    summary = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "llm_api_direct_analysis",
        "analysis_id": analysis_id,
        "created_at_utc": utc_now(),
        "evaluator_gold": {"path": str(gold_path), "sha256": sha256_file(gold_path)},
        "analysis_sets": {
            "path": str(analysis_sets_path),
            "sha256": sha256_file(analysis_sets_path),
            "response_reuse": True,
            "additional_api_calls_for_sensitivity_subset": 0,
            "sets": [
                {
                    "analysis_set_id": record["analysis_set_id"],
                    "role": record["role"],
                    "question_count": record["question_count"],
                    "question_ids_sha256": record["question_ids_sha256"],
                    "system_counts": record["system_counts"],
                }
                for record in analysis_sets
            ],
            "manifest_content_sha256": analysis_sets_manifest.get(
                "analysis_sets_content_sha256"
            ),
        },
        "run_inventory": run_inventory,
        "analysis_settings": {
            "bootstrap_replicates": args.bootstrap_replicates,
            "bootstrap_seed": args.bootstrap_seed,
            "independent_sample_unit": "base_prompt_id",
            "repeated_samples_nested_within_prompt": True,
            "cluster_unit": "origin_lineage_id",
            "fixed_strata": ["system"],
            "partial_question_sets_allowed": bool(args.allow_partial_question_set),
            "valid_subset_metrics_never_replace_full_question_accuracy": True,
            "report_micro_and_fixed_system_macro_accuracy": True,
        },
        "summaries": summaries,
        "limitations": [
            "The full 642-question set and balanced 240-question sensitivity subset use an opened retrospective data pool and are exploratory.",
            "Repeated calls for one base prompt are not independent observations.",
            "Unconfirmed provider aliases cannot support snapshot-specific claims.",
            "MAE/RMSE/MAPE/MdAPE use valid numeric responses only and must be reported with coverage; full-question accuracy counts parse, unit, refusal, empty, non-finite, and missing-number outcomes as incorrect.",
        ],
    }
    summary["analysis_content_sha256"] = stable_hash(summary)
    atomic_write_json(analysis_dir / "analysis_summary.json", summary)

    lines = [
        "# API LLM direct-answer benchmark",
        "",
        "This report is generated from immutable raw-response hashes and evaluator-side gold joins.",
        "The bundled question set is an exploratory pilot because the historical holdout was already opened.",
        "",
        "| Model key | Analysis set | N prompts | Numeric coverage | Micro Accuracy@10% | Macro-system Accuracy@10% | MAE (valid) | MdAPE (valid) |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for row in metrics:
        def pct(value: Any) -> str:
            return "NA" if value is None else f"{100 * float(value):.1f}%"

        def num(value: Any) -> str:
            return "NA" if value is None else f"{float(value):.4f}"

        lines.append(
            f"| {row['model_key']} | {row['analysis_set_id']} | {row['n_base_prompts']} | "
            f"{pct(row['valid_numeric_coverage'])} | "
            f"{pct(row['base_prompt_accuracy_10pct_mean'])} | "
            f"{pct(row['macro_system_accuracy_10pct'])} | "
            f"{num(row['mae_valid_numeric_1e9_m2_s'])} | "
            f"{num(row['mdape_valid_numeric_percent'])}% |"
        )
    lines.extend(
        [
            "",
            "Accuracy denominators include every scheduled sample. Valid-only error metrics must always be presented with numeric coverage.",
            "Confidence intervals fix solution systems and resample origin lineages as clusters; repeated API calls remain nested within each base prompt.",
            "The balanced 240-question sensitivity view reuses the exact responses from the 642-question primary run and adds zero API calls.",
            "",
        ]
    )
    atomic_write_text(analysis_dir / "manuscript_summary.md", "\n".join(lines))
    inventory = []
    for path in sorted(analysis_dir.iterdir()):
        if path.is_file():
            inventory.append(
                {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            )
    atomic_write_json(analysis_dir / "analysis_inventory.json", inventory)
    print(json.dumps({"analysis_dir": str(analysis_dir), "runs": len(run_dirs)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
