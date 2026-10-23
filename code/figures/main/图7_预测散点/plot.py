# -*- coding: utf-8 -*-
"""Fig. 7/8 Observed-vs-predicted faceted scatter (split version):
- 图7_预测散点_API: six API models, panels (a)–(f), 2 x 3 grid;
- 图8_预测散点_本地: five local base models, panels (a)–(e), 2 x 3 grid (one slot off).
Each panel: frameless legend at top-left (or lower-right if points overlap);
y=x line + ±10% band; identical axis domain across all panels and both figures
(domain computed over all eleven models, as in the original combined figure).
Output: 图7_预测散点_API.pdf/.png/.tif, 图8_预测散点_本地.pdf/.png/.tif
"""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
FIGDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
import matplotlib.pyplot as plt
import numpy as np

data = {}
for src in ("fig7_scatter_B.csv", "fig7_scatter_A.csv"):
    with open(os.path.join(FIGDATA, src), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["predicted_median"].strip():
                data.setdefault(r["model"], []).append(
                    (r["system"], float(r["observed"]), float(r["predicted_median"])))

ORDER_B = ["kimi-k3", "doubao-seed", "deepseek", "glm", "qwen3.8", "MiniMax"]
ORDER_A = ["qwen3_4b", "qwen3_8b", "qwen3_6_27b", "llama3_1_8b", "gemma2"]
api = sorted([m for m in data if any(k in m for k in ORDER_B)],
             key=lambda m: next(i for i, k in enumerate(ORDER_B) if k in m))
loc = sorted([m for m in data if any(k in m for k in ORDER_A)],
             key=lambda m: next(i for i, k in enumerate(ORDER_A) if k in m))

# axis domain computed over ALL eleven models (identical in both figures,
# same as the original combined figure)
all_models = api + loc
all_obs = [o for m in all_models for _, o, _ in data[m]]
all_pred = [p for m in all_models for _, _, p in data[m]]
lo = 0
hi = max(max(all_obs), float(np.quantile(all_pred, 0.999))) * 1.06
n_clip = sum(1 for p in all_pred if p > hi)

SYS_PLOT = ["NaCl", "KCl", "LiCl", "CaCl2"]


def draw_block(models, block_label, out_name):
    """2 x 3 grid for one block; panels (a)-..., x labels on bottom row only."""
    fig, axes = plt.subplots(2, 3, figsize=(DOUBLE, 4.6),
                             gridspec_kw=dict(left=0.065, right=0.99, top=0.885,
                                              bottom=0.10, hspace=0.52, wspace=0.28))
    for idx, (m, ax) in enumerate(zip(models, axes.flat)):
        pts = data[m]
        for sk in SYS_PLOT:
            sub = [(o, p) for s, o, p in pts if sk.lower() in s.lower()]
            if sub:
                ax.scatter([o for o, _ in sub], [p for _, p in sub], s=4.5,
                           color=sys_color(sk), alpha=0.65, edgecolors="none", zorder=3,
                           label=sys_display(sk))
        ax.plot([lo, hi], [lo, hi], color=BLACK, lw=0.7, zorder=2)
        ax.plot([lo, hi], [lo * 1.1, hi * 1.1], color=GREY, lw=0.55, ls="--", zorder=1)
        ax.plot([lo, hi], [lo * 0.9, hi * 0.9], color=GREY, lw=0.55, ls="--", zorder=1)
        ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
        tick_vals = np.arange(0, hi, 2.5)      # 界内刻度，避免出界尾刻度压面板标号
        ax.set_xticks(tick_vals); ax.set_yticks(tick_vals)
        ax.set_aspect("equal")
        ax.set_title(model_display(m), fontsize=7)
        if idx < 3:
            ax.tick_params(labelbottom=False)   # 顶行不标 x 刻度，仅末行标注
        else:
            ax.set_xlabel("Observed D (10$^{-9}$ m²/s)")
        if idx % 3 == 0:
            ax.set_ylabel("Predicted median\n(10$^{-9}$ m²/s)", fontsize=6)
        panel_label(ax, chr(97 + idx), x=-0.20, y=1.06)
        # 图例：无框；若左上区域有点则改右下角，避免点盖字
        hit_ul = any(o < lo + (hi - lo) * 0.42 and p > lo + (hi - lo) * 0.58
                     for _, o, p in pts)
        ax.legend(loc="lower right" if hit_ul else "upper left", fontsize=5.0,
                  frameon=False, handletextpad=0.2,
                  borderaxespad=0.4, labelspacing=0.25, markerscale=0.8)

    # hide unused slots
    for j in range(len(models), 6):
        axes.flat[j].axis("off")

    # block label anchored to the figure top edge, right aligned (clear of panel titles)
    fig.text(0.99, 0.985, block_label, fontsize=8, fontweight="bold",
             color="#333333", ha="right", va="top")

    save(fig, out_name, __file__)


draw_block(api, "API models (Arm B)", "图7_预测散点_API")
draw_block(loc, "Local base models (Arm A)", "图8_预测散点_本地")

if n_clip:
    print("note: %d predictions clipped at y-limit %.2f" % (n_clip, hi))
