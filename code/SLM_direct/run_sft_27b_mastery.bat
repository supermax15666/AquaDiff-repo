@echo off
rem ============================================================
rem 27B SFT 642 mastery evaluation - RESUME launcher (user-run)
rem Usage: double-click, or run in PyCharm terminal:
rem   run_sft_27b_mastery.bat
rem The pipeline is resumable: completed samples are stored in
rem py/results/SLM_direct/protocol_v2_2/lm_studio__qwen3_6_27b_sft_q4km__qwen3.6-27b-lora-r64
rem (40/1926 samples already done; resume continues from there).
rem ============================================================
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python run_benchmark.py --config config.json --model-key qwen3_6_27b_sft_q4km --mode formal --resume-only --experiment-name qwen3_6_27b_sft_642_mastery
pause
