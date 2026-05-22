"""系统状态API端点"""
from fastapi import APIRouter

from backend.schemas import SystemStatus, RunResult
from backend.services.recommendation_service import RecommendationService
from backend.services.strategy_runner import StrategyRunner
from backend.scheduler import scheduler

router = APIRouter()
rec_service = RecommendationService()


@router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """获取系统运行状态"""
    latest_log = rec_service.get_latest_scheduler_log()

    # 获取下一次执行时间
    next_run = None
    job = scheduler.get_job("daily_stock_scan")
    if job and job.next_run_time:
        next_run = job.next_run_time

    # 获取今日推荐总数
    from datetime import date
    today_recs = rec_service.get_recommendations_by_date(date.today())
    total_today = len(today_recs)

    return SystemStatus(
        scheduler_running=scheduler.running,
        last_run_time=latest_log.run_time if latest_log else None,
        last_run_status=latest_log.status if latest_log else "NEVER_RUN",
        next_run_time=next_run,
        total_recommendations_today=total_today,
    )


@router.post("/run-all", response_model=RunResult)
async def run_all_strategies():
    """手动触发全部策略执行"""
    runner = StrategyRunner()
    result = await runner.run_all()

    return RunResult(
        success=result["success"],
        message=result["message"],
        strategies_completed=result["strategies_completed"],
        sector_completed=result["sector_completed"],
        duration_seconds=result["duration"],
    )
