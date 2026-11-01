@echo off
chcp 65001 >nul
title 照护管理平台 · 公网访问
cd /d "%~dp0"

set "VENV="
if exist "%~dp0py_path.txt" for /f "usebackq delims=" %%i in ("%~dp0py_path.txt") do set "VENV=%%i"
if not defined VENV set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts"
set PY=%VENV%\python.exe

echo.
echo ============================================================
echo   照护管理平台 · 公网访问
echo   （电脑要开着，这个窗口不能关；关掉就断公网）
echo ============================================================

if not exist "%PY%" (
  echo [x] 找不到 Python：%PY%
  echo     请先运行「安装.bat」，或用打包版 exe。
  pause
  exit /b 1
)

"%PY%" tunnel.py

echo.
echo 公网访问已停止。本地局域网访问仍然可用。
pause
