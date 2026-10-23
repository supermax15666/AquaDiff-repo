# -*- coding: utf-8 -*-
"""补充图 S1 重复稳定性（每题三次重复的预测极差，按模型分组箱线图，A/B 两臂）。
数据源：CET_all/02_绘图数据_按图号/figS1_stability_A.csv / figS1_stability_B.csv
输出：图S1_重复稳定性.pdf / .png
"""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa

# 包内重跑支持：图件目录下存在 data/ 副本时优先使用，否则沿用 common_style 的 CET_all 路径
_LOCAL_DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
if os.path.isdir(_LOCAL_DATA):
    FIGDATA = _LOCAL_DATA
import matplotlib.pyplot as plt
import numpy as np

def load(fn):
    d = {}
    with open(os.path.join(FIGDATA, fn), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["predicted_range"].strip():
                d.setdefault(r["model"], []).append(float(r["predicted_range"]))
    return d

ORDER_B = ["kimi-k3", "doubao-seed", "deepseek", "glm", "qwen3.8", "MiniMax"]
ORDER_A = ["qwen3_4b", "qwen3_8b", "qwen3_6_27b", "llama3", "gemma2"]

fig, axes = plt.subplots(1, 2, figsize=(DOUBLE, 2.7),
                         gridspec_kw=dict(left=0.220, right=0.990, top=0.86, bottom=0.245,
                                          wspace=0.75))
for ax, (fn, order, title, tag) in zip(axes, [
        ("figS1_stability_A.csv", ORDER_A, "Arm A: local five models", "A"),
        ("figS1_stability_B.csv", ORDER_B, "Arm B: API six models", "B")]):
    d = load(fn)
    models = sorted(d, key=lambda m: next(i for i, k in enumerate(order) if k in m))
    data = [d[m] for m in models]
    bp = ax.boxplot(data, vert=False, widths=0.55, patch_artist=True, showfliers=False,
                    medianprops=dict(color=BLACK, lw=0.8),
                    boxprops=dict(lw=0.6), whiskerprops=dict(lw=0.6), capprops=dict(lw=0.6))
    for patch, m in zip(bp["boxes"], models):
        patch.set_facecolor(model_color(m)); patch.set_alpha(0.55)
    ax.set_yticklabels([model_display(m) for m in models], fontsize=6.0)
    ax.invert_yaxis()
    ax.set_xlabel("Prediction range over 3 repeats (10$^{-9}$ m²/s)")
    ax.set_title(title, fontsize=7.0, loc="left")
    panel_label(ax, tag, x=-0.30, y=1.12)
fig.text(0.5, 0.012, "max − min of the 3 repeats per question (all systems pooled; box = quartiles, line = median; outliers not shown but kept in the statistics). The range measures random stability and does not add independent samples",
         fontsize=5.2, color="#555555", ha="center", va="bottom")
save(fig, "图S1_重复稳定性", __file__)
