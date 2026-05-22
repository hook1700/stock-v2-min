"""推荐结果持久化服务"""
import logging
from datetime import date, datetime
from typing import Optional

from sqlalchemy.orm import Session

from backend.database import SessionLocal
from backend.models import (
    StockRecommendation, SectorAnalysis,
    SectorStockPick, SchedulerLog
)
from backend.strategies.base import TradeSignal

logger = logging.getLogger(__name__)


class RecommendationService:
    """推荐结果的存储和查询"""

    def save_recommendations(self, strategy_id: int, strategy_name: str,
                             scan_date: date, signals: list[TradeSignal]):
        """保存策略推荐结果"""
        db = SessionLocal()
        try:
            # 删除同一天同一策略的旧推荐（覆盖）
            db.query(StockRecommendation).filter(
                StockRecommendation.strategy_id == strategy_id,
                StockRecommendation.scan_date == scan_date,
            ).delete()

            for signal in signals:
                rec = StockRecommendation(
                    strategy_id=strategy_id,
                    strategy_name=strategy_name,
                    scan_date=scan_date,
                    stock_code=signal.stock_code,
                    stock_name=signal.stock_name,
                    signal_type=signal.signal_type,
                    confidence_score=signal.confidence_score,
                    current_price=signal.current_price,
                    buy_price=signal.buy_price,
                    stop_loss_price=signal.stop_loss_price,
                    take_profit_price=signal.take_profit_price,
                    buy_reason=signal.buy_reason,
                    sell_condition=signal.sell_condition,
                    extra_data=signal.extra_data,
                )
                db.add(rec)

            db.commit()
            logger.info(f"保存策略{strategy_id}推荐{len(signals)}条")
        except Exception as e:
            db.rollback()
            logger.error(f"保存推荐失败: {e}")
            raise
        finally:
            db.close()

    def save_sector_analysis(self, scan_date: date, signals: list):
        """保存板块轮动分析结果"""
        db = SessionLocal()
        try:
            # 删除同一天的旧数据
            db.query(SectorStockPick).filter(
                SectorStockPick.scan_date == scan_date
            ).delete()
            db.query(SectorAnalysis).filter(
                SectorAnalysis.scan_date == scan_date
            ).delete()

            for signal in signals:
                sector_record = SectorAnalysis(
                    scan_date=scan_date,
                    sector_code=signal.sector_code,
                    sector_name=signal.sector_name,
                    signal=signal.signal,
                    score=signal.score,
                    momentum_20d=signal.momentum_20d,
                    momentum_5d=signal.momentum_5d,
                    volume_trend=signal.volume_trend,
                    relative_strength=signal.relative_strength,
                    pe_percentile=signal.pe_percentile,
                    reasoning=signal.reasoning,
                )
                db.add(sector_record)
                db.flush()  # 获取ID

                # 保存推荐股票
                for stock in signal.recommended_stocks:
                    pick = SectorStockPick(
                        sector_analysis_id=sector_record.id,
                        scan_date=scan_date,
                        sector_code=signal.sector_code,
                        sector_name=signal.sector_name,
                        stock_code=stock.stock_code,
                        stock_name=stock.stock_name,
                        buy_price=stock.buy_price,
                        stop_loss_price=stock.stop_loss_price,
                        take_profit_price=stock.take_profit_price,
                        reasoning=stock.buy_reason,
                    )
                    db.add(pick)

            db.commit()
            logger.info(f"保存板块分析{len(signals)}条")
        except Exception as e:
            db.rollback()
            logger.error(f"保存板块分析失败: {e}")
            raise
        finally:
            db.close()

    def save_scheduler_log(self, run_date: date, status: str,
                           strategies_completed: int, sector_completed: bool,
                           error_message: Optional[str], duration_seconds: float):
        """保存调度器执行日志"""
        db = SessionLocal()
        try:
            log = SchedulerLog(
                run_date=run_date,
                run_time=datetime.now(),
                status=status,
                strategies_completed=strategies_completed,
                sector_completed=sector_completed,
                error_message=error_message,
                duration_seconds=duration_seconds,
            )
            db.add(log)
            db.commit()
        except Exception as e:
            db.rollback()
            logger.error(f"保存日志失败: {e}")
        finally:
            db.close()

    def get_latest_recommendations(self, strategy_id: Optional[int] = None) -> list:
        """获取最新推荐"""
        db = SessionLocal()
        try:
            query = db.query(StockRecommendation).order_by(
                StockRecommendation.scan_date.desc(),
                StockRecommendation.confidence_score.desc()
            )

            if strategy_id is not None:
                query = query.filter(StockRecommendation.strategy_id == strategy_id)

            # 获取最新日期的数据
            latest = query.first()
            if latest is None:
                return []

            results = query.filter(
                StockRecommendation.scan_date == latest.scan_date
            ).all()

            return results
        finally:
            db.close()

    def get_recommendations_by_date(self, scan_date: date,
                                    strategy_id: Optional[int] = None) -> list:
        """获取指定日期的推荐"""
        db = SessionLocal()
        try:
            query = db.query(StockRecommendation).filter(
                StockRecommendation.scan_date == scan_date
            )
            if strategy_id is not None:
                query = query.filter(StockRecommendation.strategy_id == strategy_id)

            return query.order_by(StockRecommendation.confidence_score.desc()).all()
        finally:
            db.close()

    def get_recommendation_history(self, strategy_id: Optional[int] = None,
                                   page: int = 1, page_size: int = 20) -> dict:
        """获取历史推荐（分页）"""
        db = SessionLocal()
        try:
            query = db.query(StockRecommendation)
            if strategy_id is not None:
                query = query.filter(StockRecommendation.strategy_id == strategy_id)

            total = query.count()
            results = query.order_by(
                StockRecommendation.scan_date.desc(),
                StockRecommendation.strategy_id,
                StockRecommendation.confidence_score.desc()
            ).offset((page - 1) * page_size).limit(page_size).all()

            return {
                "total": total,
                "page": page,
                "page_size": page_size,
                "items": results,
            }
        finally:
            db.close()

    def get_latest_sector_analysis(self) -> dict:
        """获取最新板块轮动分析"""
        db = SessionLocal()
        try:
            latest = db.query(SectorAnalysis).order_by(
                SectorAnalysis.scan_date.desc()
            ).first()

            if latest is None:
                return {"scan_date": None, "sectors": [], "picks": []}

            sectors = db.query(SectorAnalysis).filter(
                SectorAnalysis.scan_date == latest.scan_date
            ).order_by(SectorAnalysis.score.desc()).all()

            picks = db.query(SectorStockPick).filter(
                SectorStockPick.scan_date == latest.scan_date
            ).all()

            return {
                "scan_date": latest.scan_date,
                "sectors": sectors,
                "picks": picks,
            }
        finally:
            db.close()

    def get_latest_scheduler_log(self) -> Optional[SchedulerLog]:
        """获取最近一次执行日志"""
        db = SessionLocal()
        try:
            return db.query(SchedulerLog).order_by(
                SchedulerLog.run_time.desc()
            ).first()
        finally:
            db.close()
