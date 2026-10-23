# -*- coding: utf-8 -*-
"""Supplementary Fig. S3: lineage x system composition matrix (record counts).
Source: recomputed from 02_数据/01_四体系源工作簿 Confirmed_Records (45 lineages).
Moved out of the main Fig. 2 (panel C) in v6 for information density and readability.
Output: 图S3_谱系构成矩阵.pdf / .png
"""
import os, sys, re
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from common_style import *  # noqa
import matplotlib.pyplot as plt
import openpyxl
import numpy as np

WB = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "past_document", "整理归档_20261002_130246", "03_data", "01_原始数据", "CET_02_数据", "01_四体系源工作簿"))
SYS_KEYS = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]

counts = {}
for fn in os.listdir(WB):
    if not fn.endswith(".xlsx"):
        continue
    wb = openpyxl.load_workbook(os.path.join(WB, fn), read_only=True, data_only=True)
    ws = wb["Confirmed_Records"]
    rows = list(ws.iter_rows(values_only=True))
    hdr = [str(h) for h in rows[0]]
    ci_g = hdr.index("model_group_id"); ci_s = hdr.index("system")
    for r in rows[1:]:
        if r is None or r[ci_g] is None:
            continue
        key = (str(r[ci_g]).strip(), str(r[ci_s]).strip())
        counts[key] = counts.get(key, 0) + 1
    wb.close()

SHORT = {
    "FELL_HUTCHISON_1971": "Fell&Hut·71", "GOSTING_KCL_1950": "Gosting·50",
    "HARNED_1955_OSTI": "Harned·55", "HARNED_NUTTALL_KCL_1947": "H&N·47",
    "RARD_NACL_CACL2_1979": "Rard&M·79", "RARD_MILLER_1979": "Rard&M·79",
    "RARD_BACL2_KCL_1980": "Rard&M·80", "VITAGLIANO_LYONS_1956": "V&L·56",
}

def short_name(lid):
    if "LOBO" in lid:
        m = re.search(r"REF_(\d+)", lid)
        return "LOBO·" + (m.group(1) if m else "?")
    for k, v in SHORT.items():
        if k in lid:
            return v
    return lid.split(":")[-1][:14]

lineage_sys = {}
for (lid, s), n in counts.items():
    lineage_sys.setdefault(lid, {})[s] = n
ordered = []
for sk in SYS_KEYS:
    lls = [(lid, sum(d.values())) for lid, d in lineage_sys.items() if sk in d]
    lls.sort(key=lambda x: -x[1])
    ordered += [lid for lid, _ in lls]
assert len(ordered) == 45

mat = np.zeros((45, 4))
for i, lid in enumerate(ordered):
    for j, sk in enumerate(SYS_KEYS):
        mat[i, j] = lineage_sys[lid].get(sk, 0)

fig, ax = plt.subplots(figsize=(SINGLE, 5.3), gridspec_kw=dict(
    left=0.175, right=0.985, top=0.93, bottom=0.085))
im = ax.imshow(mat, cmap="Blues", aspect="auto", vmin=0)
ax.set_xticks(range(4)); ax.set_xticklabels([sys_display(k) for k in SYS_KEYS], fontsize=6.8)
ax.set_yticks(range(45))
labels = [short_name(lid) for lid in ordered]
ax.set_yticklabels(labels, fontsize=6.0)
for tick, lid in zip(ax.get_yticklabels(), ordered):
    if "REF_087" in lid:
        tick.set_fontweight("bold"); tick.set_color(OI_VERM)
for i in range(45):
    for j in range(4):
        v = int(mat[i, j])
        if v:
            ax.text(j, i, str(v), ha="center", va="center", fontsize=5.4,
                    color="white" if v > 60 else "#333333")
ax.set_xlabel("System (columns)", fontsize=7)
ax.set_ylabel("Source lineage (rows)", fontsize=7)
for s in ax.spines.values():
    s.set_visible(True); s.set_linewidth(0.4)
ax.tick_params(length=1.5, width=0.4)
cb = fig.colorbar(im, ax=ax, fraction=0.05, pad=0.03)
for sp in cb.ax.spines.values():
    sp.set_visible(False)
cb.set_label("Records", fontsize=6.5)
cb.ax.tick_params(labelsize=6)
ax.text(0.985, 1.035, "cells = raw record counts (Confirmed_Records); rows grouped by system, descending count;\nLOBO·nnn = transcribed from Lobo 1993; LOBO·087 (bold, vermillion) = Vitagliano 1960:\n109 records = 108 conditions = 82% of LiCl's 132 main-set questions",
        transform=ax.transAxes, fontsize=5.4, ha="right", va="bottom", color="#555555")

save(fig, "图S3_谱系构成矩阵", __file__)
