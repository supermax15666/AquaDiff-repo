# -*- coding: utf-8 -*-
"""C 臂训练数据生成（方案 §3.C.3、第 15 条；交接文档 §5 步骤 4）。

训练数据 = 四体系全部 642 个合格条件（同一 gold / origin_lineage_id 映射），
**不设验证集、不设测试折**（v2.10 起）。
- instruction 逐字使用**家族 C** 模板（冻结清单 `frozen/prompt_families_frozen.json`）；
- system 与基准一致 = **家族 A** system（逐字）；
- output = 单字段 `{"diffusion_1e9_m2_s": <gold>}`（冻结答案格式）。
生成前校验冻结清单中的全部相关哈希，不一致即拒绝生成（AGENTS.md/子树约束第 4 条）。

产物（--force 才能覆盖；默认一次生成）：
  data/training_records.jsonl        规范记录（含 provenance 与逐条哈希）
  data/llamafactory/train_642.json   LLaMA-Factory alpaca 格式（instruction/input/output/system）
  data/llamafactory/dataset_info.json
  data/training_data_manifest.json   全部 SHA-256 留档
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "py" / "LLM_API_direct"))

from common import canonical_json_bytes, sha256_bytes, sha256_file, stable_hash, utc_now  # noqa: E402

PROMPT_FREEZE = ROOT / "py" / "微调" / "frozen" / "prompt_families_frozen.json"
QUESTIONS_642 = ROOT / "py" / "LLM_API_direct" / "questions" / "four_system_all_questions.jsonl"
GOLD_642 = ROOT / "py" / "LLM_API_direct" / "questions" / "four_system_all_gold.evaluator.jsonl"
GOLD_642_EXPECTED_SHA256 = "a0d0a610285e6499ed3f76c4324dfc969f1ac683083ec3e337cc7cdde2305471"
DEFAULT_OUT_DIR = ROOT / "py" / "微调" / "data"


def load_frozen_prompt_families() -> dict[str, Any]:
    payload = json.loads(PROMPT_FREEZE.read_text(encoding="utf-8"))
    families = {family["family_id"]: family for family in payload["families"]}
    return payload, families


def verify_or_die(payload: dict[str, Any], families: dict[str, Any]) -> tuple[str, str, str]:
    """校验冻结哈希；返回 (family_a_system, family_c_template, answer_format)。"""
    family_a = families["A"]
    family_c = families["C"]
    checks = [
        ("family A system", family_a["system_text"], family_a["sha256"]["system_text"]),
        ("family C user template", family_c["user_template_text"], family_c["sha256"]["user_template_text"]),
        ("family C system == family A system", family_c["system_text"], family_a["sha256"]["system_text"]),
        ("answer output format", payload["answer_output_format"], payload["answer_output_format_sha256"]),
    ]
    failures: list[str] = []
    for name, text, expected in checks:
        actual = stable_hash(text)
        if actual != expected:
            failures.append(f"{name}: recorded {expected}, actual {actual}")
    if family_c["system_text"] != family_a["system_text"]:
        failures.append("family C system text is not verbatim identical to family A")
    if failures:
        raise SystemExit("prompt family freeze verification FAILED:\n" + "\n".join(failures))
    return family_a["system_text"], family_c["user_template_text"], payload["answer_output_format"]


def render_family_c(template: str, system: str, temperature: float, concentration: float) -> str:
    return template.format(
        system=system,
        T=f"{temperature:.2f}",
        c=f"{concentration:.6f}",
    )


def render_output(answer_format: str, gold_value: float) -> str:
    marker = "<gold>"
    if marker not in answer_format:
        raise SystemExit("frozen answer format does not contain <gold> marker")
    number = json.dumps(float(gold_value))
    return answer_format.replace(marker, number)


def iter_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def jsonl_sha256(records: list[dict[str, Any]]) -> str:
    lines = [canonical_json_bytes(record) for record in records]
    payload = b"\n".join(lines) + (b"\n" if lines else b"")
    return sha256_bytes(payload)


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [canonical_json_bytes(record) for record in records]
    path.write_bytes(b"\n".join(lines) + (b"\n" if lines else b""))
    return sha256_file(path)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing outputs (use only when deliberately regenerating; hashes must be re-recorded).",
    )
    args = parser.parse_args()

    if not PROMPT_FREEZE.is_file():
        raise FileNotFoundError(f"prompt family freeze record missing: {PROMPT_FREEZE}")
    payload, families = load_frozen_prompt_families()
    family_a_system, family_c_template, answer_format = verify_or_die(payload, families)
    print("prompt family freeze verification: OK")
    print("  freeze record sha256:", sha256_file(PROMPT_FREEZE))

    gold_642_sha256 = sha256_file(GOLD_642)
    if gold_642_sha256 != GOLD_642_EXPECTED_SHA256:
        raise SystemExit(
            f"642 gold hash mismatch: expected {GOLD_642_EXPECTED_SHA256}, got {gold_642_sha256}"
        )
    print("642 gold sha256: OK")

    questions = iter_jsonl(QUESTIONS_642)
    golds = iter_jsonl(GOLD_642)
    if len(questions) != 642 or len(golds) != 642:
        raise SystemExit(f"expected 642 questions/gold, got {len(questions)}/{len(golds)}")
    order_by_id = {str(record["question_id"]): int(record["question_order"]) for record in questions}
    if len(order_by_id) != 642:
        raise SystemExit("question ids not unique in question bank")

    training_records: list[dict[str, Any]] = []
    for gold in golds:
        question_id = str(gold["question_id"])
        if question_id not in order_by_id:
            raise SystemExit(f"gold question_id {question_id} missing from question bank")
        system = str(gold["system"])
        temperature = float(gold["temperature_K"])
        concentration = float(gold["concentration_mol_L"])
        gold_value = float(gold["diffusion_1e9_m2_s"])
        instruction = render_family_c(family_c_template, system, temperature, concentration)
        output = render_output(answer_format, gold_value)
        record = {
            "question_id": question_id,
            "question_order": order_by_id[question_id],
            "system": system,
            "temperature_K": temperature,
            "concentration_mol_L": concentration,
            "origin_lineage_id": gold["origin_lineage_id"],
            "system_text": family_a_system,
            "instruction": instruction,
            "output": output,
        }
        record["record_sha256"] = stable_hash(
            {
                "question_id": record["question_id"],
                "system_text": record["system_text"],
                "instruction": record["instruction"],
                "output": record["output"],
            }
        )
        training_records.append(record)
    training_records.sort(key=lambda record: record["question_order"])

    rendered_instructions = [record["instruction"] for record in training_records]
    if len(rendered_instructions) != len(set(rendered_instructions)):
        raise SystemExit("different conditions collapse to the same rendered instruction")
    by_system = Counter(record["system"] for record in training_records)
    print("training records:", len(training_records), "| by system:", dict(by_system))
    assert sum(by_system.values()) == 642

    out_dir = args.out_dir
    canonical_path = out_dir / "training_records.jsonl"
    alpaca_path = out_dir / "llamafactory" / "train_642.json"
    dataset_info_path = out_dir / "llamafactory" / "dataset_info.json"
    manifest_path = out_dir / "training_data_manifest.json"
    existing = [p for p in (canonical_path, alpaca_path, dataset_info_path, manifest_path) if p.exists()]
    if existing and not args.force:
        raise FileExistsError(
            "outputs already exist (refusing to overwrite): "
            + ", ".join(str(p) for p in existing)
            + "\nuse --force only for a deliberate regeneration, then re-record all hashes."
        )

    canonical_sha256 = write_jsonl(canonical_path, training_records)
    alpaca_records = [
        {
            "instruction": record["instruction"],
            "input": "",
            "output": record["output"],
            "system": record["system_text"],
        }
        for record in training_records
    ]
    alpaca_path.parent.mkdir(parents=True, exist_ok=True)
    alpaca_path.write_text(
        json.dumps(alpaca_records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    alpaca_sha256 = sha256_file(alpaca_path)
    dataset_info = {
        "train_642": {
            "file_name": "train_642.json",
            "formatting": "alpaca",
            "columns": {
                "prompt": "instruction",
                "query": "input",
                "response": "output",
                "system": "system",
            },
        }
    }
    dataset_info_path.parent.mkdir(parents=True, exist_ok=True)
    dataset_info_path.write_text(
        json.dumps(dataset_info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    dataset_info_sha256 = sha256_file(dataset_info_path)

    manifest: dict[str, Any] = {
        "artifact_type": "sft_training_data_manifest",
        "research_plan_version": payload["research_plan_version"],
        "created_at_utc": utc_now(),
        "record_count": len(training_records),
        "per_system_counts": dict(by_system),
        "split": "none_full_642_no_validation_no_folds",
        "instruction_family": "C",
        "system_family": "A_benchmark_identical",
        "answer_output_format": answer_format,
        "outputs": {
            "canonical_jsonl": {"path": str(canonical_path), "sha256": canonical_sha256},
            "llamafactory_alpaca_json": {"path": str(alpaca_path), "sha256": alpaca_sha256},
            "llamafactory_dataset_info": {
                "path": str(dataset_info_path),
                "sha256": dataset_info_sha256,
            },
        },
        "sources": {
            "questions_642": {"path": str(QUESTIONS_642), "sha256": sha256_file(QUESTIONS_642)},
            "gold_642": {"path": str(GOLD_642), "sha256": gold_642_sha256},
            "prompt_family_freeze": {
                "path": str(PROMPT_FREEZE),
                "sha256": sha256_file(PROMPT_FREEZE),
                "freeze_record_sha256": payload.get("freeze_record_sha256"),
            },
        },
        "generator": {
            "path": str(Path(__file__)),
            "sha256": sha256_file(Path(__file__)),
        },
        "warning": (
            "training data includes gold values by design (supervised training set). "
            "This does not affect external-set secrecy, which applies to py/微调/external/gold only."
        ),
    }
    manifest_content_sha256 = sha256_bytes(canonical_json_bytes(manifest))
    manifest["manifest_content_sha256"] = manifest_content_sha256
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_bytes(canonical_json_bytes(manifest))

    print("outputs written:")
    for name, block in manifest["outputs"].items():
        print(f"  {name}: {block['sha256']}  ({block['path']})")
    print("manifest_content_sha256:", manifest_content_sha256)
    print("example record (first):")
    example = training_records[0]
    print("  question_id:", example["question_id"])
    print("  instruction:", example["instruction"])
    print("  output     :", example["output"])


if __name__ == "__main__":
    main()
