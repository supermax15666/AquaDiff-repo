from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from slm_common import (
    ROOT,
    enabled_model_keys,
    formal_readiness_issues,
    incomplete_runs,
    load_config,
    load_question_id_filter,
    resolve_path,
)


CONFIG = ROOT / "config.json"


def run_python(script: str, *arguments: str) -> int:
    command = [sys.executable, str(ROOT / script), "--config", str(CONFIG), *arguments]
    print("\n正在启动，请不要关闭窗口……\n")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def pause() -> None:
    input("\n按回车键继续……")


def question_count(config_path: Path, config: dict[str, Any], model: dict[str, Any]) -> int:
    question_ids = load_question_id_filter(config_path, model)
    if question_ids is not None:
        return len(question_ids)
    path = resolve_path(config_path.parent, config["question_file"])
    return sum(1 for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip())


def choose_model(config: dict[str, Any]) -> str | None:
    keys = enabled_model_keys(config)
    print("\n请选择 LM Studio 中已经加载的模型：")
    for index, key in enumerate(keys, start=1):
        model = config["models"][key]
        anchor = " [主分析锚点]" if model.get("primary_anchor") else ""
        print(
            f"{index}. {model['display_name']}{anchor}\n"
            f"   key={key}\n"
            f"   served_model_id={model['served_model_id']}"
        )
    print("0. 退出")
    choice = input("\n请输入序号：").strip()
    if choice == "0":
        return None
    try:
        return keys[int(choice) - 1]
    except (ValueError, IndexError):
        print("输入无效。")
        return ""


def show_preflight(model_key: str) -> None:
    run_python(
        "run_benchmark.py",
        "--model-key",
        model_key,
        "--mode",
        "pilot",
        "--experiment-name",
        "preflight",
        "--preflight-only",
    )


def run_pilot(model_key: str) -> None:
    run_python(
        "run_benchmark.py",
        "--model-key",
        model_key,
        "--mode",
        "pilot",
        "--experiment-name",
        "pilot_json_contract",
        "--limit",
        "2",
        "--new-run",
    )


def run_dry(model_key: str) -> None:
    run_python(
        "run_benchmark.py",
        "--model-key",
        model_key,
        "--mode",
        "pilot",
        "--experiment-name",
        "dry_protocol_assets",
        "--limit",
        "2",
        "--new-run",
        "--dry-run",
        "--skip-preflight",
    )


def run_formal(
    config_path: Path, config: dict[str, Any], model_key: str
) -> None:
    issues = formal_readiness_issues(config, model_key)
    if issues:
        print("\n当前模型尚不能开始正式运行：")
        for issue in issues:
            print(f"- {issue}")
        print("\n请先填写 config.json 中的 revision、哈希、LM Studio Runtime 和部署参数，")
        print("确认 GGUF 为统一自行转换的 Q4_K_M 后，把模型 formal_ready 与顶层 protocol_frozen 设为 true。")
        return
    model = config["models"][model_key]
    count = question_count(config_path, config, model)
    repetitions = int(config["repetitions"])
    experiment_name = input(
        "实验名（建议 base_primary_q4km_v1）："
    ).strip() or "base_primary_q4km_v1"
    print(
        f"\n模型：{model['display_name']}\n"
        f"题目：{count}\n重复：{repetitions}\n"
        f"总推理次数：{count * repetitions}\n实验名：{experiment_name}"
    )
    if input("输入 YES 创建新的正式 run：").strip() != "YES":
        print("已取消。")
        return
    run_python(
        "run_benchmark.py",
        "--model-key",
        model_key,
        "--mode",
        "formal",
        "--experiment-name",
        experiment_name,
        "--new-run",
    )


def resume_run(config_path: Path, config: dict[str, Any], model_key: str) -> None:
    rows = incomplete_runs(config_path, config, model_key)
    if not rows:
        print("没有找到该模型可续跑的 v2.2 run。")
        return
    print("\n可续跑任务：")
    for index, (run_dir, manifest) in enumerate(rows, start=1):
        counts = manifest.get("counts", {})
        print(
            f"{index}. {run_dir.name}\n"
            f"   mode={manifest.get('run_mode')} status={manifest.get('status')} "
            f"terminal={counts.get('terminal', 0)}/{counts.get('total', '?')}"
        )
    choice = input("请输入序号（0取消）：").strip()
    if choice == "0":
        return
    try:
        run_dir, manifest = rows[int(choice) - 1]
    except (ValueError, IndexError):
        print("输入无效。")
        return
    run_python(
        "run_benchmark.py",
        "--model-key",
        model_key,
        "--mode",
        str(manifest.get("run_mode", "pilot")),
        "--experiment-name",
        str(manifest.get("experiment_name", run_dir.name.split("__", 1)[0])),
        "--run-id",
        run_dir.name,
        "--resume-only",
    )


def model_menu(config_path: Path, config: dict[str, Any], model_key: str) -> None:
    model = config["models"][model_key]
    count = question_count(config_path, config, model)
    repetitions = int(config["repetitions"])
    while True:
        print("\n" + "=" * 72)
        print("  四体系本地小模型闭卷扩散系数测试（SLM_direct v2.2）")
        print(f"  模型：{model['display_name']}")
        print(f"  served_model_id：{model['served_model_id']}")
        print(f"  题目：{count}；重复：{repetitions}；共 {count * repetitions} 次推理")
        print("  输出：py/results/SLM_direct/protocol_v2_2")
        print("=" * 72)
        print("1. LM Studio 双接口与模型身份预检")
        print("2. 两题 JSON 连通性测试（新建 pilot run）")
        print("3. 创建两题 dry-run 资产（不连接模型）")
        print("4. 开始一次新的正式运行")
        print("5. 继续中断的运行")
        print("6. 生成正式论文结果表")
        print("7. 返回模型选择")
        print("0. 退出")
        choice = input("\n请输入序号：").strip()
        if choice == "1":
            show_preflight(model_key)
            pause()
        elif choice == "2":
            run_pilot(model_key)
            pause()
        elif choice == "3":
            run_dry(model_key)
            pause()
        elif choice == "4":
            run_formal(config_path, config, model_key)
            pause()
        elif choice == "5":
            resume_run(config_path, config, model_key)
            pause()
        elif choice == "6":
            run_python("analyze_results.py")
            pause()
        elif choice == "7":
            return
        elif choice == "0":
            raise SystemExit(0)
        else:
            print("请输入 0–7。")


def main() -> int:
    while True:
        try:
            config_path, config = load_config(CONFIG)
        except ValueError as exc:
            print(f"配置错误：{exc}", file=sys.stderr)
            return 1
        model_key = choose_model(config)
        if model_key is None:
            return 0
        if not model_key:
            continue
        model_menu(config_path, config, model_key)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已停止。未完成任务可从菜单选择续跑。")
        raise SystemExit(130)
