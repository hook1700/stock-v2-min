"""Pydantic响应模型（API Schemas）"""
from datetime import date, datetime
from typing import Optional
from pydantic import BaseModel


class StockRecommendationSchema(BaseModel):
    """单只股票推荐信息"""
    stock_code: str
    stock_name: str
    signal_type: str = "BUY"
    confidence_score: float = 0.0
    current_price: Optional[float] = None
    buy_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    buy_reason: Optional[str] = None
    sell_condition: Optional[str] = None
    extra_data: dict = {}

    class Config:
        from_attributes = True


class StrategyOverview(BaseModel):
    """策略概览"""
    strategy_id: int
    strategy_name: str
    description: str
    last_run_date: Optional[date] = None
    last_run_status: str = "NEVER_RUN"
    recommendations: list[StockRecommendationSchema] = []


class SectorStockPickSchema(BaseModel):
    """板块推荐股票"""
    stock_code: str
    stock_name: str
    signal_type: str = "SECTOR_BUY"   # BOTH/VOLUME_BREAKOUT/SECTOR_BUY
    buy_price: Optional[float] = None
    stop_loss_price: Optional[float] = None
    take_profit_price: Optional[float] = None
    reasoning: Optional[str] = None

    class Config:
        from_attributes = True


class SectorAnalysisSchema(BaseModel):
    """板块分析结果"""
    sector_code: str
    sector_name: str
    signal: str
    score: float
    momentum_20d: Optional[float] = None
    momentum_5d: Optional[float] = None
    volume_trend: Optional[str] = None
    relative_strength: Optional[float] = None
    pe_percentile: Optional[float] = None
    ma_signal: str = "HOLD"           # BUY_STRONG/BUY/WARN/SELL/HOLD
    reasoning: Optional[str] = None
    recommended_stocks: list[SectorStockPickSchema] = []

    class Config:
        from_attributes = True


class SectorRotationResponse(BaseModel):
    """板块轮动整体响应"""
    scan_date: Optional[date] = None
    opportunity_sectors: list[SectorAnalysisSchema] = []
    risk_sectors: list[SectorAnalysisSchema] = []
    neutral_sectors: list[SectorAnalysisSchema] = []


class SystemStatus(BaseModel):
    """系统运行状态"""
    scheduler_running: bool = False
    last_run_time: Optional[datetime] = None
    last_run_status: str = "NEVER_RUN"
    next_run_time: Optional[datetime] = None
    total_recommendations_today: int = 0


class KLineDataResponse(BaseModel):
    """K线数据响应"""
    stock_code: str
    stock_name: str = ""
    data: list = []           # [[date, open, close, low, high, volume], ...]
    ma_data: dict = {}        # {"ma5": [...], "ma10": [...], ...}


class RunResult(BaseModel):
    """策略执行结果"""
    success: bool
    message: str
    strategies_completed: int = 0
    sector_completed: bool = False
    duration_seconds: float = 0.0
