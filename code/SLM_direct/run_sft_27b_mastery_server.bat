@echo off
rem ============================================================
rem 27B SFT 642 mastery evaluation - SERVER-SIDE launcher (plan B)
rem Run this ON THE SERVER (192.168.2.100) against its own
rem localhost:1234 LM Studio API. No LMlink / LAN needed.
rem Prereq: pip install openpyxl
rem ============================================================
chcp 65001 >nul
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
cd /d "%~dp0"
python run_benchmark.py --config config.json --model-key qwen3_6_27b_sft_q4km --mode formal --resume-only --experiment-name qwen3_6_27b_sft_642_mastery
pause
