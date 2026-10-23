# 使用方法

## 第一次使用

1. 在本目录打开终端，安装依赖：

   ```powershell
   python -m pip install -r requirements.txt
   ```

2. 打开 `config.json`，只需填写前两项：

   ```json
   "api_key": "你的 API Key",
   "model_name": "模型名称"
   ```

   当前默认连接 Kimi 开放平台（月之暗面）。以下四项不要修改：

       "provider": "kimi",
       "base_url": "https://api.moonshot.cn/v1",
       "endpoint": "chat_completions",
       "structured_output": "json_object"

   这是 Kimi 的 OpenAI 兼容 Chat Completions 接口，程序会发送
   response_format=json_object，并在提示中给出单字段 JSON 格式样例：

       {"diffusion_1e9_m2_s": 1.234567}

   返回后仍会使用本地 JSON Schema 校验字段和正数数值。单位由基准固定为
   `10^-9 m^2/s`，程序记录为 `unit_source=benchmark_fixed`，不要求模型重复输出。

   配置中的 thinking.type 默认是 disabled。Kimi K3 不使用 thinking 参数，
   程序会自动把它翻译为顶层 `reasoning_effort: "low"`（K3 支持 low/high/max，
   默认 max；设为 low 可减少短数值题的思考开销）。正式实验中请保持该值不变。

   注意：Kimi K3 官方只允许 `temperature=1`（传 0 会返回 400
   "only 1 is allowed for this model"），因此本模型臂的 temperature 固定为 1，
   与其余五家的 0 不同——这是平台限制，解码参数会如实记录在 run_manifest.json
   中，3 次重复的回答波动会比温度 0 的模型更大，统计口径不变（按题取平均）。

   另外 K3 即使在 reasoning_effort=low 下仍会输出较长的思考链，实测单次可达
   250+ 思考 token，因此本模型臂的 max_output_tokens 设为 1024（其余模型为
   256）。若设 256，思考内容会占满额度导致 JSON 被截断（finish_reason=length）。

   切换模型的方法：历史配置已备份为 `config.backup_deepseek.json`（DeepSeek）、
   `config.backup_zhipu.json`（智谱 glm-5.2）、`config.backup_qwen.json`
   （Qwen3.8-Max）、`config.backup_doubao.json`（豆包）和
   `config.backup_minimax.json`（MiniMax-M3），把对应文件内容复制回
   `config.json` 即可。各家的 provider/base_url：DeepSeek=deepseek /
   https://api.deepseek.com，智谱=zhipu / https://open.bigmodel.cn/api/paas/v4，
   千问=qwen / https://dashscope.aliyuncs.com/compatible-mode/v1，
   豆包=doubao / https://ark.cn-beijing.volces.com/api/v3，
   MiniMax=minimax / https://api.minimaxi.com/v1（structured_output 需为 "none"），
   Kimi=kimi / https://api.moonshot.cn/v1。

## 启动程序

双击 `start.bat`，或者运行：

```powershell
python start.py
```

根据菜单选择：

- `1`：先运行2道题（每题3次，共6次调用），检查接口是否可用；
- `2`：新建正式运行：642题、每题3次，共1,926次调用；
- `3`：断线或关闭后继续上次运行；
- `4`：模型全部跑完后生成论文结果；同一批响应同时生成642题主结果
  和240题均衡敏感性结果，敏感性分析额外调用0次；
- `0`：退出。

结果保存在：

```text
E:\Desktop\CET_docment\CET_docment\py\results\LLM_API_direct
```

注意：`config.json` 中包含 API Key，请勿上传、分享或放入公开论文附件。
