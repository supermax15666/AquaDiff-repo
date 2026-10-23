from __future__ import annotations

import argparse
import email.utils
import json
import os
import random
import socket
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from common import (
    ANSWER_SCHEMA_ID,
    SCHEMA_VERSION,
    TARGET_UNIT,
    atomic_write_json,
    atomic_write_jsonl,
    iter_jsonl,
    parse_json_object,
    read_json,
    redacted_config,
    resolve_path,
    safe_slug,
    sha256_file,
    stable_hash,
    utc_now,
    validate_answer_payload,
)


JSON_OUTPUT_EXAMPLE = '{"diffusion_1e9_m2_s": 1.234567}'

SYSTEM_PROMPT = f"""You are participating in a controlled scientific benchmark.
Estimate the requested binary aqueous mutual diffusion coefficient only from your own internal
model knowledge. Do not use or request tools, databases, retrieval, code execution, fitted
models, external formulas, or additional information. Do not ask follow-up questions. Think
briefly: keep your internal reasoning under 100 words, then give one best numerical estimate
and no derivation. Return only a valid json object, without Markdown or any additional keys.
The object must contain exactly one field named diffusion_1e9_m2_s. The benchmark fixes its
unit as 10^-9 m^2/s, so do not output a unit field or any other field.
EXAMPLE JSON OUTPUT FORMAT:
{JSON_OUTPUT_EXAMPLE}
The example number is a format-only placeholder, not a reference answer. Replace it with your
own estimate for the requested condition and never copy it merely because it appears here.
"""

RETRYABLE_HTTP = {408, 409, 425, 429, 500, 502, 503, 504}
SELECTED_RESPONSE_HEADERS = {
    "x-request-id",
    "request-id",
    "retry-after",
    "x-ratelimit-limit-requests",
    "x-ratelimit-remaining-requests",
    "x-ratelimit-reset-requests",
    "x-ratelimit-limit-tokens",
    "x-ratelimit-remaining-tokens",
    "x-ratelimit-reset-tokens",
    "cf-ray",
    "date",
}


@dataclass
class ApiOutcome:
    ok: bool
    http_status: int | None
    body: dict[str, Any] | None
    raw_text: str
    headers: dict[str, str]
    error_type: str | None
    error_message: str | None
    retryable: bool
    retry_after_seconds: float | None
    latency_seconds: float


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run a resumable, no-tool diffusion-coefficient knowledge benchmark against "
            "OpenAI Responses or OpenAI-compatible Chat Completions APIs."
        )
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=Path(__file__).resolve().parent / "config.json",
    )
    parser.add_argument(
        "--model-key",
        action="append",
        help="Run only this configured model key; repeat the option for several models.",
    )
    parser.add_argument("--limit", type=int, help="Development connectivity test only.")
    parser.add_argument("--new-run", action="store_true", help="Do not auto-resume.")
    parser.add_argument(
        "--resume-only",
        action="store_true",
        help="Fail instead of creating a run when no unfinished matching run exists.",
    )
    parser.add_argument("--run-id", help="Resume the exact run ID for one selected model.")
    parser.add_argument("--dry-run", action="store_true", help="Create/validate run assets without API calls.")
    return parser.parse_args()


def provider_schema(schema: dict[str, Any]) -> dict[str, Any]:
    allowed = {"type", "properties", "required", "additionalProperties", "description"}
    cleaned = {key: value for key, value in schema.items() if key in allowed}
    return cleaned


def api_url(model: dict[str, Any]) -> str:
    if model.get("endpoint_url"):
        url = str(model["endpoint_url"])
        parsed = urllib.parse.urlsplit(url)
        secret_names = {"key", "api_key", "apikey", "token", "access_token", "secret"}
        if parsed.username or parsed.password or any(
            name.lower() in secret_names
            for name, _value in urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
        ):
            raise ValueError(
                "API URL credentials/query secrets are forbidden; use api_key_env and headers"
            )
        return url
    base = str(model["base_url"]).rstrip("/")
    endpoint = str(model.get("endpoint", "chat_completions"))
    if endpoint == "responses":
        suffix = "/responses"
    elif endpoint == "chat_completions":
        suffix = "/chat/completions"
    else:
        raise ValueError(
            f"Unsupported endpoint {endpoint!r}; use 'responses' or 'chat_completions'"
        )
    return base + suffix


def is_deepseek_api(model: dict[str, Any]) -> bool:
    if str(model.get("provider", "")).strip().lower() == "deepseek":
        return True
    raw_url = str(model.get("endpoint_url") or model.get("base_url") or "").strip()
    try:
        hostname = (urllib.parse.urlsplit(raw_url).hostname or "").lower()
    except ValueError:
        return False
    return hostname == "api.deepseek.com" or hostname.endswith(".api.deepseek.com")


def is_zhipu_api(model: dict[str, Any]) -> bool:
    if str(model.get("provider", "")).strip().lower() == "zhipu":
        return True
    raw_url = str(model.get("endpoint_url") or model.get("base_url") or "").strip()
    try:
        hostname = (urllib.parse.urlsplit(raw_url).hostname or "").lower()
    except ValueError:
        return False
    return hostname == "open.bigmodel.cn" or hostname.endswith(".bigmodel.cn")


def is_qwen_api(model: dict[str, Any]) -> bool:
    if str(model.get("provider", "")).strip().lower() in {"qwen", "dashscope"}:
        return True
    raw_url = str(model.get("endpoint_url") or model.get("base_url") or "").strip()
    try:
        hostname = (urllib.parse.urlsplit(raw_url).hostname or "").lower()
    except ValueError:
        return False
    return (
        hostname == "dashscope.aliyuncs.com"
        or hostname.endswith(".dashscope.aliyuncs.com")
    )


def is_doubao_api(model: dict[str, Any]) -> bool:
    if str(model.get("provider", "")).strip().lower() in {"doubao", "ark", "volcengine"}:
        return True
    raw_url = str(model.get("endpoint_url") or model.get("base_url") or "").strip()
    try:
        hostname = (urllib.parse.urlsplit(raw_url).hostname or "").lower()
    except ValueError:
        return False
    return hostname.endswith(".volces.com")


def is_minimax_api(model: dict[str, Any]) -> bool:
    if str(model.get("provider", "")).strip().lower() in {"minimax"}:
        return True
    raw_url = str(model.get("endpoint_url") or model.get("base_url") or "").strip()
    try:
        hostname = (urllib.parse.urlsplit(raw_url).hostname or "").lower()
    except ValueError:
        return False
    return hostname.endswith(".minimaxi.com") or hostname.endswith(".minimax.chat")


def is_kimi_api(model: dict[str, Any]) -> bool:
    if str(model.get("provider", "")).strip().lower() in {"kimi", "moonshot"}:
        return True
    raw_url = str(model.get("endpoint_url") or model.get("base_url") or "").strip()
    try:
        hostname = (urllib.parse.urlsplit(raw_url).hostname or "").lower()
    except ValueError:
        return False
    return hostname.endswith(".moonshot.cn") or hostname.endswith(".moonshot.com.cn")


