# Provenance notes

## Code versions

| File in this repository | SHA-256 | Role |
|---|---|---|
| `code/E_agent/agent_core.py` | `f335886c1818a369281d7cd15ff4cd7c4d7f73108a45a7c03c84e23178398876` | Archived consolidated agent core (the "editorial" version preserved with the data package). |
| `code/E_agent/agent_core_repaired_r2.py` | `b8ffaae8403dba534963b711e2c0894c34b6f41b3d9de9015c89703f7bbd7418` | Repaired R2 version, used for the end-to-end replay of 2,280 logical tasks reported in SI Note S1. |

The run manifests in `archive/E_runs/` record the `agent_core_sha256` values of the
runs they describe (for example `fba67019994a...` for the final main-set run and
`0bab1626...` for the earlier external run). **Those historical code versions are
not present in the archive.** As stated in SI Note S1, the historical external and
main-set runs cannot be reconstructed bit-for-bit from the available code, but all
reported scores can be recomputed from the per-item records included here.

## Frozen training configuration

* Training-configuration freeze record SHA-256:
  `b932fdc4549d401ed4d2a0bdcc926411c8191df4fed43cfdea979d2b07c9acb1`
  (`code/training/frozen/training_config_frozen.json`).
* LLaMA-Factory dataset `train_642.json` SHA-256:
  `f95b8a5587bf41ce01573ad579be04fe39c43554099c50e509b75af189759ba4`.
* `dataset_info.json` SHA-256:
  `63d405be1414f97aaaeb0e11b1fdd43ad1cfd07f0d57cbc9c6a3b10cd2d80290`.
* Prompt-family freeze record SHA-256:
  `765bd2775d4e507960716cce3543b423048fb166afe530666ef20ff55382ac05`.

## Frozen inference assets

* Experimental database (`code/E_agent/db/experimental_records.duckdb`):
  `785ab83afd75a4b5addd14f57bdf9c55168a216d97be119b441a153a60725cd1`.
* Solubility table records content (`code/E_agent/frozen/solubility_frozen.json`):
  `b7d40c4f3b24235ef70d051774c08de899d981b5aab3c81686995c79c9e46c88`.
* Frozen numerical-model registry fingerprint:
  `ffbc8b45278774e9317b8c53780753fd3a180f351dff7defed77d1bb4ce63ad6`
  (the registry folder name is its fingerprint).

## External prospective set

* Questions SHA-256: `624db157768072d2d453e6fb46e87a0983a974254def39b8a782daab677fe637`.
* Gold SHA-256 (published hash only; the file is not distributed):
  `c09eb6d25c0b8086b4e0e136a7dc94aca202525b950c6ce66511935820a0bed5`.
* The freeze/seal record is reproduced in `data/external/SEAL.md`.

## File hashes

`SHA256SUMS.txt` lists the SHA-256 of every file in this repository (recomputed for
this release). It can be verified with standard tools, e.g.
`sha256sum -c SHA256SUMS.txt` on Linux/macOS, or PowerShell
`Get-FileHash -Algorithm SHA256`.
