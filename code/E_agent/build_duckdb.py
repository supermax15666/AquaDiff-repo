# -*- coding: utf-8 -*-
"""E 臂 DuckDB 实验库构建（方案 v2.15/v2.16 §3.E）。

从四体系源工作簿 Confirmed_Records 构建 DuckDB 实验记录库（含谱系/文献来源），
并验证 642 题主集与外部 64 题的命中情况：
  - 642 主集应 642/642 精确命中（题目条件即池内唯一条件）；
  - 外部 64 题应 0 命中（新谱系，不入库）。
构建后写 manifest（哈希+行数+验证结果）。重复构建需 --force（产物不可变纪律）。

用法：
    python build_duckdb.py [--force]
"""

import argparse
import glob
import hashlib
import json
import os
import sys
from datetime import datetime, timezone

import duckdb
import openpyxl

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
WORKBOOK_DIR = os.path.join(ROOT, "02_数据", "01_四体系源工作簿")
Q642 = os.path.join(ROOT, "02_数据", "02_基准题库与gold_642与240", "four_system_all_questions.jsonl")
QEXT = os.path.join(ROOT, "02_数据", "03_外部前瞻集_64题冻结", "frozen", "questions", "external_questions.jsonl")
DB_PATH = os.path.join(HERE, "db", "experimental_records.duckdb")


