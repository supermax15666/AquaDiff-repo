# -*- coding: utf-8 -*-
"""Freeze prompt families A/B/C (C arm, plan §3.C.8; v2.10 frozen, v2.11 unchanged; handoff §5 step 2).

家族 A：主测试家族，与 A 臂完全一致（system 提示逐字取自共享核心
  py/LLM_API_direct/run_benchmark.py 的 SYSTEM_PROMPT；user 模板逐字取自
  py/LLM_API_direct/prepare_questions.py 的 template_text(en)）。
家族 B：同义检查家族（不进训练），措辞与 A 不同、语义等价。
家族 C：训练措辞家族（仅用于训练数据），system 与基准一致（= 家族 A system），
  instruction 措辞与 A/B 均不同。
三者不得逐字互抄；哈希在训练前冻结。

本脚本一次性写入 <out-json>（已存在则拒绝覆盖）。产物含全部文案、哈希、
渲染示例（锚点条件 NaCl-H2O / 298.15 K / 0.3907 mol/L）与来源文件哈希。
用法：python freeze_prompt_families.py [--out-json PATH]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "py" / "LLM_API_direct"))

from common import sha256_file, stable_hash, utc_now  # noqa: E402
import prepare_questions  # noqa: E402
import run_benchmark  # noqa: E402

PLAN_VERSION = "2.11"
DEFAULT_OUT_JSON = ROOT / "py" / "微调" / "frozen" / "prompt_families_frozen.json"
QUESTIONS_642 = ROOT / "py" / "LLM_API_direct" / "questions" / "four_system_all_questions.jsonl"
GOLD_642 = ROOT / "py" / "LLM_API_direct" / "questions" / "four_system_all_gold.evaluator.jsonl"

ANCHOR_SYSTEM = "NaCl-H2O"
ANCHOR_T = 298.15
ANCHOR_C = 0.3907

# ---- 家族 A（逐字来自共享核心，勿改） ----
FAMILY_A_SYSTEM = run_benchmark.SYSTEM_PROMPT
FAMILY_A_USER_TEMPLATE = (
    "Predict the mutual diffusion coefficient of {system} at "
    "T = {T} K and c = {c} mol/L. "
    "Return the multiplier x where D = x * 10^-9 m^2/s. "
    "The JSON numeric field must contain x only; do not return x * 10^-9 "
    "and do not return D in base SI units."
)

# ---- 家族 B（同义检查，不进训练；与 A/C 措辞不同） ----
FAMILY_B_SYSTEM = (
    "You are taking part in a scientific recall exercise about aqueous electrolyte "
    "solutions. Answer every question using only knowledge already inside you. You are "
    "not allowed to use tools, search the web, look up tables, execute code, consult "
    "fitted formulas, or request any extra information, and you must not ask clarifying "
    "questions. Keep your internal deliberation very short, then give one single "
    "numerical guess with no explanation. Your reply must be a JSON object with exactly "
    "one key named diffusion_1e9_m2_s and nothing else - no Markdown, no unit field, no "
    "additional keys. The value you provide is the multiplier x such that the diffusion "
    "coefficient D = x * 10^-9 m^2/s."
)
FAMILY_B_USER_TEMPLATE = (
    "For the binary aqueous solution {system}, what is the mutual diffusion coefficient "
    "when the temperature is {T} K and the solute concentration is {c} mol/L? Give the "
    "multiplier x defined by D = x * 10^-9 m^2/s, in the required single-field JSON object."
)

# ---- 家族 C（训练措辞；system 与基准一致 = 家族 A system） ----
FAMILY_C_SYSTEM = FAMILY_A_SYSTEM
FAMILY_C_USER_TEMPLATE = (
    "Estimate the binary mutual diffusion coefficient of an aqueous {system} solution "
    "with temperature {T} K and molar concentration {c} mol/L. Output a JSON object "
    "whose single numeric field diffusion_1e9_m2_s holds the multiplier x where "
    "D = x * 10^-9 m^2/s."
)

# ---- 冻结的答案格式（训练数据 output；交接文档 §5 步骤 4） ----
ANSWER_OUTPUT_FORMAT = '{"diffusion_1e9_m2_s": <gold>}'
ANSWER_OUTPUT_EXAMPLE = '{"diffusion_1e9_m2_s": 1.234567}'


def render(template: str, system: str, temperature: float, concentration: float) -> str:
    return template.format(
        system=system,
        T=f"{temperature:.2f}",
        c=f"{concentration:.6f}",
    )


def family_block(
    family_id: str, system_text: str, user_template: str,
    rendered_example: str, notes: str,
) -> dict[str, Any]:
    combined = [system_text, user_template]
    return {
        "family_id": family_id,
        "notes": notes,
        "system_text": system_text,
        "user_template_text": user_template,
        "combined_texts": combined,
        "rendered_example": {
            "system": ANCHOR_SYSTEM,
            "temperature_K": ANCHOR_T,
            "concentration_mol_L": ANCHOR_C,
            "prompt": rendered_example,
        },
        "sha256": {
            "system_text": stable_hash(system_text),
            "user_template_text": stable_hash(user_template),
            "combined_texts": stable_hash(combined),
            "rendered_example_prompt": stable_hash(rendered_example),
        },
    }


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-json", type=Path, default=DEFAULT_OUT_JSON)
    args = parser.parse_args()

    rendered_a = prepare_questions.template_text(
        "en", ANCHOR_SYSTEM, ANCHOR_T, ANCHOR_C
    )
    rendered_a_from_literal = render(FAMILY_A_USER_TEMPLATE, ANCHOR_SYSTEM, ANCHOR_T, ANCHOR_C)
    if rendered_a != rendered_a_from_literal:
        raise SystemExit(
            "family A literal template does not reproduce prepare_questions.template_text; "
            "refusing to freeze a drifting prompt family"
        )
    rendered_b = render(FAMILY_B_USER_TEMPLATE, ANCHOR_SYSTEM, ANCHOR_T, ANCHOR_C)
    rendered_c = render(FAMILY_C_USER_TEMPLATE, ANCHOR_SYSTEM, ANCHOR_T, ANCHOR_C)

    rendered_set = {rendered_a, rendered_b, rendered_c}
    if len(rendered_set) != 3:
        raise SystemExit("rendered prompts of A/B/C are not mutually distinct; refusing to freeze")
    if FAMILY_A_SYSTEM == FAMILY_B_SYSTEM:
        raise SystemExit("family A and B system texts must differ")
    if FAMILY_A_USER_TEMPLATE == FAMILY_B_USER_TEMPLATE or FAMILY_A_USER_TEMPLATE == FAMILY_C_USER_TEMPLATE:
        raise SystemExit("user templates must be mutually distinct")
    if FAMILY_B_USER_TEMPLATE == FAMILY_C_USER_TEMPLATE:
        raise SystemExit("family B and C user templates must differ")

    core_path = ROOT / "py" / "LLM_API_direct" / "run_benchmark.py"
    generator_path = ROOT / "py" / "LLM_API_direct" / "prepare_questions.py"

    payload: dict[str, Any] = {
        "artifact_type": "prompt_family_freeze_record",
        "research_plan_version": PLAN_VERSION,
        "frozen_at_utc": utc_now(),
        "frozen_by": "C_arm_executor",
        "rule": (
            "families A/B/C mutually non-verbatim; A = main test (identical to A arm); "
            "B = synonym check (never in training); C = training wording (system identical "
            "to benchmark); hashes frozen before training."
        ),
        "anchor_example": {
            "system": ANCHOR_SYSTEM,
            "temperature_K": ANCHOR_T,
            "concentration_mol_L": ANCHOR_C,
        },
        "answer_output_format": ANSWER_OUTPUT_FORMAT,
        "answer_output_example": ANSWER_OUTPUT_EXAMPLE,
        "answer_output_format_sha256": stable_hash(ANSWER_OUTPUT_FORMAT),
        "families": [
            family_block(
                "A",
                FAMILY_A_SYSTEM,
                FAMILY_A_USER_TEMPLATE,
                rendered_a,
                "main test family; system prompt copied verbatim from shared core "
                "run_benchmark.py SYSTEM_PROMPT; user template copied verbatim from "
                "prepare_questions.py template_text (en). Used for 642 mastery and "
                "external-set evaluation; guarantees direct SFT-Base pairing.",
            ),
            family_block(
                "B",
                FAMILY_B_SYSTEM,
                FAMILY_B_USER_TEMPLATE,
                rendered_b,
                "synonym check family; semantically equivalent to A but reworded; "
                "NEVER used in training; tests template/format generalization.",
            ),
            family_block(
                "C",
                FAMILY_C_SYSTEM,
                FAMILY_C_USER_TEMPLATE,
                rendered_c,
                "training wording family; system prompt identical to benchmark "
                "(family A system); instruction reworded; used only for SFT training data.",
            ),
        ],
        "sources": {
            "family_a_system_source": {
                "path": str(core_path),
                "sha256": sha256_file(core_path),
                "symbol": "SYSTEM_PROMPT",
            },
            "family_a_user_template_source": {
                "path": str(generator_path),
                "sha256": sha256_file(generator_path),
                "symbol": "template_text(language='en')",
            },
            "questions_642": {
                "path": str(QUESTIONS_642),
                "sha256": sha256_file(QUESTIONS_642),
            },
            "gold_642": {
                "path": str(GOLD_642),
                "sha256": sha256_file(GOLD_642),
            },
        },
    }
    payload["freeze_record_sha256"] = stable_hash(
        {key: value for key, value in payload.items() if key != "freeze_record_sha256"}
    )

    out = args.out_json
    if out.exists():
        raise FileExistsError(
            f"{out} already exists; prompt family freeze is one-shot - choose a fresh path"
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    import json
    out.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    print("frozen:", out)
    print("freeze_record_sha256:", payload["freeze_record_sha256"])
    print()
    for family in payload["families"]:
        print("=" * 72)
        print("FAMILY", family["family_id"], "-", family["notes"])
        print("system_text_sha256   :", family["sha256"]["system_text"])
        print("user_template_sha256 :", family["sha256"]["user_template_text"])
        print("combined_sha256      :", family["sha256"]["combined_texts"])
        print("rendered_sha256      :", family["sha256"]["rendered_example_prompt"])
        print("-" * 40)
        print("SYSTEM:")
        print(family["system_text"])
        print("USER TEMPLATE:")
        print(family["user_template_text"])
        print("RENDERED EXAMPLE (NaCl-H2O / 298.15 K / 0.3907 mol/L):")
        print(family["rendered_example"]["prompt"])
    print("=" * 72)
    print("ANSWER OUTPUT FORMAT:", ANSWER_OUTPUT_FORMAT)
    print("answer_output_format_sha256:", payload["answer_output_format_sha256"])


if __name__ == "__main__":
    main()
