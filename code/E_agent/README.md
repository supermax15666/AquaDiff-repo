# Arm E — AquaDiff agent

Two-stage constrained agent: a language model performs only intent extraction and
final-answer transcription; validation, unit conversion, saturation handling,
routing, applicability-domain checks and payload validation are executed
deterministically by the host (`agent_core.py`). The tool contract is described in
`工具契约.md` (Chinese); the solubility-table data plan is in
`饱和度数据收集方案.md` (Chinese).

| File | Purpose |
|---|---|
| `agent_core.py` | host runtime: database lookup, saturation rule, applicability box, frozen-model registry, payload validation |
| `agent_core_repaired_r2.py` | repaired R2 variant used for the end-to-end replay (SI Note S1) |
| `run_agent_eval.py` | evaluation runner (writes `sample_results.jsonl` + `run_manifest.json` + `metrics_summary.md`) |
| `analyze_agent_eval.py` | scoring/analysis of a run directory |
| `agent_web.py` | zero-dependency web UI used for the graphical abstract demonstration |
| `agent_demo.py` | command-line demo |
| `agent_web_v1_backup.py` | previous web-UI version (kept for provenance) |
| `build_duckdb.py` | rebuilds `db/experimental_records.duckdb` from the source workbooks |
| `extract_solubility_crc.py`, `precheck_solubility.py`, `make_challenge_set.py` | frozen-asset construction/checks |
| `test_host_routing.py`, `test_web_stream.py` | host-routing and streaming tests |
| `db/`, `frozen/` | frozen database, solubility table and challenge set |

Runtime requirements: Python >= 3.10, `duckdb`, `joblib`; a local
OpenAI-compatible LLM endpoint (evaluated configuration: LM Studio 0.4.20 serving
`qwen3-4b-instruct-2507@q4_k_m` at `http://127.0.0.1:1234/v1`, temperature 0).

The frozen numerical-model registry is resolved by `agent_core.py` relative to the
repository root (see `03_实验结果/README.md`). The sealed external-set gold is not
needed to run the agent.

Version provenance: see `provenance/README.md`.
