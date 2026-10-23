# SLM_direct：本地小模型闭卷扩散系数基准

本目录实现研究方案 v2.2 的实验臂 A，并预留实验臂 C（SFT direct）和实验臂 E（Agent）的配对身份。它复用 `../LLM_API_direct` 已验证的题库、系统提示、严格 JSON Schema、SQLite 断点续跑、原始响应归档和论文评分器。

## 固定任务

- 四体系：NaCl–H₂O、KCl–H₂O、LiCl–H₂O、CaCl₂–H₂O。
- 主集：642 题；每题 3 次，共每模型 1,926 次推理。
- 240 题均衡敏感性分析复用同一批响应，额外推理为 0。
- 模型只能看到体系、温度和浓度；不提供数据库、MCP、RAG、搜索、代码或拟合模型。
- 唯一允许的答案格式：

```json
{"diffusion_1e9_m2_s": 1.234567}
```

单位由基准固定为 `10^-9 m^2/s`；模型不得输出 `unit` 或其他字段。

## 五个固定 Base 模型

| 稳定模型键 | 模型 | 原生训练模板 |
|---|---|---|
| `qwen3_4b_instruct_2507_base_q4km` | Qwen3-4B-Instruct-2507（主分析锚点） | `qwen3_nothink` |
| `qwen3_8b_instruct_base_q4km` | Qwen3-8B-Instruct | `qwen3_nothink` |
| `qwen3_6_27b_base_q4km` | Qwen3.6-27B（能力上锚） | `qwen3_nothink` |
| `llama3_1_8b_instruct_base_q4km` | Llama-3.1-8B-Instruct | `llama3` |
| `gemma2_9b_it_base_q4km` | Gemma-2-9B-it | `gemma2` |

主比较统一关闭思维链；Qwen3-4B/8B/27B 另设预注册 thinking 敏感性（方案 v2.5 第 14 条，不进主表）。
这里的 Base 指“原始 Instruct 基线”，不是未指令微调的预训练 Base checkpoint。

## 首次使用

1. 在 LM Studio 0.4.2 中更新并固定 GGUF/llama.cpp Runtime。
2. 导入一个 GGUF，启动 Local Server。

   **服务器地址**：程序连接地址在 `config.json` 的 `server.base_url`
   （OpenAI 兼容接口）与 `server.native_models_url`（原生接口）中填写，
   两者必须同源。当前配置指向局域网地址
   `http://192.168.2.100:1234`，并已把 `require_loopback` 设为 `false`
   （loopback 限制只是防误连远端的安全保护，不是方案要求；使用局域网内
   自己可信的 LM Studio 主机时关闭即可。若地址指向公网/不受信主机，
   请自行评估安全风险）。

   **模型名称**：模型身份使用 LM Studio 的原生命名格式，写在每个模型的
   `served_model_id` 字段里（如 `qwen3-4b-instruct-2507`、`gemma-2-2b-it`）。
   加载模型时**不需要自定义 identifier**，直接用 LM Studio 默认名称加载即可；
   程序预检会核对 LM Studio 实际返回的 id 是否等于 `served_model_id`。

3. 先卸载其他模型，再加载目标模型（在运行 LM Studio 的机器上执行）：

```powershell
lms unload --all
lms load qwen3-4b-instruct-2507 --context-length 4096 --gpu <固定值>
```

   注意：`lms` 命令需要在运行 LM Studio 的那台机器（如 192.168.2.100）上执行；
   加载后的上下文长度必须与 `deployment.context_length`（当前 4096）一致。

4. 打开 `config.json`，把相应模型的 `deployment.lmstudio_disk_key`、运行时版本和加载参数改成实际值。

   大部分部署字段可以由脚本从正在运行的 LM Studio 自动采集，只需手工提供少数无法自动化的字段：

   ```powershell
   python capture_deployment.py --model-key qwen3_4b_instruct_2507_base_q4km `
       --gguf-path D:\models\qwen3-4b-2507-Q4_K_M.gguf `
       --revision <ModelScope revision> `
       --llama-cpp-repo D:\code\llama.cpp `
       --gpu-offload full
   ```

   脚本会回填 `native_model_key`、`lmstudio_load_key`、`selected_variant`、
   `context_length`、量化、runtime 版本、GGUF 路径/文件名/SHA-256，并列出
   剩余待填字段和正式运行门禁（`formal_readiness_issues`）清单。

5. 启动交互菜单：

```powershell
python start.py
```

也可以双击 `start.bat`。

菜单先运行双接口预检：

- `GET /v1/models` 验证 OpenAI 兼容 identifier；
- `GET /api/v1/models` 验证模型确实已加载，并检查 `type=llm`、`format=gguf`、架构、`Q4_K_M`、context length 和唯一实例。

