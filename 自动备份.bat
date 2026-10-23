@echo off
chcp 65001 >nul
title 照护管理平台 · 自动备份
cd /d "%~dp0"

set "VENV="
if exist "%~dp0py_path.txt" for /f "usebackq delims=" %%i in ("%~dp0py_path.txt") do set "VENV=%%i"
if not defined VENV set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts"
set PY=%VENV%\python.exe

if not exist "%PY%" (
  echo [×] 找不到 Python 环境，请先手动安装依赖。
  pause
  exit /b 1
)

rem ====== 备份到哪：默认项目 backups 目录 ======
rem 备到 NAS：映射网络盘后改成 Z:\careplat-backup 这类路径，或写 UNC \\NAS\share
set "DEST=%~dp0backups"
if not "%~1"=="" set "DEST=%~1"

echo.
echo ============================================================
echo   照护管理平台 · 备份（数据库 + 照片视频）
echo   目标：%DEST%
echo ============================================================
echo.

"%PY%" "%~dp0backup.py" "%DEST%" --keep 14
if %errorlevel%==0 (
  echo.
  echo [√] 备份成功，保留最近 14 份
) else (
  echo.
  echo [×] 备份失败，看上面的报错
)
echo.
pause
