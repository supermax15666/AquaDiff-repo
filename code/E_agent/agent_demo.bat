@echo off
chcp 65001 >nul
set PYTHONUTF8=1
cd /d "%~dp0..\.."
"C:\Users\AS\AppData\Local\Programs\Python\Python314\python.exe" py\E_Agent\agent_demo.py
pause
