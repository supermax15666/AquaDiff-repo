from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys
from pathlib import Path
from types import ModuleType
from typing import Any

from slm_common import (
    API_BENCHMARK_ROOT,
    ROOT,
    SCHEMA_VERSION,
    apply_chat_message_policy,
    deployment_identity_id,
    formal_readiness_issues,
    load_config,
    load_question_id_filter,
    model_identity,
    pair_task_id,
    preflight_model,
    resolve_path,
    safe_slug,
    select_questions,
    sha256_file,
    stable_hash,
    utc_now,
    verify_frozen_assets,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the four-system direct-answer benchmark against a locally loaded "
            "LM Studio GGUF model."
        )
    )
    parser.add_argument("--config", type=Path, default=ROOT / "config.json")
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--experiment-name")
    parser.add_argument("--mode", choices=("pilot", "formal"), default="pilot")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--new-run", action="store_true")
    parser.add_argument("--resume-only", action="store_true")
    parser.add_argument("--run-id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--preflight-only", action="store_true")
    parser.add_argument(
        "--skip-preflight",
        action="store_true",
        help="Development/dry-run only; forbidden for formal runs.",
    )
    return parser.parse_args()


def load_api_core() -> ModuleType:
    core_path = API_BENCHMARK_ROOT / "run_benchmark.py"
    if not core_path.is_file():
        raise FileNotFoundError(f"找不到共享采集核心：{core_path}")
    api_root_text = str(API_BENCHMARK_ROOT)
    if api_root_text not in sys.path:
        sys.path.insert(0, api_root_text)
    module_name = "slm_direct_llm_api_core"
    spec = importlib.util.spec_from_file_location(module_name, core_path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"无法加载共享采集核心：{core_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def runtime_model_config(
    config: dict[str, Any],
    model_key: str,
    *,
    run_mode: str,
    experiment_name: str,
    wrapper_sha256: str,
) -> dict[str, Any]:
    source = config["models"][model_key]
    inference = dict(config.get("inference", {}))
    server = config["server"]
    api_key_env = str(server.get("api_key_env", "LM_STUDIO_API_KEY")).strip()
    api_key_value = str(os.environ.get(api_key_env, "")).strip()
    if not api_key_value:
        # LM Studio normally does not require authentication. The shared
        # transport needs a non-empty credential slot, so use a non-secret
        # placeholder value that manifests redact.
        api_key_value = "lm-studio-local"
    identity = model_identity(model_key, source)
    return {
        "enabled": True,
        "provider": "lm_studio",
        "base_url": str(server["base_url"]),
        "endpoint": "chat_completions",
        "api_key_env": api_key_env,
        "api_key_value": api_key_value,
        "model_id": str(source["served_model_id"]),
        "snapshot_confirmed": bool(source.get("formal_ready", False)),
        "evidence_level": (
            "retrospective_opened_four_system_lineage_pool"
            if run_mode == "formal"
            else "pipeline_test"
        ),
        "structured_output": str(inference.get("structured_output", "json_schema")),
        "temperature": inference.get("temperature", 0),
        "seed": inference.get("seed"),
        "max_output_tokens": int(inference.get("max_output_tokens", 256)),
        "token_parameter": "max_tokens",
        "extra_body": dict(inference.get("extra_body", {})),
        "send_metadata": False,
        "timeout_seconds": float(
            source.get("timeout_seconds", config.get("timeout_seconds", 180))
        ),
        "inter_request_seconds": float(
            source.get(
                "inter_request_seconds", config.get("inter_request_seconds", 0)
            )
        ),
        "retry": dict(source.get("retry", {})),
        "slm_schema_version": SCHEMA_VERSION,
        "run_mode": run_mode,
        "experiment_name": experiment_name,
        "slm_identity": identity,
        "deployment_identity_id": deployment_identity_id(model_key, source),
        "slm_wrapper_sha256": wrapper_sha256,
    }


