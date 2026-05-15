@echo off
REM ============================================================
REM setup_system_tools.bat — 系统工具检测引导(v0.7)
REM 转调用 setup_system_tools.ps1(主逻辑),Batch 版仅为双击友好
REM ============================================================
PowerShell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup_system_tools.ps1"
pause
