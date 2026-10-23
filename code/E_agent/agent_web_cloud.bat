@echo off
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM ============================================================
REM  Cloud API launcher - use when the laptop cannot reach LM Studio
REM  Pre-configured for Zhipu GLM-5.3-Flash (bigmodel.cn)
REM  Edit ONLY the API key line below, save, then double-click.
REM  Security: delete or rotate the key after the presentation!
REM ============================================================

REM ---- THE ONLY LINE TO EDIT: paste your Zhipu API key here ----
set AQUADIFF_API_KEY=PASTE_YOUR_API_KEY_HERE

REM ---- Pre-configured for GLM-5.3-Flash, normally no changes needed ----
set AQUADIFF_BASE_URL=https://open.bigmodel.cn/api/paas/v4
set AQUADIFF_MODEL=glm-5.3-flash
REM GLM-5.3-Flash ALWAYS thinks - keep this line or the API returns HTTP 400
set AQUADIFF_LLM_EXTRA={"thinking":{"type":"enabled"},"reasoning_effort":"low"}

REM ---- To switch provider edit the three lines above. Examples: ----
REM  DeepSeek deepseek-v4-pro   https://api.deepseek.com                          {"thinking":{"type":"disabled"}}
REM  Qwen     qwen3.8-max       https://dashscope.aliyuncs.com/compatible-mode/v1 {"thinking":{"type":"disabled"}}
REM  Doubao   doubao-seed-...   https://ark.cn-beijing.volces.com/api/v3          {"thinking":{"type":"disabled"}}
REM  Kimi     kimi-k3           https://api.moonshot.cn/v1  (forces temperature=1, not recommended)
REM
REM  For local LM Studio use agent_web.bat instead.

cd /d "%~dp0..\.."
"C:\Users\AS\AppData\Local\Programs\Python\Python314\python.exe" py\E_Agent\agent_web.py
REM If the Python path differs on the laptop, edit the line above, or use: py -3.14 py\E_Agent\agent_web.py
pause
