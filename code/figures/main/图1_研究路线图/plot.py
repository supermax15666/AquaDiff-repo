# -*- coding: utf-8 -*-
"""Fig. 1 Research roadmap (WaterRAG-style single-flow pipeline).
Five color-coded stages with sub-items, connected by bold arrows.
Below: compact model roster + evaluation summary.
Output: 图1_研究路线图.pdf / .png
"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

fig = plt.figure(figsize=(DOUBLE, 3.8))
ax = fig.add_axes([0, 0, 1, 1]); ax.set_xlim(0, 1); ax.set_ylim(0, 1); ax.axis("off")

STAGES = [
    {"title": "Data Pool", "color": "#E3F2FD", "ec": "#1565C0", "tc": "#0D47A1",
     "items": ["4 binary systems", "785 records / 45 lineages"]},
    {"title": "Lineage Audit", "color": "#E8F5E9", "ec": "#2E7D32", "tc": "#1B5E20",
     "items": ["exclude derived values", "SHA-256 frozen"]},
    {"title": "AquaDiff-Bench", "color": "#FFF3E0", "ec": "#E65100", "tc": "#BF360C",
     "items": ["642 main + 240 sensitivity", "+ 64 frozen external"]},
    {"title": "5-Arm Evaluation", "color": "#F3E5F5", "ec": "#6A1B9A", "tc": "#4A148C",
     "items": ["A/B closed-book, C SFT", "D frozen ML, E AquaDiff"]},
    {"title": "Key Findings", "color": "#FFEBEE", "ec": "#C62828", "tc": "#B71C1C",
     "items": ["closed-book unreliable", "AquaDiff: Acc+Trace+Safe"]},
]

n = len(STAGES)
bw = 0.164
gap = (1.0 - 0.02 - n * bw) / (n - 1)
y0 = 0.52
bh = 0.30

for i, st in enumerate(STAGES):
    x = 0.01 + i * (bw + gap)
    ax.add_patch(FancyBboxPatch((x, y0), bw, bh,
                                boxstyle="round,pad=0.005,rounding_size=0.012",
                                fc=st["color"], ec=st["ec"], lw=1.4))
    cx = x + bw / 2
    ax.add_patch(plt.Circle((cx, y0 + bh - 0.028), 0.014,
                            fc=st["ec"], ec="white", lw=1.0, zorder=5))
    ax.text(cx, y0 + bh - 0.028, str(i + 1), ha="center", va="center",
            fontsize=7, color="white", fontweight="bold", zorder=6)
    ax.text(cx, y0 + bh - 0.065, st["title"], ha="center", va="top",
            fontsize=7.5, fontweight="bold", color=st["tc"])
    for j, item in enumerate(st["items"]):
        ax.text(cx, y0 + bh - 0.115 - j * 0.038, item, ha="center", va="top",
                fontsize=5.8, color="#333333")
    if i < n - 1:
        ax.add_patch(FancyArrowPatch((x + bw + 0.003, y0 + bh / 2),
                                     (x + bw + gap - 0.003, y0 + bh / 2),
                                     arrowstyle="-|>", mutation_scale=14,
                                     lw=2.0, color="#666666"))

# bottom: models + evaluation
ax.add_patch(FancyBboxPatch((0.01, 0.06), 0.46, 0.38,
                            boxstyle="round,pad=0.005,rounding_size=0.012",
                            fc="#FAFAFA", ec="#9E9E9E", lw=0.8))
ax.text(0.03, 0.415, "Models (11 + agent front end)", fontsize=6.5,
        fontweight="bold", color="#424242")
col1 = ["A: Qwen3-4B (anchor)", "   Qwen3-8B / 27B", "   Llama-3.1-8B / Gemma-2-9B"]
col2 = ["B: kimi-k3 / doubao / deepseek", "   glm-5.2 / qwen3.8-max / MiniMax", "E: same Qwen3-4B + tool stack"]
for j, (t1, t2) in enumerate(zip(col1, col2)):
    ax.text(0.03, 0.365 - j * 0.055, "· " + t1, fontsize=5.6, va="top", color="#333")
    ax.text(0.25, 0.365 - j * 0.055, "· " + t2, fontsize=5.6, va="top", color="#333")
ax.text(0.03, 0.20, "Unified (local): LM Studio · temp=0 · 3 repeats · 1926 calls/model",
        fontsize=5.4, va="top", color="#666")
ax.text(0.03, 0.158, "Kimi: temp = 1 (platform exception; Tab. 2)",
        fontsize=5.0, va="top", color="#666")

ax.add_patch(FancyBboxPatch((0.53, 0.06), 0.46, 0.38,
                            boxstyle="round,pad=0.005,rounding_size=0.012",
                            fc="#FAFAFA", ec="#9E9E9E", lw=0.8))
ax.text(0.55, 0.415, "Evaluation protocol", fontsize=6.5,
        fontweight="bold", color="#424242")
eval_items = [
    "· Primary: macro-system Acc@10% (equal weight over 4 systems)",
    "· CI: lineage-clustered paired bootstrap (10,000×)",
    "· Paired contrasts: C−A (fine-tuning), E−A (tool augmentation), E−D (interface loss)",
    "· Scoring: fully deterministic (numeric tolerance + verbatim comparison)",
]
for j, item in enumerate(eval_items):
    ax.text(0.55, 0.365 - j * 0.050, item, fontsize=5.4, va="top", color="#333")

save(fig, "图1_研究路线图", __file__)