def validate_model_config(model_key: str, model: dict[str, Any]) -> None:
    endpoint = str(model.get("endpoint", "chat_completions"))
    output_mode = str(model.get("structured_output", "json_schema"))
    if endpoint not in {"responses", "chat_completions"}:
        raise ValueError(
            f"Model {model_key!r}: endpoint must be 'responses' or 'chat_completions'"
        )
    if output_mode not in {"json_schema", "json_object", "none"}:
        raise ValueError(
            f"Model {model_key!r}: structured_output must be "
            "'json_schema', 'json_object', or 'none'"
        )
    if is_deepseek_api(model):
        if endpoint != "chat_completions":
            raise ValueError(
                f"Model {model_key!r}: DeepSeek JSON Output requires "
                "endpoint='chat_completions'"
            )
        if output_mode != "json_object":
            raise ValueError(
                f"Model {model_key!r}: DeepSeek JSON Output requires "
                "structured_output='json_object'"
            )
        if not api_url(model).rstrip("/").endswith("/chat/completions"):
            raise ValueError(
                f"Model {model_key!r}: DeepSeek endpoint URL must end with "
                "'/chat/completions'"
            )
        thinking = model.get("thinking")
        if not (
            isinstance(thinking, dict)
            and str(thinking.get("type", "")).strip().lower() in {"enabled", "disabled"}
        ):
            raise ValueError(
                f"Model {model_key!r}: DeepSeek config must explicitly set "
                "thinking.type to 'enabled' or 'disabled'"
            )
        if "json" not in SYSTEM_PROMPT.lower() or JSON_OUTPUT_EXAMPLE not in SYSTEM_PROMPT:
            raise ValueError(
                "DeepSeek JSON Output requires the prompt to mention json and include "
                "the expected JSON example"
            )
    if is_zhipu_api(model):
        if endpoint != "chat_completions":
            raise ValueError(
                f"Model {model_key!r}: Zhipu BigModel only supports "
                "endpoint='chat_completions'"
            )
        if output_mode == "json_schema":
            raise ValueError(
                f"Model {model_key!r}: Zhipu supports response_format json_object, "
                "not strict json_schema; use structured_output='json_object' or 'none'"
            )
        if not api_url(model).rstrip("/").endswith("/chat/completions"):
            raise ValueError(
                f"Model {model_key!r}: Zhipu endpoint URL must end with "
                "'/chat/completions'"
            )
        thinking = model.get("thinking")
        if thinking is not None and not (
            isinstance(thinking, dict)
            and str(thinking.get("type", "")).strip().lower() in {"enabled", "disabled"}
        ):
            raise ValueError(
                f"Model {model_key!r}: Zhipu thinking.type must be "
                "'enabled' or 'disabled'"
            )
    if is_qwen_api(model):
        if endpoint != "chat_completions":
            raise ValueError(
                f"Model {model_key!r}: DashScope compatible mode only supports "
                "endpoint='chat_completions'"
            )
        if output_mode == "json_schema":
            raise ValueError(
                f"Model {model_key!r}: use structured_output='json_object' or "
                "'none' for Qwen; strict json_schema is not guaranteed in "
                "compatible mode"
            )
        if not api_url(model).rstrip("/").endswith("/chat/completions"):
            raise ValueError(
                f"Model {model_key!r}: Qwen compatible-mode URL must end with "
                "'/chat/completions'"
            )
        if model.get("thinking") is not None:
            raise ValueError(
                f"Model {model_key!r}: Qwen uses enable_thinking, not "
                "'thinking'; put it in extra_body"
            )
        enable_thinking = dict(model.get("extra_body", {})).get("enable_thinking")
        if enable_thinking is not None and not isinstance(enable_thinking, bool):
            raise ValueError(
                f"Model {model_key!r}: extra_body.enable_thinking must be boolean"
            )
    if is_doubao_api(model):
        if endpoint != "chat_completions":
            raise ValueError(
                f"Model {model_key!r}: Volcano Ark only supports "
                "endpoint='chat_completions'"
            )
        if output_mode == "json_schema":
            raise ValueError(
                f"Model {model_key!r}: use structured_output='json_object' or "
                "'none' for Doubao"
            )
        if not api_url(model).rstrip("/").endswith("/chat/completions"):
            raise ValueError(
                f"Model {model_key!r}: Ark endpoint URL must end with "
                "'/chat/completions'"
            )
        thinking = model.get("thinking")
        if thinking is not None and not (
            isinstance(thinking, dict)
            and str(thinking.get("type", "")).strip().lower()
            in {"enabled", "disabled", "auto"}
        ):
            raise ValueError(
                f"Model {model_key!r}: Doubao thinking.type must be "
                "'enabled', 'disabled', or 'auto'"
            )
    if is_minimax_api(model):
        if endpoint != "chat_completions":
            raise ValueError(
                f"Model {model_key!r}: MiniMax only supports "
                "endpoint='chat_completions'"
            )
        if output_mode != "none":
            raise ValueError(
                f"Model {model_key!r}: MiniMax Chat Completions does not "
                "accept response_format; use structured_output='none'"
            )
        if not api_url(model).rstrip("/").endswith("/chat/completions"):
            raise ValueError(
                f"Model {model_key!r}: MiniMax endpoint URL must end with "
                "'/chat/completions'"
            )
        thinking = model.get("thinking")
        if not (
            isinstance(thinking, dict)
            and str(thinking.get("type", "")).strip().lower()
            in {"disabled", "adaptive"}
        ):
            raise ValueError(
                f"Model {model_key!r}: MiniMax requires explicit "
                "thinking.type of 'disabled' or 'adaptive' "
                "(omitting it defaults to adaptive thinking)"
            )
    if is_kimi_api(model):
        if endpoint != "chat_completions":
            raise ValueError(
                f"Model {model_key!r}: Kimi only supports "
                "endpoint='chat_completions'"
            )
        if output_mode == "json_schema":
            raise ValueError(
                f"Model {model_key!r}: use structured_output='json_object' or "
                "'none' for Kimi"
            )
        if not api_url(model).rstrip("/").endswith("/chat/completions"):
            raise ValueError(
                f"Model {model_key!r}: Kimi endpoint URL must end with "
                "'/chat/completions'"
            )
        if model.get("thinking") is not None:
            raise ValueError(
                f"Model {model_key!r}: Kimi K3 uses top-level reasoning_effort "
                "('low'/'high'/'max'), not 'thinking'; put it in reasoning_effort"
            )
        reasoning_effort = model.get("reasoning_effort")
        if reasoning_effort is not None and str(reasoning_effort).strip().lower() not in {
            "low",
            "high",
            "max",
        }:
            raise ValueError(
                f"Model {model_key!r}: Kimi reasoning_effort must be "
                "'low', 'high', or 'max'"
            )


def effective_execution_settings(
    config: dict[str, Any], model: dict[str, Any]
) -> dict[str, Any]:
    global_retry = config.get("retry", {})
    model_retry = model.get("retry", {})
    if not isinstance(global_retry, dict) or not isinstance(model_retry, dict):
        raise ValueError("retry settings must be JSON objects")
    merged_retry = {**global_retry, **model_retry}
    settings = {
        "timeout_seconds": float(
            model.get("timeout_seconds", config.get("timeout_seconds", 180))
        ),
        "inter_request_seconds": float(
            model.get(
                "inter_request_seconds", config.get("inter_request_seconds", 0)
            )
        ),
        "retry": {
            "max_attempts_per_sample": int(
                merged_retry.get("max_attempts_per_sample", 12)
            ),
            "max_elapsed_seconds_per_sample": float(
                merged_retry.get("max_elapsed_seconds_per_sample", 7200)
            ),
            "base_wait_seconds": float(merged_retry.get("base_wait_seconds", 10)),
            "max_wait_seconds": float(merged_retry.get("max_wait_seconds", 300)),
            "jitter_fraction": float(merged_retry.get("jitter_fraction", 0.20)),
        },
    }
    retry = settings["retry"]
    if settings["timeout_seconds"] <= 0:
        raise ValueError("timeout_seconds must be positive")
    if settings["inter_request_seconds"] < 0:
        raise ValueError("inter_request_seconds cannot be negative")
    if retry["max_attempts_per_sample"] <= 0:
        raise ValueError("max_attempts_per_sample must be positive")
    if retry["max_elapsed_seconds_per_sample"] <= 0:
        raise ValueError("max_elapsed_seconds_per_sample must be positive")
    if retry["base_wait_seconds"] < 0 or retry["max_wait_seconds"] < 0:
        raise ValueError("retry wait settings cannot be negative")
    if retry["jitter_fraction"] < 0:
        raise ValueError("jitter_fraction cannot be negative")
    return settings


def redacted_url(url: str) -> str:
    parsed = urllib.parse.urlsplit(url)
    if parsed.username or parsed.password:
        raise ValueError("API URLs must not contain embedded credentials")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    secret_names = {"key", "api_key", "apikey", "token", "access_token", "secret"}
    redacted_query = [
        (name, "<redacted>" if name.lower() in secret_names else value)
        for name, value in query
    ]
    return urllib.parse.urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urllib.parse.urlencode(redacted_query), "")
    )


