@echo off
chcp 65001 >nul
title 照护管理平台 · 打包 exe
cd /d "%~dp0"

set "VENV="
if exist "%~dp0py_path.txt" for /f "usebackq delims=" %%i in ("%~dp0py_path.txt") do set "VENV=%%i"
if not defined VENV set "VENV=C:\Users\Administrator\.workbuddy\binaries\python\envs\default\Scripts"
set PY=%VENV%\python.exe

echo.
echo ============================================================
echo   照护管理平台 · 打包成 exe（不需要目标电脑装 Python）
echo ============================================================
echo.

"%PY%" -m PyInstaller --version >nul 2>&1
if not %errorlevel%==0 (
  echo [1/3] 首次打包，先安装 PyInstaller……
  "%PY%" -m pip install pyinstaller
)

echo [2/3] 开始打包（1-3 分钟）……
"%PY%" -m PyInstaller careplat.spec --noconfirm --clean
if not %errorlevel%==0 (
  echo.
  echo [×] 打包失败，看上面的报错
  pause
  exit /b 1
)

echo [3/3] 复制启动说明……
echo 照护管理平台双击「照护管理平台.exe」运行 > "dist\照护管理平台\使用说明.txt"
echo 数据默认存在本目录的 data\ 文件夹（数据库+照片），备份就拷它 >> "dist\照护管理平台\使用说明.txt"
echo 备份：双击「自动备份.bat」（把它也拷到这个目录） >> "dist\照护管理平台\使用说明.txt"

echo.
echo [√] 打包完成！产物在 dist\照护管理平台\ 整个文件夹
echo     把整个文件夹拷给任何 Windows 电脑，双击 exe 就能跑，不用装 Python。
echo.
pause
