from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA_VERSION = "llm_api_direct/v1"
ANSWER_SCHEMA_ID = "diffusion_internal_knowledge_answer_v1"
TARGET_UNIT = "10^-9 m^2/s"


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


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: Any, length: int | None = None) -> str:
    digest = sha256_bytes(canonical_json_bytes(value))
    return digest[:length] if length else digest


def safe_slug(value: str, max_length: int = 100) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", value.strip()).strip("._-")
    slug = slug or "unnamed"
    if len(slug) <= max_length:
        return slug
    suffix = hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]
    return f"{slug[: max_length - 11]}_{suffix}"


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for _attempt in range(3):
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            return
        except (FileNotFoundError, PermissionError):
            # Windows 上杀毒软件/清理工具可能在"关闭文件后、改名前的窗口"抢删
            # 临时文件（FileNotFoundError），或文件被短暂锁定（PermissionError）；重试。
            try:
                os.unlink(temp_name)
            except (FileNotFoundError, PermissionError):
                pass
        except BaseException:
            try:
                os.unlink(temp_name)
            except (FileNotFoundError, PermissionError):
                pass
            raise
    # 重试耗尽：直写兜底（失去原子性但保证进度；sqlite 状态仍是断点真源）。
    path.write_bytes(data)


def atomic_write_json(path: Path, value: Any, *, indent: int = 2) -> None:
    payload = json.dumps(
        value,
        ensure_ascii=False,
        indent=indent,
        sort_keys=True,
        allow_nan=False,
    ).encode("utf-8")
    atomic_write_bytes(path, payload + b"\n")


def atomic_write_text(path: Path, text: str) -> None:
    atomic_write_bytes(path, text.encode("utf-8"))


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                value = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"Expected a JSON object at {path}:{line_number}")
            yield value


def atomic_write_jsonl(path: Path, records: Iterable[dict[str, Any]]) -> None:
    lines = [canonical_json_bytes(record) for record in records]
    atomic_write_bytes(path, b"\n".join(lines) + (b"\n" if lines else b""))


def atomic_write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def resolve_path(base_dir: Path, value: str | Path) -> Path:
    path = Path(value).expanduser()
    return path.resolve() if path.is_absolute() else (base_dir / path).resolve()


def parse_json_object(text: str) -> dict[str, Any] | None:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass

    decoder = json.JSONDecoder()
    for position, character in enumerate(cleaned):
        if character != "{":
            continue
        try:
            parsed, _ = decoder.raw_decode(cleaned[position:])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def validate_answer_payload(payload: Any) -> tuple[bool, list[str]]:
    errors: list[str] = []
    if not isinstance(payload, dict):
        return False, ["not_an_object"]
    expected = {"diffusion_1e9_m2_s"}
    missing = sorted(expected - set(payload))
    extra = sorted(set(payload) - expected)
    if missing:
        errors.append("missing:" + ",".join(missing))
    if extra:
        errors.append("extra:" + ",".join(extra))

    value = payload.get("diffusion_1e9_m2_s")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        errors.append("requires_number")
    elif not math.isfinite(float(value)):
        errors.append("non_finite_number")
    elif float(value) <= 0:
        errors.append("non_positive_number")

    return not errors, errors


def redacted_config(config: dict[str, Any]) -> dict[str, Any]:
    clone = json.loads(json.dumps(config, ensure_ascii=False))
    exact_secret_keys = {
        "api_key",
        "access_token",
        "refresh_token",
        "secret",
        "client_secret",
        "password",
        "authorization",
        "x-api-key",
        "api_key_value",
    }

    def redact(value: Any) -> Any:
        if isinstance(value, dict):
            output = {}
            for key, item in value.items():
                normalized = str(key).lower()
                if normalized in exact_secret_keys and not normalized.endswith("_env"):
                    output[key] = "<redacted>"
                else:
                    output[key] = redact(item)
            return output
        if isinstance(value, list):
            return [redact(item) for item in value]
        return value

    return redact(clone)


def is_finite_number(value: Any) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
    )
