# API LLM direct-answer benchmark

This report is generated from immutable raw-response hashes and evaluator-side gold joins.
The bundled question set is an exploratory pilot because the historical holdout was already opened.

| Model key | Analysis set | N prompts | Numeric coverage | Micro Accuracy@10% | Macro-system Accuracy@10% | MAE (valid) | MdAPE (valid) |
|---|---|---:|---:|---:|---:|---:|---:|
| gemma2_9b_it_sft_q4km | primary_all_eligible_unique_conditions | 642 | 100.0% | 98.6% | 97.5% | 0.0227 | 0.5356% |
| gemma2_9b_it_sft_q4km | sensitivity_balanced_60_per_system | 240 | 100.0% | 97.1% | 97.1% | 0.0231 | 0.5042% |

Accuracy denominators include every scheduled sample. Valid-only error metrics must always be presented with numeric coverage.
Confidence intervals fix solution systems and resample origin lineages as clusters; repeated API calls remain nested within each base prompt.
The balanced 240-question sensitivity view reuses the exact responses from the 642-question primary run and adds zero API calls.
