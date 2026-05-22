@echo off
chcp 65001 >nul
title 股票选股策略系统

echo ========================================
echo   股票选股策略系统 - 一键启动
echo ========================================
echo.

:: 检查Python环境
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Python环境，请先安装Python 3.10+
    pause
    exit /b 1
)

:: 检查Node.js环境
node --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到Node.js环境，请先安装Node.js 18+
    pause
    exit /b 1
)

:: 安装后端依赖（首次运行）
if not exist "backend\venv" (
    echo [后端] 创建虚拟环境...
    cd backend
    python -m venv venv
    call venv\Scripts\activate.bat
    pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
    cd ..
    echo [后端] 依赖安装完成
) else (
    echo [后端] 虚拟环境已存在
)

:: 安装前端依赖（首次运行）
if not exist "frontend\node_modules" (
    echo [前端] 安装依赖...
    cd frontend
    npm install
    cd ..
    echo [前端] 依赖安装完成
)

echo.
echo [启动] 正在启动后端服务 (端口: 8000)...
cd backend
start "StockStrategy-Backend" cmd /c "call venv\Scripts\activate.bat && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"
cd ..

:: 等待后端启动
timeout /t 3 /nobreak >nul

echo [启动] 正在启动前端服务 (端口: 5173)...
cd frontend
start "StockStrategy-Frontend" cmd /c "npm run dev"
cd ..

echo.
echo ========================================
echo   系统启动完成！
echo ========================================
echo.
echo   后端API:   http://localhost:8000
echo   API文档:   http://localhost:8000/docs
echo   前端界面:  http://localhost:5173
echo.
echo   定时任务:  每个交易日 15:30 自动执行
echo.
echo   按任意键关闭此窗口（服务将继续运行）
echo ========================================
pause
