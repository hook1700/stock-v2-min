"""SQLAlchemy ORM模型定义"""
from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Float, Date, DateTime,
    Text, Boolean, JSON, ForeignKey, Index, UniqueConstraint
)
from backend.database import Base


class StockPool(Base):
    """股票池表 - 存储全部可用A股，由定时脚本维护"""
    __tablename__ = "stock_pool"

    id = Column(Integer, primary_key=True, autoincrement=True)
    stock_code = Column(String(10), nullable=False, index=True)     # 股票代码(纯数字)
    stock_name = Column(String(20), nullable=False, default="")     # 股票名称
    industry = Column(String(30), default="")                       # 所属行业
    updated_at = Column(Date, nullable=False)                       # 最后更新日期

    __table_args__ = (
        UniqueConstraint("stock_code", name="uq_stock_code"),
    )


class StockDailyData(Base):
    """股票日行情数据表 - 由同步脚本写入，策略从此表读取K线"""
    __tablename__ = "stock_daily_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trade_date = Column(Date, nullable=False, index=True)           # 交易日期
    stock_code = Column(String(10), nullable=False, index=True)     # 股票代码
    stock_name = Column(String(20), nullable=False, default="")     # 股票名称
    open = Column(Float)                                            # 开盘价
    close = Column(Float)                                           # 收盘价
    high = Column(Float)                                            # 最高价
    low = Column(Float)                                             # 最低价
    volume = Column(Float)                                          # 成交量
    amount = Column(Float)                                          # 成交额
    change_pct = Column(Float)                                      # 涨跌幅(%)
    turnover = Column(Float)                                        # 换手率(%)
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        UniqueConstraint("trade_date", "stock_code", name="uq_date_code"),
        Index("idx_trade_date", "trade_date"),
        Index("idx_stock_code_date", "stock_code", "trade_date"),
    )


class StockRecommendation(Base):
    """策略推荐结果表 - 每行代表某策略某天推荐的一只股票"""
    __tablename__ = "stock_recommendations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, nullable=False, index=True)      # 策略ID（1-4）
    strategy_name = Column(String(50), nullable=False)             # 策略名称
    scan_date = Column(Date, nullable=False, index=True)           # 推荐日期
    stock_code = Column(String(10), nullable=False)                # 股票代码
    stock_name = Column(String(20), nullable=False)                # 股票名称
    signal_type = Column(String(10), default="BUY")                # BUY/SELL/HOLD
    confidence_score = Column(Float, default=0.0)                  # 置信度 0-1
    current_price = Column(Float)                                  # 当前价格
    buy_price = Column(Float)                                      # 建议买入价
    stop_loss_price = Column(Float)                                # 止损价
    take_profit_price = Column(Float)                              # 止盈目标价
    buy_reason = Column(Text)                                      # 买入理由
    sell_condition = Column(Text)                                   # 卖出条件描述
    extra_data = Column(JSON)                                      # 额外数据
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_strategy_date", "strategy_id", "scan_date"),
    )


class SectorAnalysis(Base):
    """板块轮动分析结果表"""
    __tablename__ = "sector_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    scan_date = Column(Date, nullable=False, index=True)
    sector_code = Column(String(20), nullable=False)               # 板块代码
    sector_name = Column(String(30), nullable=False)               # 板块名称
    signal = Column(String(15), nullable=False)                    # OPPORTUNITY/RISK/NEUTRAL
    score = Column(Float, nullable=False)                          # 综合评分 -1.0 ~ 1.0
    momentum_20d = Column(Float)                                   # 20日涨跌幅
    momentum_5d = Column(Float)                                    # 5日涨跌幅
    volume_trend = Column(String(15))                              # expanding/contracting
    relative_strength = Column(Float)                              # 相对强度
    pe_percentile = Column(Float)                                  # PE百分位
    ma_signal = Column(String(15), default="HOLD")                 # BUY_STRONG/BUY/WARN/SELL/HOLD
    reasoning = Column(Text)                                       # 分析理由
    created_at = Column(DateTime, default=datetime.now)

    __table_args__ = (
        Index("idx_sector_date", "scan_date", "sector_code"),
    )


class SectorStockPick(Base):
    """板块内推荐股票表"""
    __tablename__ = "sector_stock_picks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    sector_analysis_id = Column(Integer, ForeignKey("sector_analysis.id"))
    scan_date = Column(Date, nullable=False, index=True)
    sector_code = Column(String(20), nullable=False)
    sector_name = Column(String(30), nullable=False)
    stock_code = Column(String(10), nullable=False)
    stock_name = Column(String(20), nullable=False)
    signal_type = Column(String(20), default="SECTOR_BUY")         # BOTH/VOLUME_BREAKOUT/SECTOR_BUY
    buy_price = Column(Float)                                      # 建议买入价
    stop_loss_price = Column(Float)                                # 止损价
    take_profit_price = Column(Float)                              # 止盈目标价
    reasoning = Column(Text)                                       # 推荐理由
    created_at = Column(DateTime, default=datetime.now)


class SchedulerLog(Base):
    """定时任务执行日志表"""
    __tablename__ = "scheduler_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_date = Column(Date, nullable=False)
    run_time = Column(DateTime, nullable=False)
    status = Column(String(10), nullable=False)                    # SUCCESS/FAILED/PARTIAL
    strategies_completed = Column(Integer, default=0)
    sector_completed = Column(Boolean, default=False)
    error_message = Column(Text)
    duration_seconds = Column(Float)
    created_at = Column(DateTime, default=datetime.now)
