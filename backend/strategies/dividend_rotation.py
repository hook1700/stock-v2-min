"""策略4: 高股息/红利低波轮动策略（Dividend Rotation）"""
import logging
from datetime import date
from typing import Optional

import pandas as pd

from backend.strategies.base import BaseStrategy, TradeSignal
from backend.config import settings

logger = logging.getLogger(__name__)


class DividendRotationStrategy(BaseStrategy):
    """
    高股息/红利低波轮动策略
    核心逻辑：买入盈利稳定、负债低、愿意分红的优质企业，赚取确定的股息收益。
    选股条件：股息率>4%，PE/PB低估值，财务健康。
    """

    @property
    def strategy_id(self) -> int:
        return 4

    @property
    def strategy_name(self) -> str:
        return "高股息红利低波"

    @property
    def description(self) -> str:
        return "防御型策略，买入高股息、低估值、财务健康的优质股票。适合不想盯盘的投资者。"

    def scan(self, stock_pool: list[str], scan_date: date) -> list[TradeSignal]:
        signals = []
        total = len(stock_pool)

        # 扩大扫描范围：取前800只（覆盖更多大盘蓝筹股）
        candidates = sorted(stock_pool)[:800]

        logger.info(f"[高股息] 候选股{len(candidates)}只")

        for i, code in enumerate(candidates):
            if i % 50 == 0:
                logger.info(f"[高股息] 扫描进度: {i}/{len(candidates)}")

            try:
                signal = self._analyze_stock(code)
                if signal is not None:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"[高股息] {code} 分析异常: {e}")
                continue

        signals.sort(key=lambda s: s.confidence_score, reverse=True)
        logger.info(f"[高股息] 扫描完成，发现{len(signals)}个信号")
        return signals

    def _analyze_stock(self, code: str) -> Optional[TradeSignal]:
        """分析单只股票"""
        fund = self.data_service.get_fundamentals(code)
        if fund is None:
            return None

        # 条件1: 高股息率（>4%）
        dividend_yield = fund.get("dividend_yield", 0)
        if not dividend_yield or dividend_yield < settings.DIVIDEND_YIELD_MIN:
            return None

        # 条件2: 低估值
        pe = fund.get("pe", 0)
        pb = fund.get("pb", 0)

        # PE必须为正且合理（排除亏损股和过高PE）
        if pe <= 0 or pe > 30:
            return None

        # PB不能过高
        if pb <= 0 or pb > 3:
            return None

        # 条件3: 财务健康检查（使用可用的指标）
        # 由于BaoStock接口限制，市值为0时跳过市值过滤（数据不可用不等于不合格）
        market_cap = fund.get("market_cap", 0)
        if market_cap > 0 and market_cap < settings.MIN_MARKET_CAP * 4:  # 高股息股通常大市值
            return None

        # 构建信号
        return self._build_signal(code, fund, dividend_yield, pe, pb)

    def _build_signal(self, code: str, fund: dict, dividend_yield: float,
                      pe: float, pb: float) -> TradeSignal:
        """构建交易信号"""
        stock_name = fund.get("name", code)
        current_price = fund.get("current_price", 0)

        # 买入价 = 当前价格
        buy_price = current_price
        # 止损 = 股息率降至3%时的对应价格（粗略估算）
        # 股息率 = 每股股息 / 股价，若股息率从4%降到3%，则股价上涨了33%
        estimated_dps = current_price * dividend_yield
        stop_loss_price_by_yield = estimated_dps / 0.03 if estimated_dps > 0 else current_price * 1.33
        # 使用技术止损（下跌10%）和估值止损的较低者
        stop_loss = min(current_price * 0.90, stop_loss_price_by_yield)
        # 止盈 = 当PE分位数高于70%时（简化为PE升到行业均值1.5倍）
        take_profit = current_price * 1.30  # 保守30%空间

        confidence = self._calculate_confidence(dividend_yield, pe, pb, fund)

        return TradeSignal(
            stock_code=code,
            stock_name=stock_name,
            signal_type="BUY",
            confidence_score=confidence,
            current_price=current_price,
            buy_price=round(buy_price, 2),
            stop_loss_price=round(stop_loss, 2),
            take_profit_price=round(take_profit, 2),
            buy_reason=(
                f"高股息率{dividend_yield*100:.2f}%，"
                f"PE={pe:.1f}倍（低估值），PB={pb:.2f}倍，"
                f"财务健康适合长期持有"
            ),
            sell_condition=(
                f"卖出条件：股息率降至3%以下，"
                f"或PE分位数高于70%，"
                f"或跌破{stop_loss:.2f}元止损"
            ),
            extra_data={
                "dividend_yield": dividend_yield,
                "pe": pe,
                "pb": pb,
                "market_cap": fund.get("market_cap", 0),
                "pattern": "dividend_rotation",
            }
        )

    def _calculate_confidence(self, dividend_yield: float, pe: float,
                              pb: float, fund: dict) -> float:
        """计算置信度"""
        score = 0.0

        # 股息率越高越好（4%-8%的范围）
        if dividend_yield >= 0.07:
            score += 0.30
        elif dividend_yield >= 0.05:
            score += 0.25
        elif dividend_yield >= 0.04:
            score += 0.15

        # PE越低越好（5-15倍区间最佳）
        if 5 <= pe <= 10:
            score += 0.25
        elif 10 < pe <= 15:
            score += 0.15
        elif pe < 5:
            score += 0.10  # 太低可能有问题

        # PB越低越好（0.5-1.5倍最佳）
        if 0.5 <= pb <= 1.0:
            score += 0.25
        elif 1.0 < pb <= 1.5:
            score += 0.15
        elif pb < 0.5:
            score += 0.10

        # 市值加分（大市值更稳定）
        market_cap = fund.get("market_cap", 0)
        if market_cap >= 1e11:  # 千亿以上
            score += 0.20
        elif market_cap >= 5e10:  # 500亿以上
            score += 0.15
        elif market_cap >= 1e10:  # 100亿以上
            score += 0.10

        return min(score, 1.0)
