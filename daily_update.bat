@echo off
REM 每日自動更新（給 Windows 工作排程器執行，也可以直接雙擊）
cd /d "%~dp0"
C:\miniconda3\envs\basketball\python.exe daily_update.py