def smoke_test_model(
    *,
    core: ModuleType,
    config_path: Path,
    config: dict[str, Any],
    model_key: str,
    runtime_model: dict[str, Any],
) -> dict[str, Any]:
    source = config["models"][model_key]
    schema = core.read_json(resolve_path(config_path.parent, config["answer_schema"]))
    smoke_prompt = (
        "Predict the mutual diffusion coefficient of NaCl-H2O at T = 298.15 K "
        "and c = 1.000000 mol/L. Return the multiplier x where "
        "D = x * 10^-9 m^2/s."
    )
    body = core.build_request_body(
        runtime_model,
        smoke_prompt,
        "slm-direct-preflight-smoke",
        schema,
    )
    body = apply_chat_message_policy(body, source)
    outcome = core.post_json(
        core.api_url(runtime_model),
        body,
        core.request_headers(runtime_model),
        min(float(runtime_model.get("timeout_seconds", 180)), 60.0),
    )
    response_body = outcome.body if isinstance(outcome.body, dict) else {}
    answer_text, refusal = core.extract_response_text(response_body, "chat_completions")
    answer = core.parse_json_object(answer_text)
    quality = core.response_quality(answer)
    returned_model_id = response_body.get("model")
    expected_model_id = str(source["served_model_id"])
    roles = [
        message.get("role")
        for message in body.get("messages", [])
        if isinstance(message, dict)
    ]
    content_hashes = [
        stable_hash(message.get("content", ""))
        for message in body.get("messages", [])
        if isinstance(message, dict)
    ]
    passed = bool(
        outcome.ok
        and returned_model_id == expected_model_id
        and quality.get("answer_schema_valid")
        and quality.get("valid_numeric_response")
        and not refusal
    )
    return {
        "checked_at_utc": utc_now(),
        "diagnostic_call_count": 1,
        "excluded_from_benchmark_denominator": True,
        "request_body_sha256": stable_hash(body),
        "request_message_roles": roles,
        "request_message_content_sha256": content_hashes,
        "system_message_policy": source["system_message_policy"],
        "http_status": outcome.http_status,
        "latency_seconds": outcome.latency_seconds,
        "response_sha256": stable_hash(outcome.raw_text),
        "returned_model_id": returned_model_id,
        "expected_model_id": expected_model_id,
        "parsed_answer": answer,
        "answer_schema_valid": bool(quality.get("answer_schema_valid")),
        "valid_numeric_response": bool(quality.get("valid_numeric_response")),
        "refusal": refusal,
        "error_type": outcome.error_type,
        "error_message": outcome.error_message,
        "passed": passed,
    }


def experiment_name_from_args(args: argparse.Namespace) -> str:
    value = args.experiment_name
    if not value and args.run_id and "__" in args.run_id:
        value = args.run_id.split("__", 1)[0]
    if not value:
        value = "pilot_connectivity" if args.mode == "pilot" else ""
    name = safe_slug(str(value), 40)
    if args.mode == "formal" and not value:
        raise ValueError("正式运行必须用 --experiment-name 指定有意义的实验名")
    if len(name) < 3:
        raise ValueError("实验名至少需要 3 个安全字符")
    return name


