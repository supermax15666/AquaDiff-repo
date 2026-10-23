# -*- coding: utf-8 -*-
"""Fig. 11 Base-to-SFT paired results (two panels, fully colored, journal palette).
(a) 642-set mastery dumbbells; (b) external-set dumbbells + gain forest.
Colors: seaborn-deep per model; Base = light tint, SFT = solid; both panels have
y-axis labels and independent boxed legends.
Output: 图11_SFT配对.pdf / .png
"""
import os, sys, csv, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
TABLEDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

rows = []
with open(os.path.join(TABLEDATA, "表6_C臂SFT配对结果.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        rows.append(r)

def ci(v):
    m = re.findall(r"-?[\d.]+", v)
    return float(m[0]), float(m[1])

# seaborn-deep palette per model
MC = {
    "Qwen3-4B": "#C44E52", "Qwen3-8B": "#DD8452", "Qwen3.6-27B": "#55A868",
    "Llama-3.1-8B": "#4C72B0", "Gemma-2-9B": "#8172B3",
}

def tint(c, f=0.55):
    r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
    r = int(r + (255 - r) * f); g = int(g + (255 - g) * f); b = int(b + (255 - b) * f)
    return "#%02x%02x%02x" % (r, g, b)

fig, (axA, axB) = plt.subplots(1, 2, figsize=(DOUBLE, 3.2),
                               gridspec_kw=dict(left=0.16, right=0.985, top=0.88, bottom=0.20,
                                                wspace=0.42))
ys = np.arange(len(rows))[::-1]
ylabels = [r["模型"] for r in rows]

# ---------- (a): 642 mastery dumbbells ----------
for y, r in zip(ys, rows):
    b, s = float(r["Base 642 macro%"]), float(r["SFT 642 macro%"])
    c = MC.get(r["模型"], "#888888")
    cl = tint(c)
    axA.plot([b, s], [y, y], color=c, lw=1.4, alpha=0.6, zorder=1)
    axA.plot(b, y, "o", color=cl, mec=c, mew=0.8, ms=5.0, zorder=3)
    axA.plot(s, y, "o", color=c, ms=5.5, zorder=4)
    axA.text(b - 1.5, y, "%.1f" % b, ha="right", va="center", fontsize=5.2, color=c)
    axA.text(s + 1.5, y + 0.30, "%.1f" % s, ha="left", va="bottom", fontsize=5.2, color=c,
             fontweight="bold")
    axA.text(108, y, "+%.1f" % float(r["642增益pp"].lstrip("+")), va="center", ha="left",
             fontsize=5.4, color=c, fontweight="bold")
axA.set_yticks(ys)
axA.set_yticklabels(ylabels, fontsize=6.5)
for tick, r in zip(axA.get_yticklabels(), rows):
    tick.set_color(MC.get(r["模型"], "#333333"))
axA.set_xlim(-2, 114); axA.set_xticks([0, 25, 50, 75, 100])
axA.set_xlabel("macro-system Acc@10% (%), 642-set mastery", fontsize=7.0)
axA.set_title("(a)  642-set mastery (Base → SFT)", fontsize=7.5, loc="left")
axA.grid(axis="x", lw=0.4, color="#DDDDDD"); axA.set_axisbelow(True)
axA.set_ylim(-0.6, len(rows) - 0.4)

# (a) 图例：左上角，带黑框
hA = [Line2D([0], [0], marker="o", color="#888", mfc="#CCC", mec="#888", ms=4.5, lw=0,
             label="Base (light)"),
      Line2D([0], [0], marker="o", color="#888", mfc="#888", mec="#888", ms=4.5, lw=0,
             label="SFT (solid)")]
legA = axA.legend(handles=hA, loc="upper center", bbox_to_anchor=(0.5, -0.18),
                  ncol=2, fontsize=5.6, frameon=False)

# ---------- (b): external dumbbells + forest ----------
for y, r in zip(ys, rows):
    b, s = float(r["Base外部macro%"]), float(r["SFT外部macro%"])
    d = float(r["外部配对差pp"].lstrip("+"))
    lo, hi = ci(r["外部差CI95"])
    c = MC.get(r["模型"], "#888888")
    cl = tint(c)
    yd, yf = y + 0.22, y - 0.24
    axB.plot([b, s], [yd, yd], color=c, lw=1.4, alpha=0.6, zorder=1)
    axB.plot(b, yd, "o", color=cl, mec=c, mew=0.8, ms=4.4, zorder=3)
    axB.plot(s, yd, "o", color=c, ms=4.8, zorder=4)
    axB.text(b - 1.2, yd, "%.1f" % b, ha="right", va="center", fontsize=5.0, color=c)
    axB.text(s + 1.2, yd, "%.1f" % s, ha="left", va="center", fontsize=5.0, color=c,
             fontweight="bold")
    axB.plot([lo, hi], [yf, yf], color=c, lw=1.2, zorder=2)
    for xx in (lo, hi):
        axB.plot([xx, xx], [yf - 0.10, yf + 0.10], color=c, lw=1.2, zorder=2)
    axB.plot(d, yf, "D", color=c, ms=3.5, zorder=4)
    axB.text(d, yf - 0.36, "+%.1f" % d, ha="center", fontsize=5.0, color=c, fontweight="bold")
    axB.text(104, y, "p<0.001", va="center", fontsize=5.4, color=c)
axB.axvline(0, color=BLACK, lw=0.6)
axB.set_yticks(ys)
axB.set_yticklabels(ylabels, fontsize=6.5)
for tick, r in zip(axB.get_yticklabels(), rows):
    tick.set_color(MC.get(r["模型"], "#333333"))
axB.set_xlim(-6, 114); axB.set_xticks([0, 25, 50, 75, 100])
axB.set_ylim(-0.8, len(rows) - 0.3)
axA.set_ylim(-0.8, len(rows) - 0.3)
axB.set_xlabel("Acc@10% (%); diamonds = paired difference (pp) with 95% CI", fontsize=7.0)
axB.set_title("(b)  prospective external set: dumbbells + gain forest", fontsize=7.5, loc="left")
axB.grid(axis="x", lw=0.4, color="#DDDDDD"); axB.set_axisbelow(True)

# (b) 图例：左上角，带黑框
hB = [Line2D([0], [0], marker="o", color="#888", mfc="#CCC", mec="#888", ms=4.2, lw=0,
             label="Base (light)"),
      Line2D([0], [0], marker="o", color="#888", mfc="#888", mec="#888", ms=4.2, lw=0,
             label="SFT (solid)"),
      Line2D([0], [0], marker="D", color="#888", mfc="#888", ms=3.5, lw=0,
             label="paired diff.")]
legB = axB.legend(handles=hB, loc="upper center", bbox_to_anchor=(0.5, -0.18),
                  ncol=3, fontsize=5.6, frameon=False)

save(fig, "图11_SFT配对", __file__)
