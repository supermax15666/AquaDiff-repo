# Configuration note

The evaluated Arm B client read its settings from `config.json`, which contained a
live provider API key and is therefore **not** included in this repository (it is
also git-ignored).

Use `config.example.json` as the template:

1. copy it to `config.json` (same folder);
2. set `api_key` (or keep it empty if you use the environment);
3. keep `question_file`, `evaluator_gold_file` etc. pointing at `data/questions/`
   and the evaluator gold file, which is available from the corresponding author.

Original backup configs for the six providers were removed for the same reason.
