@echo off
rem ============================================================
rem Generic EXTERNAL prospective set evaluation launcher (user-run)
rem Usage:
rem   run_external.bat <model_key> <experiment_name>
rem Examples (5 Base + 5 SFT，共 10 次运行):
rem   run_external.bat qwen3_4b_instruct_2507_base_q4km qwen3_4b_base_external
rem   run_external.bat qwen3_4b_instruct_2507_sft_q4km  qwen3_4b_sft_external
rem   run_external.bat qwen3_8b_instruct_base_q4km      qwen3_8b_base_external
rem   run_external.bat qwen3_8b_instruct_sft_q4km       qwen3_8b_sft_external
rem   run_external.bat qwen3_6_27b_base_q4km            qwen3_27b_base_external
rem   run_external.bat qwen3_6_27b_sft_q4km             qwen3_27b_sft_external
rem   run_external.bat llama3_1_8b_instruct_base_q4km   llama3_1_8b_base_external
rem   run_external.bat llama3_1_8b_instruct_sft_q4km    llama3_1_8b_sft_external
rem   run_external.bat gemma2_9b_it_base_q4km           gemma2_9b_base_external
rem   run_external.bat gemma2_9b_it_sft_q4km            gemma2_9b_sft_external
rem Resume after interruption: same command, replace --new-run with --resume-only.
rem NOTE 27B: before each 27B run, confirm LM Studio deployment-level
rem Reasoning=Off is active for the loaded model (see SFT部署身份记录.md).
rem ============================================================
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python run_benchmark.py --config config_external.json --model-key %1 --mode formal --new-run --experiment-name %2
pause
