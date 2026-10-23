from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import joblib
import numpy as np

from data_builder import SYSTEM_ORDER, build_dataset
from evaluate import (
    SUMMARY_CSV_NAME,
    SUMMARY_XLSX_NAME,
    export_human_summary,
    protocol_fingerprint,
    run_evaluation,
)
from ml_common import (
    atomic_write_json,
    iter_jsonl,
    read_json,
    resolve_path,
    sha256_file,
    stable_hash,
    utc_now,
)
from models import MODEL_SPECS, NUMERIC_FEATURES, build_model

ROOT = Path(__file__).resolve().parent
CONFIG_PATH = ROOT / "config.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="研究方案 v2.6 第 3.D 节（条款自 v2.2 未变）：四体系冻结数值后端比较、选模与注册。"
    )
    parser.add_argument("--config", type=Path, default=CONFIG_PATH)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("build", help="从四工作簿构建冻结训练数据集")
    subparsers.add_parser("evaluate", help="谱系分组 5 折 CV 比较六模型与 pooled 对照")
    subparsers.add_parser("register", help="按选模指标注册每体系专用模型与适用域")
    subparsers.add_parser("status", help="查看数据集、评价与注册状态")
    return parser.parse_args()


def load_config(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    config_path = args.config.resolve()
    config = read_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("config.json 顶层必须是 JSON 对象")
    return config_path, config


def _dataset_path(config_path: Path, config: dict[str, Any]) -> Path:
    return resolve_path(config_path.parent, config["output_root"]) / str(
        config["dataset_file"]
    )


def _load_dataset(config_path: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    dataset_path = _dataset_path(config_path, config)
    if not dataset_path.is_file():
        raise FileNotFoundError(
            f"数据集不存在：{dataset_path}；请先运行 `python run_backend.py build`"
        )
    return list(iter_jsonl(dataset_path))


def command_build(config_path: Path, config: dict[str, Any]) -> int:
    manifest = build_dataset(config_path, config)
    print(
        json.dumps(
            {
                "dataset": manifest["dataset_path"],
                "dataset_sha256": manifest["dataset_sha256"],
                "eligible_conditions": manifest["eligible_condition_count"],
                "system_counts": manifest["system_counts"],
                "manifest": manifest["dataset_path"].replace("ml_conditions.jsonl", "dataset_manifest.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_evaluate(config_path: Path, config: dict[str, Any]) -> int:
    dataset_path = _dataset_path(config_path, config)
    if not dataset_path.is_file():
        raise FileNotFoundError("数据集不存在；请先运行 build")
    output_root = resolve_path(config_path.parent, config["output_root"])
    results = run_evaluation(config_path, config, dataset_path, output_root)
    print(
        json.dumps(
            {
                "evaluation_dir": str(output_root / str(config["evaluation_dir"]) / results["protocol_fingerprint"]),
                "protocol_fingerprint": results["protocol_fingerprint"],
                "protocol_frozen": results["protocol_frozen"],
                "selection": results["selection"],
                "pooled_delta": results["pooled_delta"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def _system_domain(rows: list[dict[str, Any]]) -> dict[str, Any]:
    temperatures = [float(row["temperature_K"]) for row in rows]
    concentrations = [float(row["concentration_mol_L"]) for row in rows]
    return {
        "kind": "rectangular_box",
        "temperature_K": {
            "min": min(temperatures),
            "max": max(temperatures),
        },
        "concentration_mol_L": {
            "min": min(concentrations),
            "max": max(concentrations),
        },
        "rejection_policy": "structured_refusal",
    }


def command_register(config_path: Path, config: dict[str, Any]) -> int:
    rows = _load_dataset(config_path, config)
    output_root = resolve_path(config_path.parent, config["output_root"])
    evaluation_candidates = sorted(
        (output_root / str(config["evaluation_dir"])).glob("*/results.json"),
        reverse=True,
    )
    if not evaluation_candidates:
        raise FileNotFoundError("没有找到评价结果；请先运行 evaluate")
    results_path = evaluation_candidates[0]
    results = read_json(results_path)
    fingerprint = str(results["protocol_fingerprint"])
    if protocol_fingerprint(
        config, sha256_file(_dataset_path(config_path, config)), config_path.parent
    ) != fingerprint:
        raise ValueError("当前配置/代码与所选评价的协议指纹不一致；请重新 evaluate 后再注册")
    if not bool(config.get("protocol_frozen", False)):
        print(
            "警告：config.protocol_frozen 仍为 false；注册产物将标记为未冻结，"
            "进入论文前需要冻结并重跑。",
            file=sys.stderr,
        )

    registry_dir = output_root / str(config["registry_dir"]) / fingerprint
    registry_dir.mkdir(parents=True, exist_ok=True)
    by_system: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_system.setdefault(str(row["system"]), []).append(row)

    primary_metric = str(config["selection"]["primary_metric"])
    registry_rows: list[dict[str, Any]] = []
    for system in SYSTEM_ORDER:
        selection = results["selection"].get(system)
        if not selection:
            continue
        model_key = str(selection["selected_model_key"])
        system_rows = by_system.get(system, [])
        matrix = np.array(
            [[float(row[feature]) for feature in NUMERIC_FEATURES] for row in system_rows]
        )
        targets = np.array([float(row["diffusion_1e9_m2_s"]) for row in system_rows])
        model = build_model(model_key, pooled=False)
        model.fit(matrix, targets)
        artifact_path = registry_dir / f"{system}.joblib"
        joblib.dump(model, artifact_path)
        domain = _system_domain(system_rows)

        pooled_model = build_model(model_key, pooled=True)
        pooled_matrix = np.hstack(
            [
                np.full((len(system_rows), 1), system, dtype=object),
                matrix,
            ]
        )
        pooled_model.fit(pooled_matrix, targets)
        pooled_path = registry_dir / f"{system}.pooled_control.joblib"
        joblib.dump(pooled_model, pooled_path)

        registry_rows.append(
            {
                "system": system,
                "registered_model_key": model_key,
                "registered_model_display": MODEL_SPECS[model_key]["display_name"],
                "primary_metric": primary_metric,
                "primary_metric_value_cv": selection["primary_metric_value"],
                "tie_break_value_cv": selection["tie_break_value"],
                "cv_accuracy_10pct": results["specialized"][system][model_key][
                    "accuracy_10pct"
                ],
                "trained_on_conditions": len(system_rows),
                "trained_on_lineages": len(
                    {str(row["origin_lineage_id"]) for row in system_rows}
                ),
                "applicability_domain": domain,
                "artifact": {
                    "path": str(artifact_path),
                    "sha256": sha256_file(artifact_path),
                },
                "pooled_control_artifact": {
                    "path": str(pooled_path),
                    "sha256": sha256_file(pooled_path),
                },
                "target_unit": config["target_unit"],
                "features": list(config["features"]),
            }
        )

    registry: dict[str, Any] = {
        "schema_version": "ml_backend_d/v1",
        "artifact_type": "ml_backend_d_registry",
        "created_at_utc": utc_now(),
        "protocol_fingerprint": fingerprint,
        "protocol_frozen": bool(config.get("protocol_frozen", False)),
        "evaluation_source": str(results_path),
        "evaluation_sha256": sha256_file(results_path),
        "dataset_sha256": sha256_file(_dataset_path(config_path, config)),
        "selection_metric": primary_metric,
        "systems": registry_rows,
        "pooled_control_explanation": (
            "Pooled 对照按该体系入选模型家族在全部四体系数据上重训；"
            "仅用于'分体系建模是否必要'的比较，不作为 Agent 后端。"
        ),
    }
    registry["registry_content_sha256"] = stable_hash(registry)
    atomic_write_json(registry_dir / "registry.json", registry)
    summary_paths = export_human_summary(
        output_root, Path(results_path).parent, registry_dir
    )
    print(
        json.dumps(
            {
                "registry_dir": str(registry_dir),
                "human_summary": summary_paths,
                "systems": [
                    {
                        "system": row["system"],
                        "model": row["registered_model_key"],
                        "primary_metric_cv": row["primary_metric_value_cv"],
                        "domain": row["applicability_domain"],
                    }
                    for row in registry_rows
                ],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


def command_status(config_path: Path, config: dict[str, Any]) -> int:
    output_root = resolve_path(config_path.parent, config["output_root"])
    dataset_path = _dataset_path(config_path, config)
    manifest_path = output_root / str(config["dataset_manifest_file"])
    payload: dict[str, Any] = {"dataset": None, "evaluations": [], "registries": []}
    if manifest_path.is_file():
        manifest = read_json(manifest_path)
        payload["dataset"] = {
            "path": str(dataset_path),
            "sha256": manifest.get("dataset_sha256"),
            "eligible_conditions": manifest.get("eligible_condition_count"),
            "system_counts": manifest.get("system_counts"),
        }
    payload["evaluations"] = [
        {
            "dir": path.parent.name,
            "frozen": read_json(path).get("protocol_frozen"),
        }
        for path in sorted((output_root / str(config["evaluation_dir"])).glob("*/results.json"))
    ]
    payload["registries"] = [
        {
            "dir": path.parent.name,
            "frozen": read_json(path).get("protocol_frozen"),
        }
        for path in sorted((output_root / str(config["registry_dir"])).glob("*/registry.json"))
    ]
    summary_csv = output_root / SUMMARY_CSV_NAME
    summary_xlsx = output_root / SUMMARY_XLSX_NAME
    payload["human_summary"] = {
        "csv": str(summary_csv) if summary_csv.is_file() else None,
        "xlsx": str(summary_xlsx) if summary_xlsx.is_file() else None,
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    args = parse_args()
    config_path, config = load_config(args)
    if args.command == "build":
        return command_build(config_path, config)
    if args.command == "evaluate":
        return command_evaluate(config_path, config)
    if args.command == "register":
        return command_register(config_path, config)
    if args.command == "status":
        return command_status(config_path, config)
    raise ValueError(f"未知命令：{args.command}")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
