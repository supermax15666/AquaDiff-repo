# Archived records

| Folder | Content |
|---|---|
| `training/` | Arm C (SFT) handover package: `train.log` (full framework log), `trainer_log.jsonl` (one loss/learning-rate point every 5 optimization steps), `training_loss.png` (framework-generated curve), the five-model handover list (`回传清单.md`) and the execution reports with all SHA-256 hashes. |
| `metrics/A_arm/` | Arm A (five local base models, 642 main set): metrics, summary and per-question `sample_level_results.csv`. |
| `metrics/A_arm_thinking_sensitivity/` | Qwen3.6-27B reasoning sensitivity on the balanced 240-question subset. |
| `metrics/B_arm/` | Arm B (six API models): metrics, summary and per-question records. |
| `metrics/C_arm/` | Arm C (five SFT models, 642 mastery): per-model metrics/summary/per-question records and the consolidated metric CSVs. |
| `metrics/D_arm/` | Arm D frozen backend: consolidated registry/selection summary, figure tables and external-set predictions. |
| `metrics/external_64/` | External-set comparisons (Base/SFT/ML), per-model metric tables and the paired-bootstrap tables. |
| `metrics/plot_data/` | Source tables behind all main-text and SI figures. |
| `E_runs/` | Arm E run manifests, metrics and per-item records for the reported main-set and challenge-set runs. The external-set run contributes its manifest and aggregates only (per-item records would reveal the sealed gold). |

Notes

* File hashes for every archived file are listed in `provenance/SHA256SUMS.txt`.
* The Arm E manifests record the exact `agent_core.py` and frozen-asset hashes used
  at run time; see `provenance/README.md` for the version history.
* Per-call dumps (one record per transport attempt) were not copied because of size;
  the per-question tables contain the accepted answers and all scoring columns.
