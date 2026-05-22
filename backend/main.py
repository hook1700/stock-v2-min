"""FastAPI应用入口"""
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.database import init_db
from backend.scheduler import start_scheduler, shutdown_scheduler
from backend.api.router import api_router

# 日志配置
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    logger.info("正在启动股票选股策略系统...")
    init_db()
    start_scheduler()
    logger.info("系统启动完成")
    yield
    logger.info("正在关闭系统...")
    shutdown_scheduler()
    logger.info("系统已关闭")


app = FastAPI(
    title="股票选股策略系统",
    description="基于多种技术分析和基本面策略的A股选股系统",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS配置 - 允许前端开发服务器访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册API路由
app.include_router(api_router, prefix="/api")


@app.get("/")
async def root():
    return {"message": "股票选股策略系统 API", "docs": "/docs"}
