# AquaDiff

Companion repository for the manuscript

> **AquaDiff: A Domain-Aware Tool-Augmented Query System for Mutual Diffusion Coefficients in Aqueous Electrolytes**
> *Manuscript under review (2026). DOI/author list to be added on acceptance.*

This repository contains the evaluated source code, frozen assets, question sets,
training artefacts and archived evaluation records of **AquaDiff-Bench**, a
five-arm benchmark for querying mutual diffusion coefficients of aqueous
chloride electrolytes (NaCl-H2O, KCl-H2O, LiCl-H2O, CaCl2-H2O).

The five experimental arms are:

| Arm | Configuration |
|---|---|
| A | five local open-source base models, closed-book |
| B | six commercial API models, closed-book |
| C | the same five local architectures after supervised fine-tuning (LoRA) |
| D | frozen per-system numerical backend (ML models) |
| E | **AquaDiff**: Qwen3-4B front end + deterministic tool host (database + frozen models + rules) |

## Repository layout

```
code/                     evaluated source code
  E_agent/                Arm E: two-stage constrained agent (core, web demo, eval runner)
  SLM_direct/             Arm A/C evaluation client (local models, mastery runs)
  LLM_API_direct/         Arm B evaluation client (API models)
  D_ML/                   Arm D: frozen numerical backend (training + evaluation)
  training/               Arm C: frozen LoRA configs, freeze records, data generation
  figures/                plotting scripts for the main-text and SI figures
  external_checks/        data-chain verification scripts for the external set
frozen assets that the code loads by relative path:
  code/E_agent/db/        DuckDB experimental database (frozen)
  code/E_agent/frozen/    solubility table + challenge set (frozen)
  03_实验结果/           frozen numerical-model registry (path fixed in agent_core.py)
data/                     question sets, training data, prompts, source workbooks
archive/                  training logs/loss curves, per-arm metrics, per-item records
provenance/               version notes, source index, file hashes
```

## Quick start: run the AquaDiff agent (Arm E)

Requirements: Python >= 3.10, `pip install -r requirements.txt`, and a local
OpenAI-compatible LLM endpoint. The evaluated configuration used **LM Studio
0.4.20 serving Qwen3-4B-Instruct-2507 (Q4_K_M) at `http://127.0.0.1:1234/v1`**
with `temperature = 0`.

```bash
python code/E_agent/agent_web.py          # web demo -> http://127.0.0.1:8317
python code/E_agent/agent_demo.py         # command-line demo
python code/E_agent/run_agent_eval.py --set smoke --base-url http://127.0.0.1:1234/v1
```

A cloud OpenAI-compatible endpoint can be used instead; the API key is read from
the `AQUADIFF_API_KEY` environment variable (never commit a key).

> **Path note.** `agent_core.py` resolves the frozen numerical-model registry at a
> fixed relative path (`<repo>/03_实验结果/D臂_ML数值后端_冻结/output/registry/ffbc8b45.../`).
> That directory is preserved here exactly as in the evaluated environment so the
> published code runs unmodified.

## Reproducing the reported numbers

* `archive/metrics/` – per-arm metrics tables, summaries and per-question records
  for Arms A, B, C, D, the external-set comparison and the 240-question
  reasoning-sensitivity subset.
* `archive/E_runs/` – run manifests, metrics and per-item records of the reported
  Arm E runs (main set and challenge set). Each manifest records the SHA-256 of
  the exact code and frozen assets used at run time.
* `archive/training/` – Arm C training logs (`train.log`), step-wise loss logs
  (`trainer_log.jsonl`, one point every 5 steps), the framework-generated loss
  plots and the handover reports (hyper-parameters, hashes, runtimes).
* `archive/metrics/plot_data/` – the source tables behind every figure.
* `code/figures/` – the plotting scripts. They were written for the original
  working archive; input paths may need to be pointed at the folders above.

## Data and code provenance

* **Training data.** Arm C used all 642 main-set conditions (prompt family C) with
  the same gold answers and lineage mapping as the other arms. The main set is
  therefore a *mastery* set for SFT, not a held-out test; held-out evidence comes
  from the 64-question frozen external set. See `data/README.md`.
* **External set.** The 64 external questions are published here and in the
  Supporting Information (Table S10). The original reference (gold) values remain
  **sealed**: only their SHA-256 is published (`data/external/SEAL.md`), access is
  available from the corresponding author, and the per-question external records
  that would reveal them are not included in this repository.
* **Agent versions.** Two code versions are provided: `code/E_agent/agent_core.py`
  (archived consolidated version, SHA-256 `f335886c1818a369281d7cd15ff4cd7c4d7f73108a45a7c03c84e23178398876`) and
  `code/E_agent/agent_core_repaired_r2.py` (repaired version used for the
  end-to-end replay reported in SI Note S1, SHA-256 `b8ffaae8403dba534963b711e2c0894c34b6f41b3d9de9015c89703f7bbd7418`). The exact code versions
  that produced the historical external/main-set runs are **not** in the archive;
  as stated in SI Note S1, those runs cannot be reconstructed bit-for-bit, but
  scores can be recomputed from the per-item records. See `provenance/README.md`.
* **Secrets.** No API keys are stored in this repository. The Arm B client is
  shipped with a sanitized `config.example.json`; copy it to `config.json` and set
  your own key locally (that file is git-ignored).

## License

* Code: MIT (`LICENSE`).
* Data, documentation and archived records: CC BY 4.0 (`DATA_LICENSE.md`).
* Third-party experimental data compiled in `data/source_workbooks/` remain
  subject to the conditions of their original publications.

## Citation

Please cite the accompanying manuscript. A `CITATION.cff` template is provided;
the author list, paper DOI and repository DOI will be filled in on acceptance.
