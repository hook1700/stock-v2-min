"""API路由聚合"""
from fastapi import APIRouter
from backend.api.strategies import router as strategies_router
from backend.api.sectors import router as sectors_router
from backend.api.stocks import router as stocks_router
from backend.api.system import router as system_router

api_router = APIRouter()

api_router.include_router(strategies_router, prefix="/strategies", tags=["策略"])
api_router.include_router(sectors_router, prefix="/sectors", tags=["板块轮动"])
api_router.include_router(stocks_router, prefix="/stocks", tags=["股票数据"])
api_router.include_router(system_router, prefix="/system", tags=["系统"])