def build_request_body(
    model: dict[str, Any],
    prompt: str,
    task_id: str,
    schema: dict[str, Any],
) -> dict[str, Any]:
    endpoint = str(model.get("endpoint", "chat_completions"))
    output_mode = str(model.get("structured_output", "json_schema"))
    body: dict[str, Any] = {"model": str(model["model_id"])}
    if endpoint == "responses":
        body["input"] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        body["store"] = False
        body["max_output_tokens"] = int(model.get("max_output_tokens", 512))
        if output_mode == "json_schema":
            body["text"] = {
                "format": {
                    "type": "json_schema",
                    "name": ANSWER_SCHEMA_ID,
                    "strict": True,
                    "schema": provider_schema(schema),
                }
            }
        elif output_mode == "json_object":
            body["text"] = {"format": {"type": "json_object"}}
        elif output_mode != "none":
            raise ValueError(f"Unsupported structured_output mode: {output_mode!r}")
    elif endpoint == "chat_completions":
        body["messages"] = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ]
        token_parameter = str(model.get("token_parameter", "max_tokens"))
        body[token_parameter] = int(model.get("max_output_tokens", 512))
        if output_mode == "json_schema":
            body["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": ANSWER_SCHEMA_ID,
                    "strict": True,
                    "schema": provider_schema(schema),
                },
            }
        elif output_mode == "json_object":
            body["response_format"] = {"type": "json_object"}
        elif output_mode != "none":
            raise ValueError(f"Unsupported structured_output mode: {output_mode!r}")
    else:
        raise ValueError(f"Unsupported endpoint: {endpoint!r}")

    if model.get("temperature") is not None:
        body["temperature"] = float(model["temperature"])
    if model.get("seed") is not None:
        body["seed"] = int(model["seed"])
    if model.get("reasoning") is not None:
        body["reasoning"] = model["reasoning"]
    if model.get("thinking") is not None:
        body["thinking"] = model["thinking"]
    if model.get("reasoning_effort") is not None:
        body["reasoning_effort"] = model["reasoning_effort"]
    for key, value in dict(model.get("extra_body", {})).items():
        if key in body:
            raise ValueError(f"extra_body cannot override managed request field {key!r}")
        body[key] = value
    if endpoint == "responses" and bool(model.get("send_metadata", True)):
        body["metadata"] = {"benchmark": "llm_api_direct_v1", "task_id": task_id[:64]}
    return body


def request_headers(model: dict[str, Any]) -> dict[str, str]:
    api_key = str(model.get("api_key_value", "")).strip()
    if not api_key:
        env_name = str(model.get("api_key_env", "")).strip()
        if not env_name:
            raise ValueError("Configure api_key in config.json or api_key_env")
        api_key = str(os.environ.get(env_name, "")).strip()
        if not api_key:
            raise RuntimeError(f"Environment variable {env_name!r} is not set")
    header_name = str(model.get("auth_header", "Authorization"))
    scheme = str(model.get("auth_scheme", "Bearer")).strip()
    credential = f"{scheme} {api_key}".strip()
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "diffusion-internal-knowledge-benchmark/1.0",
        header_name: credential,
    }
    for key, value in dict(model.get("extra_headers", {})).items():
        if key.lower() in {"authorization", "x-api-key", header_name.lower()}:
            raise ValueError("Authentication secrets must use api_key_env, not extra_headers")
        headers[str(key)] = str(value)
    return headers


def selected_headers(headers: Any) -> dict[str, str]:
    result: dict[str, str] = {}
    if headers is None:
        return result
    for key, value in headers.items():
        if str(key).lower() in SELECTED_RESPONSE_HEADERS:
            result[str(key).lower()] = str(value)
    return result


def retry_after_seconds(headers: dict[str, str]) -> float | None:
    value = headers.get("retry-after")
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
            now = datetime.now(parsed.tzinfo or timezone.utc)
            return max(0.0, (parsed - now).total_seconds())
        except (TypeError, ValueError, OverflowError):
            return None


def post_json(url: str, body: dict[str, Any], headers: dict[str, str], timeout: float) -> ApiOutcome:
    request = urllib.request.Request(
        url=url,
        data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            kept_headers = selected_headers(response.headers)
            status = int(response.status)
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("top-level response is not an object")
        except (json.JSONDecodeError, ValueError) as exc:
            return ApiOutcome(
                False,
                status,
                None,
                raw,
                kept_headers,
                "invalid_response_json",
                str(exc),
                True,
                retry_after_seconds(kept_headers),
                time.perf_counter() - started,
            )
        return ApiOutcome(
            True,
            status,
            parsed,
            raw,
            kept_headers,
            None,
            None,
            False,
            retry_after_seconds(kept_headers),
            time.perf_counter() - started,
        )
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        kept_headers = selected_headers(exc.headers)
        # LM Studio deployment-state errors (e.g. "No models loaded") are
        # infrastructure failures per plan §8, not provider rejections:
        # mark them retryable so the >5% infrastructure pause can trigger.
        deployment_state_error = "No models loaded" in raw
        return ApiOutcome(
            False,
            int(exc.code),
            None,
            raw,
            kept_headers,
            "http_error",
            f"HTTP {exc.code}: {raw[:1000]}",
            deployment_state_error or int(exc.code) in RETRYABLE_HTTP,
            retry_after_seconds(kept_headers),
            time.perf_counter() - started,
        )
    except (urllib.error.URLError, TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
        return ApiOutcome(
            False,
            None,
            None,
            "",
            {},
            type(exc).__name__,
            str(exc),
            True,
            None,
            time.perf_counter() - started,
        )


def extract_response_text(body: dict[str, Any], endpoint: str) -> tuple[str, str | None]:
    if endpoint == "responses":
        if isinstance(body.get("output_text"), str):
            return body["output_text"].strip(), None
        text_parts: list[str] = []
        refusals: list[str] = []
        for item in body.get("output", []) if isinstance(body.get("output"), list) else []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content", []) if isinstance(item.get("content"), list) else []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") in {"output_text", "text"} and isinstance(content.get("text"), str):
                    text_parts.append(content["text"])
                if content.get("type") == "refusal" and isinstance(content.get("refusal"), str):
                    refusals.append(content["refusal"])
        return "\n".join(text_parts).strip(), "\n".join(refusals).strip() or None

    choices = body.get("choices")
    if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
        return "", None
    message = choices[0].get("message")
    if not isinstance(message, dict):
        return "", None
    refusal = message.get("refusal") if isinstance(message.get("refusal"), str) else None
    content = message.get("content")
    if isinstance(content, str):
        return content.strip(), refusal
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts).strip(), refusal
    return "", refusal


def response_metadata(body: dict[str, Any], endpoint: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "provider_response_id": body.get("id"),
        "returned_model_id": body.get("model"),
        "system_fingerprint": body.get("system_fingerprint"),
        "provider_status": body.get("status"),
        "usage": body.get("usage") if isinstance(body.get("usage"), dict) else None,
    }
    if endpoint == "chat_completions":
        choices = body.get("choices")
        first = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
        metadata["finish_reason"] = first.get("finish_reason")
    else:
        metadata["incomplete_details"] = body.get("incomplete_details")
        metadata["error"] = body.get("error")
    return metadata


def response_quality(answer: dict[str, Any] | None) -> dict[str, Any]:
    valid, validation_errors = validate_answer_payload(answer)
    prediction = answer.get("diffusion_1e9_m2_s") if isinstance(answer, dict) else None
    numeric = (
        valid
        and isinstance(prediction, (int, float))
        and not isinstance(prediction, bool)
        and float(prediction) > 0
    )
    return {
        "answer_schema_valid": valid,
        "answer_schema_errors": validation_errors,
        "parsed_prediction_1e9_m2_s": float(prediction) if numeric else None,
        "positive_prediction": bool(numeric and float(prediction) > 0),
        "canonical_unit": TARGET_UNIT,
        "unit_source": "benchmark_fixed",
        "unit_correct": bool(valid),
        "valid_numeric_response": bool(numeric),
    }


