# -*- coding: utf-8 -*-
"""检查 LM Studio / LMlink 端点连通性（本地运行，双击或在 PyCharm 运行）。

打印三个端点的状态，帮判断评测该用哪个 base_url：
  1. http://localhost:1234/v1/models          （本机 LMlink 代理，评测在用）
  2. http://localhost:1234/api/v1/models      （本机原生元数据接口，预检在用）
  3. http://192.168.2.100:1234/v1/models      （服务器直连，备用）
另外列出当前已加载的模型实例（loaded_instances）。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def check(url: str, timeout: int = 10) -> tuple[str, str]:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            body = response.read().decode("utf-8", errors="replace")
            return "OK", body
    except urllib.error.URLError as exc:
        return "FAIL", f"{exc.reason}"
    except Exception as exc:  # noqa: BLE001
        return "FAIL", str(exc)


def main() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except AttributeError:
        pass
    for url in (
        "http://localhost:1234/v1/models",
        "http://localhost:1234/api/v1/models",
        "http://192.168.2.100:1234/v1/models",
    ):
        status, body = check(url)
        print(f"{url}\n  -> {status}")
        if status == "OK" and "/v1/models" in url:
            try:
                payload = json.loads(body)
                entries = payload.get("data") or payload.get("models") or []
                ids = [e.get("id") or e.get("key") for e in entries if isinstance(e, dict)]
                loaded = []
                for e in entries:
                    if isinstance(e, dict) and e.get("loaded_instances"):
                        key = e.get("key") or e.get("id")
                        loaded.append(key)
                print("  model count:", len(ids))
                if "qwen3.6-27b-lora-r64" in ids:
                    print("  target model present: qwen3.6-27b-lora-r64")
                else:
                    print("  WARNING: qwen3.6-27b-lora-r64 NOT in list")
                print("  loaded instances:", loaded if loaded else "NONE")
            except Exception as exc:  # noqa: BLE001
                print("  parse warning:", exc)
    print()
    print("如果 localhost:1234 两项都 OK 且 loaded 列表里有 qwen3.6-27b-lora-r64，")
    print("就可以运行 run_sft_27b_mastery.bat 续跑评测。")


if __name__ == "__main__":
    main()
