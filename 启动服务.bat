@echo off
chcp 65001 >nul
title 照护管理平台 · 启动
cd /d "%~dp0"

set "VENV="
if exist "%~dp0py_path.txt" for /f "usebackq delims=" %%i in ("%~dp0py_path.txt") do set "VENV=%%i"
if not defined VENV set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts"
set PY=%VENV%\python.exe
set PYW=%VENV%\pythonw.exe

echo.
echo ============================================================
echo   照护管理平台
echo ============================================================
echo.

if not exist "%PY%" (
  echo [×] 找不到 Python 环境，请先双击运行「安装.bat」。
  echo.
  pause
  exit /b 1
)

rem 首次运行：自动在桌面放一个快捷方式
if not exist "%USERPROFILE%\Desktop\照护管理平台.lnk" (
  if exist "%~dp0创建桌面快捷方式.vbs" (
    wscript "%~dp0创建桌面快捷方式.vbs"
  )
)

netstat -ano | findstr ":5810" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 (
  echo [√] 服务已经在运行
  goto :open
)

echo [1/2] 正在后台启动服务...
start "careplat" /min /D "%~dp0" "%PYW%" "%~dp0app.py"

echo [2/2] 等待服务就绪...
set /a n=0
:wait
timeout /t 1 /nobreak >nul
netstat -ano | findstr ":5810" | findstr "LISTENING" >nul 2>&1
if %errorlevel%==0 goto :ready
set /a n+=1
if %n% lss 25 goto :wait

echo.
echo [×] 启动超时。请查看 data\server.log 里的错误信息。
echo     常见原因：Python 环境不对，或 5800 端口被其他程序占用。
echo.
pause
exit /b 1

:ready
echo [√] 启动成功
echo.
type "%~dp0data\访问地址.txt" 2>nul
echo.

:open
start "" http://127.0.0.1:5810
timeout /t 2 /nobreak >nul
exit /b 0
