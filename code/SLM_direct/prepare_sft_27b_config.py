# -*- coding: utf-8 -*-
"""为 27B SFT 模型准备 642 掌握度评测配置（一次性）。

1. 生成 questions_642_full.json（全部 642 个 question_id，按 question_order 排序）；
2. 计算 merged_model_sha256（12 分片哈希的 canonical JSON 摘要）；
3. config.json：research_plan_version -> 2.14；新增 sft 条目 qwen3_6_27b_sft_q4km
   （formal_ready=false，预检通过后单独置 true）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(r"E:\Desktop\CET_docment\CET_docment")
SLM = ROOT / "py" / "SLM_direct"
QUESTIONS = ROOT / "py" / "LLM_API_direct" / "questions" / "four_system_all_questions.jsonl"
CONFIG = SLM / "config.json"
QIDS_OUT = SLM / "questions_642_full.json"

MERGE_SHARDS = [
    ("model-00001-of-00012.safetensors", "994D372DA0812952C05A3FB1093DB5B1245E314385290892F0DCE3883F4C2643"),
    ("model-00002-of-00012.safetensors", "3E4AA812450AAA21D21304F280377183AAF39EBEB0F167E26D7156A35EEB5D15"),
    ("model-00003-of-00012.safetensors", "FE57B54ECE333D5C401D23DDC4A9BA6B81B5FA0B2F2C7B4DF2C5F8DD77D26C4D"),
    ("model-00004-of-00012.safetensors", "19A518D5D9C9E14FCDC9F5FC41AA1610FF14AB71CB9C44E83C84DB7D6BF58DE9"),
    ("model-00005-of-00012.safetensors", "62DB1065A8D0C4E91D6933D8D2FF6F8BE673CCE4C8E247747090A70E09296000"),
    ("model-00006-of-00012.safetensors", "FB126B5184EFD1E0DF8988D1265277BEAA7F0363E3138CAD1580FB02EA962326"),
    ("model-00007-of-00012.safetensors", "5A40E6FE28C871D151350B08056292945C1AAB27B601692BE107540EFFA209E9"),
    ("model-00008-of-00012.safetensors", "B11AE8E77AADC399E0E9920008F7DDA56E87C75712E470FA28EF4F8A0BB698F4"),
    ("model-00009-of-00012.safetensors", "98C050313AF8E41DCFD10FD97C687F23E4AF154F9F187148E7E3349900F78474"),
    ("model-00010-of-00012.safetensors", "8F219F1D903456CB80AF6CC45D19C0E0258F0B94CACC6BC17F357AEE4F4E0C42"),
    ("model-00011-of-00012.safetensors", "73691F6A0E77427718EAC9A2220D8CD50C1DADA3A4DBC1BBF8587EFCFFF01367"),
    ("model-00012-of-00012.safetensors", "380B337E40DE1F9A2903A327765D87C1AE217FF984949A3070CCB7FEFC3D374D"),
]
ADAPTER_SHA256 = "C56104FBC50461F20156AC04A195F94C202EC4C9AD28839B4AFAADFACB6FB186"
GGUF_SHA256 = "7EDE95F348E2764668C97E404CCAA917058A600DE86B9A09655163EB58A56B8B"
CONFIG_YAML_SHA256 = "d3623a9381e73dce19b97536a88f766482b9705d098fe7695672bbba23fbc1f9"
DATASET_SHA256 = "f95b8a5587bf41ce01573ad579be04fe39c43554099c50e509b75af189759ba4"
DATA_MANIFEST_CONTENT_SHA256 = "a6672fa914f6ad2be6169a1da7f2f070bf07579555a2411961ddba29ed4e131d"
BASE_REVISION = "cea40373b9214dd387123e68841890af30dcd469"
BASE_SNAPSHOT = "6f82553ba0f2ac2eb83e72909c89111363a2db7a6653942549294212e41f2afc"
BASE_GGUF_SHA256 = "0b4d82bcbb9f36cbb9df6f6e3060d9fea6be5ee970305312c3436575ddfb4a96"
LLAMA_CPP_COMMIT = "d0bfb1981266c271cd0536a8aa7c5e863e7cdf61"
TARGET_MODULES = [
    "in_proj_qkv", "out_proj", "o_proj", "k_proj", "up_proj", "v_proj",
    "down_proj", "in_proj_b", "gate_proj", "in_proj_z", "in_proj_a", "q_proj",
]


def main() -> None:
    # 1. question ids in question_order
    questions = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    questions.sort(key=lambda row: int(row["question_order"]))
    ids = [str(row["question_id"]) for row in questions]
    assert len(ids) == 642 and len(set(ids)) == 642
    payload = {"description": "full 642-question mastery set for SFT runs (v2.10 design: no folds, all training data)", "question_ids": ids}
    QIDS_OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    qids_sha256 = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    print("questions_642_full.json sha256:", qids_sha256)

    # 2. merged model hash
    merged_payload = json.dumps(
        [list(item) for item in MERGE_SHARDS], ensure_ascii=False, sort_keys=True, separators=(",", ":")
    )
    merged_hash = hashlib.sha256(merged_payload.encode("utf-8")).hexdigest()
    print("merged_model_sha256:", merged_hash)

    # 3. config update
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    config["research_plan_version"] = "2.14"
    sft_entry = {
        "enabled": True,
        "formal_ready": False,
        "display_name": "Qwen3.6-27B-SFT-LoRA-r64",
        "model_family": "qwen3",
        "expected_lmstudio_architecture": "qwen35",
        "served_model_id": "qwen3.6-27b-lora-r64",
        "pair_id": "qwen3_6_27b",
        "pair_role": "sft",
        "paired_model_keys": [],
        "model_variant": "domain_sft",
        "experiment_arm": "C_sft_direct",
        "fold_id": 0,
        "primary_anchor": False,
        "chat_template": "qwen3_nothink",
        "gguf_template_family": "qwen_chatml",
        "reasoning_mode": "disabled",
        "system_message_policy": "native_system_role",
        "question_ids_file": "questions_642_full.json",
        "base_checkpoint": {
            "modelscope_id": "Qwen/Qwen3.6-27B",
            "revision": BASE_REVISION,
            "snapshot_manifest_sha256": BASE_SNAPSHOT,
        },
        "parent_base": {"model_key": "qwen3_6_27b_base_q4km"},
        "sft_artifacts": {
            "adapter_sha256": ADAPTER_SHA256,
            "merged_model_sha256": merged_hash,
            "merged_model_sha256_definition": "sha256 of canonical JSON list of 12 shard filenames+hashes",
            "merged_shard_sha256s": [list(item) for item in MERGE_SHARDS],
            "gguf_q4_km_sha256": GGUF_SHA256,
            "adapter_dir": "E:\\models\\cet_formal_sft\\qwen3.6-27b-lora-r64",
            "merged_dir": "E:\\models\\cet_formal_sft\\qwen3.6-27b-lora-r64-merged",
        },
        "training_provenance": {
            "split_manifest_sha256": DATA_MANIFEST_CONTENT_SHA256,
            "split_note": "v2.10 full-642 design: no validation set, no folds; hash = training_data_manifest.json content sha",
            "training_config_sha256": CONFIG_YAML_SHA256,
            "llamafactory_version": "0.9.5",
            "dataset_sha256": DATASET_SHA256,
            "dataset": "train_642 (642 records, family C instruction, family A system)",
            "target_modules": TARGET_MODULES,
            "lora": "r=64, alpha=128, dropout=0, lr=1e-4, 5 epochs, effective batch 16, cosine, warmup 0.1, cutoff 512, bf16, seed 42, paged_adamw_8bit, gradient_checkpointing, max_grad_norm 1.0",
            "train_loss_initial_step5": 1.0403,
            "train_loss_final_step205": 0.2082,
            "train_runtime_seconds": 7876,
            "gpu_peak_mb": 63471,
            "python_version": "3.13.12",
            "chat_template_matches_base": True,
            "chat_template_sha256": "e84f32a23fdda27689f868aa4a1a5621f41133e51a48d7f3efcbea2839574259",
        },
        "gguf": {
            "connectivity_repo": "cet-sft/qwen3.6-27b-lora-r64",
            "connectivity_filename": "qwen3.6-27b-lora-r64-q4_k_m.gguf",
            "connectivity_source_kind": "self_converted",
            "source_kind": "self_converted",
            "filename": "qwen3.6-27b-lora-r64-q4_k_m.gguf",
            "local_path": "E:\\gguf\\cet_sft\\qwen3.6-27b-lora-r64-q4_k_m.gguf",
            "sha256": GGUF_SHA256,
            "quantization": "Q4_K_M",
            "converter": "llama.cpp",
            "converter_commit": LLAMA_CPP_COMMIT,
            "conversion_note": "--no-mtp (CUDA12 runtime cannot load MTP-head GGUFs; MTP unused at inference; recorded deviation)",
            "imatrix_policy": "none",
            "imatrix_sha256": None,
        },
        "deployment": {
            "lmstudio_load_key": "qwen3.6-27b-lora-r64",
            "native_model_key": "qwen3.6-27b-lora-r64",
            "native_selected_variant": None,
            "lm_studio_app_version": "0.4.20+1",
            "lm_studio_runtime_version": "llama.cpp-win-x86_64-nvidia-cuda12-avx2-2.29.0",
            "runtime_note": "v2.14: SFT on CUDA12 runtime; A-arm Base was avx2 (recorded deviation)",
            "context_length": 4096,
            "gpu_offload": "max",
            "prompt_template_override": False,
        },
    }
    config["models"]["qwen3_6_27b_sft_q4km"] = sft_entry
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("config updated: research_plan_version=2.14, new model entry qwen3_6_27b_sft_q4km (formal_ready=false)")


if __name__ == "__main__":
    main()
