from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path
from typing import Any

from slm_common import (
    API_BENCHMARK_ROOT,
    ROOT,
    iter_run_manifests,
    load_config,
    read_json,
    resolve_path,
    safe_slug,
    sha256_file,
    utc_now,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze completed SLM_direct runs with the shared paper scorer."
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--run-dir", type=Path, action="append")
    parser.add_argument("--analysis-id")
    parser.add_argument("--bootstrap-replicates", type=int, default=10000)
    parser.add_argument("--bootstrap-seed", type=int, default=20260810)
    parser.add_argument(
        "--allow-partial-question-set",
        action="store_true",
        help="Development/fold diagnostics only; not an OOF SFT paper analysis.",
    )
    return parser.parse_args()


def validate_runs(
    config_path: Path,
    config: dict[str, Any],
    requested: list[Path] | None,
    *,
    allow_partial: bool,
) -> list[Path]:
    output_root = resolve_path(config_path.parent, config["output_root"])
    if requested:
        run_dirs = [path.resolve() for path in requested]
    else:
        run_dirs = [
            run_dir
            for run_dir, manifest in iter_run_manifests(output_root)
            if manifest.get("status") == "completed"
            and manifest.get("run_mode") == "formal"
        ]
    if not run_dirs:
        raise ValueError("没有可分析的 completed formal SLM_direct run")
    by_model: dict[str, list[Path]] = defaultdict(list)
    for run_dir in run_dirs:
        try:
            run_dir.relative_to(output_root)
        except ValueError as exc:
            raise ValueError(f"run 不在 protocol_v2_2 输出根目录内：{run_dir}") from exc
        manifest_path = run_dir / "run_manifest.json"
        manifest = read_json(manifest_path)
        if manifest.get("artifact_type") != "slm_direct_run_manifest":
            raise ValueError(f"不是 SLM_direct v2.2 run：{run_dir}")
        if manifest.get("status") != "completed":
            raise ValueError(f"run 尚未完成：{run_dir}")
        if manifest.get("protocol_pause_triggered"):
            raise ValueError(f"run 触发协议暂停，不能进入论文分析：{run_dir}")
        if manifest.get("run_mode") != "formal" and not allow_partial:
            raise ValueError(f"pilot run 不能进入正式分析：{run_dir}")
        by_model[str(manifest["model_key"])].append(run_dir)
    if not requested:
        duplicates = {key: rows for key, rows in by_model.items() if len(rows) > 1}
        if duplicates:
            detail = "; ".join(
                f"{key}={len(rows)} runs" for key, rows in sorted(duplicates.items())
            )
            raise ValueError(
                "同一模型存在多个 completed formal run，自动择优会造成选择偏差。"
                f"请用 --run-dir 明确指定每个模型的唯一运行：{detail}"
            )
    return sorted(run_dirs)


def registry_row(run_dir: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    identity = manifest.get("model_identity", {})
    base = identity.get("base_checkpoint", {}) if isinstance(identity, dict) else {}
    gguf = identity.get("gguf", {}) if isinstance(identity, dict) else {}
    deployment = identity.get("deployment", {}) if isinstance(identity, dict) else {}
    return {
        "run_id": manifest.get("run_id"),
        "run_dir": str(run_dir),
        "run_manifest_sha256": sha256_file(run_dir / "run_manifest.json"),
        "model_key": manifest.get("model_key"),
        "requested_model_id": manifest.get("requested_model_id"),
        "experiment_name": manifest.get("experiment_name"),
        "experiment_arm": manifest.get("experiment_arm"),
        "pair_id": manifest.get("pair_id"),
        "pair_role": manifest.get("pair_role"),
        "model_variant": manifest.get("model_variant"),
        "fold_id": manifest.get("fold_id"),
        "language_model_artifact_id": manifest.get("language_model_artifact_id"),
        "base_checkpoint_id": base.get("modelscope_id"),
        "base_checkpoint_revision": base.get("revision"),
        "base_checkpoint_sha256": base.get("snapshot_manifest_sha256"),
        "gguf_filename": gguf.get("filename"),
        "gguf_sha256": gguf.get("sha256"),
        "quantization": gguf.get("quantization"),
        "llama_cpp_commit": gguf.get("converter_commit"),
        "lm_studio_app_version": deployment.get("lm_studio_app_version"),
        "lm_studio_runtime_version": deployment.get("lm_studio_runtime_version"),
        "context_length": deployment.get("context_length"),
        "gpu_offload": deployment.get("gpu_offload"),
        "inference_protocol_sha256": manifest.get("inference_protocol_sha256"),
    }


def atomic_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        Path(temp_name).replace(path)
    except BaseException:
        Path(temp_name).unlink(missing_ok=True)
        raise


def augment_csv(path: Path, registry: dict[str, dict[str, Any]]) -> None:
    if not path.is_file():
        return
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        original_fields = list(reader.fieldnames or [])
    if "run_id" not in original_fields:
        return
    extension_fields = [
        "experiment_name",
        "experiment_arm",
        "pair_id",
        "pair_role",
        "model_variant",
        "fold_id",
        "language_model_artifact_id",
        "base_checkpoint_id",
        "base_checkpoint_revision",
        "base_checkpoint_sha256",
        "gguf_filename",
        "gguf_sha256",
        "quantization",
        "llama_cpp_commit",
        "lm_studio_app_version",
        "lm_studio_runtime_version",
        "context_length",
        "gpu_offload",
        "inference_protocol_sha256",
    ]
    for row in rows:
        metadata = registry.get(str(row.get("run_id")), {})
        for field in extension_fields:
            row[field] = metadata.get(field)
    fieldnames = original_fields + [
        field for field in extension_fields if field not in original_fields
    ]
    atomic_csv(path, fieldnames, rows)


def write_json(path: Path, value: Any) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if args.bootstrap_replicates <= 0:
        raise ValueError("--bootstrap-replicates 必须大于 0")
    config_path, config = load_config(args.config)
    run_dirs = validate_runs(
        config_path,
        config,
        args.run_dir,
        allow_partial=args.allow_partial_question_set,
    )
    analysis_id = safe_slug(
        args.analysis_id
        or ("slm_" + utc_now().replace(":", "").replace("-", "").split(".")[0] + "Z"),
        100,
    )
    output_root = resolve_path(config_path.parent, config["output_root"])
    analysis_dir = output_root / "_analysis" / analysis_id
    command = [
        sys.executable,
        str(API_BENCHMARK_ROOT / "analyze_results.py"),
        "--config",
        str(config_path),
        "--analysis-id",
        analysis_id,
        "--bootstrap-replicates",
        str(args.bootstrap_replicates),
        "--bootstrap-seed",
        str(args.bootstrap_seed),
    ]
    for run_dir in run_dirs:
        command.extend(["--run-dir", str(run_dir)])
    if args.allow_partial_question_set:
        command.append("--allow-partial-question-set")
    completed = subprocess.run(
        command,
        cwd=API_BENCHMARK_ROOT,
        check=False,
        text=True,
        encoding="utf-8",
    )
    if completed.returncode != 0:
        return completed.returncode

    registry_rows = [
        registry_row(run_dir, read_json(run_dir / "run_manifest.json"))
        for run_dir in run_dirs
    ]
    registry = {str(row["run_id"]): row for row in registry_rows}
    write_json(analysis_dir / "slm_run_registry.json", registry_rows)
    atomic_csv(
        analysis_dir / "slm_run_registry.csv",
        list(registry_rows[0].keys()),
        registry_rows,
    )
    for filename in (
        "sample_level_results.csv",
        "base_prompt_results.csv",
        "manuscript_model_metrics.csv",
    ):
        augment_csv(analysis_dir / filename, registry)
    write_json(
        analysis_dir / "slm_analysis_manifest.json",
        {
            "schema_version": "slm_direct_analysis/v1",
            "created_at_utc": utc_now(),
            "analysis_id": analysis_id,
            "run_ids": [row["run_id"] for row in registry_rows],
            "run_count": len(registry_rows),
            "bootstrap_replicates": args.bootstrap_replicates,
            "bootstrap_seed": args.bootstrap_seed,
            "allow_partial_question_set": bool(args.allow_partial_question_set),
            "warning": (
                "Partial-run output is fold/development diagnostics, not a combined OOF SFT result."
                if args.allow_partial_question_set
                else None
            ),
            "wrapper_path": str(Path(__file__).resolve()),
            "wrapper_sha256": sha256_file(Path(__file__).resolve()),
            "shared_analyzer_path": str(API_BENCHMARK_ROOT / "analyze_results.py"),
            "shared_analyzer_sha256": sha256_file(
                API_BENCHMARK_ROOT / "analyze_results.py"
            ),
        },
    )
    inventory = []
    for path in sorted(analysis_dir.iterdir()):
        if path.is_file() and path.name != "analysis_inventory.json":
            inventory.append(
                {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256_file(path)}
            )
    write_json(analysis_dir / "analysis_inventory.json", inventory)
    print(
        json.dumps(
            {"analysis_dir": str(analysis_dir), "runs": len(run_dirs)},
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
