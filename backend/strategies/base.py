"""策略抽象基类"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import date
from typing import Optional


@dataclass
class TradeSignal:
    """交易信号数据类"""
    stock_code: str              # 股票代码
    stock_name: str              # 股票名称
    signal_type: str = "BUY"     # 信号类型 BUY/SELL/HOLD
    confidence_score: float = 0.0  # 置信度 0-1
    current_price: float = 0.0   # 当前价格
    buy_price: float = 0.0       # 建议买入价
    stop_loss_price: float = 0.0  # 止损价
    take_profit_price: float = 0.0  # 止盈目标价
    buy_reason: str = ""         # 买入理由
    sell_condition: str = ""     # 卖出条件
    extra_data: dict = field(default_factory=dict)  # 额外数据


class BaseStrategy(ABC):
    """选股策略抽象基类"""

    def __init__(self, data_service):
        self.data_service = data_service

    @property
    @abstractmethod
    def strategy_id(self) -> int:
        """策略唯一ID（1-4）"""
        ...

    @property
    @abstractmethod
    def strategy_name(self) -> str:
        """策略名称"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """策略描述"""
        ...

    @abstractmethod
    def scan(self, stock_pool: list[str], scan_date: date) -> list[TradeSignal]:
        """
        扫描整个股票池，返回所有符合条件的信号
        按confidence_score降序排列
        """
        ...

    def get_top_picks(self, stock_pool: list[str], scan_date: date, top_n: int = 3) -> list[TradeSignal]:
        """返回置信度最高的N只推荐股票"""
        signals = self.scan(stock_pool, scan_date)
        return signals[:top_n]
