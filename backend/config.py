"""全局配置管理"""
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """应用配置"""
    APP_NAME: str = "股票选股策略系统"

    # 路径配置
    BASE_DIR: Path = Path(__file__).parent
    DB_PATH: Path = Path(__file__).parent / "data" / "stock_v2.db"
    CACHE_DIR: Path = Path(__file__).parent / "data" / "cache"

    # 定时任务配置
    DAILY_RUN_HOUR: int = 21
    DAILY_RUN_MINUTE: int = 30
    TIMEZONE: str = "Asia/Shanghai"

    # 策略1: 杯柄形态参数
    CUP_MIN_DAYS: int = 15          # 杯底最短形成时间（放宽到3周）
    CUP_MAX_DAYS: int = 150         # 杯底最长形成时间（放宽到7个月）
    CUP_MIN_DEPTH: float = 0.10     # 杯底最小深度（放宽到10%）
    HANDLE_MAX_DAYS: int = 25       # 柄部最长持续时间（5周）
    HANDLE_MIN_DAYS: int = 3        # 柄部最短持续时间（放宽到3天）
    HANDLE_RETRACE_MAX: float = 0.50  # 柄部回撤不超过杯身的1/2（放宽）
    VOLUME_RATIO_THRESHOLD: float = 1.3  # 突破量比阈值（放宽）

    # 策略2: 均线回踩参数
    MA_PERIODS: list = [5, 10, 20, 60]
    MA_PULLBACK_TOLERANCE: float = 0.03  # 回踩均线的容差（放宽到±3%）
    MA_ALIGNMENT_DAYS: int = 3      # 多头排列至少持续天数（放宽到3天）
    VOLUME_SHRINK_RATIO: float = 0.85  # 缩量标准（放宽到85%）

    # 策略3: 底部放量参数
    BOTTOM_DECLINE_MONTHS: int = 2   # 前期下跌至少2个月（放宽）
    BOTTOM_DECLINE_RATIO: float = 0.20  # 前期跌幅至少20%（放宽）
    BREAKOUT_VOLUME_RATIO: float = 1.8  # 突破日成交量倍数（放宽）
    PULLBACK_DAYS_MIN: int = 2       # 回调最少天数（放宽）
    PULLBACK_DAYS_MAX: int = 12      # 回调最多天数（放宽）
    STABILIZE_AMPLITUDE: float = 0.06  # 企稳日振幅小于6%（放宽）

    # 策略4: 高股息参数
    DIVIDEND_YIELD_MIN: float = 0.03  # 最低股息率3%（放宽）
    PE_PERCENTILE_MAX: float = 0.50   # PE分位数低于50%（放宽）
    DEBT_RATIO_MAX: float = 0.65      # 最高资产负债率65%（放宽）
    PROFIT_GROWTH_MIN: float = -0.05  # 允许小幅下滑

    # 板块轮动参数
    SECTOR_MOMENTUM_DAYS: int = 20    # 动量计算周期
    SECTOR_SHORT_DAYS: int = 5        # 短期动量周期
    SECTOR_TOP_N: int = 5             # 机会板块取前N个
    SECTOR_BOTTOM_N: int = 5          # 风险板块取后N个

    # 选股通用参数
    TOP_PICKS: int = 3                # 每个策略推荐股票数
    MIN_MARKET_CAP: float = 5e8       # 最低市值5亿
    MIN_TURNOVER: float = 0.5         # 最低换手率0.5%

    # 数据同步参数
    SYNC_ON_STARTUP: bool = True      # 启动时是否自动同步数据
    KLINE_DAYS: int = 250             # 全量同步K线天数

    # 股票池过滤关键词（名称包含这些关键词的股票将被排除）
    STOCK_POOL_EXCLUDE: list = ["ST", "*ST", "退市", "退"]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()
