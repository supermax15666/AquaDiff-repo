# -*- coding: utf-8 -*-
"""C 臂外部前瞻集评测：一键生成 SLM_direct 外部配置与配套文件（冻结后使用）。

用法（在 py/SLM_direct 目录或项目根下均可）：
    python py/SLM_direct/prepare_external_eval.py

产物（全部写入 py/SLM_direct/）：
    1. questions_external_full.json      外部 64 题的题号文件（SFT 条目绑定用）
    2. analysis_sets_external.json       分析集占位文件（管道哈希校验用）
    3. external_questions.manifest.json  外部题库 manifest（仅含哈希，供 verify_frozen_assets）
    4. config_external.json              外部评测 config（题库/gold 指向冻结目录；其余与 config.json 一致）

纪律：本脚本只读取外部 questions（不含真值）与冻结 manifest（只有哈希），
绝不读取 external/frozen/gold/ 内容；不在任何输出中打印扩散系数真值。
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
FROZEN = HERE.parent / "微调" / "external" / "frozen"

sys.path.insert(0, str(HERE.parent / "LLM_API_direct"))
from common import stable_hash  # noqa: E402

QUESTIONS_FILE = FROZEN / "questions" / "external_questions.jsonl"
MANIFEST_FILE = FROZEN / "manifest" / "external_manifest.json"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    if not QUESTIONS_FILE.is_file():
        raise FileNotFoundError(f"未找到外部题库：{QUESTIONS_FILE}")
    if not MANIFEST_FILE.is_file():
        raise FileNotFoundError(f"未找到冻结 manifest：{MANIFEST_FILE}")

    # 1) 读取外部题库（只取 question_id/system 与顺序，不含任何真值）
    question_ids: list[str] = []
    id_to_system: dict[str, str] = {}
    first_id_per_system: dict[str, str] = {}
    for line in QUESTIONS_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line:
            continue
        record = json.loads(line)
        question_id = str(record["question_id"])
        question_ids.append(question_id)
        id_to_system[question_id] = str(record["system"])
        first_id_per_system.setdefault(str(record["system"]), question_id)

    # 2) 读取冻结 manifest（仅哈希与计数，无真值）
    frozen = json.loads(MANIFEST_FILE.read_text(encoding="utf-8-sig"))
    expected_question_hash = frozen.get("question_set_sha256")
    expected_gold_hash = frozen.get("evaluator_gold_sha256")
    expected_count = frozen.get("question_count")
    if not expected_question_hash or not expected_gold_hash:
        raise ValueError("冻结 manifest 缺少 question_set_sha256/evaluator_gold_sha256")
    actual_question_hash = sha256_file(QUESTIONS_FILE)
    if actual_question_hash != expected_question_hash:
        raise ValueError("外部题库哈希与冻结 manifest 不一致")
    if len(question_ids) != int(expected_count):
        raise ValueError(f"题数不一致：实际 {len(question_ids)}，manifest {expected_count}")
    if len(question_ids) != len(set(question_ids)):
        raise ValueError("外部题库存在重复 question_id")

    # 3) 题号文件（SFT 条目绑定用；Base 条目不绑、默认跑整个题库）
    ids_payload = {
        "description": "external prospective set (64 questions, frozen 2026-08-23) for C-arm external evaluation",
        "question_ids": question_ids,
    }
    (HERE / "questions_external_full.json").write_text(
        json.dumps(ids_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 4) 分析集文件（LLM_API_direct/analyze_results.py 的完整格式：
    #    sets 为数组，每套含 analysis_set_id/role/question_count/question_ids/
    #    question_ids_sha256/system_counts；顶层含 response_reuse 与题库/gold 指针）
    sensitivity_ids = [first_id_per_system[system] for system in first_id_per_system]

    def make_set(set_id: str, role: str, ids: list[str]) -> dict:
        counts = Counter(id_to_system[question_id] for question_id in ids)
        return {
            "analysis_set_id": set_id,
            "role": role,
            "question_count": len(ids),
            "question_ids": ids,
            "question_ids_sha256": stable_hash(sorted(ids)),
            "system_counts": dict(sorted(counts.items())),
        }

    analysis_sets = {
        "schema_version": "llm_api_direct/v1",
        "artifact_type": "llm_api_direct_analysis_sets",
        "response_reuse": True,
        "additional_api_calls_for_sensitivity_subset": 0,
        "primary_question_file": "../微调/external/frozen/questions/external_questions.jsonl",
        "primary_question_file_sha256": actual_question_hash,
        "evaluator_gold_file": "../微调/external/frozen/gold/external_gold.evaluator.jsonl",
        "evaluator_gold_file_sha256": expected_gold_hash,
        "sets": [
            make_set("external_primary_all", "primary", question_ids),
            make_set("external_sensitivity_1_per_system", "sensitivity", sensitivity_ids),
        ],
    }
    analysis_sets["analysis_sets_content_sha256"] = stable_hash(analysis_sets)
    (HERE / "analysis_sets_external.json").write_text(
        json.dumps(analysis_sets, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 5) 外部题库 manifest（verify_frozen_assets 所需的四个键）
    external_manifest = {
        "artifact_type": "external_prospective_question_set_manifest",
        "schema_version": "llm_api_direct/v1",
        "language": "en",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "question_count": len(question_ids),
        "question_set_sha256": actual_question_hash,
        "evaluator_gold_sha256": expected_gold_hash,
        "analysis_sets_sha256": sha256_file(HERE / "analysis_sets_external.json"),
        "primary_analysis_set_id": "external_all",
        "evidence_level": "prospective_external_frozen",
        "note": "gold is sealed; this manifest carries hashes only",
    }
    (HERE / "external_questions.manifest.json").write_text(
        json.dumps(external_manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 6) 生成 config_external.json（复制 config.json，只改题库/gold/分析集路径与 SFT 题号文件）
    config_path = HERE / "config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["question_file"] = "../微调/external/frozen/questions/external_questions.jsonl"
    config["question_manifest_file"] = "external_questions.manifest.json"
    config["evaluator_gold_file"] = "../微调/external/frozen/gold/external_gold.evaluator.jsonl"
    config["analysis_sets_file"] = "analysis_sets_external.json"
    sft_keys: list[str] = []
    for key, model in config.get("models", {}).items():
        if model.get("pair_role") == "sft":
            model["question_ids_file"] = "questions_external_full.json"
            sft_keys.append(key)
    config_path_out = HERE / "config_external.json"
    config_path_out.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"外部题库题数：{len(question_ids)}")
    print(f"SFT 条目绑定题号文件：{sft_keys}")
    print(f"question_set_sha256: {actual_question_hash}")
    print(f"evaluator_gold_sha256: {expected_gold_hash}")

    # 7) 自检：用管道自身的校验器验证新配置（不接触 gold 内容，仅哈希比对）
    sys.path.insert(0, str(HERE))
    from slm_common import validate_config, verify_frozen_assets

    validate_config(config_path_out, config)
    checks = verify_frozen_assets(config_path_out, config)
    print("自检通过：schema 校验 + 冻结资产哈希校验 OK（gold 未读取，仅哈希比对）")

    # 8) 额外自检：用 analyze_results.py 同款加载器验证 analysis_sets 格式
    question_records = [
        json.loads(line)
        for line in QUESTIONS_FILE.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]
    gold_path_resolved = (HERE / config["evaluator_gold_file"]).resolve()
    spec = importlib.util.spec_from_file_location(
        "llm_api_analyze", HERE.parent / "LLM_API_direct" / "analyze_results.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.load_analysis_sets(
        HERE / "analysis_sets_external.json",
        set(question_ids),
        question_records,
        gold_path_resolved,
    )
    print("自检通过：analysis_sets_external.json 已通过 analyze_results.py 同款加载器校验")
    print("question_count:", checks["question_count"])
    print("生成完毕：")
    for name in (
        "questions_external_full.json",
        "analysis_sets_external.json",
        "external_questions.manifest.json",
        "config_external.json",
    ):
        print("  -", name)


if __name__ == "__main__":
    main()
