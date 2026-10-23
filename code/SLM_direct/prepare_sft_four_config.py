# -*- coding: utf-8 -*-
"""为剩余四模型的 SFT 训练产物写 SLM_direct config 条目（27B 同款，一次性）。

字段来源：py/微调/微调日志、/回传/清单.md（服务器 agent 回传，2026-08-22 已验收）。
merged_model_sha256 = canonical JSON 分片清单摘要（与 27B 同口径）。
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(r"E:\Desktop\CET_docment\CET_docment")
SLM = ROOT / "py" / "SLM_direct"
CONFIG = SLM / "config.json"

DATA_MANIFEST_CONTENT_SHA256 = "a6672fa914f6ad2be6169a1da7f2f070bf07579555a2411961ddba29ed4e131d"
DATASET_SHA256 = "f95b8a5587bf41ce01573ad579be04fe39c43554099c50e509b75af189759ba4"
LLAMA_CPP_COMMIT = "d0bfb1981266c271cd0536a8aa7c5e863e7cdf61"
LORA_DESC = "r=64, alpha=128, dropout=0, lr=1e-4, 5 epochs, effective batch 16, cosine, warmup 0.1, cutoff 512, bf16, seed 42, paged_adamw_8bit, gradient_checkpointing, max_grad_norm 1.0"

SPECS = [
    {
        "model_key": "qwen3_4b_instruct_2507_sft_q4km",
        "display_name": "Qwen3-4B-Instruct-2507-SFT-LoRA-r64",
        "parent_key": "qwen3_4b_instruct_2507_base_q4km",
        "pair_id": "qwen3_4b_instruct_2507",
        "arch": "qwen3",
        "family": "qwen3",
        "template": "qwen3_nothink",
        "gguf_template_family": "qwen_chatml",
        "reasoning": "disabled",
        "system_policy": "native_system_role",
        "served": "qwen3-4b-instruct-2507-lora-r64",
        "gguf_filename": "qwen3-4b-instruct-2507-lora-r64-q4_k_m.gguf",
        "gguf_sha256": "56ED01A11BD8995DF0A6A1E10F065C586098346A5303AE9A79DBE6283E4DB2F6",
        "adapter_sha256": "E0099C5313AF248BAA81CAE5A12FD4217427852C470859E41DD955253BAB2F91",
        "adapter_config_sha256": "CF9455A1A3754E9FF27CBD68FFEE19A074876175D93168CEA2F1D36B619E2404",
        "shards": [
            ("model-00001-of-00002.safetensors", "BEEA7DAF4E8447D8D7C38959E3F2F1015CCF5C4A49288270669B229B2966AC94"),
            ("model-00002-of-00002.safetensors", "444158794BEF06A86B289D82038624E7D79CEA35456479AD3DE5F31142B7C9F7"),
        ],
        "yaml_sha256": "1032e8650a20fb0a554f89e5ccdee6903d30eec4b8c4c9892578d8fe5aba2ce7",
        "target_modules": ["v_proj", "k_proj", "q_proj", "down_proj", "o_proj", "gate_proj", "up_proj"],
        "loss_init": 1.647, "loss_final": 0.2114, "runtime_s": 803, "gpu_mb": 29443,
    },
    {
        "model_key": "qwen3_8b_instruct_sft_q4km",
        "display_name": "Qwen3-8B-SFT-LoRA-r64",
        "parent_key": "qwen3_8b_instruct_base_q4km",
        "pair_id": "qwen3_8b_instruct",
        "arch": "qwen3",
        "family": "qwen3",
        "template": "qwen3_nothink",
        "gguf_template_family": "qwen_chatml",
        "reasoning": "disabled",
        "system_policy": "native_system_role",
        "served": "qwen3-8b-instruct-lora-r64",
        "gguf_filename": "qwen3-8b-instruct-lora-r64-q4_k_m.gguf",
        "gguf_sha256": "51C58E127FF391F7334F4A881DBA57F414688A9EED3F87F3366F5B23140770CE",
        "adapter_sha256": "B564ED69DEF6EB1FE3915D9FE21B23CA7FD4D1D5CF1536FF3FA96B872F453254",
        "adapter_config_sha256": "E03A82D841B6BF880DB9D14B187CE64A8DE918F26B8A8D7387F774D4413C357F",
        "shards": [
            ("model-00001-of-00004.safetensors", "6B9C1C6C6A4F439BD9B3B051601E60F7A69373EF3418E26B0225DAB61FFFBFFA"),
            ("model-00002-of-00004.safetensors", "FAF1C3FADA272B49A6E1053AB72141C42715234179420BC16606F6F5EAAA77E0"),
            ("model-00003-of-00004.safetensors", "5325D57E64A221505A51103716420A5195A184445429805FEE2471E7E46682B3"),
            ("model-00004-of-00004.safetensors", "51ABDBCDF19ACCD15F493D1D7E729C52704A8898CC0298E14C020539E5D14773"),
        ],
        "yaml_sha256": "c9140592598c8b25a022adfa2eddf9237e0022c67e403af864df1a875fcc01a5",
        "target_modules": ["up_proj", "v_proj", "q_proj", "gate_proj", "down_proj", "o_proj", "k_proj"],
        "loss_init": 3.916, "loss_final": 0.223, "runtime_s": 827, "gpu_mb": 37891,
    },
    {
        "model_key": "llama3_1_8b_instruct_sft_q4km",
        "display_name": "Llama-3.1-8B-Instruct-SFT-LoRA-r64",
        "parent_key": "llama3_1_8b_instruct_base_q4km",
        "pair_id": "llama3_1_8b_instruct",
        "arch": "llama",
        "family": "llama",
        "template": "llama3",
        "gguf_template_family": "llama3_header",
        "reasoning": "not_applicable",
        "system_policy": "native_system_role",
        "served": "llama-3.1-8b-instruct-lora-r64",
        "gguf_filename": "llama-3.1-8b-instruct-lora-r64-q4_k_m.gguf",
        "gguf_sha256": "BF13BD54EF6451E3385704C99BCE7B9B8BE0D299F0E1348A7BF3B311CC4E1C7E",
        "adapter_sha256": "60EFE33417F729E7AF62F181D37C8092D78132B77F6377394491AD2A9A928CD0",
        "adapter_config_sha256": "9D6A3CE1244357938744B8DE7C214C49F69E1A97AF9D16175E9A8CE6F3FCEFD9",
        "shards": [
            ("model-00001-of-00004.safetensors", "7C44BC0E9426BDF56AD45F53CD6DC0D15236E32FB35767319944472634B3AFA2"),
            ("model-00002-of-00004.safetensors", "D2F0F924D5B18A58A3C4C16EB7E2B1BD909FCBC49FEBF88B54A041D24FE5665A"),
            ("model-00003-of-00004.safetensors", "AEF2FE2CCF853A1FF586A03FD4F239D5AEDAC8CF16BB62A5EAD550A62084DE9C"),
            ("model-00004-of-00004.safetensors", "BDF44CAE17296F8C8148884D32A68323A26B9D81625208F8FACDF8CE0AC29EA3"),
        ],
        "yaml_sha256": "ef921451f51433f42f706ba47de6c052030cb71597eec3f654ce650f1b0c7a61",
        "target_modules": ["down_proj", "v_proj", "k_proj", "up_proj", "o_proj", "gate_proj", "q_proj"],
        "loss_init": 0.6306, "loss_final": 0.1712, "runtime_s": 647, "gpu_mb": 35968,
    },
    {
        "model_key": "gemma2_9b_it_sft_q4km",
        "display_name": "Gemma-2-9B-it-SFT-LoRA-r64",
        "parent_key": "gemma2_9b_it_base_q4km",
        "pair_id": "gemma2_9b_it",
        "arch": "gemma2",
        "family": "gemma2",
        "template": "gemma2",
        "gguf_template_family": "gemma_turn",
        "reasoning": "not_applicable",
        "system_policy": "fold_system_into_first_user",
        "served": "gemma-2-9b-it-lora-r64",
        "gguf_filename": "gemma-2-9b-it-lora-r64-q4_k_m.gguf",
        "gguf_sha256": "52A7EF406CBB62010D5B5027C4441F1AD21AEE7129ECC63F842F76A11E710290",
        "adapter_sha256": "48420851B386D60798CCE7D0B1E8CC33FD1A9978864BE965AB27F68F449DB86A",
        "adapter_config_sha256": "A859106DD4E01974F9CDDF496FB449D434C56ED7826E633CF168B6A9ABBA2C86",
        "shards": [
            ("model-00001-of-00004.safetensors", "55FF212D908004858F689114BAC0F20D1B0EF7D2C033975FDAD3B2BA312F91BC"),
            ("model-00002-of-00004.safetensors", "98A67CA9447E2B75D5827C2C5D2E2765659C6BD3DFFD622A7D010BAB4B6E8AF6"),
            ("model-00003-of-00004.safetensors", "99764DC133EE17C8C971F5FB1F3943A035E3A7423019AE89B89EC17C1EB47A07"),
            ("model-00004-of-00004.safetensors", "684C7632B6F034C9B340AC048B37143D0C9A23421E9B99C431D6F4F62F1BBD77"),
        ],
        "yaml_sha256": "6fa41f6288283f36736d37bd735e4a90e64dc42b9148a3ef41ca1d05a407bd8e",
        "target_modules": ["v_proj", "k_proj", "gate_proj", "o_proj", "up_proj", "down_proj", "q_proj"],
        "loss_init": 0.6997, "loss_final": 0.0929, "runtime_s": 1031, "gpu_mb": 42839,
    },
]


def merged_hash(shards: list) -> str:
    payload = json.dumps([list(item) for item in shards], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def main() -> None:
    config = json.loads(CONFIG.read_text(encoding="utf-8"))
    for spec in SPECS:
        parent = config["models"][spec["parent_key"]]
        config["models"][spec["model_key"]] = {
            "enabled": True,
            "formal_ready": False,
            "display_name": spec["display_name"],
            "model_family": spec["family"],
            "expected_lmstudio_architecture": spec["arch"],
            "served_model_id": spec["served"],
            "pair_id": spec["pair_id"],
            "pair_role": "sft",
            "paired_model_keys": [],
            "model_variant": "domain_sft",
            "experiment_arm": "C_sft_direct",
            "fold_id": 0,
            "primary_anchor": False,
            "chat_template": spec["template"],
            "gguf_template_family": spec["gguf_template_family"],
            "reasoning_mode": spec["reasoning"],
            "system_message_policy": spec["system_policy"],
            "question_ids_file": "questions_642_full.json",
            "base_checkpoint": dict(parent["base_checkpoint"]),
            "parent_base": {"model_key": spec["parent_key"]},
            "sft_artifacts": {
                "adapter_sha256": spec["adapter_sha256"],
                "adapter_config_sha256": spec["adapter_config_sha256"],
                "merged_model_sha256": merged_hash(spec["shards"]),
                "merged_model_sha256_definition": "sha256 of canonical JSON list of shard filenames+hashes",
                "merged_shard_sha256s": [list(item) for item in spec["shards"]],
                "gguf_q4_km_sha256": spec["gguf_sha256"],
            },
            "training_provenance": {
                "split_manifest_sha256": DATA_MANIFEST_CONTENT_SHA256,
                "split_note": "v2.10 full-642 design: no folds; hash = training_data_manifest.json content sha",
                "training_config_sha256": spec["yaml_sha256"],
                "llamafactory_version": "0.9.5",
                "dataset_sha256": DATASET_SHA256,
                "dataset": "train_642 (642 records, family C instruction, family A system)",
                "target_modules": spec["target_modules"],
                "lora": LORA_DESC,
                "train_loss_initial_step5": spec["loss_init"],
                "train_loss_final_step205": spec["loss_final"],
                "train_runtime_seconds": spec["runtime_s"],
                "gpu_peak_mb": spec["gpu_mb"],
                "python_version": "3.13.12",
            },
            "gguf": {
                "connectivity_repo": f"cet-sft/{spec['served']}",
                "connectivity_filename": spec["gguf_filename"],
                "connectivity_source_kind": "self_converted",
                "source_kind": "self_converted",
                "filename": spec["gguf_filename"],
                "local_path": f"E:\\gguf\\cet_sft\\{spec['gguf_filename']}",
                "sha256": spec["gguf_sha256"],
                "quantization": "Q4_K_M",
                "converter": "llama.cpp",
                "converter_commit": LLAMA_CPP_COMMIT,
                "imatrix_policy": "none",
                "imatrix_sha256": None,
            },
            "deployment": {
                "lmstudio_load_key": spec["served"],
                "native_model_key": spec["served"],
                "native_selected_variant": None,
                "lm_studio_app_version": "0.4.20+1",
                "lm_studio_runtime_version": "llama.cpp-win-x86_64-nvidia-cuda12-avx2-2.29.0",
                "runtime_note": "v2.14: SFT on CUDA12 runtime; A-arm Base was avx2 (recorded deviation)",
                "context_length": 4096,
                "gpu_offload": "max",
                "prompt_template_override": False,
            },
        }
    CONFIG.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for spec in SPECS:
        print("entry added:", spec["model_key"], "| merged hash:", merged_hash(spec["shards"]))


if __name__ == "__main__":
    main()