def validate_run_request(
    args: argparse.Namespace,
    config: dict[str, Any],
    model_key: str,
    selected_count: int,
    full_count: int,
) -> None:
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit 必须大于 0")
    if args.new_run and args.resume_only:
        raise ValueError("--new-run 与 --resume-only 不能同时使用")
    if args.run_id and not args.resume_only:
        raise ValueError("--run-id 必须与 --resume-only 一起使用")
    if args.preflight_only and (args.new_run or args.resume_only or args.run_id or args.dry_run):
        raise ValueError("--preflight-only 不能与运行/续跑参数同时使用")
    if args.skip_preflight and not args.dry_run:
        raise ValueError("--skip-preflight 只能用于 --dry-run")
    if not args.preflight_only and not (args.new_run or args.resume_only):
        raise ValueError("必须明确选择 --new-run 或 --resume-only；不会自动复用旧实验")
    if args.mode == "formal":
        if args.limit is not None:
            raise ValueError("正式运行禁止 --limit")
        if args.skip_preflight:
            raise ValueError("正式运行禁止 --skip-preflight")
        if not (args.new_run or args.resume_only):
            raise ValueError("正式运行必须明确选择 --new-run 或 --resume-only")
        issues = formal_readiness_issues(config, model_key)
        if issues:
            raise ValueError("正式协议尚未冻结：\n- " + "\n- ".join(issues))
        model = config["models"][model_key]
        if model["pair_role"] == "base" and selected_count != full_count:
            raise ValueError("实验臂 A 的正式 Base direct 必须运行完整 642 题")
        if model["pair_role"] == "sft" and not model.get("question_ids_file"):
            raise ValueError("实验臂 C 的 SFT 正式运行必须绑定该折 question_ids_file")


def run_extension(
    *,
    config_path: Path,
    config: dict[str, Any],
    model_key: str,
    runtime_model: dict[str, Any],
    experiment_name: str,
    run_mode: str,
    frozen_assets: dict[str, Any],
    preflight: dict[str, Any] | None,
    core: ModuleType,
) -> dict[str, Any]:
    source = config["models"][model_key]
    identity = model_identity(model_key, source)
    inference_contract = {
        "system_prompt_sha256": stable_hash(core.SYSTEM_PROMPT),
        "answer_schema_sha256": sha256_file(
            resolve_path(config_path.parent, config["answer_schema"])
        ),
        "structured_output": runtime_model["structured_output"],
        "temperature": runtime_model["temperature"],
        "seed": runtime_model["seed"],
        "max_output_tokens": runtime_model["max_output_tokens"],
        "repetitions": int(config["repetitions"]),
        "order_seed": int(config["order_seed"]),
        "parser_source": str(API_BENCHMARK_ROOT / "common.py"),
        "parser_sha256": sha256_file(API_BENCHMARK_ROOT / "common.py"),
        "system_message_policy": source["system_message_policy"],
    }
    return {
        "slm_schema_version": SCHEMA_VERSION,
        "benchmark_program": "SLM_direct",
        "research_plan_version": "2.2",
        "run_mode": run_mode,
        "experiment_name": experiment_name,
        "experiment_arm": source["experiment_arm"],
        "pair_id": source["pair_id"],
        "pair_role": source["pair_role"],
        "model_variant": source["model_variant"],
        "fold_id": source.get("fold_id"),
        "model_identity": identity,
        "language_model_artifact_id": runtime_model["deployment_identity_id"],
        "agent_comparison_model_artifact_id": runtime_model["deployment_identity_id"],
        "frozen_assets": frozen_assets,
        "lm_studio_preflight": preflight,
        "inference_contract": inference_contract,
        "inference_protocol_sha256": stable_hash(inference_contract),
        "pair_task_id_definition": {
            "version": "pair-task/v2",
            "fields": [
                "pair_id",
                "question_id",
                "sample_index",
                "prompt_family_id",
            ],
            "excludes": ["model_fingerprint", "run_id"],
        },
        "comparison_guards": {
            "tools_provided": False,
            "retrieval_provided": False,
            "database_access": False,
            "code_execution": False,
            "gold_sent_to_model": False,
            "base_sft_same_quantization_required": True,
            "base_agent_same_language_model_artifact_required": True,
        },
        "wrapper": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
            "shared_core_path": str(API_BENCHMARK_ROOT / "run_benchmark.py"),
            "shared_core_sha256": sha256_file(
                API_BENCHMARK_ROOT / "run_benchmark.py"
            ),
        },
    }


