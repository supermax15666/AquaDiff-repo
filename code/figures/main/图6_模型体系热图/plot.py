# -*- coding: utf-8 -*-
"""图 7 模型×体系 Accuracy@10% 热图（行序同图 5：B 臂 6 + A 臂 5）。
数据源：CET_all/02_绘图数据_按图号/fig6_heatmap_B.csv + fig6_heatmap_A.csv
规范：色阶固定 0–80%；单元格标一位小数；不做结果驱动的层次聚类。
输出：图6_模型体系热图.pdf / .png
"""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
FIGDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
import matplotlib.pyplot as plt
import numpy as np

SYS_KEYS = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]
# CSV 为长表（model, system, acc10_mean_percent）——先透视为 {model: {system: acc}}
piv = {}
for fn in ("fig6_heatmap_B.csv", "fig6_heatmap_A.csv"):
    with open(os.path.join(FIGDATA, fn), encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            piv.setdefault(r["model"], {})[r["system"]] = r["acc10_mean_percent"]

# 行序同图 5：B 臂按 macro 降序（kimi→MiniMax），A 臂同（27B→4B）
ORDER_B = ["kimi-k3", "doubao-seed-2-1-pro-260628", "deepseek-v4-pro", "glm-5.2", "qwen3.8-max", "MiniMax-M3"]
ORDER_A = ["qwen3_6_27b", "gemma2", "llama3", "qwen3_8b", "qwen3_4b"]


def find_model(key):
    for m in piv:
        if key in m:
            return piv[m]
    return None


def vals_of(d):
    if d is None:
        return [0.0] * 4
    return [(float(d[sk]) if d.get(sk, "").strip() else 0.0) for sk in SYS_KEYS]


mat, names, arm_tags = [], [], []
for key in ORDER_B:
    mat.append(vals_of(find_model(key)))
    names.append(model_display(key)); arm_tags.append("B")
for key in ORDER_A:
    mat.append(vals_of(find_model(key)))
    names.append(model_display(key)); arm_tags.append("A")

mat = np.array(mat)
fig, ax = plt.subplots(figsize=(SINGLE, 3.6), gridspec_kw=dict(
    left=0.30, right=0.90, top=0.90, bottom=0.10))
im = ax.imshow(mat, cmap="Blues", vmin=0, vmax=80, aspect="auto")
ax.set_xticks(range(4)); ax.set_xticklabels([sys_display(k) for k in SYS_KEYS], fontsize=6.2)
ax.set_yticks(range(len(names)))
labs = ax.set_yticklabels(names, fontsize=6.2)
for t, tag in zip(labs, arm_tags):
    t.set_color(OI_BLUE if tag == "B" else OI_VERM)
for i in range(len(names)):
    for j in range(4):
        v = mat[i, j]
        ax.text(j, i, "%.1f" % v, ha="center", va="center", fontsize=5.4,
                color="white" if v > 50 else "#333333")
for s in ax.spines.values():
    s.set_visible(True); s.set_linewidth(0.4)
ax.tick_params(length=1.5, width=0.4)
ax.set_xlabel("System")
ax.set_ylabel("Model (top: Arm B API; bottom: Arm A local)")
cb = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.03)
for sp in cb.ax.spines.values():
    sp.set_visible(False)  # colorbar 用自身 outline，不加四边框
cb.set_label("Acc@10% (%)", fontsize=6.2)
cb.ax.tick_params(labelsize=5.8)
cb.outline.set_linewidth(0.4)
save(fig, "图6_模型体系热图", __file__)
