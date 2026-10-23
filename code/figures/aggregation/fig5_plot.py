# -*- coding: utf-8 -*-
"""Fig. 6 Model accuracy with confidence intervals (core figure, two panels).
(a) Six API models; (b) five local models. Main set: filled circles + CIs;
    240-question sensitivity subset: open diamonds with separate CIs (offset to
    avoid occlusion). Boxed legend at bottom center.
Output: 图6_准确率点CI图.pdf / .png
"""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D


def load(fn):
    d = {}
    with open(os.path.join(FIGDATA, fn), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            d.setdefault(r["model"], {})[r["view"]] = (
                float(r["acc10_macro_percent"]), float(r["ci_low_percent"]), float(r["ci_high_percent"]))
    return d


def draw(ax, data, title):
    models = sorted(data, key=lambda m: -data[m]["primary"][0])
    ys = np.arange(len(models))[::-1]
    for y, m in zip(ys, models):
        c = model_color(m)
        # 主集：实心圆 + CI 线（粗）
        acc, lo, hi = data[m]["primary"]
        ax.plot([lo, hi], [y, y], color=c, lw=1.4, solid_capstyle="butt", zorder=2)
        for xx in (lo, hi):
            ax.plot([xx, xx], [y - 0.12, y + 0.12], color=c, lw=1.4, zorder=2)
        ax.plot(acc, y, "o", color=c, ms=5.0, zorder=4)
        # 240 题子集：空心菱形 + 虚线 CI（偏移避免遮挡）
        if "sensitivity" in data[m]:
            a2, l2, h2 = data[m]["sensitivity"]
            dy = 0.24
            ax.plot([l2, h2], [y + dy, y + dy], color=c, lw=0.9, ls=":", alpha=0.7, zorder=1)
            ax.plot(a2, y + dy, "D", mfc="white", mec=c, mew=1.0, ms=4.0, zorder=3)
    ax.set_yticks(ys)
    ax.set_yticklabels([model_display(m) for m in models])
    ax.set_xlim(0, 80)
    ax.set_xticks([0, 20, 40, 60, 80])
    ax.set_xlabel("macro-system Acc@10% (%)")
    ax.set_title(title, fontsize=7.5, loc="left")
    ax.grid(axis="x", lw=0.4, color="#DDDDDD", zorder=0)
    ax.set_axisbelow(True)
    ax.set_ylim(-0.6, len(models) - 0.2)


fig, (axA, axB) = plt.subplots(1, 2, figsize=(DOUBLE, 3.0),
                               gridspec_kw=dict(left=0.190, right=0.990, top=0.88, bottom=0.20,
                                                wspace=0.62))
draw(axA, load("图5a_闭卷CI_B臂.csv"), "Arm B: API LLMs (n=6)")
draw(axB, load("图5b_闭卷CI_A臂.csv"), "Arm A: local base models (n=5)")
panel_label(axA, "a", x=-0.24, y=1.10)
panel_label(axB, "b", x=-0.30, y=1.10)

# 图例：两面板底部中间，带黑框
h = [Line2D([0], [0], marker="o", color=BLACK, mfc=BLACK, mec=BLACK, ms=4.5, lw=0,
            label="642-question main set (filled circle) + 95% CI"),
     Line2D([0], [0], marker="D", color=BLACK, mfc="white", mec=BLACK, mew=1.0, ms=4.0, lw=0,
            label="240-question sensitivity subset (open diamond, offset)")]
fig.legend(handles=h, loc="lower center", bbox_to_anchor=(0.5, 0.005), ncol=2,
           fontsize=5.8, frameon=True, edgecolor="black", linewidth=0.5,
           fancybox=False, borderaxespad=0.4)
save(fig, "图5_准确率点CI图", __file__)
