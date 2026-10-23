# -*- coding: utf-8 -*-
"""CET 论文图件共享样式：Nature 版式参数 + 项目统一制图规范。

规范来源：paper_draft/06_图表清单.md §0（统一制图规范）：
- 色盲友好配色；体系颜色全文一致；全文固定模型颜色与顺序；
- 准确率轴统一百分数；扩散系数统一 10^-9 m^2/s；小数位统一（准确率 1 位百分数）；
- 不用 3D/饼图/截断坐标；矢量 PDF 输出（pdf.fonttype=42 嵌入 TrueType）。
用法：各图脚本将本目录加入 sys.path 后 `from common_style import *`。
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import rcParams

# ---- 字体：全英文图件用 Arial；YaHei 仅作兜底（若出现中文会触发缺字形告警=漏翻探测器）----
rcParams["font.family"] = "sans-serif"
rcParams["font.sans-serif"] = ["Arial", "Microsoft YaHei", "SimHei", "DejaVu Sans"]
rcParams["axes.unicode_minus"] = False

# ---- Nature 版式参数 ----
rcParams.update({
    "font.size": 7.0,
    "axes.labelsize": 7.5,
    "axes.titlesize": 8.0,
    "xtick.labelsize": 6.5,
    "ytick.labelsize": 6.5,
    "legend.fontsize": 6.0,
    "axes.linewidth": 0.6,
    "lines.linewidth": 0.9,
    "lines.markersize": 3.5,
    "xtick.major.width": 0.6, "ytick.major.width": 0.6,
    "xtick.major.size": 2.5, "ytick.major.size": 2.5,
    "xtick.direction": "out", "ytick.direction": "out",
    "axes.spines.top": True, "axes.spines.right": True,  # 数据图四边框（期刊惯例，用户要求）
    "legend.frameon": False,
    "figure.dpi": 150,
    "savefig.dpi": 350,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.03,
    "pdf.fonttype": 42,  # 期刊要求：嵌入 TrueType，文本可编辑
})

SINGLE = 3.5    # 单栏宽 89 mm
DOUBLE = 7.09   # 双栏宽 183 mm

# ---- 体系色（Okabe–Ito，全文一致）----
OI_BLUE, OI_ORANGE, OI_GREEN, OI_VERM = "#0072B2", "#E69F00", "#009E73", "#D55E00"
OI_SKY, OI_PURPLE, OI_YELLOW, OI_GREY = "#56B4E9", "#CC79A7", "#F0E442", "#999999"
SYS_COLOR = {"NaCl–H₂O": OI_BLUE, "KCl–H₂O": OI_ORANGE,
             "LiCl–H₂O": OI_GREEN, "CaCl₂–H₂O": OI_VERM}
SYS_ORDER = ["NaCl–H₂O", "KCl–H₂O", "LiCl–H₂O", "CaCl₂–H₂O"]
GREY = "#7F7F7F"; BLACK = "#000000"; LIGHT = "#F2F2F2"

# ---- 模型固定顺序与颜色（全文一致；顺序=图 5 排序）----
MODELS_B = ["kimi-k3", "doubao-seed-2-1-pro-260628", "deepseek-v4-pro",
            "glm-5.2", "qwen3.8-max", "MiniMax-M3"]
MODELS_A = ["Qwen3-4B-Instruct-2507", "Qwen3-8B", "Qwen3.6-27B",
            "Llama-3.1-8B-Instruct", "Gemma-2-9B-it"]
MODEL_COLOR = {
    "kimi-k3": "#0072B2", "doubao-seed-2-1-pro-260628": "#56B4E9",
    "deepseek-v4-pro": "#009E73", "glm-5.2": "#CC79A7",
    "qwen3.8-max": "#E69F00", "MiniMax-M3": "#888888",
    "Qwen3-4B-Instruct-2507": "#D55E00", "Qwen3-8B": "#E18727",
    "Qwen3.6-27B": "#8C564B", "Llama-3.1-8B-Instruct": "#7B68AE",
    "Gemma-2-9B-it": "#3C8DAA",
}


def model_color(key):
    """按模型键（CSV 原始键或显示名）取固定颜色。"""
    k = str(key)
    if k in MODEL_COLOR:
        return MODEL_COLOR[k]
    for disp, pat in zip(MODELS_A, ["qwen3_4b", "qwen3_8b", "qwen3_6_27b", "llama3", "gemma2"]):
        if pat in k:
            return MODEL_COLOR[disp]
    return GREY


def model_display(key):
    """CSV 模型键 → 显示名。"""
    k = str(key)
    _map = {
        "qwen3_4b_instruct_2507_base_q4km": "Qwen3-4B-Instruct-2507",
        "qwen3_8b_base_q4km": "Qwen3-8B",
        "qwen3_6_27b_base_q4km": "Qwen3.6-27B",
        "llama3_1_8b_base_q4km": "Llama-3.1-8B-Instruct",
        "gemma2_9b_base_q4km": "Gemma-2-9B-it",
    }
    for disp, pat in zip(MODELS_A, ["qwen3_4b", "qwen3_8b", "qwen3_6_27b", "llama3", "gemma2"]):
        if pat in k:
            return disp
    return _map.get(k, k)


# ---- 体系名/体系色：匹配 CSV 原始键（NaCl-H2O、CaCl2-H2O 等） ----
# 注意：下标用 mathtext（$_2$）——YaHei 缺 ₂/⁻/⁹ 字形且回退不生效，全部图件禁用这些字符
_SYS_NAME = [("cacl", "CaCl$_2$–H$_2$O"), ("nacl", "NaCl–H$_2$O"),
             ("kcl", "KCl–H$_2$O"), ("licl", "LiCl–H$_2$O")]


def sys_display(key):
    k = str(key).lower()
    for pat, name in _SYS_NAME:
        if pat in k:
            return name
    return str(key)


def sys_color(key):
    k = str(key).lower()
    if "cacl" in k: return OI_VERM
    if "kcl" in k: return OI_ORANGE
    if "licl" in k: return OI_GREEN
    if "nacl" in k: return OI_BLUE
    return GREY


# ---- 数据目录 ----
FIGDATA = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "CET_all", "02_绘图数据_按图号"))
TABLEDATA = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "CET_all", "01_论文主表数字"))


def panel_label(ax, s, x=-0.14, y=1.06):
    """面板角标。CET 体例：单字母自动转 (a)/(b)/(c) 小写括号式。"""
    txt = "(" + s.lower() + ")" if len(s) == 1 and s.isalpha() else s
    ax.text(x, y, txt, transform=ax.transAxes, fontsize=9.5,
            fontweight="bold", va="bottom", ha="left")


def _iter_texts(fig):
    """产出 (text, 所属 axes)。fig 级文字的所属为 None。
    跳过空文字与不可见文字；twinx 隐藏侧刻度不产出。"""
    for ax in fig.axes:
        ok_axis = getattr(ax, "axison", True)
        for t in ax.texts:
            if t.get_visible() and t.get_text().strip():
                yield t, ax  # 示意图（axis off）的文字仍归属该轴：箭头穿字检查需要
        if ok_axis:
            for t in ax.get_xticklabels():
                if t.get_text().strip() and t.get_visible() and ax.xaxis.get_visible():
                    yield t, ax
            for t in ax.get_yticklabels():
                if t.get_text().strip() and t.get_visible() and ax.yaxis.get_visible():
                    yield t, ax
            if ax.xaxis.label.get_text().strip() and ax.xaxis.label.get_visible():
                yield ax.xaxis.label, ax
            if ax.yaxis.label.get_text().strip() and ax.yaxis.label.get_visible():
                yield ax.yaxis.label, ax
            if ax.get_title().strip() and ax.title.get_visible():
                yield ax.title, ax
            leg = ax.get_legend()
            if leg is not None:
                for t in leg.get_texts():
                    if t.get_visible() and t.get_text().strip():
                        yield t, ax
    for t in fig.texts:
        if t.get_text().strip() and t.get_visible():
            yield t, None


def check_layout(fig):
    """程序化版式自检（替代本环境不可用的目测验收）：
    1) 文字两两重叠（>较小者面积 10%，跨轴也查——示意图同轴文字大多在 axis-off 轴上）；
    2) 方框（FancyBboxPatch）内文字溢出；3) 箭头穿字（同轴，端点 12% 按 shrink 跳过，
    注释箭头跳过自身文字）；4) 标记点/散点盖字（同轴）。
    返回问题列表。"""
    fig.canvas.draw()
    r = fig.canvas.get_renderer()
    issues = []
    boxes = []            # (text, bbox, owner_ax)
    for t, owner in _iter_texts(fig):
        try:
            bb = t.get_window_extent(renderer=r)
            if bb.width > 0 and bb.height > 0:
                boxes.append((t, bb, owner))
        except Exception:
            pass

    # 1) 文字两两重叠
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            ti, bi, _ = boxes[i]
            tj, bj, _ = boxes[j]
            ix = min(bi.x1, bj.x1) - max(bi.x0, bj.x0)
            iy = min(bi.y1, bj.y1) - max(bi.y0, bj.y0)
            if ix > 0 and iy > 0:
                small = min(bi.width * bi.height, bj.width * bj.height)
                if small > 0 and (ix * iy) / small > 0.10:
                    issues.append("[重叠] %r × %r 重叠 %.0f%%" % (
                        ti.get_text()[:12], tj.get_text()[:12], (ix * iy) / small * 100))

    # 2) 方框内文字溢出
    from matplotlib.patches import FancyBboxPatch, FancyArrowPatch
    for ax in fig.axes:
        for p in ax.patches:
            if not isinstance(p, FancyBboxPatch):
                continue
            try:
                pb = p.get_window_extent(renderer=r)
            except Exception:
                continue
            for t, bb, _ in boxes:
                if len(t.get_text().strip()) <= 2 and t.get_text().strip().isalpha():
                    continue  # 面板角标（a/b/c…）允许贴框角放置
                cx, cy = (bb.x0 + bb.x1) / 2, (bb.y0 + bb.y1) / 2
                if pb.x0 <= cx <= pb.x1 and pb.y0 <= cy <= pb.y1:
                    if bb.x0 < pb.x0 - 1 or bb.x1 > pb.x1 + 1 or bb.y0 < pb.y0 - 1 or bb.y1 > pb.y1 + 1:
                        issues.append("[溢出] 文字 %r 超出所在方框" % t.get_text()[:18])

    # 3) 箭头穿字（同轴；注释箭头跳过自身文字）
    def _arrow_ends(p):
        pp = getattr(p, "arrow_patch", None) or p
        pos = getattr(pp, "_posA_posB", None)
        if pos is not None:
            return pp.get_transform(), pos[0], pos[1]
        return None

    for ax in fig.axes:
        ax_texts = [(t, bb) for t, bb, owner in boxes if owner is ax]
        for p in list(getattr(ax, "patches", [])) + list(getattr(ax, "texts", [])):
            if not (isinstance(p, FancyArrowPatch) or getattr(p, "arrow_patch", None) is not None):
                continue
            try:
                ends = _arrow_ends(p)
                if ends is None:
                    continue
                trans, pa, pb2 = ends
                for tt in range(21):
                    f = tt / 20.0
                    if f < 0.12 or f > 0.88:
                        continue  # 端点附近按 shrink 处理
                    qx = pa[0] + (pb2[0] - pa[0]) * f
                    qy = pa[1] + (pb2[1] - pa[1]) * f
                    px, py = trans.transform((qx, qy))
                    for t, bb in ax_texts:
                        if t is p:
                            continue  # 注释箭头与自身文字相连，属正常
                        if bb.x0 - 1 <= px <= bb.x1 + 1 and bb.y0 - 1 <= py <= bb.y1 + 1:
                            issues.append("[箭头穿字] 箭头经过文字 %r" % t.get_text()[:18])
                            break
                    else:
                        continue
                    break
            except Exception:
                pass

    # 4) 标记点/散点盖字（同轴）
    from matplotlib.collections import PathCollection
    for ax in fig.axes:
        ax_texts = [(t, bb) for t, bb, owner in boxes if owner is ax]
        if not ax_texts:
            continue
        point_sets = []
        for coll in ax.collections:
            if isinstance(coll, PathCollection):
                try:
                    point_sets.append(ax.transData.transform(coll.get_offsets()))
                except Exception:
                    pass
        for ln in ax.lines:
            try:
                mk = ln.get_marker()
                if mk is None or mk in ("None", ""):
                    continue
                point_sets.append(ax.transData.transform(ln.get_xydata()))
            except Exception:
                continue
        for t, bb in ax_texts:
            for pts in point_sets:
                hit = False
                for px, py in pts:
                    if bb.x0 - 0.5 <= px <= bb.x1 + 0.5 and bb.y0 - 0.5 <= py <= bb.y1 + 0.5:
                        issues.append("[点盖字] 标记点覆盖文字 %r" % t.get_text()[:18])
                        hit = True
                        break
                if hit:
                    break

    # 5) 标签侵入相邻面板绘图区（如右面板的 y 刻度标签伸进左面板压住数据）
    ax_rects = []
    for ax in fig.axes:
        if getattr(ax, "axison", True):
            try:
                ax_rects.append((ax, ax.get_window_extent(renderer=r)))
            except Exception:
                pass
    owner_rects = {ax: ab for ax, ab in ax_rects}
    for t, bb, owner in boxes:
        if owner is None:
            continue
        ob = owner_rects.get(owner)
        for ax2, ab in ax_rects:
            if ax2 is owner:
                continue
            if ob is not None:
                # 孪生轴（twinx/twiny）与本轴同单元格，不构成"相邻面板"
                ix = min(ob.x1, ab.x1) - max(ob.x0, ab.x0)
                iy = min(ob.y1, ab.y1) - max(ob.y0, ab.y0)
                if ix > 0 and iy > 0 and (ix * iy) / (ob.width * ob.height) > 0.85:
                    continue
            ix = min(bb.x1, ab.x1) - max(bb.x0, ab.x0)
            iy = min(bb.y1, ab.y1) - max(bb.y0, ab.y0)
            if ix > 0 and iy > 0 and (ix * iy) / (bb.width * bb.height) > 0.15:
                issues.append("[侵入面板] 文字 %r 侵入相邻面板 %r 的绘图区" % (
                    t.get_text()[:18], ax2.get_title()[:12] or "panel"))
    return issues


def save(fig, name, script_path):
    """保存 PDF（矢量）+ PNG（350 dpi）到脚本所在目录，并运行程序化版式自检。"""
    import warnings as _w
    d = os.path.dirname(os.path.abspath(script_path))
    issues = check_layout(fig)
    with _w.catch_warnings(record=True) as wlist:
        _w.simplefilter("always")
        fig.savefig(os.path.join(d, name + ".pdf"))
        fig.savefig(os.path.join(d, name + ".png"))
        # CET 投稿格式：TIF ≥300 dpi（PNG 不被接受）——600 dpi LZW 压缩
        try:
            fig.savefig(os.path.join(d, name + ".tif"), dpi=600,
                        pil_kwargs={"compression": "tiff_lzw"})
        except Exception as e:
            print("  [TIFF 导出失败] %s" % e)
        glyph = [str(x.message) for x in wlist if "missing from font" in str(x.message)]
    print("saved:", os.path.join(d, name + ".pdf / .png / .tif"))
    if glyph:
        print("  [缺字形] %d 条：" % len(glyph))
        for g in sorted(set(glyph))[:5]:
            print("   ", g)
    if issues:
        print("  [版式自检] %d 个问题：" % len(issues))
        for s in issues:
            print("   ", s)
    else:
        print("  [版式自检] 通过（无越界/重叠/溢出）")
