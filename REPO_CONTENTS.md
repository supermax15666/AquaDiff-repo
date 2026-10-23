# Repository contents and source mapping

This folder is a curated subset of the manuscript working archive. It is built to
be sufficient for re-running the agent, re-scoring the reported metrics and
auditing the training, without shipping model weights, copyright-restricted
literature PDFs, secrets or the sealed external-set gold.

## Included

| Repository path | Content | Original source (working archive) |
|---|---|---|
| `code/E_agent/` | Arm E agent, web demo, evaluation runner, DuckDB database, frozen solubility/challenge assets | `原始数据与分析脚本/10_共享_脚本/E_Agent/` |
| `code/E_agent/agent_core_repaired_r2.py` | repaired agent core used for the end-to-end replay (SI Note S1) | `修复/py/r2/E_Agent/agent_core.py` |
| `code/SLM_direct/` | Arm A/C evaluation client and run configs | `原始数据与分析脚本/10_共享_脚本/SLM_direct/` |
| `code/LLM_API_direct/` | Arm B evaluation client; `config.example.json` is sanitized | `原始数据与分析脚本/10_共享_脚本/LLM_API_direct/` |
| `code/D_ML/` | Arm D frozen numerical backend | `原始数据与分析脚本/10_共享_脚本/3.D_ML/code/` |
| `code/training/` | frozen LoRA YAML configs, freeze records, data-generation scripts | `原始数据与分析脚本/10_共享_脚本/微调/` |
| `code/figures/` | plotting scripts for main-text and SI figures | `01_figures_main/`, `02_figures_SI/`, `10_共享_脚本/汇总与绘图/` |
| `code/external_checks/` | external-set data-chain verification scripts | `07_外部前瞻集_64题/analysis/宏口径配对修正_v1/` |
| `data/questions/` | 642 main-set questions, 240-question sensitivity subset, analysis-set definitions (inputs only) | `01_源数据与题库/题库与gold_642与240/` |
| `data/external/` | 64 frozen external questions, manifest, audit log, seal note (no gold) | `01_源数据与题库/外部前瞻集_64题冻结/frozen/` |
| `data/training/` | 642-record SFT training data, LLaMA-Factory files, 64-record pilot, manifest | `01_源数据与题库/SFT训练数据_642全量/` |
| `data/prompts/` | frozen prompt families A/B/C | `10_共享_脚本/微调/frozen/prompt_families_frozen.json` |
| `data/source_workbooks/` | curated four-system record workbooks | `01_源数据与题库/四体系源工作簿/` |
| `data/solubility/` | CRC-derived solubility table used by the saturation rule | `01_源数据与题库/溶解度数据/` |
| `data/D_dataset/` | feature/target table used to fit Arm D | `05_D臂_ML数值后端/analysis/冻结后端输出/dataset/` |
| `archive/training/` | Arm C training logs, step-wise loss logs, loss plots, handover reports | `04_C臂_SFT训练与掌握度/training/` |
| `archive/metrics/` | per-arm metrics, per-question records, figure source tables | `02_A臂...`, `03_B臂...`, `04_C臂...`, `05_D臂...`, `07_外部...`, `09_共享_绘图数据/` |
| `archive/E_runs/` | Arm E run manifests, metrics and public per-item records | `06_E臂_受限Agent/raw/` |
| `03_实验结果/` | frozen numerical-model registry (path required by `agent_core.py`) | `修复/py/03_实验结果/D臂_ML数值后端_冻结/output/registry/` |
| `provenance/` | source index, version notes, full SHA-256 list (`SHA256SUMS.txt`) | mixed |

## Deliberately excluded

* **Sealed external gold** — `external_gold.evaluator.jsonl` and every per-question
  external record that would reveal reference values (policy: hash published, access
  from the corresponding author). Only aggregate external metrics are included.
* **Arm A/B/C per-question records for the external set** — not applicable for A/B;
  Arm C external per-question records are excluded for the same reason.
* **API keys** — `config.json` and `config.backup_*.json` in the API client contain
  live keys and were excluded; a sanitized `config.example.json` is provided instead.
* **Model weights** — merged checkpoints, GGUF files and adapters (not in this
  workspace; available from the authors / on request).
* **Literature PDFs and the CRC Handbook** (~50 MB, copyright) and the raw external
  search artefacts.
* **Raw per-call dumps and intermediate run directories** (tens of thousands of
  files, multi-hundred-MB) — processed record tables are included instead.
* **Manuscript/SI files, figure image files and internal task books** — the paper
  and its Supporting Information are published separately.
* **Large per-call tables** `源数据_逐次调用_A/B臂.csv` and `源数据_题目级_A/B臂.csv`
  (≈24 MB) — the per-question `sample_level_results.csv` tables are included.
