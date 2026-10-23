@echo off
chcp 65001 >nul
title 照护管理平台 · 停止
cd /d "%~dp0"

echo.
echo 正在停止照护管理平台...

set FOUND=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":5810" ^| findstr "LISTENING"') do (
  echo   结束进程 PID %%p
  taskkill /F /PID %%p >nul 2>&1
  set FOUND=1
)

if "%FOUND%"=="0" (
  echo   端口 5800 上没有运行中的服务。
) else (
  echo.
  echo 已停止。数据库文件 data\careplat.db 没有被动过。
)

echo.
timeout /t 3 /nobreak >nul
exit /b 0
