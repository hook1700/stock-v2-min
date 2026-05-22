"""策略运行器 - 编排所有策略和板块分析的执行"""
import logging
import time
from datetime import date, datetime

from backend.services.data_service import DataService
from backend.services.recommendation_service import RecommendationService
from backend.strategies.cup_and_handle import CupAndHandleStrategy
from backend.strategies.ma_pullback import MAPullbackStrategy
from backend.strategies.volume_breakout import VolumeBreakoutStrategy
from backend.strategies.dividend_rotation import DividendRotationStrategy
from backend.analysis.sector_rotation import SectorRotationAnalyzer

logger = logging.getLogger(__name__)


class StrategyRunner:
    """策略执行调度器"""

    def __init__(self):
        self.data_service = DataService()
        self.rec_service = RecommendationService()
        self.strategies = [
            CupAndHandleStrategy(self.data_service),
            MAPullbackStrategy(self.data_service),
            VolumeBreakoutStrategy(self.data_service),
            DividendRotationStrategy(self.data_service),
        ]

    async def run_all(self) -> dict:
        """执行全部策略和板块分析"""
        start_time = time.time()
        today = date.today()

        # 检查是否交易日
        if not self.data_service.is_trading_day(today):
            logger.info(f"{today} 非交易日，跳过执行")
            return {
                "success": True,
                "message": "非交易日，跳过执行",
                "strategies_completed": 0,
                "sector_completed": False,
                "duration": 0,
            }

        strategies_completed = 0
        sector_completed = False
        errors = []

        # 执行4个策略
        logger.info("开始执行选股策略...")
        stock_pool = self.data_service.get_stock_pool()
        if not stock_pool:
            error_msg = "获取股票池失败（返回为空），中止本次执行"
            logger.error(error_msg)
            duration = time.time() - start_time
            self.rec_service.save_scheduler_log(
                run_date=today,
                status="FAILED",
                strategies_completed=0,
                sector_completed=False,
                error_message=error_msg,
                duration_seconds=duration,
            )
            return {
                "success": False,
                "message": error_msg,
                "strategies_completed": 0,
                "sector_completed": False,
                "duration": duration,
            }
        logger.info(f"股票池大小: {len(stock_pool)}")

        for strategy in self.strategies:
            try:
                logger.info(f"执行策略: {strategy.strategy_name}")
                picks = strategy.get_top_picks(stock_pool, today, top_n=3)

                if picks:
                    self.rec_service.save_recommendations(
                        strategy_id=strategy.strategy_id,
                        strategy_name=strategy.strategy_name,
                        scan_date=today,
                        signals=picks,
                    )
                    logger.info(
                        f"  策略 [{strategy.strategy_name}] 推荐{len(picks)}只: "
                        f"{', '.join(s.stock_name for s in picks)}"
                    )
                else:
                    logger.info(f"  策略 [{strategy.strategy_name}] 未发现符合条件的股票")

                strategies_completed += 1
            except Exception as e:
                error_msg = f"策略 [{strategy.strategy_name}] 执行失败: {e}"
                logger.error(error_msg)
                errors.append(error_msg)

        # 执行板块轮动分析
        try:
            logger.info("开始执行板块轮动分析...")
            analyzer = SectorRotationAnalyzer(self.data_service)
            sector_signals = analyzer.analyze(today)

            if sector_signals:
                self.rec_service.save_sector_analysis(today, sector_signals)
                opportunity_count = sum(1 for s in sector_signals if s.signal == "OPPORTUNITY")
                risk_count = sum(1 for s in sector_signals if s.signal == "RISK")
                logger.info(
                    f"  板块分析完成: 机会板块{opportunity_count}个，风险板块{risk_count}个"
                )

            sector_completed = True
        except Exception as e:
            error_msg = f"板块轮动分析失败: {e}"
            logger.error(error_msg)
            errors.append(error_msg)

        duration = time.time() - start_time

        # 记录执行日志
        status = "SUCCESS" if not errors else ("PARTIAL" if strategies_completed > 0 else "FAILED")
        self.rec_service.save_scheduler_log(
            run_date=today,
            status=status,
            strategies_completed=strategies_completed,
            sector_completed=sector_completed,
            error_message="\n".join(errors) if errors else None,
            duration_seconds=duration,
        )

        return {
            "success": not errors or strategies_completed > 0,
            "message": f"执行完成: {strategies_completed}/4策略成功" + (
                f", 错误: {'; '.join(errors)}" if errors else ""
            ),
            "strategies_completed": strategies_completed,
            "sector_completed": sector_completed,
            "duration": duration,
        }

    async def run_single_strategy(self, strategy_id: int) -> dict:
        """执行单个策略"""
        start_time = time.time()
        today = date.today()

        target_strategy = None
        for s in self.strategies:
            if s.strategy_id == strategy_id:
                target_strategy = s
                break

        if target_strategy is None:
            return {"success": False, "message": f"策略ID {strategy_id} 不存在"}

        try:
            stock_pool = self.data_service.get_stock_pool()
            if not stock_pool:
                return {
                    "success": False,
                    "message": "获取股票池失败（返回为空）",
                    "strategies_completed": 0,
                    "sector_completed": False,
                    "duration": time.time() - start_time,
                }
            picks = target_strategy.get_top_picks(stock_pool, today, top_n=3)

            if picks:
                self.rec_service.save_recommendations(
                    strategy_id=target_strategy.strategy_id,
                    strategy_name=target_strategy.strategy_name,
                    scan_date=today,
                    signals=picks,
                )

            duration = time.time() - start_time
            return {
                "success": True,
                "message": f"策略 [{target_strategy.strategy_name}] 推荐{len(picks)}只股票",
                "strategies_completed": 1,
                "sector_completed": False,
                "duration": duration,
            }
        except Exception as e:
            return {
                "success": False,
                "message": f"策略执行失败: {e}",
                "strategies_completed": 0,
                "sector_completed": False,
                "duration": time.time() - start_time,
            }
