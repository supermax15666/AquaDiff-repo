# -*- coding: utf-8 -*-
"""Fig. 12 两面板版（v3，2026-09-19 修订）。
(a) 模型选择：单轴分组横条——4 体系 × 6 候选算法的宏谱系 MdAPE（谱系分组 5 折 CV），
    算法配色与旧版一致；金星 = 入选注册模型；灰 = Dummy 基线（KCl Dummy 45.54 截断标值）。
    v3：数值直接取权威冻结 CSV 全精度（不再经 fig11_panel.csv 的 4 位中间舍入，
    消除 CaCl₂ Dummy 7.874969→7.875→7.88 的双重舍入，标签与 Tab. S12 一致为 7.87）。
(b) 外部测试三组对比：全题/域内/域外三个题集；Base/SFT 五模型 min–max 须线，冻结 ML 确定性。
    v3：域内改为四体系宏平均（macro，与正文 Sect. 3.10 及 Fig. 13 的 16.8/94.0 一致，
    数据源 external_unified_caliber.csv 的 macro_ind 列）；域外保留题均口径（micro）
    并在图例/轴标签显式标注——域外无 NaCl 题，四体系宏平均不适用（原 21.1/93.3 为 micro，
    与 macro 轴标签冲突，即 DSH 复核问题）。
    v3.1（2026-09-20）：全题口径亦改用 external_unified_caliber.csv 的未舍入 macro_full
    （Base 16.0 / SFT 79.5，最后一步舍入；此前沿用表6 舍入值再平均得 15.9，与正文统一为 16.0）。
砍掉：旧 (a) 流程图（协议见 §2.2 与图注）、旧 (c) 专用 vs pooled（正文改引 Tab. S13）。
Data: data/图11_D臂_冻结汇总_权威数字.csv（面板 a，全精度）；
      data/external_unified_caliber.csv（面板 b 全题/域内 macro，未舍入）；
      data/外部集三组对比.md §5（面板 b 域外 micro，题均）。
Output: 图12_数值后端.pdf / .png / .tif
"""
import os, sys, csv
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")