`/v1/models` 在开启 JIT 时可能列出所有已下载模型，因此程序不会仅凭该接口判断模型已经加载。

## Pilot 与正式运行

建议顺序：

1. 菜单 1：身份预检；
2. 菜单 2：两题 JSON 连通性 pilot；
3. 检查 pilot 的 raw request/response 和 `sample_results.jsonl`；
4. 冻结模型及运行信息；
5. 菜单 4：创建新的正式运行。

正式运行前必须填写：

- ModelScope revision 与下载快照 manifest SHA-256；
- 自行转换 GGUF 的文件名和 SHA-256；
- llama.cpp converter/quantizer commit；
- LM Studio 0.4.2 Runtime 版本、disk key、context length 和 GPU offload；
- `gguf.source_kind=self_converted`；
- 模型级 `formal_ready=true` 和顶层 `protocol_frozen=true`。

社区 GGUF 只能用于连通性测试。论文正式 Base 与 SFT 必须从完整 Safetensors 使用同一 llama.cpp commit、同一 imatrix 策略和 Q4_K_M 量化流程自行生成。

## 输出目录

旧两体系 pilot 保留在 `../results/SLM_direct/` 根目录；新版程序只读写：

```text
py/results/SLM_direct/protocol_v2_2/
└── lm_studio__<model_key>__<served_model_id>/
    └── runs/
        └── <experiment_name>__<UTC timestamp>_<protocol fingerprint>/
            ├── run_manifest.json
            ├── protocol_material.json
            ├── state.sqlite3
            ├── progress.json
            ├── sample_results.jsonl
            ├── raw_inventory.json
            └── raw/
                ├── requests/
                └── responses/
```

每次 pilot、dry-run 或正式实验都使用 `--new-run` 新建目录。续跑只接受完整协议指纹一致的原 run，不会复用旧平面 CSV。

## 直接 CLI

两题 pilot：

```powershell
python run_benchmark.py --model-key qwen3_4b_instruct_2507_base_q4km --mode pilot --experiment-name pilot_json_contract --limit 2 --new-run
```

正式运行：

```powershell
python run_benchmark.py --model-key qwen3_4b_instruct_2507_base_q4km --mode formal --experiment-name base_primary_q4km_v1 --new-run
```

程序收到 Ctrl+C 后会持久化进度。再次运行 `start.py`，选择“继续中断的运行”。

## 结果分析

```powershell
python analyze_results.py
```

分析器默认只纳入 `completed + formal + 未触发协议暂停` 的 642 题运行。同一模型存在多个完整正式 run 时，程序拒绝自动择优，必须显式使用 `--run-dir` 选择。

输出沿用大模型分析字段，并额外加入：

- `experiment_arm`、`pair_id`、`pair_role`、`model_variant`、`fold_id`；
- Base checkpoint、GGUF、llama.cpp 和 LM Studio Runtime 身份；
- `language_model_artifact_id`；
- 不含模型/run fingerprint 的 `pair_task_id`，用于 Base/SFT 同题配对。

## 后续 SFT 接入

每个 SFT fold 新增一个模型条目，并至少修改：

```json
{
  "pair_role": "sft",
  "model_variant": "domain_sft",
  "experiment_arm": "C_sft_direct",
  "fold_id": 0,
  "question_ids_file": "<该折测试 question_id 清单>",
  "parent_base": {"model_key": "<对应 Base 键>", "sha256": "<Base 哈希>"},
  "sft_artifacts": {
    "adapter_sha256": "<SHA-256>",
    "merged_model_sha256": "<SHA-256>"
  },
  "training_provenance": {
    "split_manifest_sha256": "<SHA-256>",
    "training_config_sha256": "<SHA-256>",
    "llamafactory_version": "<版本>"
  }
}
```

Base 与 SFT 必须保持相同 `pair_id`、模板、测试题、解码、解析器、重复数、GGUF 转换版本和量化类型。单折 `--allow-partial-question-set` 只用于诊断，五折 OOF 完整合并后才能进入论文 SFT 主表。

## Agent 对比

`run_manifest.json` 同时保存 `language_model_artifact_id` 和 `agent_comparison_model_artifact_id`。实验臂 E 必须引用与实验臂 A 完全相同的 Base GGUF 身份；否则不能把差异解释为工具增强。

## 安全与可重复性

- 配置文件禁止明文密钥；如开启 LM Studio Authentication，只设置环境变量 `LM_STUDIO_API_KEY`。
- gold 始终由分析器侧联结，不进入模型请求。
- JSON/空答/拒答/非有限值均按错误计入全题分母。
- 请求成功但 JSON 无效时不会选择性重试。
- 基础设施失败超过 5% 或模型 identifier 不匹配时，manifest 会触发协议暂停，结果不能进入论文分析。
