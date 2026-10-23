# -*- coding: utf-8 -*-
"""Flip formal gates: formal_ready=true for all five models + protocol_frozen=true."""
import json
from pathlib import Path

p = Path(__file__).resolve().parent / "config.json"
cfg = json.loads(p.read_text(encoding="utf-8"))
for model in cfg["models"].values():
    model["formal_ready"] = True
cfg["protocol_frozen"] = True
p.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print("formal_ready set for:", sorted(cfg["models"]))
print("protocol_frozen:", cfg["protocol_frozen"])
