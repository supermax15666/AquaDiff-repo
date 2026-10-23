from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from slm_common import (
    ROOT,
    fetch_native_models,
    formal_readiness_issues,
    is_sha256,
    load_config,
    sha256_file,
)

CONFIG = ROOT / "config.json"


def atomic_write_config(path: Path, config: dict[str, Any]) -> None:
    descriptor, temp_name = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(config, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_name, path)
    except BaseException:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
        raise


def find_loaded_match(
    native_snapshot: dict[str, Any], expected_id: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None, int]:
    total = 0
    for native_model in native_snapshot.get("models", []):
        if not isinstance(native_model, dict):
            continue
        for instance in native_model.get("loaded_instances", []):
            if not isinstance(instance, dict):
                continue
            total += 1
            if str(instance.get("id", "")) == expected_id:
                return native_model, instance, total
    return None, None, total


def remaining_placeholders(value: Any, path: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            found.extend(remaining_placeholders(item, f"{path}.{key}" if path else key))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(remaining_placeholders(item, f"{path}[{index}]"))
    elif isinstance(value, str) and "REPLACE_WITH" in value.upper():
        found.append(path)
    return found


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "从正在运行的 LM Studio 自动采集模型部署信息，并回填 config.json，"
            "减少手工填写工作量。"
        )
    )
    parser.add_argument("--config", type=Path, default=CONFIG)
    parser.add_argument("--model-key", required=True)
    parser.add_argument("--gguf-path", type=Path, help="本地 GGUF 文件路径（计算 local_path/filename/sha256）")
    parser.add_argument("--revision", help="ModelScope 仓库 revision（commit hash 或分支）")
    parser.add_argument(
        "--snapshot-manifest",
        type=Path,
        help="ModelScope 下载快照的 manifest 文件（计算 snapshot_manifest_sha256）",
    )
    parser.add_argument(
        "--llama-cpp-repo",
        type=Path,
        help="llama.cpp 仓库路径（git rev-parse HEAD 作为 converter_commit）",
    )
    parser.add_argument("--gpu-offload", help="实际加载时使用的 GPU offload 值")
    parser.add_argument(
        "--runtime-version",
        help="LM Studio 运行时版本（若 /api/v1/models 未提供时手动指定）",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path, config = load_config(args.config)
    if args.model_key not in config["models"]:
        raise ValueError(f"未知模型键：{args.model_key}")
    model = config["models"][args.model_key]
    expected_id = str(model["served_model_id"])

    native_snapshot = fetch_native_models(config)
    native_model, instance, total_loaded = find_loaded_match(native_snapshot, expected_id)
    if native_model is None or instance is None:
        raise RuntimeError(
            f"LM Studio 中未找到 identifier={expected_id!r} 的已加载实例"
            f"（当前共加载 {total_loaded} 个实例）。请先用 "
            f"`lms load <key> --identifier {expected_id} --context-length 4096 "
            "--gpu <值>` 加载。"
        )
    if total_loaded != 1:
        print(f"警告：当前加载了 {total_loaded} 个实例，正式运行要求唯一实例。", file=sys.stderr)

    changes: list[str] = []
    deployment = model.setdefault("deployment", {})
    native_key = str(native_model.get("key", "")).strip()
    if native_key:
        for field in ("native_model_key", "lmstudio_load_key"):
            deployment[field] = native_key
            changes.append(f"deployment.{field} <- {native_key!r}")
    selected_variant = native_model.get("selected_variant")
    if selected_variant:
        deployment["native_selected_variant"] = str(selected_variant)
        changes.append(f"deployment.native_selected_variant <- {selected_variant!r}")

    instance_config = instance.get("config") if isinstance(instance, dict) else {}
    context_length = (
        instance_config.get("context_length")
        if isinstance(instance_config, dict)
        else None
    )
    if isinstance(context_length, int):
        deployment["context_length"] = int(context_length)
        changes.append(f"deployment.context_length <- {context_length}")
        if int(context_length) != 4096:
            print("警告：context_length 不是 4096，请检查加载参数。", file=sys.stderr)

    quantization = native_model.get("quantization")
    quant_name = (
        str(quantization.get("name", "")) if isinstance(quantization, dict) else ""
    )
    if quant_name:
        gguf = model.setdefault("gguf", {})
        gguf["quantization"] = quant_name
        changes.append(f"gguf.quantization <- {quant_name!r}")
        if quant_name.upper() != "Q4_K_M":
            print("警告：当前加载的量化不是 Q4_K_M。", file=sys.stderr)

    runtime_hint = None
    for key in ("runtime_version", "llama_cpp_version", "runtime"):
        value = native_model.get(key)
        if value:
            runtime_hint = str(value)
            break
    runtime_version = args.runtime_version or runtime_hint
    if runtime_version:
        deployment["lm_studio_runtime_version"] = str(runtime_version)
        changes.append(f"deployment.lm_studio_runtime_version <- {runtime_version!r}")
    else:
        print("提示：/api/v1/models 未提供运行时版本，可用 --runtime-version 指定。", file=sys.stderr)

    if args.gpu_offload:
        deployment["gpu_offload"] = str(args.gpu_offload)
        changes.append(f"deployment.gpu_offload <- {args.gpu_offload!r}")

    gguf = model.setdefault("gguf", {})
    if args.gguf_path:
        gguf_path = args.gguf_path.expanduser().resolve()
        if not gguf_path.is_file():
            raise FileNotFoundError(f"GGUF 文件不存在：{gguf_path}")
        gguf["local_path"] = str(gguf_path)
        gguf["filename"] = gguf_path.name
        gguf["sha256"] = sha256_file(gguf_path)
        changes.append(f"gguf.local_path <- {gguf_path}")
        changes.append(f"gguf.filename <- {gguf_path.name}")
        changes.append(f"gguf.sha256 <- {gguf['sha256']}")

    base_checkpoint = model.setdefault("base_checkpoint", {})
    if args.revision:
        base_checkpoint["revision"] = str(args.revision)
        changes.append(f"base_checkpoint.revision <- {args.revision!r}")
    if args.snapshot_manifest:
        manifest_path = args.snapshot_manifest.expanduser().resolve()
        if not manifest_path.is_file():
            raise FileNotFoundError(f"snapshot manifest 不存在：{manifest_path}")
        digest = sha256_file(manifest_path)
        base_checkpoint["snapshot_manifest_sha256"] = digest
        changes.append(f"base_checkpoint.snapshot_manifest_sha256 <- {digest}")

    if args.llama_cpp_repo:
        repo = args.llama_cpp_repo.expanduser().resolve()
        if not (repo / ".git").exists():
            raise ValueError(f"不是 git 仓库：{repo}")
        completed = subprocess.run(
            ["git", "-C", str(repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError(f"git rev-parse 失败：{completed.stderr.strip()}")
        commit = completed.stdout.strip()
        gguf["converter_commit"] = commit
        changes.append(f"gguf.converter_commit <- {commit}")

    if not changes:
        print("没有采集到任何变更。请确认模型已加载，或提供 --gguf-path 等参数。")
        return 1

    atomic_write_config(config_path, config)
    _, reloaded = load_config(config_path)
    remaining = remaining_placeholders(reloaded["models"][args.model_key])
    print(f"已写入 {config_path}：")
    for change in changes:
        print(f"  + {change}")
    if remaining:
        print("\n仍需手工填写：")
        for item in sorted(remaining):
            print(f"  - {item}")
    blockers = formal_readiness_issues(reloaded, args.model_key)
    if blockers:
        print("\n距正式运行还差（formal_readiness_issues）：")
        for blocker in blockers:
            print(f"  - {blocker}")
    else:
        print("\n该模型已满足正式运行的全部冻结条件。")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {type(exc).__name__}: {exc}", file=sys.stderr)
        raise SystemExit(1)
