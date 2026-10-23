# Frozen numerical-model registry (Arm D)

`agent_core.py` (Arm E) hard-codes the location of the frozen per-system numerical
models used for database misses:

```
<repository root>/03_实验结果/D臂_ML数值后端_冻结/output/registry/ffbc8b45.../
```

The folder is kept at this exact relative path so that the published agent code runs
unmodified; `ffbc8b45...` is the registry fingerprint. It contains the four
per-system scikit-learn models (NaCl-H2O, KCl-H2O, LiCl-H2O, CaCl2-H2O), the pooled
control models and `registry.json` (provenance manifest). See `archive/README.md` and
`code/D_ML/` for the model definitions and evaluation protocol.