# ---------- data: 面板 (a) 权威冻结 CSV（全精度） ----------
# auth[(system, model_display)] = (macro_lineage_mdape_percent, selected)
auth = {}
with open(os.path.join(DATA, "图11_D臂_冻结汇总_权威数字.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        if r["role"] == "specialized":
            auth[(r["system"], r["model_display"])] = (
                float(r["macro_lineage_mdape_percent"]), r["selected"].strip() == "是")

SYS_KEYS = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]
ALGOS = ["Polynomial Ridge", "RBF-SVR", "Random Forest", "Gradient Boosting",
         "Gaussian Process Regression", "Mean/Median Dummy"]
ALGO_SHORT = ["Poly Ridge", "RBF-SVR", "Rand. Forest", "Grad. Boost",
              "Gauss. Proc.", "Dummy"]
ALGO_COLORS = ["#4C72B0", "#DD8452", "#55A868", "#C44E52", "#8172B3", "#9A9A9A"]

# panel (b) data：全题与域内 macro 均取统一口径表 external_unified_caliber.csv 的
# 未舍入逐模型值（macro_full / macro_ind），最后一步才舍入——Base 全题 15.9537→16.0、
# SFT 79.5185→79.5，与正文及 Fig. 13 一致（此前全题用表6 的 1 位小数模型值再平均，
# 15.94→15.9，属"先舍入后平均"，已按统一舍入规则改为 16.0，2026-09-20）。
# 域外为题均 micro（外部集三组对比文档 §5；域外无 NaCl 题，四体系宏平均不适用，
# 图例显式标注 micro）。
macro_full = {"Base": [], "SFT": []}
macro_ind = {"Base": [], "SFT": []}
with open(os.path.join(DATA, "external_unified_caliber.csv"), encoding="utf-8-sig") as f:
    for r in csv.DictReader(f):
        macro_full[r["group"]].append(float(r["macro_full"]))
        macro_ind[r["group"]].append(float(r["macro_ind"]))
b_full = macro_full["Base"]; s_full = macro_full["SFT"]
b_ind = macro_ind["Base"]; s_ind = macro_ind["SFT"]

D = dict(
    base=dict(full=(np.mean(b_full), min(b_full), max(b_full)),
              indom=(np.mean(b_ind), min(b_ind), max(b_ind)), outdom=(7.5, 0.0, 25.0)),
    sft=dict(full=(np.mean(s_full), min(s_full), max(s_full)),
             indom=(np.mean(s_ind), min(s_ind), max(s_ind)), outdom=(30.0, 12.5, 43.8)),
    ml=dict(full=(71.9, None, None), indom=(97.9, None, None), outdom=(0.0, None, None)),
)
# 注：base 域外均值 7.5% 为 2026-09-01 由逐题数据+ML域标记复算（域外范围 0–25%
# 复现已发布值）；ML 域外 = 16/16 结构化拒绝，按口径计 0。
WHISK = "#8C8C8C"   # 误差棒浅色化；数值标签带白底，须线不再穿字
LBBOX = dict(boxstyle="square,pad=0.12", fc="white", ec="none")

fig = plt.figure(figsize=(DOUBLE, 4.1))
gs = fig.add_gridspec(1, 2, width_ratios=[1.18, 1.0],
                      left=0.135, right=0.99, top=0.90, bottom=0.09, wspace=0.20)

# ---------- (a): model selection, grouped horizontal bars ----------
axA = fig.add_subplot(gs[0])
XLIM = (0, 10.8)
CLIP = 10.0          # KCl Dummy 截断阈值
BAR_H = 0.72
GROUP_GAP = 0.9

bars = []            # (y, system, algo_idx, value, selected)
y = 0.0
group_centers = []
for sk in SYS_KEYS:
    top_y = y
    for i, algo in enumerate(ALGOS):
        v, sel = auth[(sk, algo)]   # 全精度，两位格式化后与 Tab. S12 一致
        bars.append((y, sk, i, v, sel))
        y -= 1.0
    group_centers.append((sk, (top_y + y + 1.0) / 2.0, top_y))
    y -= GROUP_GAP
ymin = y + 0.3

for y0, sk, i, v, sel in bars:
    c = ALGO_COLORS[i]
    if v > CLIP:  # 截断：KCl Dummy 45.54
        axA.barh(y0, CLIP, height=BAR_H, color=c, ec="none", zorder=2, alpha=0.85)
        for dx in (-0.10, 0.10):  # 截断符 //
            axA.plot([CLIP - 0.18 + dx, CLIP + 0.02 + dx],
                     [y0 - BAR_H * 0.42, y0 + BAR_H * 0.42],
                     color="white", lw=1.1, zorder=4)
        axA.text(CLIP - 0.35, y0, "%.2f" % v, va="center", ha="right",
                 fontsize=5.2, color="white", fontweight="bold", zorder=5)
    else:
        axA.barh(y0, v, height=BAR_H, color=c, ec="none", zorder=2, alpha=0.85)
        axA.text(v + 0.28, y0, "%.2f" % v, va="center", ha="left",
                 fontsize=5.0, color=c, zorder=4)
    if sel:
        axA.plot(v, y0, "*", color="#FFD700", ms=8.5, mec=BLACK, mew=0.5,
                 zorder=6)

# 体系组标签（加粗，置于每组上方空白处）
for sk, yc, ytop in group_centers:
    axA.text(0.12, ytop + 0.72, sys_display(sk), fontsize=6.6,
             fontweight="bold", color=sys_color(sk), ha="left", va="center")

axA.set_yticks([b[0] for b in bars])
axA.set_yticklabels([ALGO_SHORT[b[2]] for b in bars], fontsize=5.6)
axA.set_xlim(*XLIM)
axA.set_ylim(ymin, 1.6)
axA.set_xticks([0, 2, 4, 6, 8, 10])
axA.set_xlabel("macro-lineage MdAPE (%), 5-fold lineage-grouped CV", fontsize=7.0)
axA.set_title("(a)  model selection: six candidates per system", fontsize=7.5,
              loc="left")
axA.grid(axis="x", lw=0.4, color="#DDDDDD"); axA.set_axisbelow(True)

hA = [Line2D([0], [0], marker="*", color="#FFD700", mec=BLACK, mew=0.5, ms=8.5,
             lw=0, label="selected (registered)"),
      Patch(fc="#9A9A9A", ec="none", label="Dummy baseline")]
legA = axA.legend(handles=hA, loc="upper right", bbox_to_anchor=(0.99, 0.99),
                  fontsize=5.4, frameon=True, facecolor="white",
                  edgecolor="black", linewidth=0.5, fancybox=False)
legA.set_zorder(10)

# ---------- (b): three groups, three calibers（沿用旧 d） ----------
axB = fig.add_subplot(gs[1])
groups = [("Base\n(5 models)", "base"), ("SFT\n(5 models)", "sft"),
          ("Frozen ML\n(deterministic)", "ml")]
cals = [("Full set (64, macro)", "full", "#A6BDDB"),
        ("In-domain (48, macro)", "indom", OI_BLUE),
        ("Out-of-domain (16, micro)", "outdom", OI_VERM)]
for gi, (gname, gk) in enumerate(groups):
    for ci, (cname, ck, c) in enumerate(cals):
        x = gi + (ci - 1) * 0.26
        m, lo, hi = D[gk][ck]
        axB.bar(x, m, width=0.22, color=c, ec="none", zorder=2)
        if lo is not None:
            axB.plot([x, x], [lo, hi], color=WHISK, lw=0.9, zorder=3)
            axB.plot([x - 0.035, x + 0.035], [lo, lo], color=WHISK, lw=0.9, zorder=3)
            axB.plot([x - 0.035, x + 0.035], [hi, hi], color=WHISK, lw=0.9, zorder=3)
        axB.text(x, (m + 1.5) if m > 0 else 1.5, "%.1f" % m, ha="center",
                 fontsize=5.4, color="#333333", zorder=6, bbox=LBBOX)
axB.set_xticks(range(len(groups)))
axB.set_xticklabels([g[0] for g in groups], fontsize=6.2)
axB.set_xlim(-0.55, 2.62)
axB.set_ylim(0, 108)
axB.set_yticks([0, 20, 40, 60, 80, 100])
axB.set_ylabel("External-set Acc@10% (%)")
axB.set_title("(b)  three-group external comparison", fontsize=7.5, loc="left")
axB.grid(axis="y", lw=0.4, color="#DDDDDD"); axB.set_axisbelow(True)
hB = [Patch(fc="#A6BDDB", ec="none", label="Full set (64, macro)"),
      Patch(fc=OI_BLUE, ec="none", label="In-domain (48, macro)"),
      Patch(fc=OI_VERM, ec="none", label="Out-of-domain (16, micro)")]
axB.legend(handles=hB, loc="upper left", fontsize=5.4, frameon=True,
           facecolor="white", edgecolor="black", linewidth=0.5, fancybox=False)

save(fig, "图12_数值后端", __file__)
