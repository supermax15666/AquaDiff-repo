from __future__ import annotations

"""为论文图 10 生成 Origin 导入模板数据（只读冻结评价，写入 output/Origin导入模板/）。

用法：
    python export_origin_template.py

规则：
- 只读取 protocol_frozen=true 的评价目录（results.json）与注册清单（registry.json）；
- 输出的 CSV 均为 UTF-8 BOM、逗号分隔，Origin 可直接导入；
- 本脚本不在 3.D 协议指纹范围内（不影响已冻结的 evaluate/register 产物）。
"""

import csv
import io
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
OUTPUT_ROOT = ROOT.parent / "output"
EVALUATION_ROOT = OUTPUT_ROOT / "evaluation"
REGISTRY_ROOT = OUTPUT_ROOT / "registry"
TEMPLATE_DIR = OUTPUT_ROOT / "Origin导入模板"

PANEL_CSV = "图10_面板数据_专用模型.csv"
PAIRED_CSV = "图10_专用vs_pooled.csv"
PAIRED_LONG_CSV = "图10_专用vs_pooled_长表.csv"

SYSTEM_ORDER = ["NaCl-H2O", "KCl-H2O", "LiCl-H2O", "CaCl2-H2O"]
MODEL_ORDER = {
    "polynomial_ridge": 1,
    "rbf_svr": 2,
    "random_forest": 3,
    "gradient_boosting": 4,
    "gaussian_process": 5,
    "dummy_median": 6,
}


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, Any]]) -> None:
    buffer = io.StringIO()
    writer = csv.DictWriter(
        buffer, fieldnames=fieldnames, extrasaction="ignore", lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(buffer.getvalue().encode("utf-8-sig"))


def _find_frozen() -> tuple[dict[str, Any], dict[str, Any]]:
    candidates = sorted(EVALUATION_ROOT.glob("*/results.json"))
    frozen_results: list[dict[str, Any]] = []
    for path in candidates:
        payload = _read_json(path)
        if payload.get("protocol_frozen"):
            frozen_results.append(payload)
    if not frozen_results:
        raise SystemExit(
            "没有找到 protocol_frozen=true 的评价结果；请先完成冻结重跑（register）。"
        )
    results = frozen_results[-1]
    fingerprint = str(results["protocol_fingerprint"])
    registry_path = REGISTRY_ROOT / fingerprint / "registry.json"
    if not registry_path.is_file():
        raise SystemExit(f"缺少冻结注册清单：{registry_path}")
    registry = _read_json(registry_path)
    if not registry.get("protocol_frozen"):
        raise SystemExit(f"注册清单未冻结：{registry_path}")
    return results, registry


def _panel_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    model_keys = [key for key in MODEL_ORDER if key in results["model_specs"]]
    rows: list[dict[str, Any]] = []
    for system in SYSTEM_ORDER:
        selected_key = (
            results.get("selection", {}).get(system, {}).get("selected_model_key")
        )
        for model_key in model_keys:
            metrics = results["specialized"][system][model_key]
            folds = results.get("fold_details", {}).get(system, {}).get(model_key, [])
            fold_mdapes = [
                folds[fold_index]["mdape_percent"]
                for fold_index in range(len(folds))
            ]
            row: dict[str, Any] = {
                "体系": system,
                "模型": results["model_specs"][model_key]["display_name"],
                "模型顺序": MODEL_ORDER[model_key],
                "是否入选": "入选" if model_key == selected_key else "",
                "宏谱系MdAPE%": round(metrics["macro_lineage_mdape_percent"], 4),
                "整体MdAPE%": round(metrics["mdape_percent"], 4),
                "MAE": metrics["mae_1e9_m2_s"],
                "RMSE": metrics["rmse_1e9_m2_s"],
                "CV_Acc5%": metrics["accuracy_5pct"],
                "CV_Acc10%": metrics["accuracy_10pct"],
                "P95APE%": round(metrics["p95_ape_percent"], 4),
                "maxAPE%": round(metrics["max_ape_percent"], 4),
                "条件数": metrics["n"],
                "谱系数": metrics["n_lineages"],
                "折间min_MdAPE%": round(min(fold_mdapes), 4) if fold_mdapes else "",
                "折间max_MdAPE%": round(max(fold_mdapes), 4) if fold_mdapes else "",
            }
            for fold_index in range(1, 6):
                if fold_index <= len(folds):
                    row[f"折{fold_index}_MdAPE%"] = round(
                        folds[fold_index - 1]["mdape_percent"], 4
                    )
                else:
                    row[f"折{fold_index}_MdAPE%"] = ""
            rows.append(row)
    return rows


def _paired_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for system in SYSTEM_ORDER:
        selected_key = results["selection"][system]["selected_model_key"]
        spec = results["specialized"][system][selected_key]
        pooled = results["pooled"][system][selected_key]
        delta = spec["macro_lineage_mdape_percent"] - pooled[
            "macro_lineage_mdape_percent"
        ]
        rows.append(
            {
                "体系": system,
                "模型家族": results["model_specs"][selected_key]["display_name"],
                "专用_宏MdAPE%": round(spec["macro_lineage_mdape_percent"], 4),
                "pooled_宏MdAPE%": round(pooled["macro_lineage_mdape_percent"], 4),
                "Δ_宏MdAPE%": round(delta, 4),
                "专用_MAE": spec["mae_1e9_m2_s"],
                "pooled_MAE": pooled["mae_1e9_m2_s"],
                "专用_Acc10%": spec["accuracy_10pct"],
                "pooled_Acc10%": pooled["accuracy_10pct"],
                "解读": "pooled 更优（数据借用有利）" if delta > 0 else "专用模型更优",
            }
        )
    return rows


def _paired_long_rows(results: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for system in SYSTEM_ORDER:
        selected_key = results["selection"][system]["selected_model_key"]
        for label, role in (("专用", "specialized"), ("pooled", "pooled")):
            metrics = results[role][system][selected_key]
            rows.append(
                {
                    "体系": system,
                    "组别": label,
                    "宏MdAPE%": round(metrics["macro_lineage_mdape_percent"], 4),
                    "MAE": metrics["mae_1e9_m2_s"],
                    "Acc10%": metrics["accuracy_10pct"],
                }
            )
    return rows


def main() -> int:
    results, registry = _find_frozen()
    print(f"冻结指纹：{results['protocol_fingerprint']}")
    print(f"冻结状态：{results['protocol_frozen']}")

    panel_rows = _panel_rows(results)
    _write_csv(
        TEMPLATE_DIR / PANEL_CSV,
        list(panel_rows[0].keys()),
        panel_rows,
    )
    paired_rows = _paired_rows(results)
    _write_csv(
        TEMPLATE_DIR / PAIRED_CSV,
        list(paired_rows[0].keys()),
        paired_rows,
    )
    paired_long_rows = _paired_long_rows(results)
    _write_csv(
        TEMPLATE_DIR / PAIRED_LONG_CSV,
        list(paired_long_rows[0].keys()),
        paired_long_rows,
    )
    print(f"已生成：{TEMPLATE_DIR / PANEL_CSV}（{len(panel_rows)} 行）")
    print(f"已生成：{TEMPLATE_DIR / PAIRED_CSV}（{len(paired_rows)} 行）")
    print(f"已生成：{TEMPLATE_DIR / PAIRED_LONG_CSV}（{len(paired_long_rows)} 行）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
