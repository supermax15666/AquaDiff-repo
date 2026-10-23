# -*- coding: utf-8 -*-
"""图 9 误差分布（B 臂六模型）。
A：APE 的 ECDF（5%/10% 参考线；主图 0–100%，超范围计入统计）——fig8A_ecdf_B.csv（题目级 APE 中位）
B：有符号误差小提琴（按体系分面，零线）——fig8B_signed_error_B.csv
输出：图9_误差分布.pdf / .png
"""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
FIGDATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
import matplotlib.pyplot as plt
import numpy as np

ORDER = ["kimi-k3", "doubao-seed", "deepseek", "glm", "qwen3.8", "MiniMax"]
MODELS = None

ape = {}
with open(os.path.join(FIGDATA, "fig8A_ecdf_B.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        ape.setdefault(r["model"], []).append(float(r["ape_median_percent"]))
models = sorted(ape, key=lambda m: next(i for i, k in enumerate(ORDER) if k in m))
MODELS = models

err = {}
with open(os.path.join(FIGDATA, "fig8B_signed_error_B.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["signed_error"].strip():
            err.setdefault((r["model"], r["system"]), []).append(float(r["signed_error"]))

fig = plt.figure(figsize=(DOUBLE, 2.9))
gs = fig.add_gridspec(1, 2, width_ratios=[1.0, 1.55], wspace=0.26,
                      left=0.065, right=0.99, top=0.86, bottom=0.26)

# ---------- A：ECDF ----------
axA = fig.add_subplot(gs[0, 0])
for m in models:
    v = np.sort(np.array(ape[m], dtype=float))
    # 主图显示 0–100%：超出者按 100 计入累计（统计保留原值）
    v_show = np.clip(v, 0, 100)
    y = np.arange(1, len(v) + 1) / len(v)
    axA.step(np.concatenate([[0], v_show]), np.concatenate([[0], y]),
             where="post", color=model_color(m), lw=1.0, label=model_display(m))
axA.axvline(5, color=GREY, lw=0.6, ls=":")
axA.axvline(10, color=GREY, lw=0.6, ls="--")
axA.text(4.7, 0.97, "5%", ha="right", va="top", fontsize=5.4, color="#555555")
axA.text(10.6, 0.895, "10%", ha="left", va="top", fontsize=5.4, color="#555555")
axA.set_xlim(-4, 100); axA.set_ylim(0, 1.02)
axA.set_xticks([0, 25, 50, 75, 100])
axA.set_xlabel("APE (%, per-question median; values >100% clipped at 100)")
axA.set_ylabel("Cumulative proportion")
axA.legend(fontsize=5.2, loc="lower right", handlelength=1.2, labelspacing=0.25,
           frameon=False)
panel_label(axA, "A", x=-0.19, y=1.16)

# ---------- B：有符号误差小提琴（4 体系分面 × 6 模型） ----------
SYS_KEYS = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]
gsB = gs[0, 1].subgridspec(1, 4, wspace=0.06)
allv = [v for k, v in err.items() for v in v]
ylo = float(np.quantile(allv, 0.002)); yhi = float(np.quantile(allv, 0.998))
pad = (yhi - ylo) * 0.06
for j, sk in enumerate(SYS_KEYS):
    ax = fig.add_subplot(gsB[0, j])
    for i, m in enumerate(models):
        v = err.get((m, sk), [])
        if len(v) >= 8:
            ax.violinplot([v], positions=[i], widths=0.75, showextrema=False,
                          showmedians=True)
            for pc in ax.collections[-2:]:
                pc.set_facecolor(model_color(m)); pc.set_alpha(0.75)
                pc.set_edgecolor(model_color(m))
            med = np.median(v)
            ax.plot(i, med, "o", color=model_color(m), ms=2.6, mec="white", mew=0.4, zorder=5)
    ax.axhline(0, color=BLACK, lw=0.6)
    ax.set_ylim(ylo - pad, yhi + pad)
    ax.set_xticks(range(len(models)))
    # 短名逐面标注（竖排）；全名对照移入图注（自包含图注）
    SHORT_API = {"kimi-k3": "kimi-k3", "doubao": "doubao", "deepseek": "deepseek",
                 "glm": "glm-5.2", "qwen3.8": "qwen3.8", "MiniMax": "MiniMax"}
    def api_short(m):
        d = model_display(m)
        for k, v in SHORT_API.items():
            if k in m:
                return v
        return d
    ax.set_xticklabels([api_short(m) for m in models],
                       rotation=90, fontsize=4.6)
    ax.set_xlim(-0.6, len(models) - 0.4)
    ax.set_title(sys_display(sk), fontsize=6.4)
    if j == 0:
        ax.set_ylabel("Signed error (pred − obs, 10$^{-9}$ m²/s)")
    else:
        ax.tick_params(labelleft=False)
    if j == 0:
        panel_label(ax, "B", x=-0.42, y=1.16)
save(fig, "图9_误差分布", __file__)
