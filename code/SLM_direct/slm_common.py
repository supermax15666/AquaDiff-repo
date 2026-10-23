from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parent
PY_ROOT = ROOT.parent
PROJECT_ROOT = PY_ROOT.parent
API_BENCHMARK_ROOT = PY_ROOT / "LLM_API_direct"
EXPECTED_OUTPUT_ROOT = PY_ROOT / "results" / "SLM_direct" / "protocol_v2_2"
SCHEMA_VERSION = "slm_direct/v1"
EXPECTED_BASE_MODEL_KEYS = {
    "qwen3_4b_instruct_2507_base_q4km",
    "qwen3_8b_instruct_base_q4km",
    "qwen3_6_27b_base_q4km",
    "llama3_1_8b_instruct_base_q4km",
    "gemma2_9b_it_base_q4km",
}
EXPECTED_RESEARCH_PLAN_VERSION = "2.14"
EXPECTED_LM_STUDIO_APP_VERSION = "0.4.20+1"
PLACEHOLDER_MARKERS = (
    "REPLACE_WITH",
    "FILL_ME",
    "TODO",
    "UNKNOWN",
    "未填写",
    "待填写",
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def stable_hash(value: Any, length: int | None = None) -> str:
    digest = hashlib.sha256(canonical_json_bytes(value)).hexdigest()
    return digest[:length] if length else digest


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def safe_slug(value: str, max_length: int = 80) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    slug = slug or "unnamed"
    if len(slug) <= max_length:
        return slug
    return f"{slug[: max_length - 11]}_{stable_hash(value, 10)}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_path(base_dir: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def load_config(path: Path | None = None) -> tuple[Path, dict[str, Any]]:
    config_path = (path or (ROOT / "config.json")).resolve()
    try:
        config = read_json(config_path)
    except FileNotFoundError as exc:
        raise ValueError(f"找不到配置文件：{config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"配置文件不是有效 JSON：{exc}") from exc
    if not isinstance(config, dict):
        raise ValueError("配置文件顶层必须是 JSON 对象")
    validate_config(config_path, config)
    return config_path, config


def _is_loopback_url(url: str) -> bool:
    parsed = urllib.parse.urlsplit(url)
    return parsed.scheme in {"http", "https"} and (parsed.hostname or "").lower() in {
        "127.0.0.1",
        "localhost",
        "::1",
    }


def _same_origin(left: str, right: str) -> bool:
    first = urllib.parse.urlsplit(left)
    second = urllib.parse.urlsplit(right)
    return (
        first.scheme.lower(),
        (first.hostname or "").lower(),
        first.port,
    ) == (
        second.scheme.lower(),
        (second.hostname or "").lower(),
        second.port,
    )


def is_sha256(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-fA-F]{64}", value) is not None


def is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            return True
        upper = cleaned.upper()
        return any(marker in upper for marker in PLACEHOLDER_MARKERS)
    return False


def _required_mapping(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} 必须是 JSON 对象")
    return value


def validate_config(config_path: Path, config: dict[str, Any]) -> None:
    if config.get("schema_version") != SCHEMA_VERSION:
        raise ValueError(f"schema_version 必须为 {SCHEMA_VERSION!r}")
    server = _required_mapping(config.get("server"), "server")
    base_url = str(server.get("base_url", "")).strip()
    if not base_url:
        raise ValueError("server.base_url 不能为空")
    if bool(server.get("require_loopback", True)) and not _is_loopback_url(base_url):
        raise ValueError("正式本地基准默认只允许 localhost/127.0.0.1/::1 的 LM Studio 地址")
    native_models_url = str(server.get("native_models_url", "")).strip()
    if not native_models_url:
        raise ValueError("server.native_models_url 不能为空")
    if bool(server.get("require_loopback", True)) and not _is_loopback_url(
        native_models_url
    ):
        raise ValueError("server.native_models_url 必须是 loopback 地址")
    if not _same_origin(base_url, native_models_url):
        raise ValueError("server.base_url 与 native_models_url 必须同源，防止身份信息泄漏")
    if server.get("require_native_metadata") is not True:
        raise ValueError("server.require_native_metadata 必须显式为 true")
    forbidden_secret_keys = {"api_key", "api_key_value", "password", "token", "secret"}
    present_secret_keys = forbidden_secret_keys.intersection(server)
    if present_secret_keys:
        raise ValueError(
            "配置文件不得保存密钥；请只使用 server.api_key_env。发现："
            + ", ".join(sorted(present_secret_keys))
        )

    models = _required_mapping(config.get("models"), "models")
    if not models:
        raise ValueError("models 不能为空")
    missing_base_models = EXPECTED_BASE_MODEL_KEYS - set(models)
    if missing_base_models:
        raise ValueError(f"缺少已冻结的五模型条目：{sorted(missing_base_models)}")
    served_model_ids: set[str] = set()
    for model_key, model_value in models.items():
        model = _required_mapping(model_value, f"models.{model_key}")
        if safe_slug(str(model_key)) != model_key:
            raise ValueError(f"模型键必须是稳定的安全 slug：{model_key!r}")
        for field in ("display_name", "served_model_id", "model_family", "chat_template"):
            if not str(model.get(field, "")).strip():
                raise ValueError(f"models.{model_key}.{field} 不能为空")
        served_model_id = str(model["served_model_id"])
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._@/-]{0,199}", served_model_id):
            raise ValueError(
                f"models.{model_key}.served_model_id 必须是 LM Studio 原生 id 格式"
                f"（无空白，允许 / @ . _ -）：{served_model_id!r}"
            )
        if served_model_id in served_model_ids:
            raise ValueError(f"served_model_id 不能重复：{served_model_id!r}")
        served_model_ids.add(served_model_id)
        if model.get("pair_role") not in {"base", "sft"}:
            raise ValueError(f"models.{model_key}.pair_role 必须是 base 或 sft")
        expected_variant = (
            "original_instruct" if model.get("pair_role") == "base" else "domain_sft"
        )
        if model.get("model_variant") != expected_variant:
            raise ValueError(
                f"models.{model_key}.model_variant 应为 {expected_variant!r}"
            )
        expected_arm = "A_base_direct" if model.get("pair_role") == "base" else "C_sft_direct"
        if model.get("experiment_arm") != expected_arm:
            raise ValueError(
                f"models.{model_key}.experiment_arm 应为 {expected_arm!r}"
            )
        if not str(model.get("pair_id", "")).strip():
            raise ValueError(f"models.{model_key}.pair_id 不能为空")
        if model.get("system_message_policy") not in {
            "native_system_role",
            "fold_system_into_first_user",
        }:
            raise ValueError(
                f"models.{model_key}.system_message_policy 不受支持"
            )

    seen_sft_folds: set[tuple[str, int]] = set()
    for model_key, model in models.items():
        if model.get("pair_role") == "base":
            paired = model.get("paired_model_keys", [])
            if not isinstance(paired, list):
                raise ValueError(f"models.{model_key}.paired_model_keys 必须是数组")
            continue
        fold_id = model.get("fold_id")
        if fold_id not in {0, 1, 2, 3, 4}:
            raise ValueError(f"models.{model_key}.fold_id 必须为 0–4")
        fold_key = (str(model["pair_id"]), int(fold_id))
        if fold_key in seen_sft_folds:
            raise ValueError(f"SFT pair_id/fold_id 重复：{fold_key}")
        seen_sft_folds.add(fold_key)
        parent_key = str(model.get("parent_base", {}).get("model_key", ""))
        if parent_key not in models:
            raise ValueError(f"models.{model_key}.parent_base.model_key 不存在")
        parent = models[parent_key]
        if parent.get("pair_role") != "base" or parent.get("pair_id") != model.get(
            "pair_id"
        ):
            raise ValueError(f"models.{model_key} 与 parent_base 的 pair_id/角色不匹配")
        for field in ("chat_template", "gguf_template_family", "system_message_policy"):
            if model.get(field) != parent.get(field):
                raise ValueError(f"models.{model_key}.{field} 必须与 Base 一致")

    base_dir = config_path.parent
    output_root = resolve_path(base_dir, config.get("output_root", ""))
    if output_root != EXPECTED_OUTPUT_ROOT.resolve():
        # End-to-end tests need an isolated disposable result root. This escape
        # hatch is intentionally limited to the OS temporary directory, and
        # formal_readiness_issues() always rejects pipeline_test configurations.
        temporary_root = Path(tempfile.gettempdir()).resolve()
        test_output_allowed = bool(config.get("pipeline_test", False))
        try:
            output_root.relative_to(temporary_root)
        except ValueError:
            test_output_allowed = False
        if not test_output_allowed:
            raise ValueError(
                "output_root 必须隔离到 py/results/SLM_direct/protocol_v2_2，"
                "以免混入旧两体系 pilot"
            )
    for field in (
        "question_file",
        "question_manifest_file",
        "evaluator_gold_file",
        "analysis_sets_file",
        "answer_schema",
    ):
        path = resolve_path(base_dir, str(config.get(field, "")))
        if not path.is_file():
            raise ValueError(f"{field} 不存在：{path}")


def verify_frozen_assets(config_path: Path, config: dict[str, Any]) -> dict[str, Any]:
    base_dir = config_path.parent
    question_path = resolve_path(base_dir, config["question_file"])
    manifest_path = resolve_path(base_dir, config["question_manifest_file"])
    gold_path = resolve_path(base_dir, config["evaluator_gold_file"])
    analysis_sets_path = resolve_path(base_dir, config["analysis_sets_file"])
    manifest = read_json(manifest_path)
    checks = {
        "question_file": {
            "path": str(question_path),
            "actual_sha256": sha256_file(question_path),
            "expected_sha256": manifest.get("question_set_sha256"),
        },
        "evaluator_gold_file": {
            "path": str(gold_path),
            "actual_sha256": sha256_file(gold_path),
            "expected_sha256": manifest.get("evaluator_gold_sha256"),
        },
        "analysis_sets_file": {
            "path": str(analysis_sets_path),
            "actual_sha256": sha256_file(analysis_sets_path),
            "expected_sha256": manifest.get("analysis_sets_sha256"),
        },
    }
    mismatches = [
        name
        for name, check in checks.items()
        if check["actual_sha256"] != check["expected_sha256"]
    ]
    if mismatches:
        raise ValueError(f"冻结资产哈希不一致：{mismatches}")
    expected_count = int(manifest.get("question_count", 0))
    actual_count = sum(
        1
        for line in question_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    )
    if actual_count != expected_count:
        raise ValueError(f"题库数量不一致：实际 {actual_count}，manifest {expected_count}")
    return {
        "manifest_path": str(manifest_path),
        "manifest_sha256": sha256_file(manifest_path),
        "question_count": actual_count,
        "checks": checks,
    }


def enabled_model_keys(config: dict[str, Any]) -> list[str]:
    return [
        key
        for key, model in config["models"].items()
        if bool(model.get("enabled", True))
    ]


def model_identity(model_key: str, model: dict[str, Any]) -> dict[str, Any]:
    return {
        "model_key": model_key,
        "display_name": model["display_name"],
        "model_family": model["model_family"],
        "model_variant": model["model_variant"],
        "experiment_arm": model["experiment_arm"],
        "pair_id": model["pair_id"],
        "pair_role": model["pair_role"],
        "fold_id": model.get("fold_id"),
        "primary_anchor": bool(model.get("primary_anchor", False)),
        "served_model_id": model["served_model_id"],
        "expected_lmstudio_architecture": model.get("expected_lmstudio_architecture"),
        "chat_template": model["chat_template"],
        "gguf_template_family": model.get("gguf_template_family"),
        "system_message_policy": model.get("system_message_policy"),
        "reasoning_mode": model.get("reasoning_mode"),
        "paired_model_keys": model.get("paired_model_keys", []),
        "base_checkpoint": model.get("base_checkpoint", {}),
        "parent_base": model.get("parent_base", {}),
        "sft_artifacts": model.get("sft_artifacts", {}),
        "gguf": model.get("gguf", {}),
        "deployment": model.get("deployment", {}),
        "training_provenance": model.get("training_provenance", {}),
        "question_ids_file": model.get("question_ids_file"),
    }


def deployment_identity_id(model_key: str, model: dict[str, Any]) -> str:
    identity = model_identity(model_key, model)
    material = {
        "model_key": model_key,
        "pair_role": identity["pair_role"],
        "model_variant": identity["model_variant"],
        "base_checkpoint": identity["base_checkpoint"],
        "parent_base": identity["parent_base"],
        "sft_artifacts": identity["sft_artifacts"],
        "gguf": identity["gguf"],
        "deployment": identity["deployment"],
        "chat_template": identity["chat_template"],
        "gguf_template_family": identity["gguf_template_family"],
        "system_message_policy": identity["system_message_policy"],
        "reasoning_mode": identity["reasoning_mode"],
        "expected_lmstudio_architecture": identity["expected_lmstudio_architecture"],
    }
    return "slm-deployment-" + stable_hash(material, 16)


def formal_readiness_issues(config: dict[str, Any], model_key: str) -> list[str]:
    model = config["models"][model_key]
    issues: list[str] = []
    if bool(config.get("pipeline_test", False)):
        issues.append("pipeline_test 配置不得用于正式运行")
    if str(config.get("research_plan_version", "")) != EXPECTED_RESEARCH_PLAN_VERSION:
        issues.append(
            f"research_plan_version 必须为 {EXPECTED_RESEARCH_PLAN_VERSION}（当前方案版本）"
        )
    if int(config.get("repetitions", 0)) != 3:
        issues.append("正式运行 repetitions 必须为 3")
    if int(config.get("order_seed", -1)) != 42:
        issues.append("正式运行 order_seed 必须为 42")
    inference = config.get("inference", {})
    if not isinstance(inference, dict):
        inference = {}
    if inference.get("structured_output") != "json_schema":
        issues.append("正式运行 structured_output 必须为 json_schema")
    if inference.get("temperature") != 0:
        issues.append("正式运行 temperature 必须为 0")
    if not bool(config.get("protocol_frozen", False)):
        issues.append("config.protocol_frozen 仍为 false")
    if not bool(model.get("formal_ready", False)):
        issues.append(f"models.{model_key}.formal_ready 仍为 false")
    required_paths = {
        "served_model_id": (model, "served_model_id"),
        "base_checkpoint.modelscope_id": (model.get("base_checkpoint", {}), "modelscope_id"),
        "base_checkpoint.revision": (model.get("base_checkpoint", {}), "revision"),
        "base_checkpoint.snapshot_manifest_sha256": (
            model.get("base_checkpoint", {}),
            "snapshot_manifest_sha256",
        ),
        "gguf.filename": (model.get("gguf", {}), "filename"),
        "gguf.local_path": (model.get("gguf", {}), "local_path"),
        "gguf.sha256": (model.get("gguf", {}), "sha256"),
        "gguf.converter_commit": (model.get("gguf", {}), "converter_commit"),
        "deployment.lm_studio_app_version": (
            model.get("deployment", {}),
            "lm_studio_app_version",
        ),
        "deployment.lm_studio_runtime_version": (
            model.get("deployment", {}),
            "lm_studio_runtime_version",
        ),
        "deployment.lmstudio_load_key": (
            model.get("deployment", {}),
            "lmstudio_load_key",
        ),
        "deployment.native_model_key": (
            model.get("deployment", {}),
            "native_model_key",
        ),
        "deployment.native_selected_variant": (
            model.get("deployment", {}),
            "native_selected_variant",
        ),
        "deployment.gpu_offload": (
            model.get("deployment", {}),
            "gpu_offload",
        ),
    }
    for label, (mapping, field) in required_paths.items():
        if field == "native_selected_variant" and mapping.get(field) is None:
            continue  # 实测无变体（LM Studio 原生接口返回 null），视为已冻结
        if not isinstance(mapping, dict) or is_placeholder(mapping.get(field)):
            issues.append(f"{label} 未冻结")
    gguf = model.get("gguf", {})
    for label, value in (
        ("base_checkpoint.snapshot_manifest_sha256", model.get("base_checkpoint", {}).get("snapshot_manifest_sha256")),
        ("gguf.sha256", gguf.get("sha256")),
    ):
        if not is_placeholder(value) and not is_sha256(value):
            issues.append(f"{label} 必须是 64 位 SHA-256")
    if str(gguf.get("quantization", "")).upper() != "Q4_K_M":
        issues.append("gguf.quantization 必须为 Q4_K_M")
    if str(gguf.get("source_kind", "")) != "self_converted":
        issues.append("正式比较只允许 source_kind=self_converted")
    deployment = model.get("deployment", {})
    if not isinstance(deployment.get("context_length"), int) or int(
        deployment.get("context_length", 0)
    ) <= 0:
        issues.append("deployment.context_length 必须是正整数")
    if deployment.get("prompt_template_override") is not False:
        issues.append("正式运行禁止 LM Studio GUI 覆盖 GGUF 内嵌模板")
    if str(deployment.get("lm_studio_app_version", "")) != EXPECTED_LM_STUDIO_APP_VERSION:
        issues.append(
            f"deployment.lm_studio_app_version 必须为 {EXPECTED_LM_STUDIO_APP_VERSION}"
        )
    if model.get("model_family") == "qwen3" and model.get("reasoning_mode") != "disabled":
        issues.append("Qwen3-2507 正式运行必须禁用 reasoning")
    if model.get("pair_role") == "sft":
        if model.get("fold_id") not in {0, 1, 2, 3, 4}:
            issues.append("SFT 模型 fold_id 必须为 0–4")
        if not model.get("question_ids_file"):
            issues.append("SFT 模型必须配置该折 question_ids_file")
        parent_key = str(model.get("parent_base", {}).get("model_key", ""))
        parent = config.get("models", {}).get(parent_key)
        if not isinstance(parent, dict):
            issues.append("SFT parent_base.model_key 未绑定到已注册 Base")
        else:
            if parent.get("pair_id") != model.get("pair_id"):
                issues.append("SFT 与 Base 的 pair_id 不一致")
            if parent.get("chat_template") != model.get("chat_template"):
                issues.append("SFT 与 Base 的 chat_template 不一致")
            if parent.get("gguf", {}).get("converter_commit") != gguf.get(
                "converter_commit"
            ):
                issues.append("SFT 与 Base 必须使用同一 llama.cpp commit")
        for field in ("adapter_sha256", "merged_model_sha256"):
            value = model.get("sft_artifacts", {}).get(field)
            if is_placeholder(value):
                issues.append(f"sft_artifacts.{field} 未冻结")
            elif not is_sha256(value):
                issues.append(f"sft_artifacts.{field} 必须是 64 位 SHA-256")
        for field in (
            "split_manifest_sha256",
            "training_config_sha256",
            "llamafactory_version",
        ):
            value = model.get("training_provenance", {}).get(field)
            if is_placeholder(value):
                issues.append(f"training_provenance.{field} 未冻结")
            elif field.endswith("sha256") and not is_sha256(value):
                issues.append(f"training_provenance.{field} 必须是 64 位 SHA-256")
    return issues


def apply_chat_message_policy(
    body: dict[str, Any], model: dict[str, Any]
) -> dict[str, Any]:
    policy = str(model.get("system_message_policy", "native_system_role"))
    if policy == "native_system_role":
        return body
    if policy != "fold_system_into_first_user":
        raise ValueError(f"不支持的 system_message_policy：{policy}")
    messages = body.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValueError("无法对非 Chat Completions 请求折叠 system 消息")
    first, second = messages[0], messages[1]
    if not (
        isinstance(first, dict)
        and first.get("role") == "system"
        and isinstance(first.get("content"), str)
        and isinstance(second, dict)
        and second.get("role") == "user"
        and isinstance(second.get("content"), str)
    ):
        raise ValueError("system 折叠要求首两条消息为 system/user 文本")
    combined_user = {
        **second,
        "content": first["content"].rstrip() + "\n\n" + second["content"].lstrip(),
    }
    return {**body, "messages": [combined_user, *messages[2:]]}


def _auth_headers(server: dict[str, Any]) -> dict[str, str]:
    headers = {
        "Accept": "application/json",
        "User-Agent": "diffusion-slm-direct-benchmark/2.2",
    }
    env_name = str(server.get("api_key_env", "")).strip()
    token = str(os.environ.get(env_name, "")).strip() if env_name else ""
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _get_json(url: str, server: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    request = urllib.request.Request(url, headers=_auth_headers(server), method="GET")
    try:
        with urllib.request.urlopen(
            request, timeout=float(server.get("preflight_timeout_seconds", 10))
        ) as response:
            raw = response.read().decode("utf-8", errors="replace")
            status = int(response.status)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(
            f"无法连接 LM Studio：{url}；请先启动 Local Server。{type(exc).__name__}: {exc}"
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"LM Studio 返回的不是 JSON：{url}：{raw[:300]}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"LM Studio 响应顶层不是 JSON 对象：{url}")
    return status, payload


def fetch_server_models(config: dict[str, Any]) -> dict[str, Any]:
    server = config["server"]
    url = str(server["base_url"]).rstrip("/") + "/models"
    started = utc_now()
    status, payload = _get_json(url, server)
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, list):
        raise RuntimeError("LM Studio /models 响应缺少 data 数组")
    model_ids = sorted(
        str(item["id"])
        for item in data
        if isinstance(item, dict) and str(item.get("id", "")).strip()
    )
    return {
        "checked_at_utc": started,
        "endpoint": url,
        "http_status": status,
        "model_ids": model_ids,
        "response_sha256": stable_hash(payload),
    }


def fetch_native_models(config: dict[str, Any]) -> dict[str, Any]:
    server = config["server"]
    url = str(server.get("native_models_url", "")).strip()
    if not url:
        parsed = urllib.parse.urlsplit(str(server["base_url"]))
        url = urllib.parse.urlunsplit(
            (parsed.scheme, parsed.netloc, "/api/v1/models", "", "")
        )
    status, payload = _get_json(url, server)
    models = payload.get("models")
    if not isinstance(models, list):
        raise RuntimeError("LM Studio /api/v1/models 响应缺少 models 数组")
    return {
        "checked_at_utc": utc_now(),
        "endpoint": url,
        "http_status": status,
        "models": models,
        "response_sha256": stable_hash(payload),
    }


def preflight_model(
    config: dict[str, Any], model_key: str, config_path: Path | None = None
) -> dict[str, Any]:
    model = config["models"][model_key]
    expected = str(model["served_model_id"])
    openai_snapshot = fetch_server_models(config)
    native_snapshot = fetch_native_models(config)
    loaded_matches: list[dict[str, Any]] = []
    all_loaded_instances: list[dict[str, Any]] = []
    for native_model in native_snapshot["models"]:
        if not isinstance(native_model, dict):
            continue
        for instance in native_model.get("loaded_instances", []):
            if not isinstance(instance, dict):
                continue
            combined = {
                "id": instance.get("id"),
                "config": instance.get("config", {}),
                "model_key": native_model.get("key"),
                "type": native_model.get("type"),
                "format": native_model.get("format"),
                "architecture": native_model.get("architecture"),
                "quantization": native_model.get("quantization"),
                "selected_variant": native_model.get("selected_variant"),
                "capabilities": native_model.get("capabilities"),
            }
            all_loaded_instances.append(combined)
            if str(instance.get("id", "")) == expected:
                loaded_matches.append(combined)

    exact_loaded = len(loaded_matches) == 1
    match = loaded_matches[0] if exact_loaded else {}
    expected_arch = str(model.get("expected_lmstudio_architecture", "")).lower()
    actual_arch = str(match.get("architecture", "")).lower()
    quantization = match.get("quantization") if isinstance(match, dict) else None
    quant_name = (
        str(quantization.get("name", ""))
        if isinstance(quantization, dict)
        else ""
    )
    instance_config = match.get("config") if isinstance(match, dict) else None
    actual_context = (
        instance_config.get("context_length")
        if isinstance(instance_config, dict)
        else None
    )
    expected_context = model.get("deployment", {}).get("context_length")
    deployment = model.get("deployment", {})
    expected_native_key = deployment.get("native_model_key")
    native_key_matches = (
        True
        if is_placeholder(expected_native_key)
        else str(match.get("model_key", "")) == str(expected_native_key)
    )
    expected_selected_variant = deployment.get("native_selected_variant")
    selected_variant_matches = (
        True
        if is_placeholder(expected_selected_variant)
        else str(match.get("selected_variant", "")) == str(expected_selected_variant)
    )
    metadata_checks = {
        "type_is_llm": match.get("type") == "llm",
        "format_is_gguf": str(match.get("format", "")).lower() == "gguf",
        "architecture_matches": bool(expected_arch and actual_arch == expected_arch),
        "quantization_is_q4_k_m": quant_name.upper() == "Q4_K_M",
        "context_length_matches": actual_context == expected_context,
        "native_model_key_matches_when_frozen": native_key_matches,
        "native_selected_variant_matches_when_frozen": selected_variant_matches,
    }
    gguf = model.get("gguf", {})
    local_path_value = gguf.get("local_path")
    file_identity_required = bool(
        model.get("formal_ready", False) or gguf.get("source_kind") == "self_converted"
    )
    local_path: Path | None = None
    if not is_placeholder(local_path_value):
        base_dir = (config_path or (ROOT / "config.json")).resolve().parent
        local_path = resolve_path(base_dir, str(local_path_value))
    file_exists = bool(local_path is not None and local_path.is_file())
    actual_file_sha256 = sha256_file(local_path) if file_exists and local_path else None
    expected_file_sha256 = gguf.get("sha256")
    expected_filename = str(gguf.get("filename", ""))
    file_checks = {
        "required_for_this_run": file_identity_required,
        "path": str(local_path) if local_path else None,
        "exists": file_exists,
        "filename_matches": bool(
            file_exists and local_path and local_path.name == expected_filename
        ),
        "expected_sha256": expected_file_sha256,
        "actual_sha256": actual_file_sha256,
        "sha256_matches": bool(
            file_exists
            and is_sha256(expected_file_sha256)
            and actual_file_sha256 == str(expected_file_sha256).lower()
        ),
    }
    verified_locally = bool(
        file_checks["exists"]
        and file_checks["filename_matches"]
        and file_checks["sha256_matches"]
    )
    # 方案 v2.8：本机存在 GGUF 副本时复验文件名与字节（不一致阻断）；
    # 不存在时不阻断（部署对象由 LM Studio 原生身份核验，文件哈希以服务器
    # 回填记录为准，与 API 臂 snapshot_confirmed=false 同口径）。
    file_identity_blocking = bool(
        file_identity_required and file_exists and not verified_locally
    )
    file_identity_passed = not file_identity_blocking
    total_loaded = len(all_loaded_instances)
    single_loaded_ok = (
        total_loaded == 1
        if bool(config["server"].get("require_single_loaded_instance", True))
        else True
    )
    return {
        "checked_at_utc": utc_now(),
        "model_key": model_key,
        "expected_served_model_id": expected,
        "openai_compatible": openai_snapshot,
        "native": native_snapshot,
        "exact_model_id_present": expected in openai_snapshot["model_ids"],
        "exact_loaded_instance_count": len(loaded_matches),
        "exact_loaded_instance": match or None,
        "total_loaded_instance_count": total_loaded,
        "single_loaded_instance_requirement_passed": single_loaded_ok,
        "metadata_checks": metadata_checks,
        "gguf_file_identity": {**file_checks, "verified_locally": verified_locally, "passed": file_identity_passed},
        "passed": bool(
            expected in openai_snapshot["model_ids"]
            and exact_loaded
            and single_loaded_ok
            and all(metadata_checks.values())
            and file_identity_passed
        ),
    }


def load_question_id_filter(config_path: Path, model: dict[str, Any]) -> list[str] | None:
    raw_path = model.get("question_ids_file")
    if not raw_path:
        return None
    path = resolve_path(config_path.parent, str(raw_path))
    if not path.is_file():
        raise ValueError(f"question_ids_file 不存在：{path}")
    if path.suffix.lower() == ".json":
        payload = read_json(path)
        values = payload.get("question_ids") if isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise ValueError("question_ids_file JSON 必须是数组或含 question_ids 数组")
        ids = [str(value) for value in values]
    elif path.suffix.lower() == ".jsonl":
        ids = []
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8-sig").splitlines(), start=1
        ):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict) or not value.get("question_id"):
                raise ValueError(f"{path}:{line_number} 缺少 question_id")
            ids.append(str(value["question_id"]))
    else:
        ids = [line.strip() for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if not ids or len(ids) != len(set(ids)):
        raise ValueError("question_ids_file 为空或包含重复 question_id")
    return ids


def select_questions(
    all_questions: list[dict[str, Any]], question_ids: list[str] | None
) -> list[dict[str, Any]]:
    if question_ids is None:
        return all_questions
    by_id = {str(row["question_id"]): row for row in all_questions}
    missing = [question_id for question_id in question_ids if question_id not in by_id]
    if missing:
        raise ValueError(f"question_ids_file 包含题库外 ID：{missing[:5]}")
    return [by_id[question_id] for question_id in question_ids]


def pair_task_id(
    model: dict[str, Any],
    question_id: str,
    sample_index: int,
    prompt_family_id: str,
) -> str:
    material = {
        "pair_id": model["pair_id"],
        "question_id": str(question_id),
        "sample_index": int(sample_index),
        "prompt_family_id": str(prompt_family_id),
    }
    return "pair-task-" + stable_hash(material, 20)


def iter_run_manifests(output_root: Path) -> Iterable[tuple[Path, dict[str, Any]]]:
    if not output_root.exists():
        return []
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(output_root.glob("*/runs/*/run_manifest.json"), reverse=True):
        try:
            manifest = read_json(path)
        except (OSError, json.JSONDecodeError):
            continue
        if manifest.get("artifact_type") == "slm_direct_run_manifest":
            rows.append((path.parent, manifest))
    return rows


def incomplete_runs(config_path: Path, config: dict[str, Any], model_key: str) -> list[tuple[Path, dict[str, Any]]]:
    output_root = resolve_path(config_path.parent, config["output_root"])
    terminal = {"completed", "dry_run_complete", "invalidated"}
    return [
        (run_dir, manifest)
        for run_dir, manifest in iter_run_manifests(output_root)
        if manifest.get("model_key") == model_key and manifest.get("status") not in terminal
    ]
