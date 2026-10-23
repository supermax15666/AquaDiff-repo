# -*- coding: utf-8 -*-
"""Prepare thinking sensitivity assets per plan v2.11.

1. Extract the frozen 240-question sensitivity subset ids into
   questions_240_sensitivity.json (same 240 reused by the main comparison).
2. Create/refresh config_thinking_sensitivity.json from config.json with:
   - inference.max_output_tokens = 16384 (v2.11; 4096 caused 38% truncation,
     old-pilot 8192 still had ~26% truncation)
   - 27B deployment.context_length = 32768
   - 27B reasoning_mode = "enabled"
   - 27B question_ids_file = questions_240_sensitivity.json (240 x 3 = 720 calls)
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
QUESTIONS = Path(
    r"E:\Desktop\CET_docment\CET_docment\py\LLM_API_direct\questions"
)

sets_path = QUESTIONS / "four_system_analysis_sets.json"
sets = json.loads(sets_path.read_text(encoding="utf-8"))
subset = None
for entry in sets["sets"]:
    if entry.get("analysis_set_id") == "sensitivity_balanced_60_per_system":
        subset = entry
        break
assert subset is not None, "sensitivity_balanced_60_per_system set not found"
raw = subset["question_ids"]
if isinstance(raw, str):
    ids = [x for x in raw.split() if x.strip()]
else:
    ids = [str(x) for x in raw]
assert len(ids) == 240, f"expected 240 ids, got {len(ids)}"
assert len(set(ids)) == 240, "duplicate ids in subset"

ids_path = BASE / "questions_240_sensitivity.json"
ids_path.write_text(
    json.dumps({"question_ids": ids}, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
print("wrote", ids_path, "with", len(ids), "ids")

cfg_path = BASE / "config.json"
dst = BASE / "config_thinking_sensitivity.json"
cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
cfg["inference"]["max_output_tokens"] = 16384
m = cfg["models"]["qwen3_6_27b_base_q4km"]
m["deployment"]["context_length"] = 32768
m["reasoning_mode"] = "enabled"
m["question_ids_file"] = "questions_240_sensitivity.json"
dst.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(
    "wrote", dst, "| max_tokens", cfg["inference"]["max_output_tokens"],
    "| ctx", m["deployment"]["context_length"],
    "| reasoning", m["reasoning_mode"],
    "| qids", m["question_ids_file"],
)
