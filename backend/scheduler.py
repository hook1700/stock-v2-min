"""定时任务调度器"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from backend.config import settings

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler(timezone=settings.TIMEZONE)


def start_scheduler():
    """启动定时调度器"""
    scheduler.add_job(
        run_daily_analysis,
        trigger=CronTrigger(
            day_of_week="mon-fri",
            hour=settings.DAILY_RUN_HOUR,
            minute=settings.DAILY_RUN_MINUTE,
            timezone=settings.TIMEZONE
        ),
        id="daily_stock_scan",
        name="每日选股策略扫描",
        replace_existing=True,
    )
    scheduler.start()
    logger.info(
        f"定时任务已启动：每个交易日 {settings.DAILY_RUN_HOUR}:{settings.DAILY_RUN_MINUTE:02d} 执行"
    )


def shutdown_scheduler():
    """关闭调度器"""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("定时任务已关闭")


async def run_daily_analysis():
    """每日定时执行的分析任务：先同步数据，再跑策略"""
    from backend.services.data_sync_service import DataSyncService
    from backend.services.strategy_runner import StrategyRunner

    # Step 1: 增量同步今日数据
    logger.info("开始增量同步今日行情数据...")
    try:
        sync_service = DataSyncService()
        sync_service.sync_incremental()
    except Exception as e:
        logger.error(f"数据同步失败: {e}", exc_info=True)
        # 数据同步失败不阻止策略运行（可能用已有数据）

    # Step 2: 执行选股策略
    logger.info("开始执行每日选股分析...")
    runner = StrategyRunner()
    result = await runner.run_all()
    logger.info(
        f"每日分析完成: 策略完成{result['strategies_completed']}个, "
        f"板块分析{'成功' if result['sector_completed'] else '失败'}, "
        f"耗时{result['duration']:.1f}秒"
    )
