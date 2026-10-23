# -*- coding: utf-8 -*-
"""构建 CET_all 论文查阅快照（2026-08-27，用户批准方案：只读快照、外部 gold 不入、
补齐表格数据、生成图9失败案例）。

用法：python py/build_cet_all.py
产出：CET_all/（00 先读我 + 01 主表数字 + 02 绘图数据 + 03 各臂分析 + 04 基准数据
+ 05 方法支撑 + 06 汇总文档 + 07 溯源索引）。权威源仍在主工作区；本快照不承担写入。
"""

import csv
import glob
import json
import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
R = os.path.join(ROOT, "CET_all")
RES = os.path.join(ROOT, "03_实验结果")

A_MERGE = os.path.join(RES, "A臂_本地Base直接回答_642题", "合并分析_formal_5models_20260816", "formal_5models_20260816")
B_MERGE = os.path.join(RES, "B臂_API六模型直接回答_642题", "合并分析_六模型_20260814T151400Z")
C_MET = os.path.join(RES, "C臂_SFT训练与642掌握度", "642掌握度_分析", "指标汇总CSV")
EXT_DIR = os.path.join(RES, "外部前瞻集评测_64题_10场", "对比分析")
D_DIR = os.path.join(RES, "D臂_ML数值后端_冻结")
E_DIR = os.path.join(RES, "E臂_受限Agent评测")
E_RUNS = {
    "642": os.path.join(E_DIR, "agent_642__20260827T110710453851Z"),
    "external": os.path.join(E_DIR, "agent_external__20260827T101046384799Z"),
    "challenge": os.path.join(E_DIR, "agent_challenge__20260827T121022629572Z"),
}

GEN_DATE = "2026-08-27"


def wcsv(path, header, rows):
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)


def load_metrics(csv_path, only_primary=True):
    out = {}
    for r in csv.DictReader(open(csv_path, encoding="utf-8-sig")):
        if only_primary and "primary" not in r.get("analysis_set_id", ""):
            continue
        out[r["model_key"]] = r
    return out


def f(x, nd=1):
    return f"{float(x) * 100:.{nd}f}" if x not in (None, "") else ""