def augment_sample_results(
    run_dir: Path, model_key: str, model: dict[str, Any], core: ModuleType
) -> None:
    path = run_dir / "sample_results.jsonl"
    if not path.is_file():
        return
    records = list(core.iter_jsonl(path))
    artifact_id = deployment_identity_id(model_key, model)
    for record in records:
        record.update(
            {
                "slm_schema_version": SCHEMA_VERSION,
                "experiment_arm": model["experiment_arm"],
                "pair_id": model["pair_id"],
                "pair_role": model["pair_role"],
                "model_variant": model["model_variant"],
                "fold_id": model.get("fold_id"),
                "language_model_artifact_id": artifact_id,
                "pair_task_id": pair_task_id(
                    model,
                    str(record["question_id"]),
                    int(record["sample_index"]),
                    str(record["template_family_id"]),
                ),
                "prompt_family_id": str(record["template_family_id"]),
            }
        )
    core.atomic_write_jsonl(path, records)
    manifest_path = run_dir / "run_manifest.json"
    if manifest_path.is_file():
        manifest = core.read_json(manifest_path)
        manifest["results_sha256"] = sha256_file(path)
        manifest["sample_result_extension"] = {
            "schema_version": SCHEMA_VERSION,
            "pair_task_id_added": True,
            "updated_at_utc": utc_now(),
        }
        returned = set(str(value) for value in manifest.get("returned_model_ids", []))
        expected = str(model["served_model_id"])
        identity_mismatch = bool(
            manifest.get("status") == "completed"
            and (not returned or returned != {expected})
        )
        manifest["served_model_identity_check"] = {
            "expected": expected,
            "returned": sorted(returned),
            "passed": not identity_mismatch,
        }
        if identity_mismatch:
            manifest["protocol_identity_mismatch"] = True
            manifest["protocol_pause_triggered"] = True
            reasons = list(manifest.get("protocol_pause_reasons", []))
            reasons.append("LM Studio response model ID did not exactly match served_model_id")
            manifest["protocol_pause_reasons"] = sorted(set(reasons))
        core.atomic_write_json(manifest_path, manifest)