def interrupted_retry_budget_result(
    manifest: dict[str, Any],
    task: sqlite3.Row,
    question: dict[str, Any],
    model_key: str,
    model: dict[str, Any],
    attempt_count: int,
    elapsed_seconds: float,
    max_attempts: int,
    max_elapsed: float,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "task_id": str(task["task_id"]),
        "queue_index": int(task["queue_index"]),
        "question_id": question["question_id"],
        "base_prompt_id": question["base_prompt_id"],
        "template_family_id": question["template_family_id"],
        "sample_index": int(task["sample_index"]),
        "model_key": model_key,
        "provider": model.get("provider"),
        "requested_model_id": model["model_id"],
        "question": {
            "system": question["system"],
            "temperature_K": question["temperature_K"],
            "concentration_mol_L": question["concentration_mol_L"],
            "evidence_level": question.get("evidence_level"),
        },
        "prompt": str(question["prompt"]),
        "request_success": False,
        "infrastructure_failure": True,
        "attempt_count": attempt_count,
        "latency_seconds_final_attempt": None,
        "error": {
            "type": "interrupted_after_retry_budget_exhausted",
            "message": (
                "The prior process stopped after reserving the last allowed attempt but "
                "before saving a terminal result; no extra paid request was sent on resume."
            ),
            "http_status": None,
            "retryable": True,
            "retry_exhausted": True,
            "max_attempts_per_sample": max_attempts,
            "max_elapsed_seconds_per_sample": max_elapsed,
            "persisted_attempt_latency_seconds": elapsed_seconds,
        },
        "raw_answer_text": None,
        "provider_refusal": None,
        "parsed_answer": None,
        "response_quality": response_quality(None),
        "response_metadata": None,
        "accepted_response_path": None,
        "accepted_response_sha256": None,
        "completed_at_utc": utc_now(),
    }


def provider_response_error(
    body: dict[str, Any], endpoint: str
) -> tuple[str, bool] | None:
    if endpoint == "chat_completions":
        base_resp = body.get("base_resp")
        if isinstance(base_resp, dict) and int(base_resp.get("status_code") or 0) != 0:
            code = int(base_resp["status_code"])
            message = json.dumps(base_resp, ensure_ascii=False)[:1000]
            retryable = code in {1000, 1001, 1002, 1013}
            return message, retryable
    error = body.get("error")
    if error:
        return json.dumps(error, ensure_ascii=False)[:1000], True
    if endpoint == "responses":
        status = body.get("status")
        if status in {"failed", "cancelled", "incomplete"}:
            detail = body.get("incomplete_details") or status
            return json.dumps(detail, ensure_ascii=False)[:1000], True
    return None


