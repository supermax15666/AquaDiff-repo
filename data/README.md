# Data

## Included

| Folder | Content |
|---|---|
| `questions/` | 642 main-set questions (`four_system_all_questions.jsonl`), the balanced 240-question sensitivity subset (`four_system_questions.jsonl`, reuses main-set responses) and the analysis-set definitions. **Inputs only — no reference values.** |
| `external/` | 64 frozen external questions, their audit log/manifest and the seal note. **No gold values.** |
| `training/` | The 642-record SFT training set (prompt family C wording) in canonical JSONL, LLaMA-Factory/Alpaca JSON and dataset_info, plus the 64-record pilot and the data manifest with SHA-256 hashes. |
| `prompts/` | Frozen prompt families A (evaluation), B (synonym rewordings, unused in training) and C (training), with per-family hashes. |
| `source_workbooks/` | The four curated source workbooks of confirmed experimental records (NaCl-H2O, KCl-H2O, LiCl-H2O, CaCl2-H2O) that underlie the database and the pooled ground truth. |
| `solubility/` | CRC-92nd-edition derived solubility table used by the saturation rule of the tool host. |
| `D_dataset/` | Conditions and target values used to fit and cross-validate the frozen Arm D models. |

## Important notes

* **The 642 main-set questions are the SFT training set.** Publishing the training
  data therefore also makes the main-set reference values public. Those results are
  reported as *mastery*, not as held-out performance; the held-out evidence is the
  external set.
* **The 64 external reference (gold) values remain sealed.** The original gold file
  is intentionally not distributed; its SHA-256 is published in `external/SEAL.md`
  (and in the manuscript version manifest), and access is available from the
  corresponding author. Per-question external run records that would reveal the
  values are excluded from this repository as well.
* Questions of both sets are also reproduced in the Supporting Information
  (Tables S6/S10), so the repository and the paper are self-consistent.
* The frozen Arm E database (`code/E_agent/db/experimental_records.duckdb`) contains
  the pooled curated records and is required to run the agent. For the 7 external
  questions that are database hits (documented in the paper, Sect. 3.5), the
  database therefore contains the corresponding experimental values; this is a
  property of the evaluated system, not a release of the sealed gold file.
