# 服务器 agent：4B SFT 评测修复与执行提示词（直接粘贴）

```text
你是这台 Windows 服务器（192.168.2.100）上的执行 agent。任务：让 Qwen3-4B SFT 的
642 题评测（1926 次调用）成功跑完。评测包在 D:\cet_sft\服务器评测包\ 下。

## 第 1 步：确认/修复 common.py（关键，之前的失败都是它引起的）

在服务器上运行：
    Select-String -Path D:\cet_sft\服务器评测包\py\LLM_API_direct\common.py -Pattern '直写兜底'

- 有输出 → 文件已修复，跳到第 2 步。
- 无输出 → 需要修复：用文本编辑方式打开
  D:\cet_sft\服务器评测包\py\LLM_API_direct\common.py，找到函数
  `def atomic_write_bytes(path: Path, data: bytes) -> None:` 到下一个 `def ` 之前的
  整段，**整体替换**为下面这段（逐字复制，保持缩进）：

def atomic_write_bytes(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for _attempt in range(3):
        descriptor, temp_name = tempfile.mkstemp(
            prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent)
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(data)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_name, path)
            return
        except FileNotFoundError:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
        except BaseException:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
            raise
    path.write_bytes(data)

  替换后再次运行 Select-String 验证能匹配到 '直写兜底'，把验证结果写进报告。

## 第 2 步：删除半成品 run

    Remove-Item 'D:\cet_sft\服务器评测包\py\results\SLM_direct\protocol_v2_2\lm_studio__qwen3_4b_instruct_2507_sft_q4km__qwen3-4b-instruct-2507-lora-r64' -Recurse -Force

## 第 3 步：验证模型与 LM Studio 状态

1. LM Studio 的 Local Server 必须处于运行状态（Developer → Local Server → Started，
   端口 1234）；未运行则启动它。
2. 模型 qwen3-4b-instruct-2507-lora-r64 必须已加载；用普通请求探测（不带任何
   thinking 参数）：
   POST http://127.0.0.1:1234/v1/chat/completions
   {"model":"qwen3-4b-instruct-2507-lora-r64","messages":[{"role":"user","content":"What is 2+2? Reply with only the number."}],"max_tokens":64,"temperature":0,"top_p":1.0}
   要求返回 reasoning_tokens=0 且 content 非空；不是则先到 LM Studio 把该模型的
   Reasoning 设为 Off、context 设为 4096、runtime 选 nvidia-cuda12-avx2 2.29.0，
   重新加载后再探测。
3. 探测结果写进报告。

## 第 4 步：启动评测（必须带 UTF-8 环境变量）

    cd D:\cet_sft\服务器评测包\py\SLM_direct
    $env:PYTHONUTF8='1'; $env:PYTHONIOENCODING='utf-8'
    python run_benchmark.py --config config.json --model-key qwen3_4b_instruct_2507_sft_q4km --mode formal --new-run --experiment-name qwen3_4b_sft_642_mastery

预期：终端逐行输出 [1/1926] [2/1926] …，每条约 0.5–1 秒（服务器本机，无网络开销），
全程约 20–40 分钟。运行期间保持窗口/进程存活；不要关闭 LM Studio、不要卸载模型、
不要重启服务器。

## 第 5 步：完成与报告

- 等待全部 1926 条完成（终端会显示完成信息；或查看
  D:\cet_sft\服务器评测包\py\results\SLM_direct\protocol_v2_2\lm_studio__qwen3_4b_instruct_2507_sft_q4km__qwen3-4b-instruct-2507-lora-r64\runs\<run目录>\progress.json
  中 state=completed 与 counts.completed=1926）。
- 若中途报错：原样记录错误文本，不要自行改配置/删文件/重训；报告后等待指令。
- 完成后报告：run 目录完整路径、completed 数、terminal_failure 数、首尾各 3 条
  终端进度行、以及第 1 步 common.py 验证结果与第 3 步探测结果。

## 禁止事项

不得修改 config.json / run_benchmark.py / slm_common.py / questions 目录；
不得删除 raw 文件之外的结果；不得动 D:\cet_sft 下训练产物与其它模型；
不得运行与本次评测无关的训练或推理任务。
```