def main():
    # 增量模式：目录被占用（如资源管理器打开）时不删除，直接覆写文件（幂等）
    try:
        if os.path.exists(R):
            shutil.rmtree(R)
    except PermissionError:
        print("（CET_all 被其他程序占用，改为增量覆写模式）")
    for d in ["01_论文主表数字", "02_绘图数据_按图号", "03_各臂完整分析/A臂_本地五模型",
              "03_各臂完整分析/B臂_API六模型", "03_各臂完整分析/C臂_SFT掌握度",
              "03_各臂完整分析/D臂_ML后端", "03_各臂完整分析/E臂_Agent",
              "03_各臂完整分析/外部集评测_三组对比", "04_基准与数据集/题库_642与240",
              "04_基准与数据集/外部前瞻集", "04_基准与数据集/四体系源工作簿",
              "04_基准与数据集/溶解度表", "05_方法与配置支撑", "06_关键汇总文档"]:
        os.makedirs(os.path.join(R, d), exist_ok=True)

    # ============ 01 主表数字 ============
    # 表1 数据集统计（唯一条件数已重算核实）
    wcsv(os.path.join(R, "01_论文主表数字", "表1_数据集统计.csv"),
         ["体系", "原始记录数", "来源谱系数", "唯一条件数", "主集题目数", "敏感性子集题目数"],
         [["NaCl-H2O", 256, 16, 200, 174, 60], ["KCl-H2O", 268, 16, 256, 247, 60],
          ["LiCl-H2O", 152, 6, 141, 132, 60], ["CaCl2-H2O", 109, 7, 99, 89, 60],
          ["合计", 785, 45, 696, 642, 240]])

    # 表3 A/B 臂主结果（补齐 Acc@5%/P95——原稿待填项）
    A = load_metrics(os.path.join(A_MERGE, "manuscript_model_metrics.csv"))
    B = load_metrics(os.path.join(B_MERGE, "manuscript_model_metrics.csv"))
    rows = []
    order_b = ["kimi-k3", "doubao-seed-2-1-pro-260628", "deepseek-v4-pro", "glm-5.2",
               "qwen3.8-max", "MiniMax-M3"]
    for k in order_b:
        r = B[k]
        rows.append(["B", k, f(r["valid_numeric_coverage"]), f(r["full_question_accuracy_10pct"]),
                     f(r["macro_system_accuracy_10pct"]), f(r["macro_system_accuracy_5pct"]),
                     f"{float(r['mae_valid_numeric_1e9_m2_s']):.3f}",
                     f"{float(r['mdape_valid_numeric_percent']):.2f}",
                     f"{float(r['p95_ape_valid_numeric_percent']):.1f}",
                     f"[{f(r['macro_system_accuracy_10pct_ci95_low'])},{f(r['macro_system_accuracy_10pct_ci95_high'])}]"])
    order_a = ["qwen3_4b_instruct_2507_base_q4km", "qwen3_8b_instruct_base_q4km",
               "qwen3_6_27b_base_q4km", "llama3_1_8b_instruct_base_q4km", "gemma2_9b_it_base_q4km"]
    aname = {"qwen3_4b_instruct_2507_base_q4km": "Qwen3-4B-Instruct-2507",
             "qwen3_8b_instruct_base_q4km": "Qwen3-8B", "qwen3_6_27b_base_q4km": "Qwen3.6-27B",
             "llama3_1_8b_instruct_base_q4km": "Llama-3.1-8B-Instruct",
             "gemma2_9b_it_base_q4km": "Gemma-2-9B-it"}
    for k in order_a:
        r = A[k]
        rows.append(["A", aname[k], f(r["valid_numeric_coverage"]), f(r["full_question_accuracy_10pct"]),
                     f(r["macro_system_accuracy_10pct"]), f(r["macro_system_accuracy_5pct"]),
                     f"{float(r['mae_valid_numeric_1e9_m2_s']):.3f}",
                     f"{float(r['mdape_valid_numeric_percent']):.2f}",
                     f"{float(r['p95_ape_valid_numeric_percent']):.1f}",
                     f"[{f(r['macro_system_accuracy_10pct_ci95_low'])},{f(r['macro_system_accuracy_10pct_ci95_high'])}]"])
    wcsv(os.path.join(R, "01_论文主表数字", "表3_AB臂主结果_完成版.csv"),
         ["臂", "模型", "覆盖率%", "micro Acc@10%", "macro Acc@10%", "macro Acc@5%",
          "MAE(1e-9)", "MdAPE%", "P95 APE%", "macro Acc@10% CI95"], rows)

    # 表4/表5 D 臂（从冻结汇总提取）
    src = list(csv.DictReader(open(os.path.join(D_DIR, "output", "冻结汇总.csv"), encoding="utf-8-sig")))
    disp = {"polynomial_ridge": "Polynomial Ridge", "rbf_svr": "RBF-SVR", "random_forest": "Random Forest",
            "gradient_boosting": "Gradient Boosting", "gaussian_process": "Gaussian Process",
            "dummy_median": "Dummy"}
    sys_disp = {"NaCl-H2O": "NaCl-H2O(174/10)", "KCl-H2O": "KCl-H2O(247/13)",
                "LiCl-H2O": "LiCl-H2O(132/5)", "CaCl2-H2O": "CaCl2-H2O(89/7)"}
    sel = {("NaCl-H2O", "gaussian_process"), ("KCl-H2O", "polynomial_ridge"),
           ("LiCl-H2O", "gradient_boosting"), ("CaCl2-H2O", "gradient_boosting")}
    t4, t5 = [], []
    for s in ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]:
        row4 = [sys_disp[s]]
        for m in ["polynomial_ridge", "rbf_svr", "random_forest", "gradient_boosting", "gaussian_process", "dummy_median"]:
            r = next(x for x in src if x["system"] == s and x["model_key"] == m and x["role"] == "specialized")
            v = f"{float(r['macro_lineage_mdape_percent']):.2f}" + (" ✓" if (s, m) in sel else "")
            row4.append(v)
            if (s, m) in sel:
                p = next(x for x in src if x["system"] == s and x["model_key"] == m and x["role"] == "pooled")
                t5.append([s, disp[m], f"{float(r['macro_lineage_mdape_percent']):.2f}",
                           f"{float(r['mae_1e9_m2_s']):.3f}", f"{float(r['accuracy_10pct'])*100:.1f}",
                           f"{float(p['macro_lineage_mdape_percent']):.2f}",
                           f"{float(r['macro_lineage_mdape_percent'])-float(p['macro_lineage_mdape_percent']):+.2f}"])
        t4.append(row4)
    wcsv(os.path.join(R, "01_论文主表数字", "表4_D臂候选模型CV.csv"),
         ["体系(条件/谱系)", "PolyRidge", "RBF-SVR", "RF", "GB", "GP", "Dummy"], t4)
    wcsv(os.path.join(R, "01_论文主表数字", "表5_D臂专用vs_pooled.csv"),
         ["体系", "入选模型", "宏谱系MdAPE%(专用)", "MAE", "CV Acc@10%", "pooled同族MdAPE%", "Δ(pp)"], t5)

    # 表6 C 臂 SFT 配对（642 掌握度从 CSV；外部集配对差 CI 取自已发布汇总 md）
    cname = {"qwen3_4b": ("Qwen3-4B", "qwen3_4b_instruct_2507_base_q4km", "qwen3_4b_instruct_2507_sft_q4km"),
             "qwen3_8b": ("Qwen3-8B", "qwen3_8b_instruct_base_q4km", "qwen3_8b_instruct_sft_q4km"),
             "qwen3_6_27b": ("Qwen3.6-27B", "qwen3_6_27b_base_q4km", "qwen3_6_27b_sft_q4km"),
             "llama3_1_8b": ("Llama-3.1-8B", "llama3_1_8b_instruct_base_q4km", "llama3_1_8b_instruct_sft_q4km"),
             "gemma2_9b": ("Gemma-2-9B", "gemma2_9b_it_base_q4km", "gemma2_9b_it_sft_q4km")}
    ext_pair = {"Qwen3-4B": (19.7, 81.0, "+64.6", "[+40.8,+85.8]"),
                "Qwen3-8B": (8.3, 83.5, "+71.9", "[+42.3,+100.0]"),
                "Qwen3.6-27B": (27.9, 81.0, "+45.3", "[+28.6,+64.3]"),
                "Llama-3.1-8B": (17.6, 75.1, "+43.8", "[+19.6,+79.6]"),
                "Gemma-2-9B": (6.2, 76.9, "+73.4", "[+51.2,+90.1]")}
    t6 = []
    for stem, (name, akey, ckey) in cname.items():
        c = load_metrics(os.path.join(C_MET, f"{stem}_sft_642_mastery_metrics.csv"))
        cr = c[ckey] if ckey in c else list(c.values())[0]
        ar = A[akey]
        t6.append([name,
                   f(ar["macro_system_accuracy_10pct"]),
                   f"[{f(ar['macro_system_accuracy_10pct_ci95_low'])},{f(ar['macro_system_accuracy_10pct_ci95_high'])}]",
                   f(cr["macro_system_accuracy_10pct"]),
                   f"[{f(cr['macro_system_accuracy_10pct_ci95_low'])},{f(cr['macro_system_accuracy_10pct_ci95_high'])}]",
                   f"{(float(cr['macro_system_accuracy_10pct'])-float(ar['macro_system_accuracy_10pct']))*100:+.1f}"] +
                   list(ext_pair[name]) + ["p<0.001"])
    wcsv(os.path.join(R, "01_论文主表数字", "表6_C臂SFT配对结果.csv"),
         ["模型", "Base 642 macro%", "Base CI95", "SFT 642 macro%", "SFT CI95", "642增益pp",
          "Base外部macro%", "SFT外部macro%", "外部配对差pp", "外部差CI95", "p"],
         t6)

    # 表7 外部集三组对比
    dml = json.load(open(os.path.join(D_DIR, "外部集64题预测_20260825", "metrics.json"), encoding="utf-8"))
    t7 = [["NaCl-H2O", "0.0–38.9", "100.0", "100.0", 0],
          ["KCl-H2O", "0.0–33.3", "60.0–80.0", "73.3", 3],
          ["LiCl-H2O", "0.0–70.4", "70.4–77.8", "74.1", 7],
          ["CaCl2-H2O", "0.0–40.0", "50.0–100.0", "40.0", 6]]
    wcsv(os.path.join(R, "01_论文主表数字", "表7_外部集三组对比.csv"),
         ["体系", "Base范围%(5模型)", "SFT范围%(5模型)", "ML专用%", "ML域外拒绝"],
         t7 + [["总体(micro/macro)", "6.2–27.9", "75.1–83.5",
                f"micro {dml['overall']['accuracy_10pct_micro']*100:.1f}/macro {dml['overall']['accuracy_10pct_macro_system']*100:.1f}",
                dml['overall']['n_refused_out_of_domain']]])

    # 表8 E 臂
    t8 = []
    names = {"642": "642主集(检索忠实度口径)", "external": "外部前瞻集64题", "challenge": "挑战集54题"}
    for k, p in E_RUNS.items():
        m = json.load(open(os.path.join(p, "metrics.json"), encoding="utf-8"))
        pr = (f"{m['refusal_precision']*100:.0f}/{m['refusal_recall']*100:.0f}"
              if m.get("refusal_precision") is not None and m.get("refusal_recall") is not None else "—")
        t8.append([names[k], m["n_samples"],
                   f"{m['route_accuracy']*100:.1f}", f"{m['faithfulness']*100:.1f}",
                   pr,
                   f"{m['acc10_any_repeat']*100:.1f}" if m["acc10_any_repeat"] is not None else "—"])
    wcsv(os.path.join(R, "01_论文主表数字", "表8_E臂Agent指标.csv"),
         ["测试集", "样本", "路由准确%", "载荷忠实%", "拒绝P/R%", "Acc@10%(题级)"], t8)

    # ============ 02 绘图数据 ============
    for sub in ["02_绘图数据", "03_最小绘图表"]:
        srcd = os.path.join(ROOT, "paper_draft", "data", sub)
        if os.path.isdir(srcd):
            for p in glob.glob(os.path.join(srcd, "*")):
                if os.path.isfile(p):
                    shutil.copy2(p, os.path.join(R, "02_绘图数据_按图号", os.path.basename(p)))
    # 图10 Base→SFT 配对（从表6数据）
    wcsv(os.path.join(R, "02_绘图数据_按图号", "图11_Base到SFT配对.csv"),
         ["模型", "Base_642_macro", "SFT_642_macro", "Base_外部_macro", "SFT_外部_macro", "外部配对差pp"],
         [[r[0], r[1], r[3], r[6], r[7], r[8]] for r in t6])
    # 图13 统一性能对比
    t13 = []
    for k in order_a:
        t13.append(["Base本地", aname[k], f(A[k]["macro_system_accuracy_10pct"]), "—"])
    for k in order_b:
        t13.append(["API", k, f(B[k]["macro_system_accuracy_10pct"]), "—"])
    for r in t6:
        t13.append(["SFT", r[0], r[3], r[7]])
    t13 += [["冻结ML", "专用模型(四体系)", "—", "71.9"],
            ["Agent", "Qwen3-4B+工具栈", "100(检索口径)", "71.9"]]
    wcsv(os.path.join(R, "02_绘图数据_按图号", "图13_统一性能对比.csv"),
         ["组", "条目", "642_macro%", "外部_macro%"], t13)
    # 图15B 成本延迟（实测）
    lat = []
    for k in order_a:
        lat.append(["本地小模型(直接回答)", aname[k], f"{float(A[k]['mean_final_attempt_latency_seconds']):.1f}"])
    lat.append(["API", "六模型均值", f"{sum(float(B[k]['mean_final_attempt_latency_seconds']) for k in order_b)/6:.1f}"])
    lat.append(["冻结ML", "单次预测", "<0.01"])
    for k, p in E_RUNS.items():
        m = json.load(open(os.path.join(p, "metrics.json"), encoding="utf-8"))
        if m["latency_s"]["intent_mean"]:
            lat.append(["Agent(意图+誊写两次调用)", names[k],
                        f"{m['latency_s']['intent_mean']+m['latency_s']['final_mean']:.1f}"])
    wcsv(os.path.join(R, "02_绘图数据_按图号", "图15b_成本延迟.csv"),
         ["路径", "条目", "延迟s/题(实测)"], lat)

    # 图9 失败案例三例（真实样本，从原始 run 提取）
    import re
    cases = []
    # (a) 常数背诵：Qwen3-8B
    run_a = glob.glob(os.path.join(RES, "A臂_本地Base直接回答_642题", "runs",
                                    "qwen3_8b_base_primary_q4km_v1__*"))[0]
    for line in open(os.path.join(run_a, "sample_results.jsonl"), encoding="utf-8"):
        d = json.loads(line)
        pa = d.get("parsed_answer")
        pa = pa.get("diffusion_1e9_m2_s") if isinstance(pa, dict) else pa
        if pa is not None and abs(float(pa) - 1.85) < 0.01 and d["question"]["concentration_mol_L"] > 3:
            cases.append(["a 常数背诵/无输入依赖", "Qwen3-8B",
                          f"{d['question']['system']} T={d['question']['temperature_K']}K c={d['question']['concentration_mol_L']}M",
                          str(d["raw_answer_text"])[:120].replace("\n", " "), "1.85",
                          "全642题仅4个唯一预测值，输出与输入条件无关"])
            break
    # (b) 尾部大误差：MiniMax 最差题
    bp = list(csv.DictReader(open(os.path.join(B_MERGE, "base_prompt_results.csv"), encoding="utf-8-sig")))
    worst = max((r for r in bp if r["model_key"] == "MiniMax-M3" and r["absolute_percentage_error_median"]),
                key=lambda r: float(r["absolute_percentage_error_median"]))
    cases.append(["b 系统性偏差与尾部大误差", "MiniMax-M3",
                  f"{worst['system']} T={worst['temperature_K']}K c={worst['concentration_mol_L']}M",
                  f"预测={worst['predicted_median_1e9_m2_s']} vs 实测={worst['observed_diffusion_1e9_m2_s']}",
                  f"APE={float(worst['absolute_percentage_error_median']):.1f}%",
                  "P95 APE 49.8%，尾部误差突出"])
    # (c) 格式失败：kimi 无数值样本
    run_k = glob.glob(os.path.join(RES, "B臂_API六模型直接回答_642题", "kimi__kimi-k3__kimi-k3",
                                    "runs", "20260814T100902857940Z_84485736bc"))[0]
    for line in open(os.path.join(run_k, "sample_results.jsonl"), encoding="utf-8"):
        d = json.loads(line)
        if d.get("parsed_answer") is None:
            cases.append(["c 格式/解析失败", "kimi-k3",
                          f"{d['question']['system']} T={d['question']['temperature_K']}K c={d['question']['concentration_mol_L']}M",
                          str(d["raw_answer_text"])[:120].replace("\n", " "),
                          "该题 3 次重复中 1 次空答（kimi 全部空答题均如此，无 3 次全空题）",
                          "空答/非有限值直接计错（kimi 全库 12/1926 样本）"])
            break
    wcsv(os.path.join(R, "02_绘图数据_按图号", "图10b_失败案例三例.csv"),
         ["案例", "模型", "题目条件", "模型输出/预测", "关键值", "诊断"], cases)

    # 图14 路由轨迹三例（E 臂真实 run 记录）
    ext_run = E_RUNS["external"]
    picks = {"db_hit": None, "ml": None, "refuse_out_of_domain": None}
    for line in open(os.path.join(ext_run, "sample_results.jsonl"), encoding="utf-8"):
        d = json.loads(line)
        rt = d.get("route_result", {}).get("route")
        if rt in picks and picks[rt] is None and d.get("repeat") == 1:
            picks[rt] = d
    with open(os.path.join(R, "02_绘图数据_按图号", "图14_路由轨迹三例.md"), "w", encoding="utf-8") as fh:
        for rt, d in picks.items():
            if not d:
                continue
            fh.write(f"## {rt}\n\n**问题**：{d['question'][:150]}...\n\n")
            fh.write(f"**路由轨迹**：{' → '.join(d['route_result'].get('trace', []))}\n\n")
            fh.write(f"**工具结果块**：\n\n```\n{d.get('tool_block', '')[:600]}\n```\n\n")
            fh.write(f"**终答**：`{json.dumps(d.get('final'), ensure_ascii=False)[:200]}`\n\n---\n\n")

    # ============ 03 各臂完整分析 ============
    for src, dst in [
        (os.path.join(A_MERGE, "manuscript_summary.md"), "03_各臂完整分析/A臂_本地五模型/A臂_合并分析说明.md"),
        (os.path.join(A_MERGE, "manuscript_model_metrics.csv"), "03_各臂完整分析/A臂_本地五模型/A臂_五模型指标.csv"),
        (os.path.join(A_MERGE, "base_prompt_results.csv"), "03_各臂完整分析/A臂_本地五模型/A臂_题目级结果.csv"),
        (os.path.join(B_MERGE, "manuscript_summary.md"), "03_各臂完整分析/B臂_API六模型/B臂_合并分析说明.md"),
        (os.path.join(B_MERGE, "manuscript_model_metrics.csv"), "03_各臂完整分析/B臂_API六模型/B臂_六模型指标.csv"),
        (os.path.join(B_MERGE, "base_prompt_results.csv"), "03_各臂完整分析/B臂_API六模型/B臂_题目级结果.csv"),
        (os.path.join(B_MERGE, "sample_level_results.csv"), "03_各臂完整分析/B臂_API六模型/B臂_样本级结果.csv"),
    ]:
        shutil.copy2(src, os.path.join(R, dst))
    # C 臂：五模型指标合并 + 外部集 12 个指标 CSV
    rows = []
    for p in sorted(glob.glob(os.path.join(C_MET, "*.csv"))):
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if "primary" in r["analysis_set_id"]:
                rows.append(r)
    if rows:
        wcsv(os.path.join(R, "03_各臂完整分析", "C臂_SFT掌握度", "C臂_五模型指标合并.csv"),
             list(rows[0].keys()), [[r.get(k, "") for k in rows[0].keys()] for r in rows])
    for p in sorted(glob.glob(os.path.join(EXT_DIR, "*.csv"))):
        shutil.copy2(p, os.path.join(R, "03_各臂完整分析", "外部集评测_三组对比", os.path.basename(p)))
    # D 臂
    for srcname, dstname in [("冻结汇总.csv", "D臂_冻结汇总.csv"),
                             ("D臂_冻结报告.md", "D臂_冻结报告.md")]:
        p = os.path.join(D_DIR, srcname)
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(R, "03_各臂完整分析", "D臂_ML后端", dstname))
    ev = glob.glob(os.path.join(D_DIR, "output", "evaluation", "ffbc8b45*", "manuscript_metrics.csv"))
    if ev:
        shutil.copy2(ev[0], os.path.join(R, "03_各臂完整分析", "D臂_ML后端", "D臂_全模型指标.csv"))
    # E 臂三个定稿 metrics
    for k, p in E_RUNS.items():
        shutil.copy2(os.path.join(p, "metrics.json"),
                     os.path.join(R, "03_各臂完整分析", "E臂_Agent", f"E臂_{k}_metrics.json"))
        sp = os.path.join(p, "metrics_summary.md")
        if os.path.exists(sp):
            shutil.copy2(sp, os.path.join(R, "03_各臂完整分析", "E臂_Agent", f"E臂_{k}_metrics_summary.md"))

    # ============ 04 基准与数据集 ============
    qdir = os.path.join(ROOT, "02_数据", "02_基准题库与gold_642与240")
    for fn in os.listdir(qdir):
        shutil.copy2(os.path.join(qdir, fn), os.path.join(R, "04_基准与数据集", "题库_642与240", fn))
    fdir = os.path.join(ROOT, "02_数据", "03_外部前瞻集_64题冻结", "frozen")
    for sub in ["questions", "manifest", "sealed"]:
        for fn in os.listdir(os.path.join(fdir, sub)):
            shutil.copy2(os.path.join(fdir, sub, fn),
                         os.path.join(R, "04_基准与数据集", "外部前瞻集", f"{sub}_{fn}"))
    for p in glob.glob(os.path.join(ROOT, "02_数据", "01_四体系源工作簿", "*.xlsx")):
        shutil.copy2(p, os.path.join(R, "04_基准与数据集", "四体系源工作簿", os.path.basename(p)))
    sat = os.path.join(ROOT, "02_数据", "08_各体系溶液溶解度数据")
    for fn in ["溶解度录入_CRC92_v2.xlsx", "溶解度录入_CRC92_v2.csv", "溶解度收集日志.md"]:
        shutil.copy2(os.path.join(sat, fn), os.path.join(R, "04_基准与数据集", "溶解度表", fn))

    # ============ 05 方法与配置支撑 ============
    for src, dst in [
        (os.path.join(ROOT, "py", "SLM_direct", "模型身份冻结清单.md"), "模型身份冻结清单.md"),
        (os.path.join(RES, "C臂_SFT训练与642掌握度", "部署记录", "SFT部署身份记录.md"), "SFT部署身份记录.md"),
        (os.path.join(ROOT, "py", "微调", "训练配置冻结清单.md"), "SFT训练配置冻结清单.md"),
        (os.path.join(ROOT, "py", "微调", "提示家族冻结清单.md"), "提示家族冻结清单.md"),
        (os.path.join(RES, "C臂_SFT训练与642掌握度", "训练回传_五模型", "回传", "清单.md"), "SFT训练回传清单.md"),
        (os.path.join(ROOT, "py", "E_Agent", "工具契约.md"), "E臂工具契约.md"),
    ]:
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(R, "05_方法与配置支撑", dst))

    # ============ 06 关键汇总文档 ============
    for src, dst in [
        (os.path.join(RES, "四臂结果汇总.md"), "四臂结果汇总.md"),
        (os.path.join(EXT_DIR, "三组对比_Base_SFT_ML.md"), "外部集三组对比.md"),
        (os.path.join(EXT_DIR, "external_comparison_summary.md"), "外部集SFT-Base配对对比.md"),
        (os.path.join(E_DIR, "E臂_最终汇总.md"), "E臂最终汇总.md"),
    ]:
        shutil.copy2(src, os.path.join(R, "06_关键汇总文档", dst))

    print("CET_all 构建完成。文件清单：")
    n = 0
    for root, dirs, files in os.walk(R):
        for fn in files:
            n += 1
    print(f"共 {n} 个文件")


if __name__ == "__main__":
    main()
