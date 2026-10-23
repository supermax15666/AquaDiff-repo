# API LLM direct-answer benchmark

This report is generated from immutable raw-response hashes and evaluator-side gold joins.
The bundled question set is an exploratory pilot because the historical holdout was already opened.

| Model key | Analysis set | N prompts | Numeric coverage | Micro Accuracy@10% | Macro-system Accuracy@10% | MAE (valid) | MdAPE (valid) |
|---|---|---:|---:|---:|---:|---:|---:|
| qwen3_8b_instruct_sft_q4km | primary_all_eligible_unique_conditions | 642 | 100.0% | 90.7% | 90.6% | 0.0747 | 2.1234% |
| qwen3_8b_instruct_sft_q4km | sensitivity_balanced_60_per_system | 240 | 100.0% | 93.3% | 93.3% | 0.0634 | 1.6907% |

Accuracy denominators include every scheduled sample. Valid-only error metrics must always be presented with numeric coverage.
Confidence intervals fix solution systems and resample origin lineages as clusters; repeated API calls remain nested within each base prompt.
The balanced 240-question sensitivity view reuses the exact responses from the 642-question primary run and adds zero API calls.