def open_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA synchronous=FULL")
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            queue_index INTEGER NOT NULL UNIQUE,
            question_id TEXT NOT NULL,
            sample_index INTEGER NOT NULL,
            question_json TEXT NOT NULL,
            status TEXT NOT NULL,
            attempt_count INTEGER NOT NULL DEFAULT 0,
            retry_elapsed_seconds REAL NOT NULL DEFAULT 0,
            result_json TEXT,
            created_at_utc TEXT NOT NULL,
            updated_at_utc TEXT NOT NULL,
            UNIQUE(question_id, sample_index)
        );
        CREATE TABLE IF NOT EXISTS attempts (
            task_id TEXT NOT NULL,
            attempt_number INTEGER NOT NULL,
            started_at_utc TEXT NOT NULL,
            completed_at_utc TEXT NOT NULL,
            http_status INTEGER,
            retryable INTEGER NOT NULL,
            latency_seconds REAL NOT NULL,
            request_path TEXT NOT NULL,
            request_sha256 TEXT NOT NULL,
            response_path TEXT NOT NULL,
            response_sha256 TEXT NOT NULL,
            error_type TEXT,
            error_message TEXT,
            PRIMARY KEY(task_id, attempt_number)
        );
        """
    )
    task_columns = {
        str(row[1]) for row in connection.execute("PRAGMA table_info(tasks)")
    }
    if "retry_elapsed_seconds" not in task_columns:
        connection.execute(
            "ALTER TABLE tasks ADD COLUMN retry_elapsed_seconds REAL NOT NULL DEFAULT 0"
        )
    connection.execute(
        """
        UPDATE tasks
        SET retry_elapsed_seconds = MAX(
            retry_elapsed_seconds,
            COALESCE(
                (SELECT SUM(attempts.latency_seconds)
                 FROM attempts WHERE attempts.task_id = tasks.task_id),
                0
            )
        )
        """
    )
    recovered = connection.execute(
        "UPDATE tasks SET status='pending', updated_at_utc=? WHERE status='in_progress'",
        (utc_now(),),
    ).rowcount
    connection.commit()
    if recovered:
        print(f"Recovered {recovered} interrupted task(s).")
    return connection


def initialize_tasks(
    connection: sqlite3.Connection,
    questions: list[dict[str, Any]],
    repetitions: int,
    order_seed: int,
    fingerprint: str,
) -> None:
    if connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]:
        return
    queue: list[tuple[dict[str, Any], int]] = [
        (question, sample_index)
        for question in questions
        for sample_index in range(1, repetitions + 1)
    ]
    random.Random(order_seed).shuffle(queue)
    now = utc_now()
    for queue_index, (question, sample_index) in enumerate(queue, start=1):
        task_id = stable_hash(
            {
                "fingerprint": fingerprint,
                "question_id": question["question_id"],
                "sample_index": sample_index,
            },
            32,
        )
        connection.execute(
            """
            INSERT INTO tasks(
                task_id, queue_index, question_id, sample_index, question_json,
                status, attempt_count, created_at_utc, updated_at_utc
            ) VALUES (?, ?, ?, ?, ?, 'pending', 0, ?, ?)
            """,
            (
                task_id,
                queue_index,
                question["question_id"],
                sample_index,
                json.dumps(question, ensure_ascii=False, sort_keys=True),
                now,
                now,
            ),
        )
    connection.commit()


def run_counts(connection: sqlite3.Connection) -> dict[str, int]:
    counts = {str(row[0]): int(row[1]) for row in connection.execute("SELECT status, COUNT(*) FROM tasks GROUP BY status")}
    counts["total"] = int(connection.execute("SELECT COUNT(*) FROM tasks").fetchone()[0])
    counts["terminal"] = counts.get("completed", 0) + counts.get("terminal_failure", 0)
    return counts


def rebuild_results(connection: sqlite3.Connection, path: Path) -> None:
    records = []
    for row in connection.execute(
        "SELECT result_json FROM tasks WHERE result_json IS NOT NULL ORDER BY queue_index"
    ):
        records.append(json.loads(row[0]))
    atomic_write_jsonl(path, records)


def wait_with_progress(seconds: float, progress_path: Path, progress: dict[str, Any]) -> None:
    deadline = time.monotonic() + max(0.0, seconds)
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        progress["state"] = "waiting_before_retry"
        progress["retry_wait_remaining_seconds"] = round(remaining, 1)
        progress["updated_at_utc"] = utc_now()
        atomic_write_json(progress_path, progress)
        time.sleep(min(30.0, remaining))


def calculate_wait(retry: dict[str, Any], attempt: int, retry_after: float | None, task_id: str) -> float:
    base = float(retry.get("base_wait_seconds", 10))
    maximum = float(retry.get("max_wait_seconds", 300))
    jitter_fraction = max(0.0, float(retry.get("jitter_fraction", 0.20)))
    exponential = min(maximum, base * (2 ** max(0, attempt - 1)))
    deterministic = random.Random(f"{task_id}:{attempt}").uniform(-jitter_fraction, jitter_fraction)
    wait = max(0.0, exponential * (1.0 + deterministic))
    if retry_after is not None:
        wait = max(wait, retry_after)
    return min(maximum, wait)


def find_resume_run(model_dir: Path, fingerprint: str) -> Path | None:
    runs_dir = model_dir / "runs"
    if not runs_dir.exists():
        return None
    candidates: list[Path] = []
    for manifest_path in runs_dir.glob("*/run_manifest.json"):
        try:
            manifest = read_json(manifest_path)
        except Exception:
            continue
        if (
            manifest.get("run_fingerprint") == fingerprint
            and manifest.get("status")
            not in {"completed", "invalidated", "dry_run_complete"}
        ):
            candidates.append(manifest_path.parent)
    return sorted(candidates, reverse=True)[0] if candidates else None


def prepare_run(
    config_path: Path,
    config: dict[str, Any],
    model_key: str,
    model: dict[str, Any],
    questions: list[dict[str, Any]],
    question_path: Path,
    answer_schema_path: Path,
    output_root: Path,
    force_new: bool,
    requested_run_id: str | None,
    resume_only: bool,
) -> tuple[Path, dict[str, Any], str]:
    model_slug = safe_slug(f"{model.get('provider', 'provider')}__{model_key}__{model['model_id']}")
    model_dir = output_root / model_slug
    selected_questions = [
        {
            "question_id": str(question["question_id"]),
            "record_sha256": stable_hash(question),
        }
        for question in questions
    ]
    selected_question_set_sha256 = stable_hash(selected_questions)
    execution_settings = effective_execution_settings(config, model)
    analysis_sets_path = resolve_path(
        config_path.parent, config["analysis_sets_file"]
    )
    protocol_material = {
        "schema_version": SCHEMA_VERSION,
        "model_key": model_key,
        "model": redacted_config(model),
        "question_set_sha256": sha256_file(question_path),
        "selected_question_set_sha256": selected_question_set_sha256,
        "selected_question_count": len(questions),
        "analysis_sets_sha256": sha256_file(analysis_sets_path),
        "answer_schema_sha256": sha256_file(answer_schema_path),
        "system_prompt": SYSTEM_PROMPT,
        "repetitions": int(config.get("repetitions", 3)),
        "order_seed": int(config.get("order_seed", 42)),
        "execution_settings": execution_settings,
        "runner_sha256": sha256_file(Path(__file__).resolve()),
    }
    fingerprint = stable_hash(protocol_material)
    if requested_run_id:
        run_dir = model_dir / "runs" / safe_slug(requested_run_id)
        if not run_dir.exists():
            raise FileNotFoundError(f"Run does not exist: {run_dir}")
        existing = read_json(run_dir / "run_manifest.json")
        if existing.get("run_fingerprint") != fingerprint:
            raise ValueError("Requested run fingerprint does not match the current protocol/config")
        return run_dir, existing, fingerprint

    resumed = None if force_new else find_resume_run(model_dir, fingerprint)
    if resumed:
        print(f"Resuming: {resumed}")
        return resumed, read_json(resumed / "run_manifest.json"), fingerprint
    if resume_only:
        raise RuntimeError("没有找到可续跑的未完成正式任务，请先在启动菜单选择 2。")

    started = datetime.now(timezone.utc)
    run_id = started.strftime("%Y%m%dT%H%M%S%fZ") + "_" + fingerprint[:10]
    run_dir = model_dir / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "raw" / "requests").mkdir(parents=True)
    (run_dir / "raw" / "responses").mkdir(parents=True)
    manifest = {
        "schema_version": SCHEMA_VERSION,
        "artifact_type": "llm_api_direct_run_manifest",
        "run_id": run_id,
        "run_fingerprint": fingerprint,
        "status": "initialized",
        "evidence_level": model.get("evidence_level", "exploratory"),
        "snapshot_confirmed": bool(model.get("snapshot_confirmed", False)),
        "model_key": model_key,
        "provider": model.get("provider"),
        "requested_model_id": model["model_id"],
        "endpoint_type": model.get("endpoint", "chat_completions"),
        "endpoint_url_redacted": redacted_url(api_url(model)),
        "access_started_at_utc": started.isoformat(),
        "access_completed_at_utc": None,
        "question_set": {
            "path": str(question_path),
            "sha256": sha256_file(question_path),
            "count": len(questions),
            "selected_records_sha256": selected_question_set_sha256,
        },
        "analysis_sets": {
            "path": str(analysis_sets_path),
            "sha256": sha256_file(analysis_sets_path),
        },
        "response_schema": {
            "path": str(answer_schema_path),
            "sha256": sha256_file(answer_schema_path),
            "schema_id": ANSWER_SCHEMA_ID,
        },
        "system_prompt": SYSTEM_PROMPT,
        "system_prompt_sha256": stable_hash(SYSTEM_PROMPT),
        "decoding_and_transport": redacted_config(model),
        "execution_settings": execution_settings,
        "repetitions_per_base_prompt": int(config.get("repetitions", 3)),
        "independent_sample_unit": "base_prompt_id",
        "new_session_per_request": True,
        "tools_provided": False,
        "retrieval_provided": False,
        "gold_sent_to_model": False,
        "randomized_request_order": True,
        "order_seed": int(config.get("order_seed", 42)),
        "runner": {
            "path": str(Path(__file__).resolve()),
            "sha256": sha256_file(Path(__file__).resolve()),
            "python_version": sys.version,
        },
        "config": {
            "path": str(config_path),
            "sha256": sha256_file(config_path),
            "redacted": redacted_config(config),
        },
        "counts": {},
        "returned_model_ids": [],
        "system_fingerprints": [],
        "raw_response_inventory_sha256": None,
        "results_sha256": None,
        "protocol_material_sha256": fingerprint,
        "notes": [
            "Retries are transport recovery for one logical sample; retry attempts are not independent observations.",
            "A provider alias without a confirmed immutable snapshot remains exploratory.",
        ],
    }
    atomic_write_json(run_dir / "protocol_material.json", protocol_material)
    atomic_write_json(run_dir / "run_manifest.json", manifest)
    return run_dir, manifest, fingerprint


def raw_inventory(run_dir: Path) -> list[dict[str, Any]]:
    records = []
    for kind in ("requests", "responses"):
        for path in sorted((run_dir / "raw" / kind).glob("*.json")):
            records.append(
                {
                    "kind": kind[:-1],
                    "relative_path": path.relative_to(run_dir).as_posix(),
                    "bytes": path.stat().st_size,
                    "sha256": sha256_file(path),
                }
            )
    return records


def run_model(
    config_path: Path,
    config: dict[str, Any],
    model_key: str,
    model: dict[str, Any],
    questions: list[dict[str, Any]],
    question_path: Path,
    answer_schema_path: Path,
    output_root: Path,
    *,
    force_new: bool,
    requested_run_id: str | None,
    dry_run: bool,
    resume_only: bool,
) -> Path:
    answer_schema = read_json(answer_schema_path)
    run_dir, manifest, fingerprint = prepare_run(
        config_path,
        config,
        model_key,
        model,
        questions,
        question_path,
        answer_schema_path,
        output_root,
        force_new,
        requested_run_id,
        resume_only,
    )
    database_path = run_dir / "state.sqlite3"
    connection = open_database(database_path)
    initialize_tasks(
        connection,
        questions,
        int(config.get("repetitions", 3)),
        int(config.get("order_seed", 42)),
        fingerprint,
    )
    results_path = run_dir / "sample_results.jsonl"
    progress_path = run_dir / "progress.json"
    execution_settings = effective_execution_settings(config, model)
    retry = dict(execution_settings["retry"])
    max_attempts = int(retry.get("max_attempts_per_sample", 12))
    max_elapsed = float(retry.get("max_elapsed_seconds_per_sample", 7200))
    timeout = float(execution_settings["timeout_seconds"])
    inter_request = float(execution_settings["inter_request_seconds"])
    url = api_url(model)
    headers = None if dry_run else request_headers(model)

    manifest["status"] = "dry_run" if dry_run else "running"
    manifest["counts"] = run_counts(connection)
    atomic_write_json(run_dir / "run_manifest.json", manifest)
    progress = {
        "schema_version": SCHEMA_VERSION,
        "run_id": manifest["run_id"],
        "state": manifest["status"],
        "counts": manifest["counts"],
        "updated_at_utc": utc_now(),
    }
    atomic_write_json(progress_path, progress)
    if dry_run:
        rebuild_results(connection, results_path)
        manifest["status"] = "dry_run_complete"
        manifest["counts"] = run_counts(connection)
        atomic_write_json(run_dir / "run_manifest.json", manifest)
        progress.update(
            {
                "state": "dry_run_complete",
                "counts": manifest["counts"],
                "updated_at_utc": utc_now(),
            }
        )
        atomic_write_json(progress_path, progress)
        connection.close()
        return run_dir

    try:
        deployment_abort = False
        while True:
            task = connection.execute(
                "SELECT * FROM tasks WHERE status='pending' ORDER BY queue_index LIMIT 1"
            ).fetchone()
            if task is None:
                break
            task_id = str(task["task_id"])
            question = json.loads(task["question_json"])
            persisted_attempt_count = int(task["attempt_count"])
            prior_attempt_elapsed = float(task["retry_elapsed_seconds"])
            if persisted_attempt_count >= max_attempts or prior_attempt_elapsed >= max_elapsed:
                terminal_result = interrupted_retry_budget_result(
                    manifest,
                    task,
                    question,
                    model_key,
                    model,
                    persisted_attempt_count,
                    prior_attempt_elapsed,
                    max_attempts,
                    max_elapsed,
                )
                connection.execute(
                    "UPDATE tasks SET status='terminal_failure', result_json=?, "
                    "updated_at_utc=? WHERE task_id=?",
                    (
                        json.dumps(
                            terminal_result,
                            ensure_ascii=False,
                            sort_keys=True,
                            allow_nan=False,
                        ),
                        utc_now(),
                        task_id,
                    ),
                )
                connection.commit()
                rebuild_results(connection, results_path)
                progress.update(
                    {
                        "state": "running",
                        "counts": run_counts(connection),
                        "last_completed_task_id": task_id,
                        "updated_at_utc": utc_now(),
                    }
                )
                atomic_write_json(progress_path, progress)
                continue
            attempt_start_monotonic = time.monotonic()
            terminal_result: dict[str, Any] | None = None
            while True:
                attempt = int(
                    connection.execute(
                        "SELECT attempt_count FROM tasks WHERE task_id=?", (task_id,)
                    ).fetchone()[0]
                ) + 1
                connection.execute(
                    "UPDATE tasks SET status='in_progress', attempt_count=?, updated_at_utc=? WHERE task_id=?",
                    (attempt, utc_now(), task_id),
                )
                connection.commit()
                prompt = str(question["prompt"])
                body = build_request_body(model, prompt, task_id, answer_schema)
                request_record = {
                    "schema_version": SCHEMA_VERSION,
                    "task_id": task_id,
                    "question_id": question["question_id"],
                    "sample_index": int(task["sample_index"]),
                    "attempt_number": attempt,
                    "created_at_utc": utc_now(),
                    "method": "POST",
                    "url": redacted_url(url),
                    "headers": {"Content-Type": "application/json", "Accept": "application/json"},
                    "body": body,
                    "gold_in_request": False,
                }
                request_path = run_dir / "raw" / "requests" / f"{task_id}_a{attempt:02d}.json"
                atomic_write_json(request_path, request_record)
                started_at = utc_now()
                print(
                    f"[{int(task['queue_index'])}/{run_counts(connection)['total']}] "
                    f"{question['question_id']} sample={int(task['sample_index'])} attempt={attempt}"
                )
                elapsed_before_request = (
                    prior_attempt_elapsed + time.monotonic() - attempt_start_monotonic
                )
                remaining_elapsed = max_elapsed - elapsed_before_request
                if remaining_elapsed <= 0:
                    raise RuntimeError(
                        f"Task {task_id} exhausted elapsed retry budget before request"
                    )
                outcome = post_json(
                    url, body, headers or {}, min(timeout, remaining_elapsed)
                )
                endpoint = str(model.get("endpoint", "chat_completions"))
                if outcome.ok and outcome.body is not None:
                    response_error = provider_response_error(outcome.body, endpoint)
                    if response_error is not None:
                        message, provider_retryable = response_error
                        outcome = ApiOutcome(
                            ok=False,
                            http_status=outcome.http_status,
                            body=outcome.body,
                            raw_text=outcome.raw_text,
                            headers=outcome.headers,
                            error_type="provider_response_error",
                            error_message=message,
                            retryable=provider_retryable,
                            retry_after_seconds=outcome.retry_after_seconds,
                            latency_seconds=outcome.latency_seconds,
                        )
                completed_at = utc_now()
                response_record = {
                    "schema_version": SCHEMA_VERSION,
                    "task_id": task_id,
                    "question_id": question["question_id"],
                    "sample_index": int(task["sample_index"]),
                    "attempt_number": attempt,
                    "started_at_utc": started_at,
                    "completed_at_utc": completed_at,
                    "http_status": outcome.http_status,
                    "selected_headers": outcome.headers,
                    "body": outcome.body,
                    "raw_text_if_not_json": outcome.raw_text if outcome.body is None else None,
                    "error_type": outcome.error_type,
                    "error_message": outcome.error_message,
                    "retryable": outcome.retryable,
                    "latency_seconds": outcome.latency_seconds,
                }
                response_path = run_dir / "raw" / "responses" / f"{task_id}_a{attempt:02d}.json"
                atomic_write_json(response_path, response_record)
                connection.execute(
                    """
                    INSERT INTO attempts(
                        task_id, attempt_number, started_at_utc, completed_at_utc,
                        http_status, retryable, latency_seconds, request_path,
                        request_sha256, response_path, response_sha256, error_type, error_message
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        task_id,
                        attempt,
                        started_at,
                        completed_at,
                        outcome.http_status,
                        int(outcome.retryable),
                        outcome.latency_seconds,
                        request_path.relative_to(run_dir).as_posix(),
                        sha256_file(request_path),
                        response_path.relative_to(run_dir).as_posix(),
                        sha256_file(response_path),
                        outcome.error_type,
                        outcome.error_message,
                    ),
                )
                connection.execute(
                    "UPDATE tasks SET retry_elapsed_seconds = retry_elapsed_seconds + ? "
                    "WHERE task_id=?",
                    (outcome.latency_seconds, task_id),
                )
                connection.commit()

                elapsed = float(
                    connection.execute(
                        "SELECT retry_elapsed_seconds FROM tasks WHERE task_id=?",
                        (task_id,),
                    ).fetchone()[0]
                )
                if outcome.ok and outcome.body is not None:
                    answer_text, provider_refusal = extract_response_text(outcome.body, endpoint)
                    answer = parse_json_object(answer_text)
                    scored = response_quality(answer)
                    terminal_result = {
                            "schema_version": SCHEMA_VERSION,
                            "run_id": manifest["run_id"],
                            "task_id": task_id,
                            "queue_index": int(task["queue_index"]),
                            "question_id": question["question_id"],
                            "base_prompt_id": question["base_prompt_id"],
                            "template_family_id": question["template_family_id"],
                            "sample_index": int(task["sample_index"]),
                            "model_key": model_key,
                            "provider": model.get("provider"),
                            "requested_model_id": model["model_id"],
                            "question": {
                                "system": question["system"],
                                "temperature_K": question["temperature_K"],
                                "concentration_mol_L": question["concentration_mol_L"],
                                "evidence_level": question.get("evidence_level"),
                            },
                            "prompt": prompt,
                            "request_success": True,
                            "infrastructure_failure": False,
                            "attempt_count": attempt,
                            "latency_seconds_final_attempt": outcome.latency_seconds,
                            "raw_answer_text": answer_text,
                            "provider_refusal": provider_refusal,
                            "parsed_answer": answer,
                            "response_quality": scored,
                            "response_metadata": response_metadata(outcome.body, endpoint),
                            "accepted_response_path": response_path.relative_to(run_dir).as_posix(),
                            "accepted_response_sha256": sha256_file(response_path),
                            "completed_at_utc": completed_at,
                    }
                    break

                exhausted = attempt >= max_attempts or elapsed >= max_elapsed
                if not outcome.retryable or exhausted:
                    terminal_result = {
                        "schema_version": SCHEMA_VERSION,
                        "run_id": manifest["run_id"],
                        "task_id": task_id,
                        "queue_index": int(task["queue_index"]),
                        "question_id": question["question_id"],
                        "base_prompt_id": question["base_prompt_id"],
                        "template_family_id": question["template_family_id"],
                        "sample_index": int(task["sample_index"]),
                        "model_key": model_key,
                        "provider": model.get("provider"),
                        "requested_model_id": model["model_id"],
                        "question": {
                            "system": question["system"],
                            "temperature_K": question["temperature_K"],
                            "concentration_mol_L": question["concentration_mol_L"],
                            "evidence_level": question.get("evidence_level"),
                        },
                        "prompt": prompt,
                        "request_success": False,
                        "infrastructure_failure": bool(outcome.retryable),
                        "attempt_count": attempt,
                        "latency_seconds_final_attempt": outcome.latency_seconds,
                        "error": {
                            "type": outcome.error_type,
                            "message": outcome.error_message,
                            "http_status": outcome.http_status,
                            "retryable": outcome.retryable,
                            "retry_exhausted": bool(outcome.retryable and exhausted),
                        },
                        "raw_answer_text": None,
                        "provider_refusal": None,
                        "parsed_answer": None,
                        "response_quality": response_quality(None),
                        "response_metadata": None,
                        "accepted_response_path": response_path.relative_to(run_dir).as_posix(),
                        "accepted_response_sha256": sha256_file(response_path),
                        "completed_at_utc": completed_at,
                    }
                    if outcome.error_message and "No models loaded" in str(outcome.error_message):
                        deployment_abort = True
                        terminal_result["infrastructure_failure"] = True
                        terminal_result["error"]["deployment_state_error"] = True
                    break

                wait_seconds = calculate_wait(retry, attempt, outcome.retry_after_seconds, task_id)
                if elapsed + wait_seconds >= max_elapsed:
                    terminal_result = {
                        "schema_version": SCHEMA_VERSION,
                        "run_id": manifest["run_id"],
                        "task_id": task_id,
                        "queue_index": int(task["queue_index"]),
                        "question_id": question["question_id"],
                        "base_prompt_id": question["base_prompt_id"],
                        "template_family_id": question["template_family_id"],
                        "sample_index": int(task["sample_index"]),
                        "model_key": model_key,
                        "provider": model.get("provider"),
                        "requested_model_id": model["model_id"],
                        "question": {
                            "system": question["system"],
                            "temperature_K": question["temperature_K"],
                            "concentration_mol_L": question["concentration_mol_L"],
                            "evidence_level": question.get("evidence_level"),
                        },
                        "prompt": prompt,
                        "request_success": False,
                        "infrastructure_failure": True,
                        "attempt_count": attempt,
                        "latency_seconds_final_attempt": outcome.latency_seconds,
                        "error": {
                            "type": outcome.error_type,
                            "message": outcome.error_message,
                            "http_status": outcome.http_status,
                            "retryable": True,
                            "retry_exhausted": True,
                            "next_wait_would_exceed_elapsed_budget": True,
                        },
                        "raw_answer_text": None,
                        "provider_refusal": None,
                        "parsed_answer": None,
                        "response_quality": response_quality(None),
                        "response_metadata": None,
                        "accepted_response_path": response_path.relative_to(run_dir).as_posix(),
                        "accepted_response_sha256": sha256_file(response_path),
                        "completed_at_utc": completed_at,
                    }
                    break
                if outcome.error_message and "No models loaded" in str(outcome.error_message):
                    print(
                        f"⚠ LM Studio 未加载模型：第 {attempt}/{max_attempts} 次尝试失败，"
                        f"等待 {wait_seconds:.1f}s 后自动重试（在 LM Studio 加载模型后无需重启）。"
                    )
                else:
                    print(
                        f"  transient {outcome.error_type}: {outcome.error_message}; "
                        f"waiting {wait_seconds:.1f}s (progress saved)"
                    )
                connection.execute(
                    "UPDATE tasks SET status='pending', updated_at_utc=? WHERE task_id=?",
                    (utc_now(), task_id),
                )
                connection.commit()
                wait_started = time.monotonic()
                try:
                    wait_with_progress(wait_seconds, progress_path, progress)
                finally:
                    actual_wait = max(0.0, time.monotonic() - wait_started)
                    connection.execute(
                        "UPDATE tasks SET retry_elapsed_seconds = "
                        "retry_elapsed_seconds + ?, updated_at_utc=? WHERE task_id=?",
                        (actual_wait, utc_now(), task_id),
                    )
                    connection.commit()

            assert terminal_result is not None
            terminal_status = "completed" if terminal_result["request_success"] else "terminal_failure"
            connection.execute(
                "UPDATE tasks SET status=?, result_json=?, updated_at_utc=? WHERE task_id=?",
                (
                    terminal_status,
                    json.dumps(terminal_result, ensure_ascii=False, sort_keys=True, allow_nan=False),
                    utc_now(),
                    task_id,
                ),
            )
            connection.commit()
            rebuild_results(connection, results_path)
            progress.update(
                {
                    "state": "running",
                    "counts": run_counts(connection),
                    "last_completed_task_id": task_id,
                    "updated_at_utc": utc_now(),
                }
            )
            atomic_write_json(progress_path, progress)
            if deployment_abort:
                print(
                    "⚠ 检测到 LM Studio 未加载模型且重试耗尽，自动暂停本批次；"
                    "在 LM Studio 加载模型后重新运行同一命令（或菜单 5）即可续跑。"
                )
                break
            if inter_request > 0:
                time.sleep(inter_request)
    except KeyboardInterrupt:
        manifest["status"] = "interrupted"
        manifest["counts"] = run_counts(connection)
        atomic_write_json(run_dir / "run_manifest.json", manifest)
        progress.update({"state": "interrupted", "counts": manifest["counts"], "updated_at_utc": utc_now()})
        atomic_write_json(progress_path, progress)
        rebuild_results(connection, results_path)
        connection.close()
        print("Interrupted safely; rerun the same command to resume.")
        raise

    rebuild_results(connection, results_path)
    inventory = raw_inventory(run_dir)
    inventory_path = run_dir / "raw_inventory.json"
    atomic_write_json(inventory_path, inventory)
    returned_models: set[str] = set()
    fingerprints: set[str] = set()
    infrastructure_failures = 0
    for row in connection.execute("SELECT result_json FROM tasks WHERE result_json IS NOT NULL"):
        result = json.loads(row[0])
        infrastructure_failures += int(bool(result.get("infrastructure_failure")))
        metadata = result.get("response_metadata") or {}
        if metadata.get("returned_model_id"):
            returned_models.add(str(metadata["returned_model_id"]))
        if metadata.get("system_fingerprint"):
            fingerprints.add(str(metadata["system_fingerprint"]))
    counts = run_counts(connection)
    if deployment_abort:
        manifest["deployment_pause_reason"] = "no_models_loaded_auto_pause"
        reasons = list(manifest.get("protocol_pause_reasons", []))
        reasons.append("LM Studio 未加载模型：重试耗尽后自动暂停，需加载模型后续跑")
        manifest["protocol_pause_reasons"] = sorted(set(reasons))
    status = (
        "interrupted"
        if deployment_abort
        else ("completed" if counts["terminal"] == counts["total"] else "incomplete")
    )
    manifest.update(
        {
            "status": status,
            "access_completed_at_utc": utc_now(),
            "counts": counts,
            "returned_model_ids": sorted(returned_models),
            "system_fingerprints": sorted(fingerprints),
            "raw_response_inventory_sha256": sha256_file(inventory_path),
            "results_sha256": sha256_file(results_path),
            "infrastructure_failure_fraction": (
                infrastructure_failures / counts["total"] if counts["total"] else None
            ),
            "terminal_failure_fraction": (
                counts.get("terminal_failure", 0) / counts["total"] if counts["total"] else None
            ),
            "protocol_pause_triggered": bool(
                counts["total"] and infrastructure_failures / counts["total"] > 0.05
            ),
        }
    )
    atomic_write_json(run_dir / "run_manifest.json", manifest)
    progress.update({"state": manifest["status"], "counts": counts, "updated_at_utc": utc_now()})
    atomic_write_json(progress_path, progress)
    connection.close()
    if deployment_abort:
        print(f"Paused {model_key} (LM Studio 未加载模型)；加载模型后续跑：{run_dir}")
    else:
        print(f"Completed {model_key}: {run_dir}")
    return run_dir


