from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
CONFIG = ROOT / "config.json"


def load_config() -> dict:
    try:
        config = json.loads(CONFIG.read_text(encoding="utf-8-sig"))
    except FileNotFoundError:
        raise SystemExit(f"找不到配置文件：{CONFIG}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"config.json 格式错误：{exc}")

    api_key = str(config.get("api_key", "")).strip()
    model_name = str(config.get("model_name", "")).strip()
    if not api_key or api_key.startswith("请在这里"):
        raise SystemExit("请先打开 config.json，在 api_key 中填写你的 API Key。")
    if not model_name or model_name.startswith("请在这里"):
        raise SystemExit("请先打开 config.json，在 model_name 中填写模型名称。")
    return config


def count_questions(config: dict) -> tuple[int, int, int]:
    question_path = ROOT / str(config["question_file"])
    with question_path.open("r", encoding="utf-8-sig") as handle:
        question_count = sum(1 for line in handle if line.strip())
    repetitions = int(config.get("repetitions", 1))
    if question_count <= 0 or repetitions <= 0:
        raise SystemExit("题库为空，或 repetitions 不是正整数。")
    return question_count, repetitions, question_count * repetitions


def sensitivity_count(config: dict) -> int | None:
    value = config.get("analysis_sets_file")
    if not value:
        return None
    path = ROOT / str(value)
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        for item in payload.get("sets", []):
            if item.get("role") == "sensitivity":
                return int(item["question_count"])
    except (FileNotFoundError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None
    return None


def run_script(script: str, *arguments: str) -> int:
    command = [sys.executable, str(ROOT / script), "--config", str(CONFIG), *arguments]
    print("\n正在启动，请不要关闭窗口……\n")
    return subprocess.run(command, cwd=ROOT, check=False).returncode


def pause() -> None:
    input("\n按回车键返回菜单……")


def main() -> int:
    while True:
        config = load_config()
        model_name = config["model_name"]
        question_count, repetitions, call_count = count_questions(config)
        balanced_count = sensitivity_count(config)
        print("\n" + "=" * 58)
        print("  四体系大语言模型扩散系数知识测试")
        print(f"  当前模型：{model_name}")
        print(f"  接口地址：{config.get('base_url', 'https://api.openai.com/v1')}")
        print("=" * 58)
        pilot_questions = min(2, question_count)
        pilot_calls = pilot_questions * repetitions
        print(f"1. 小规模测试（{pilot_questions}道题，共{pilot_calls}次 API 调用）")
        print(
            f"2. 开始一次新的正式运行（{question_count}道题，共{call_count}次调用）"
        )
        if balanced_count is not None:
            print(
                f"   其中{balanced_count}题均衡敏感性分析复用同一响应，额外调用0次"
            )
        print("3. 继续上次中断的正式运行")
        print("4. 生成论文结果表")
        print("0. 退出")
        choice = input("\n请输入序号：").strip()

        if choice == "1":
            run_script("run_benchmark.py", "--limit", "2", "--new-run")
            pause()
        elif choice == "2":
            confirm = input(
                f"将创建新的{call_count}次调用任务，输入 YES 确认："
            ).strip()
            if confirm == "YES":
                run_script("run_benchmark.py", "--new-run")
            else:
                print("已取消。")
            pause()
        elif choice == "3":
            run_script("run_benchmark.py", "--resume-only")
            pause()
        elif choice == "4":
            run_script("analyze_results.py")
            pause()
        elif choice == "0":
            return 0
        else:
            print("请输入 0、1、2、3 或 4。")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n已停止。再次启动并选择 3 即可续跑。")
        raise SystemExit(130)
