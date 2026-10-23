# -*- coding: utf-8 -*-
"""Mark the two overnight formal runs invalidated (plan §8 / §7).

The server had no model loaded during most of each run (HTTP 400
"No models loaded"), so 66-71% of samples are empty. These runs are voided
and must be re-run with the model loaded. Only the manifest status and
reason are changed; all raw artifacts stay untouched.
"""
import json
from datetime import datetime, timezone
from pathlib import Path

TARGETS = [
    Path(
        r"E:\Desktop\CET_docment\CET_docment\py\results\SLM_direct\protocol_v2_2"
        r"\lm_studio__qwen3_4b_instruct_2507_base_q4km__cet-gguf_qwen3-4b-instruct-2507_q4_k_m"
        r"\runs\qwen3-4b-instrust-2507-base_p_406a39f8ad__20260815T184528139366Z_f610b7cba7"
        r"\run_manifest.json"
    ),
    Path(
        r"E:\Desktop\CET_docment\CET_docment\py\results\SLM_direct\protocol_v2_2"
        r"\lm_studio__qwen3_6_27b_base_q4km__qwen3.6-27b_q4_k_m"
        r"\runs\qwen3.6-27b_base_primary_q4km_v1__20260815T145201170457Z_bcd777e2ad"
        r"\run_manifest.json"
    ),
]

REASON = (
    "2026-08-16: majority of samples failed with HTTP 400 'No models loaded' "
    "(LM Studio had no model loaded during most of the run; 4B 1272/1926 and "
    "27B 1362/1926 empty answers). Voided per plan §7/§8; must be re-run as a "
    "whole with the model loaded on the server."
)


def main() -> None:
    now = datetime.now(timezone.utc).isoformat()
    for path in TARGETS:
        if not path.is_file():
            print(f"SKIP (missing): {path}")
            continue
        manifest = json.loads(path.read_text(encoding="utf-8"))
        if manifest.get("status") != "completed":
            print(f"SKIP (status={manifest.get('status')}): {path.parent.name}")
            continue
        manifest["status"] = "invalidated"
        manifest["invalidation_reason"] = REASON
        manifest["invalidation_recorded_at_utc"] = now
        path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"INVALIDATED: {path.parent.name}")


if __name__ == "__main__":
    main()