def validate_questions(questions: list[dict[str, Any]]) -> None:
    seen: set[str] = set()
    required = {
        "question_id",
        "base_prompt_id",
        "template_family_id",
        "system",
        "temperature_K",
        "concentration_mol_L",
        "prompt",
    }
    for index, question in enumerate(questions, start=1):
        missing = sorted(required - set(question))
        if missing:
            raise ValueError(f"Question {index} is missing: {missing}")
        question_id = str(question["question_id"])
        if question_id in seen:
            raise ValueError(f"Duplicate question_id: {question_id}")
        seen.add(question_id)
        forbidden = {"gold", "diffusion_1e9_m2_s", "observed_diffusion_1e9_m2_s"}
        leaked = sorted(forbidden.intersection(question))
        if leaked:
            raise ValueError(f"Question {question_id} contains evaluator-only fields: {leaked}")
        recorded_hash = question.get("question_sha256")
        if recorded_hash is not None:
            unhashed = {key: value for key, value in question.items() if key != "question_sha256"}
            if recorded_hash != stable_hash(unhashed):
                raise ValueError(f"Question hash mismatch: {question_id}")


def main() -> int:
    args = parse_args()
    if args.limit is not None and args.limit <= 0:
        raise ValueError("--limit must be greater than zero")
    if args.run_id and (not args.model_key or len(args.model_key) != 1):
        raise ValueError("--run-id requires exactly one --model-key")
    config_path = args.config.resolve()
    config = read_json(config_path)
    if not isinstance(config, dict):
        raise ValueError("Configuration must be a JSON object")
    if "models" not in config:
        api_key = str(config.get("api_key", "")).strip()
        model_name = str(config.get("model_name", "")).strip()
        if not api_key or api_key.startswith("请在这里"):
            raise ValueError("请先在 config.json 的 api_key 中填写 API Key")
        if not model_name or model_name.startswith("请在这里"):
            raise ValueError("请先在 config.json 的 model_name 中填写模型名称")
        simple_provider = str(config.get("provider", "openai")).strip().lower()
        simple_base_url = config.get("base_url")
        if simple_base_url is None:
            if simple_provider == "deepseek":
                simple_base_url = "https://api.deepseek.com"
            elif simple_provider == "zhipu":
                simple_base_url = "https://open.bigmodel.cn/api/paas/v4"
            elif simple_provider == "qwen":
                simple_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
            elif simple_provider == "doubao":
                simple_base_url = "https://ark.cn-beijing.volces.com/api/v3"
            elif simple_provider == "minimax":
                simple_base_url = "https://api.minimaxi.com/v1"
            elif simple_provider == "kimi":
                simple_base_url = "https://api.moonshot.cn/v1"
            else:
                simple_base_url = "https://api.openai.com/v1"
        simple_endpoint = config.get("endpoint")
        if simple_endpoint is None:
            simple_endpoint = (
                "chat_completions"
                if simple_provider
                in {"deepseek", "zhipu", "qwen", "doubao", "minimax", "kimi"}
                else "responses"
            )
        simple_output_mode = config.get("structured_output")
        if simple_output_mode is None:
            if simple_provider == "minimax":
                simple_output_mode = "none"
            else:
                simple_output_mode = (
                    "json_object"
                    if simple_provider
                    in {"deepseek", "zhipu", "qwen", "doubao", "kimi"}
                    else "json_schema"
                )
        simple_token_parameter = config.get("token_parameter")
        if simple_token_parameter is None:
            simple_token_parameter = (
                "max_completion_tokens" if simple_provider == "minimax" else "max_tokens"
            )
        thinking_value = config.get("thinking")
        simple_extra_body = {}
        if simple_provider == "qwen":
            thinking_enabled = bool(
                isinstance(thinking_value, dict)
                and str(thinking_value.get("type", "")).strip().lower() == "enabled"
            )
            simple_extra_body["enable_thinking"] = thinking_enabled
            thinking_value = None
        simple_reasoning_effort = config.get("reasoning_effort")
        if simple_provider == "kimi":
            thinking_enabled = bool(
                isinstance(thinking_value, dict)
                and str(thinking_value.get("type", "")).strip().lower() == "enabled"
            )
            simple_reasoning_effort = "max" if thinking_enabled else "low"
            thinking_value = None
        model_key = safe_slug(model_name, 60)
        config = {
            **config,
            "models": {
                model_key: {
                    "enabled": True,
                    "provider": simple_provider,
                    "base_url": simple_base_url,
                    "endpoint": simple_endpoint,
                    "api_key_value": api_key,
                    "api_key_env": "CONFIG_JSON_API_KEY",
                    "model_id": model_name,
                    "snapshot_confirmed": bool(config.get("snapshot_confirmed", False)),
                    "evidence_level": "retrospective_opened_four_system_lineage_pool",
                    "structured_output": simple_output_mode,
                    "temperature": config.get("temperature", 0),
                    "seed": config.get("seed"),
                    "max_output_tokens": config.get("max_output_tokens", 256),
                    "token_parameter": simple_token_parameter,
                    "thinking": thinking_value,
                    "extra_body": simple_extra_body,
                    "reasoning_effort": simple_reasoning_effort,
                    "send_metadata": True,
                }
            },
        }
        if args.model_key and args.model_key != [model_key]:
            raise ValueError(f"简化配置的模型键为 {model_key!r}，请不要手动传 --model-key")
    base_dir = config_path.parent
    question_path = resolve_path(base_dir, config["question_file"])
    output_root = resolve_path(base_dir, config["output_root"])
    answer_schema_path = resolve_path(
        base_dir, config.get("answer_schema", "schemas/diffusion_answer.schema.json")
    )
    questions = list(iter_jsonl(question_path))
    validate_questions(questions)
    if args.limit is not None:
        questions = questions[: args.limit]
    models = config.get("models")
    if not isinstance(models, dict) or not models:
        raise ValueError("config.models must be a non-empty object")
    selected = args.model_key or [key for key, model in models.items() if model.get("enabled", True)]
    if not selected:
        raise ValueError("No enabled models selected")
    missing_models = sorted(set(selected) - set(models))
    if missing_models:
        raise ValueError(f"Unknown model keys: {missing_models}")
    output_root.mkdir(parents=True, exist_ok=True)
    completed_runs = []
    for model_key in selected:
        model = models[model_key]
        if not isinstance(model, dict):
            raise ValueError(f"Model {model_key!r} must be a JSON object")
        for field in ("provider", "model_id"):
            if not model.get(field):
                raise ValueError(f"Model {model_key!r} is missing {field!r}")
        if not model.get("api_key_value") and not model.get("api_key_env"):
            raise ValueError(f"Model {model_key!r} is missing API credentials")
        if not model.get("base_url") and not model.get("endpoint_url"):
            raise ValueError(
                f"Model {model_key!r} must configure either 'base_url' or 'endpoint_url'"
            )
        validate_model_config(model_key, model)
        completed_runs.append(
            run_model(
                config_path,
                config,
                model_key,
                model,
                questions,
                question_path,
                answer_schema_path,
                output_root,
                force_new=args.new_run,
                requested_run_id=args.run_id,
                dry_run=args.dry_run,
                resume_only=args.resume_only,
            )
        )
    print(json.dumps({"run_dirs": [str(path) for path in completed_runs]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130)
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
