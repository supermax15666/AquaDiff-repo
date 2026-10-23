@echo off
rem ============================================================
rem Generic SFT 642 mastery evaluation launcher (user-run)
rem Usage:
rem   run_sft_mastery.bat <model_key> <experiment_name>
rem Examples:
rem   run_sft_mastery.bat qwen3_4b_instruct_2507_sft_q4km qwen3_4b_sft_642_mastery
rem   run_sft_mastery.bat qwen3_8b_instruct_sft_q4km     qwen3_8b_sft_642_mastery
rem   run_sft_mastery.bat llama3_1_8b_instruct_sft_q4km  llama3_1_8b_sft_642_mastery
rem   run_sft_mastery.bat gemma2_9b_it_sft_q4km          gemma2_9b_it_sft_642_mastery
rem Resume after interruption: same command, but replace --new-run with --resume-only.
rem ============================================================
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python run_benchmark.py --config config.json --model-key %1 --mode formal --new-run --experiment-name %2
pause
