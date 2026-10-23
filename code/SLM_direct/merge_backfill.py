# -*- coding: utf-8 -*-
"""Merge identity_backfill_*.json (from back.json/) into config.json.

Read-only w.r.t. the backfill files; writes config.json in place (atomic via temp).
Usage: python merge_backfill.py
"""
import json
from pathlib import Path

BASE = Path(__file__).resolve().parent
CFG = BASE / "config.json"
BACKDIR = BASE / "back.json"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


def main() -> None:
    backfills = [load(p) for p in sorted(BACKDIR.glob("identity_backfill_*.json"))]
    assert len(backfills) == 5, f"expected 5 backfill files, got {len(backfills)}"

    commits = {b["llama_cpp_commit"] for b in backfills}
    assert len(commits) == 1, f"llama_cpp_commit mismatch: {commits}"
    runtimes = {b["lm_studio"]["runtime_version"] for b in backfills}
    assert len(runtimes) == 1, f"runtime mismatch: {runtimes}"
    apps = {b["lm_studio"]["app_version"] for b in backfills}
    assert len(apps) == 1, f"app version mismatch: {apps}"

    cfg = load(CFG)
    for b in backfills:
        mk = b["model_key"]
        assert mk in cfg["models"], f"config has no model entry {mk}"
        m = cfg["models"][mk]
        m["served_model_id"] = b["lm_studio"]["served_model_id_actual"]
        m["base_checkpoint"]["revision"] = b["revision"]
        m["base_checkpoint"]["snapshot_manifest_sha256"] = b["snapshot_manifest_sha256"]
        g = m["gguf"]
        g["source_kind"] = "self_converted"
        g["filename"] = b["gguf"]["filename"]
        g["local_path"] = b["gguf"]["local_path"]
        g["sha256"] = b["gguf"]["sha256"]
        g["converter_commit"] = b["llama_cpp_commit"]
        d = m["deployment"]
        d["lmstudio_load_key"] = b["lm_studio"]["native_model_key"]
        d["native_model_key"] = b["lm_studio"]["native_model_key"]
        d["native_selected_variant"] = b["lm_studio"]["native_selected_variant"]
        d["lm_studio_app_version"] = b["lm_studio"]["app_version"]
        d["lm_studio_runtime_version"] = b["lm_studio"]["runtime_version"]
        d["gpu_offload"] = "max"
        print(
            f"merged {mk}: served={m['served_model_id']} "
            f"rev={b['revision'][:10]} gguf={b['gguf']['filename']}"
        )

    tmp = CFG.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    tmp.replace(CFG)
    print(f"config.json written ({CFG})")


if __name__ == "__main__":
    main()
