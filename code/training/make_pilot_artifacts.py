# -*- coding: utf-8 -*-
"""生成 27B 连通性 pilot 工件（方案 §3.C.6：小批全链路验证）。

- data/pilot/train_642_pilot.json：train_642.json 前 64 条（alpaca 同格式）
- data/pilot/dataset_info.json：注册 train_642_pilot
- configs/qwen3_6_27b_sft_lora_pilot.yaml：与冻结 27B yaml 同超参，仅
  dataset/dataset_dir/num_train_epochs=1/output_dir 不同
产物全部 SHA-256 留档（写入同目录 manifest_pilot.json）。
正式冻结的 data/llamafactory/dataset_info.json 不动（避免破坏冻结哈希）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "py" / "微调" / "data"
CONFIGS = ROOT / "py" / "微调" / "configs"
PILOT_DIR = DATA / "pilot"
FROZEN_27B_YAML = CONFIGS / "qwen3_6_27b_sft_lora.yaml"

PILOT_N = 64
PILOT_DATASET_DIR_SERVER = "D:\\cet_sft\\data\\pilot"
PILOT_OUTPUT_DIR_SERVER = "E:\\models\\cet_formal_sft\\qwen3.6-27b-lora-r64-pilot"


def sha256_file(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def main() -> None:
    train = json.loads((DATA / "llamafactory" / "train_642.json").read_text(encoding="utf-8"))
    pilot_rows = train[:PILOT_N]
    pilot_path = PILOT_DIR / "train_642_pilot.json"
    pilot_path.parent.mkdir(parents=True, exist_ok=True)
    pilot_path.write_text(json.dumps(pilot_rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    dataset_info = {
        "train_642_pilot": {
            "file_name": "train_642_pilot.json",
            "formatting": "alpaca",
            "columns": {
                "prompt": "instruction",
                "query": "input",
                "response": "output",
                "system": "system",
            },
        }
    }
    dataset_info_path = PILOT_DIR / "dataset_info.json"
    dataset_info_path.write_text(json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    frozen = FROZEN_27B_YAML.read_text(encoding="utf-8")
    pilot_yaml = frozen.replace(
        "dataset_dir: D:\\cet_sft\\data\\llamafactory",
        f"dataset_dir: {PILOT_DATASET_DIR_SERVER}",
    )
    pilot_yaml = pilot_yaml.replace("dataset: train_642", "dataset: train_642_pilot")
    pilot_yaml = pilot_yaml.replace("num_train_epochs: 5.0", "num_train_epochs: 1.0")
    pilot_yaml = pilot_yaml.replace(
        "output_dir: E:\\models\\cet_formal_sft\\qwen3.6-27b-lora-r64",
        f"output_dir: {PILOT_OUTPUT_DIR_SERVER}",
    )
    pilot_yaml = pilot_yaml.replace(
        "### 冻结依据: py/微调/训练配置冻结清单.md（任何改动须先升版方案）",
        "### 冻结依据: py/微调/训练配置冻结清单.md；本文件为连通性 pilot（方案 §3.C.6，"
        "前 64 条、1 epoch，仅验证全链路，不进论文主表）",
    )
    pilot_yaml_path = CONFIGS / "qwen3_6_27b_sft_lora_pilot.yaml"
    pilot_yaml_path.write_text(pilot_yaml, encoding="utf-8", newline="\n")

    manifest = {
        "artifact_type": "pilot_artifacts_manifest",
        "pilot_records": PILOT_N,
        "pilot_source": "train_642.json first 64 records (frozen dataset)",
        "note": "pilot for full-chain connectivity only (plan §3.C.6); results never enter the paper",
        "files": {
            "train_642_pilot.json": {"path": str(pilot_path), "sha256": sha256_file(pilot_path)},
            "dataset_info.json": {"path": str(dataset_info_path), "sha256": sha256_file(dataset_info_path)},
            "qwen3_6_27b_sft_lora_pilot.yaml": {"path": str(pilot_yaml_path), "sha256": sha256_file(pilot_yaml_path)},
        },
    }
    manifest_path = PILOT_DIR / "manifest_pilot.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
