# -*- coding: utf-8 -*-
"""Freeze the five-model LLaMA-Factory LoRA training configs (C arm, plan §15; handoff §5 step 3).

五模型统一 LoRA 超参（方案第 15 条，冻结）：
r=64、alpha=128、dropout=0、lr=1e-4、5 epochs、有效 batch 16（bs2×ga8）、cosine、
warmup_ratio=0.1、cutoff_len=512、bf16、seed=42、paged_adamw_8bit + gradient_checkpointing、
max_grad_norm=1.0。
五模型只有 model_name_or_path / template / output_dir 不同。
lora_target 省略 = 按各模型 LLaMA-Factory 模板默认，训练时记录实际 target_modules 留档。
步骤数：642/16 = 41 steps/epoch（ceil），5 epochs = 205 steps；save_steps=41 每 epoch 存点。

产物（一次性写入，已存在则拒绝覆盖）：
  configs/<短名>.yaml × 5
  frozen/training_config_frozen.json（机器可读冻结记录）
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "py" / "LLM_API_direct"))

from common import canonical_json_bytes, sha256_bytes, sha256_file, utc_now  # noqa: E402

PLAN_VERSION = "2.11"
DEFAULT_OUT_JSON = ROOT / "py" / "微调" / "frozen" / "training_config_frozen.json"
DEFAULT_CONFIGS_DIR = ROOT / "py" / "微调" / "configs"
TRAINING_DATA_MANIFEST = ROOT / "py" / "微调" / "data" / "training_data_manifest.json"

DATASET_DIR_SERVER = "D:\\cet_sft\\data\\llamafactory"

MODEL_SPECS: list[dict[str, str]] = [
    {
        "model_key": "qwen3_4b_instruct_2507",
        "model": "Qwen3-4B-Instruct-2507",
        "base_path": "E:\\models\\cet_formal\\qwen3-4b-instruct-2507",
        "template": "qwen3_nothink",
        "output_dir": "E:\\models\\cet_formal_sft\\qwen3-4b-instruct-2507-lora-r64",
    },
    {
        "model_key": "qwen3_8b_instruct",
        "model": "Qwen3-8B",
        "base_path": "E:\\models\\cet_formal\\qwen3-8b-instruct",
        "template": "qwen3_nothink",
        "output_dir": "E:\\models\\cet_formal_sft\\qwen3-8b-instruct-lora-r64",
    },
    {
        "model_key": "qwen3_6_27b",
        "model": "Qwen3.6-27B",
        "base_path": "E:\\models\\cet_formal\\qwen3.6-27b",
        "template": "qwen3_nothink",
        "output_dir": "E:\\models\\cet_formal_sft\\qwen3.6-27b-lora-r64",
    },
    {
        "model_key": "llama3_1_8b_instruct",
        "model": "Llama-3.1-8B-Instruct",
        "base_path": "E:\\models\\cet_formal\\llama-3.1-8b-instruct",
        "template": "llama3",
        "output_dir": "E:\\models\\cet_formal_sft\\llama-3.1-8b-instruct-lora-r64",
    },
    {
        "model_key": "gemma2_9b_it",
        "model": "Gemma-2-9B-it",
        "base_path": "E:\\models\\cet_formal\\gemma-2-9b-it",
        "template": "gemma2",
        "output_dir": "E:\\models\\cet_formal_sft\\gemma-2-9b-it-lora-r64",
    },
]

HYPERPARAMS: dict[str, Any] = {
    "finetuning_type": "lora",
    "lora_rank": 64,
    "lora_alpha": 128,
    "lora_dropout": 0,
    "lora_target": "omitted_llamafactory_template_default_record_at_training",
    "learning_rate": 1.0e-4,
    "num_train_epochs": 5.0,
    "per_device_train_batch_size": 2,
    "gradient_accumulation_steps": 8,
    "effective_batch_size": 16,
    "lr_scheduler_type": "cosine",
    "warmup_ratio": 0.1,
    "cutoff_len": 512,
    "bf16": True,
    "seed": 42,
    "optim": "paged_adamw_8bit",
    "gradient_checkpointing": True,
    "max_grad_norm": 1.0,
    "dataset": "train_642",
    "val_size": 0,
    "save_steps": 41,
    "save_total_limit": 6,
    "overwrite_output_dir": False,
    "steps_per_epoch": 41,
    "total_steps": 205,
}


def render_yaml(spec: dict[str, str]) -> str:
    return (
        "### ============================================================\n"
        f"### {spec['model']} SFT LoRA 训练配置（C 臂，方案第 15 条统一 LoRA，已冻结）\n"
        "### 数据集: train_642（642 全量、家族 C instruction / 家族 A system，无验证集）\n"
        "### 硬件: 服务器单卡 RTX 6000 Ada 84GB；LLaMA-Factory CLI\n"
        "### 冻结依据: py/微调/训练配置冻结清单.md（任何改动须先升版方案）\n"
        "### ============================================================\n"
        "\n"
        "### --- 模型 ---\n"
        f"model_name_or_path: {spec['base_path']}\n"
        "trust_remote_code: true\n"
        "\n"
        "### --- 阶段 / 方法（统一 LoRA，方案第 15 条，禁止改动）---\n"
        "stage: sft\n"
        "do_train: true\n"
        "finetuning_type: lora\n"
        "### lora_target 省略 = 按各模型 LLaMA-Factory 模板默认；训练时记录实际 target_modules 留档\n"
        "lora_rank: 64\n"
        "lora_alpha: 128\n"
        "lora_dropout: 0\n"
        "\n"
        "### --- 数据 ---\n"
        f"dataset_dir: {DATASET_DIR_SERVER}\n"
        "dataset: train_642\n"
        f"template: {spec['template']}\n"
        "cutoff_len: 512\n"
        "val_size: 0\n"
        "overwrite_cache: true\n"
        "preprocessing_num_workers: 1\n"
        "\n"
        "### --- 输出 ---\n"
        f"output_dir: {spec['output_dir']}\n"
        "logging_steps: 5\n"
        "save_steps: 41\n"
        "save_total_limit: 6\n"
        "overwrite_output_dir: false\n"
        "plot_loss: true\n"
        "\n"
        "### --- 训练（方案第 15 条超参，禁止改动）---\n"
        "per_device_train_batch_size: 2\n"
        "gradient_accumulation_steps: 8\n"
        "learning_rate: 1.0e-4\n"
        "num_train_epochs: 5.0\n"
        "lr_scheduler_type: cosine\n"
        "warmup_ratio: 0.1\n"
        "bf16: true\n"
        "ddp_timeout: 180000000\n"
        "max_grad_norm: 1.0\n"
        "optim: paged_adamw_8bit\n"
        "gradient_checkpointing: true\n"
        "seed: 42\n"
        "\n"
        "### --- 报告 ---\n"
        "report_to: none\n"
    )


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    parser.add_argument("--configs-dir", type=Path, default=DEFAULT_CONFIGS_DIR)
    args = parser.parse_args()

    if args.out_json.exists():
        raise FileExistsError(f"{args.out_json} exists; config freeze is one-shot")
    configs_dir = args.configs_dir
    configs_dir.mkdir(parents=True, exist_ok=True)

    per_model: list[dict[str, Any]] = []
    for spec in MODEL_SPECS:
        yaml_text = render_yaml(spec)
        yaml_path = configs_dir / f"{spec['model_key']}_sft_lora.yaml"
        if yaml_path.exists():
            raise FileExistsError(f"{yaml_path} exists; refusing to overwrite")
        yaml_path.write_text(yaml_text, encoding="utf-8", newline="\n")
        per_model.append(
            {
                "model_key": spec["model_key"],
                "model": spec["model"],
                "base_path": spec["base_path"],
                "template": spec["template"],
                "output_dir": spec["output_dir"],
                "yaml_path": str(yaml_path),
                "yaml_sha256": sha256_file(yaml_path),
            }
        )

    training_data_manifest = json.loads(TRAINING_DATA_MANIFEST.read_text(encoding="utf-8"))
    payload: dict[str, Any] = {
        "artifact_type": "training_config_freeze_record",
        "research_plan_version": PLAN_VERSION,
        "frozen_at_utc": utc_now(),
        "framework": "LLaMA-Factory CLI",
        "framework_note": (
            "framework chosen 2026-08-16 (pilot-proven on the training server; plan §15 "
            "references LLaMA-Factory template defaults). Unsloth evaluated and rejected "
            "for this project; switching frameworks requires a plan version bump."
        ),
        "hyperparameters": HYPERPARAMS,
        "models": per_model,
        "dataset": {
            "name": "train_642",
            "server_dataset_dir": DATASET_DIR_SERVER,
            "server_note": (
                "dataset_dir/output_dir are environment paths on the training server; "
                "if changed at deployment time, the actual paths must be recorded in the "
                "deployment report (same convention as 模型身份冻结清单 §五)."
            ),
            "training_data_manifest_path": str(TRAINING_DATA_MANIFEST),
            "training_data_manifest_sha256": sha256_file(TRAINING_DATA_MANIFEST),
            "training_data_manifest_content_sha256": training_data_manifest.get(
                "manifest_content_sha256"
            ),
            "canonical_jsonl_sha256": training_data_manifest["outputs"]["canonical_jsonl"]["sha256"],
            "llamafactory_alpaca_json_sha256": training_data_manifest["outputs"]["llamafactory_alpaca_json"]["sha256"],
            "llamafactory_dataset_info_sha256": training_data_manifest["outputs"]["llamafactory_dataset_info"]["sha256"],
        },
        "training_protocol": (
            "no validation set, no early stopping, epochs fixed at 5 (plan §3.C.5); "
            "no post-training tuning or retraining; adapter + merged weight hashes "
            "recorded; merge then convert via llama.cpp b10188 (d0bfb198…) to Q4_K_M "
            "identically to Base."
        ),
    }
    payload["freeze_record_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("frozen:", args.out_json)
    print("freeze_record_sha256:", payload["freeze_record_sha256"])
    for block in per_model:
        print(f"  {block['model_key']:24s} template={block['template']:12s} "
              f"yaml_sha256={block['yaml_sha256'][:16]}…")


if __name__ == "__main__":
    main()
