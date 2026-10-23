from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
API_BENCHMARK_ROOT = ROOT.parent.parent / "LLM_API_direct"
if str(API_BENCHMARK_ROOT) not in sys.path:
    sys.path.insert(0, str(API_BENCHMARK_ROOT))

from prepare_questions import (  # noqa: E402
    EXPECTED_WORKBOOKS,
    aggregate_conditions,
    lineage_is_derived,
    read_workbook,
)

from ml_common import (  # noqa: E402
    atomic_write_json,
    atomic_write_jsonl,
    iter_jsonl,
    resolve_path,
    sha256_file,
    stable_hash,
    utc_now,
)

SYSTEM_ORDER = list(EXPECTED_WORKBOOKS)


def condition_sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        SYSTEM_ORDER.index(str(row["system"])),
        str(row["origin_lineage_id"]),
        float(row["temperature_K"]),
        float(row["concentration_mol_L"]),
        str(row["condition_id"]),
    )


def build_dataset(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    base_dir = config_path.parent
    input_dir = resolve_path(base_dir, config["input_dir"])
    sheet_name = str(config.get("sheet_name", "Confirmed_Records"))
    output_root = resolve_path(base_dir, config["output_root"])
    dataset_path = output_root / str(config["dataset_file"])
    manifest_path = output_root / str(config["dataset_manifest_file"])
    gold_path = resolve_path(base_dir, config["evaluator_gold_file"])

    all_records: list[dict[str, Any]] = []
    source_assets: list[dict[str, Any]] = []
    for expected_system, filename in EXPECTED_WORKBOOKS.items():
        path = input_dir / filename
        if not path.is_file():
            raise FileNotFoundError(f"Required four-system workbook not found: {path}")
        records = read_workbook(path, sheet_name, expected_system)
        all_records.extend(records)
        source_assets.append(
            {
                "path": str(path),
                "filename": filename,
                "sha256": sha256_file(path),
                "sheet": sheet_name,
                "record_count": len(records),
                "system": expected_system,
                "lineage_count": len({row["origin_lineage_id"] for row in records}),
            }
        )

    all_conditions = aggregate_conditions(all_records)
    eligible = [
        condition
        for condition in all_conditions
        if len(condition["origin_lineage_ids"]) == 1
        and float(condition["concentration_mol_L"]) > 0
        and not any(
            lineage_is_derived(lineage) for lineage in condition["origin_lineage_ids"]
        )
    ]

    gold = {str(record["condition_id"]): record for record in iter_jsonl(gold_path)}
    eligible_ids = {str(condition["condition_id"]) for condition in eligible}
    gold_ids = set(gold)
    if eligible_ids != gold_ids:
        missing = sorted(gold_ids - eligible_ids)[:5]
        extra = sorted(eligible_ids - gold_ids)[:5]
        raise ValueError(
            "Eligible ML conditions do not match the frozen 642-question evaluator "
            f"gold set. missing_in_gold={missing} extra_vs_gold={extra}"
        )

    rows: list[dict[str, Any]] = []
    for condition in sorted(eligible, key=condition_sort_key):
        rows.append(
            {
                "schema_version": "ml_backend_d/v1",
                "condition_id": str(condition["condition_id"]),
                "system": str(condition["system"]),
                "temperature_K": float(condition["temperature_K"]),
                "concentration_mol_L": float(condition["concentration_mol_L"]),
                "diffusion_1e9_m2_s": float(condition["diffusion_1e9_m2_s"]),
                "target_unit": config["target_unit"],
                "origin_lineage_id": str(condition["origin_lineage_id"]),
                "origin_lineage_ids": list(condition["origin_lineage_ids"]),
                "reference_value_policy": condition["reference_value_policy"],
                "reference_value_count": int(condition["reference_value_count"]),
                "source_record_ids": [
                    str(source["source_record_id"])
                    for source in condition["source_records"]
                ],
                "evidence_level": "retrospective_opened_four_system_lineage_pool",
            }
        )

    atomic_write_jsonl(dataset_path, rows)
    by_system: dict[str, int] = {}
    by_system_lineage: dict[str, dict[str, int]] = {}
    for row in rows:
        by_system[row["system"]] = by_system.get(row["system"], 0) + 1
        by_system_lineage.setdefault(row["system"], {})
        lineage_counts = by_system_lineage[row["system"]]
        lineage_counts[row["origin_lineage_id"]] = (
            lineage_counts.get(row["origin_lineage_id"], 0) + 1
        )

    excluded = {
        "multi_lineage": sum(
            len(condition["origin_lineage_ids"]) > 1 for condition in all_conditions
        ),
        "zero_concentration": sum(
            float(condition["concentration_mol_L"]) == 0 for condition in all_conditions
        ),
        "derived_lineage": sum(
            any(
                lineage_is_derived(lineage)
                for lineage in condition["origin_lineage_ids"]
            )
            for condition in all_conditions
        ),
    }

    manifest: dict[str, Any] = {
        "schema_version": "ml_backend_d/v1",
        "artifact_type": "ml_backend_d_dataset_manifest",
        "created_at_utc": utc_now(),
        "research_plan_version": str(config.get("research_plan_version", "2.2")),
        "dataset_path": str(dataset_path),
        "dataset_sha256": sha256_file(dataset_path),
        "source_assets": source_assets,
        "source_record_count": len(all_records),
        "unique_condition_count": len(all_conditions),
        "eligible_condition_count": len(rows),
        "filter_log": excluded,
        "system_counts": dict(sorted(by_system.items())),
        "system_lineage_counts": {
            system: dict(sorted(counts.items()))
            for system, counts in sorted(by_system_lineage.items())
        },
        "same_condition_consensus_policy": "median_across_same_condition_records",
        "evaluator_gold": {
            "path": str(gold_path),
            "sha256": sha256_file(gold_path),
            "condition_count": len(gold),
            "match": "exact",
        },
        "warning": (
            "The four lineage workbooks and their reference values are already "
            "available in the project; this dataset is retrospective/exploratory, "
            "not a sealed blind or prospective external evaluation."
        ),
    }
    manifest["manifest_content_sha256"] = stable_hash(manifest)
    atomic_write_json(manifest_path, manifest)
    output_root.mkdir(parents=True, exist_ok=True)
    return manifest
