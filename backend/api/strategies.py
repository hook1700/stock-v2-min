"""策略相关API端点"""
import asyncio
from datetime import date
from fastapi import APIRouter, HTTPException

from backend.schemas import (
    StrategyOverview, StockRecommendationSchema, RunResult
)
from backend.services.recommendation_service import RecommendationService
from backend.services.strategy_runner import StrategyRunner

router = APIRouter()
rec_service = RecommendationService()

# 策略元信息
STRATEGY_META = {
    1: {
        "name": "杯柄形态突破",
        "description": "捕捉主升浪起涨点，识别U型杯底+窄幅柄部+放量突破形态"
    },
    2: {
        "name": "均线多头排列回踩",
        "description": "顺势低吸策略，在强势股回踩20/60日均线时买入"
    },
    3: {
        "name": "底部放量首板回调",
        "description": "捕捉底部放量涨停后缩量回调企稳的二波行情"
    },
    4: {
        "name": "高股息红利低波",
        "description": "防御型策略，买入高股息、低估值、财务健康的优质股票"
    },
}


@router.get("", response_model=list[StrategyOverview])
async def get_all_strategies():
    """获取所有策略概览及最新推荐"""
    results = []

    for strategy_id, meta in STRATEGY_META.items():
        recs = rec_service.get_latest_recommendations(strategy_id=strategy_id)

        last_date = recs[0].scan_date if recs else None
        status = "SUCCESS" if recs else "NEVER_RUN"

        results.append(StrategyOverview(
            strategy_id=strategy_id,
            strategy_name=meta["name"],
            description=meta["description"],
            last_run_date=last_date,
            last_run_status=status,
            recommendations=[
                StockRecommendationSchema.model_validate(r) for r in recs
            ],
        ))

    return results


@router.get("/{strategy_id}", response_model=StrategyOverview)
async def get_strategy_detail(strategy_id: int):
    """获取单个策略详情"""
    if strategy_id not in STRATEGY_META:
        raise HTTPException(status_code=404, detail="策略不存在")

    meta = STRATEGY_META[strategy_id]
    recs = rec_service.get_latest_recommendations(strategy_id=strategy_id)

    last_date = recs[0].scan_date if recs else None
    status = "SUCCESS" if recs else "NEVER_RUN"

    return StrategyOverview(
        strategy_id=strategy_id,
        strategy_name=meta["name"],
        description=meta["description"],
        last_run_date=last_date,
        last_run_status=status,
        recommendations=[
            StockRecommendationSchema.model_validate(r) for r in recs
        ],
    )


@router.get("/{strategy_id}/history")
async def get_strategy_history(strategy_id: int, page: int = 1, page_size: int = 20):
    """获取策略历史推荐"""
    if strategy_id not in STRATEGY_META:
        raise HTTPException(status_code=404, detail="策略不存在")

    result = rec_service.get_recommendation_history(
        strategy_id=strategy_id, page=page, page_size=page_size
    )

    return {
        "total": result["total"],
        "page": result["page"],
        "page_size": result["page_size"],
        "items": [
            StockRecommendationSchema.model_validate(r) for r in result["items"]
        ],
    }


@router.post("/{strategy_id}/run", response_model=RunResult)
async def run_single_strategy(strategy_id: int):
    """手动触发单个策略"""
    if strategy_id not in STRATEGY_META:
        raise HTTPException(status_code=404, detail="策略不存在")

    runner = StrategyRunner()
    result = await runner.run_single_strategy(strategy_id)

    return RunResult(
        success=result["success"],
        message=result["message"],
        strategies_completed=result["strategies_completed"],
        sector_completed=result["sector_completed"],
        duration_seconds=result["duration"],
    )
