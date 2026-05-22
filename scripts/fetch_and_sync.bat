@echo off
REM 本地拉股票数据 + 同步到云服务器
REM 双击运行即可

cd /d %~dp0..

REM 优先使用 backend/venv，没有则用全局 python
if exist backend\venv\Scripts\python.exe (
    set PYEXE=backend\venv\Scripts\python.exe
) else (
    set PYEXE=python
)

echo 使用 Python: %PYEXE%
%PYEXE% scripts\fetch_and_sync.py

echo.
echo 按任意键退出...
pause >nul