def main() -> int:
    args = parse_args()
    config_path, config = load_config(args.config)
    if args.model_key not in config["models"]:
        raise ValueError(f"未知模型键：{args.model_key}")
    if not bool(config["models"][args.model_key].get("enabled", True)):
        raise ValueError(f"模型已禁用：{args.model_key}")

    core = load_api_core()
    frozen_assets = verify_frozen_assets(config_path, config)
    question_path = resolve_path(config_path.parent, config["question_file"])
    all_questions = list(core.iter_jsonl(question_path))
    core.validate_questions(all_questions)
    model_source = config["models"][args.model_key]
    question_ids = load_question_id_filter(config_path, model_source)
    questions = select_questions(all_questions, question_ids)
    if args.limit is not None:
        questions = questions[: args.limit]
    experiment_name = experiment_name_from_args(args)
    validate_run_request(
        args, config, args.model_key, len(questions), len(all_questions)
    )

    wrapper_sha256 = sha256_file(Path(__file__).resolve())
    runtime_model = runtime_model_config(
        config,
        args.model_key,
        run_mode=args.mode,
        experiment_name=experiment_name,
        wrapper_sha256=wrapper_sha256,
    )
    core.validate_model_config(args.model_key, runtime_model)

    preflight: dict[str, Any] | None = None
    if not args.skip_preflight and not args.dry_run:
        preflight = preflight_model(config, args.model_key, config_path)
        metadata_passed = bool(preflight["passed"])
        smoke = (
            smoke_test_model(
                core=core,
                config_path=config_path,
                config=config,
                model_key=args.model_key,
                runtime_model=runtime_model,
            )
            if metadata_passed
            else {
                "diagnostic_call_count": 0,
                "skipped": True,
                "reason": "metadata_preflight_failed",
                "passed": False,
            }
        )
        preflight["metadata_passed"] = metadata_passed
        preflight["smoke_test"] = smoke
        preflight["passed"] = bool(metadata_passed and smoke["passed"])
        if not preflight["passed"]:
            available = ", ".join(
                preflight["openai_compatible"]["model_ids"]
            ) or "<none>"
            raise RuntimeError(
                "LM Studio 模型预检未通过。请确保只加载一个模型，且其 id 与配置中的 "
                f"served_model_id={model_source['served_model_id']!r} 一致；"
                f"当前 /v1/models：{available}；native loaded count="
                f"{preflight['exact_loaded_instance_count']}；metadata="
                f"{preflight['metadata_checks']}"
                f"; gguf_file={preflight['gguf_file_identity']}"
                f"; smoke={preflight.get('smoke_test')}"
            )
    if args.preflight_only:
        print(json.dumps(preflight, ensure_ascii=False, indent=2))
        return 0

    extension = run_extension(
        config_path=config_path,
        config=config,
        model_key=args.model_key,
        runtime_model=runtime_model,
        experiment_name=experiment_name,
        run_mode=args.mode,
        frozen_assets=frozen_assets,
        preflight=preflight,
        core=core,
    )

    output_root = resolve_path(config_path.parent, config["output_root"])
    output_root.mkdir(parents=True, exist_ok=True)
    answer_schema_path = resolve_path(config_path.parent, config["answer_schema"])
    shared_config = {
        **config,
        "schema_version": "llm_api_direct/v1",
        "models": {args.model_key: runtime_model},
    }
    original_prepare_run = core.prepare_run
    original_build_request_body = core.build_request_body
    run_holder: dict[str, Path] = {}

    def prepare_slm_run(*prepare_args: Any, **prepare_kwargs: Any):
        run_dir, manifest, fingerprint = original_prepare_run(
            *prepare_args, **prepare_kwargs
        )
        is_new_slm_run = manifest.get("artifact_type") != "slm_direct_run_manifest"
        if is_new_slm_run:
            target_name = f"{experiment_name}__{run_dir.name}"
            target_dir = run_dir.parent / target_name
            if target_dir.exists():
                raise FileExistsError(f"目标 run 目录已存在：{target_dir}")
            run_dir.rename(target_dir)
            run_dir = target_dir
            manifest["run_id"] = target_name
        elif manifest.get("experiment_name") != experiment_name:
            raise ValueError("续跑 experiment_name 与原 run manifest 不一致")
        manifest.update(extension)
        manifest["artifact_type"] = "slm_direct_run_manifest"
        manifest["result_schema_compatibility"] = "llm_api_direct/v1"
        manifest["runner"] = {
            "path": str(Path(__file__).resolve()),
            "sha256": wrapper_sha256,
            "shared_core_path": str(API_BENCHMARK_ROOT / "run_benchmark.py"),
            "shared_core_sha256": sha256_file(
                API_BENCHMARK_ROOT / "run_benchmark.py"
            ),
            "python_version": sys.version,
        }
        core.atomic_write_json(run_dir / "run_manifest.json", manifest)
        run_holder["path"] = run_dir
        return run_dir, manifest, fingerprint

    core.prepare_run = prepare_slm_run
    def build_slm_request_body(
        runtime_source: dict[str, Any],
        prompt: str,
        task_id: str,
        schema: dict[str, Any],
    ) -> dict[str, Any]:
        body = original_build_request_body(runtime_source, prompt, task_id, schema)
        return apply_chat_message_policy(body, model_source)

    core.build_request_body = build_slm_request_body
    try:
        run_dir = core.run_model(
            config_path,
            shared_config,
            args.model_key,
            runtime_model,
            questions,
            question_path,
            answer_schema_path,
            output_root,
            force_new=args.new_run,
            requested_run_id=args.run_id,
            dry_run=args.dry_run,
            resume_only=args.resume_only,
        )
    finally:
        core.prepare_run = original_prepare_run
        core.build_request_body = original_build_request_body
    if "path" in run_holder:
        # Run after the try/finally so an augmentation failure can never mask
        # the original exception; the run is only augmented once it completed.
        augment_sample_results(
            run_holder["path"], args.model_key, model_source, core
        )

    print(json.dumps({"run_dir": str(run_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已安全中断；请从 start.py 选择续跑。", file=sys.stderr)
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