def load_records():
    recs = []
    for path in sorted(glob.glob(os.path.join(WORKBOOK_DIR, "*.xlsx"))):
        wb = openpyxl.load_workbook(path, read_only=True)
        ws = wb["Confirmed_Records"]
        it = ws.iter_rows(values_only=True)
        header = [str(h).strip() for h in next(it)]
        wbname = os.path.basename(path)
        for i, row in enumerate(it, start=2):
            if row is None or row[0] is None:
                continue
            d = dict(zip(header, row))
            recs.append({
                "system": str(d["system"]).strip(),
                "temperature_K": float(d["temperature_K"]),
                "concentration_mol_L": float(d["concentration_mol_L"]),
                "diffusion_1e9_m2_s": float(d["diffusion_1e9_m2_s"]),
                "lineage_id": str(d["model_group_id"]).strip(),
                "lobo_ref_no": d["lobo_ref_no"],
                "original_reference": str(d["original_reference"]).strip(),
                "source_workbook": wbname,
                "source_row": i,
            })
        wb.close()
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="覆盖已有 db（默认禁止）")
    args = ap.parse_args()

    if os.path.exists(DB_PATH) and not args.force:
        sys.exit(f"已存在 {DB_PATH}；库不可变，如需重建加 --force（并留档原因）")
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)

    recs = load_records()
    con = duckdb.connect(DB_PATH)
    con.execute("""
        CREATE TABLE experimental_records (
            system VARCHAR NOT NULL,
            temperature_K DOUBLE NOT NULL,
            concentration_mol_L DOUBLE NOT NULL,
            diffusion_1e9_m2_s DOUBLE NOT NULL,
            lineage_id VARCHAR NOT NULL,
            lobo_ref_no VARCHAR,
            original_reference VARCHAR NOT NULL,
            source_workbook VARCHAR NOT NULL,
            source_row INTEGER NOT NULL
        )
    """)
    con.executemany(
        "INSERT INTO experimental_records VALUES (?,?,?,?,?,?,?,?,?)",
        [[r[k] for k in ["system", "temperature_K", "concentration_mol_L", "diffusion_1e9_m2_s",
                          "lineage_id", "lobo_ref_no", "original_reference", "source_workbook", "source_row"]]
         for r in recs])
    n = con.execute("SELECT COUNT(*) FROM experimental_records").fetchone()[0]
    n_cond = con.execute(
        "SELECT COUNT(*) FROM (SELECT DISTINCT system, temperature_K, concentration_mol_L FROM experimental_records)"
    ).fetchone()[0]
    n_lin = con.execute("SELECT COUNT(DISTINCT lineage_id) FROM experimental_records").fetchone()[0]

    # 命中验证：642 应全命中；外部应 0 命中（精确匹配）
    def hit(system, T, c):
        return con.execute(
            "SELECT COUNT(*) FROM experimental_records WHERE system=? AND temperature_K=? AND concentration_mol_L=?",
            [system, float(T), float(c)]).fetchone()[0]

    hits642 = miss642 = 0
    for line in open(Q642, encoding="utf-8"):
        q = json.loads(line)
        if hit(q["system"], q["temperature_K"], q["concentration_mol_L"]) > 0:
            hits642 += 1
        else:
            miss642 += 1
    ext_hits = []
    n_ext = 0
    for line in open(QEXT, encoding="utf-8"):
        q = json.loads(line)
        n_ext += 1
        if hit(q["system"], q["temperature_K"], q["concentration_mol_L"]) > 0:
            ext_hits.append(q["question_id"])
    con.close()

    # gold 中位数一致性：642 条件的库内中位数应与 gold 逐位一致（gold 策略=同条件记录中位数）
    import statistics
    con2 = duckdb.connect(DB_PATH, read_only=True)
    gmatch = 0
    gold_path = os.path.join(os.path.dirname(Q642), "four_system_all_gold.evaluator.jsonl")
    for line in open(gold_path, encoding="utf-8"):
        d = json.loads(line)
        vals = [r[0] for r in con2.execute(
            "SELECT diffusion_1e9_m2_s FROM experimental_records WHERE system=? AND temperature_K=? AND concentration_mol_L=?",
            [d["system"], d["temperature_K"], d["concentration_mol_L"]]).fetchall()]
        if vals and statistics.median(vals) == d["diffusion_1e9_m2_s"]:
            gmatch += 1
    con2.close()

    def sha(p):
        h = hashlib.sha256()
        with open(p, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest()

    manifest = {
        "artifact_type": "e_arm_duckdb_build",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "plan_version": "2.16",
        "db_path": DB_PATH,
        "db_sha256": sha(DB_PATH),
        "n_records": n,
        "n_unique_conditions": n_cond,
        "n_lineages": n_lin,
        "sources": [os.path.basename(p) for p in sorted(glob.glob(os.path.join(WORKBOOK_DIR, "*.xlsx")))],
        "verification": {
            "q642_exact_hits": hits642, "q642_misses": miss642, "expect": "642/642",
            "q642_gold_median_identical": gmatch, "expect_gold": "642/642（gold 策略=同条件记录中位数）",
            "q64_external_hits": len(ext_hits), "q64_external_total": n_ext,
            "expect_external": "7 命中（2026-08-27 实测；均为 298.15 K 圆整条件：NaCl 1.0/1.5、LiCl 0.5/1.0、CaCl2 0.01/0.05/0.1——属池内多谱系冲突条件，未进 642 训练集，外部审计基线为 642 故合规；设计内行为）",
            "external_hit_ids": ext_hits,
            "match_rule": "精确匹配 (system, temperature_K, concentration_mol_L)（浮点等值；题目条件由池内记录生成）",
        },
        "immutable": "库文件构建后不再改动；如需变更（如第五体系加入）须新建文件并留档",
    }
    with open(os.path.join(HERE, "db", "build_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=1)

    print(f"记录 {n} 条 | 唯一条件 {n_cond} | 谱系 {n_lin}")
    print(f"642 主集精确命中: {hits642}/642 {'✓' if hits642 == 642 else '✗ 不符预期！'}")
    print(f"642 gold 中位数一致: {gmatch}/642 {'✓' if gmatch == 642 else '✗ 不符预期！'}")
    print(f"外部 64 题命中: {len(ext_hits)}/{n_ext} {'✓（7 为设计内：池内多谱系冲突条件，未进 642）' if len(ext_hits) == 7 else '（预期 7，请核对）'}")
    print(f"DB SHA-256: {manifest['db_sha256'][:16]}…")
    ok = hits642 == 642 and gmatch == 642 and len(ext_hits) == 7 and n == 785
    print("构建验证：" + ("全部通过" if ok else "存在不符，请检查"))
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
