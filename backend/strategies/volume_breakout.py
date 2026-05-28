"""策略3: 底部放量首板/连板回调策略（Volume Breakout Pullback）"""
import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from backend.strategies.base import BaseStrategy, TradeSignal
from backend.analysis.technical import (
    compute_ma, compute_volume_ratio, detect_volume_shrink
)
from backend.config import settings

logger = logging.getLogger(__name__)


class VolumeBreakoutStrategy(BaseStrategy):
    """
    底部放量首板/连板回调策略
    核心逻辑：长期缩量阴跌后突然放量涨停，说明新主力进场。
    随后缩量回调至关键支撑位企稳时，是二次爆发起点。
    """

    @property
    def strategy_id(self) -> int:
        return 3

    @property
    def strategy_name(self) -> str:
        return "底部放量首板回调"

    @property
    def description(self) -> str:
        return "捕捉主力建仓后的二波行情，利用A股涨停板基因和资金记忆。适合偏好短线爆发力的投资者。"

    def scan(self, stock_pool: list[str], scan_date: date) -> list[TradeSignal]:
        signals = []
        total = len(stock_pool)

        for i, code in enumerate(stock_pool):
            if i % 100 == 0:
                logger.info(f"[底部放量] 扫描进度: {i}/{total}")

            try:
                df = self.data_service.get_daily_kline(code, days=250)
                if df is None or len(df) < 90:
                    continue

                signal = self._analyze_stock(code, df)
                if signal is not None:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"[底部放量] {code} 分析异常: {e}")
                continue

        signals.sort(key=lambda s: s.confidence_score, reverse=True)
        logger.info(f"[底部放量] 扫描完成，发现{len(signals)}个信号")
        return signals

    def _analyze_stock(self, code: str, df: pd.DataFrame) -> Optional[TradeSignal]:
        """分析单只股票"""

        # 步骤1: 检测底部放量涨停（首板）
        breakout = self._find_bottom_breakout(df)
        if breakout is None:
            return None

        # 步骤2: 检测涨停后缩量回调
        pullback = self._detect_pullback(df, breakout)
        if pullback is None:
            return None

        # 步骤3: 检测企稳信号
        if not self._is_stabilizing(df, pullback):
            return None

        # 构建信号
        return self._build_signal(code, df, breakout, pullback)

    def _find_bottom_breakout(self, df: pd.DataFrame) -> Optional[dict]:
        """
        在底部区域寻找放量涨停
        条件：
        1. 前期下跌2个月以上，跌幅>20%
        2. 某日放量涨停（涨幅>=9.5%，成交量>=前5日均量的1.8倍）
        """
        n = len(df)
        min_decline_days = settings.BOTTOM_DECLINE_MONTHS * 20  # 约40个交易日

        # 从后往前寻找涨停日
        # 搜索范围：从最近 PULLBACK_DAYS_MIN 天前开始向前搜索（允许最近的涨停也被检测到）
        search_start = n - settings.PULLBACK_DAYS_MIN - 1
        search_end = max(min_decline_days, 0)

        for i in range(search_start, search_end, -1):
            row = df.iloc[i]
            prev_row = df.iloc[i - 1]

            # 检查是否涨停（涨幅>=9.5%）
            if prev_row["close"] == 0:
                continue
            change_pct = (row["close"] - prev_row["close"]) / prev_row["close"]
            if change_pct < 0.095:
                continue

            # 检查放量（>=前5日均量的1.8倍）
            if i < 5:
                continue
            avg_vol_5 = df.iloc[i - 5:i]["volume"].mean()
            if avg_vol_5 == 0:
                continue
            vol_ratio = row["volume"] / avg_vol_5
            if vol_ratio < settings.BREAKOUT_VOLUME_RATIO:
                continue

            # 检查前期是否下跌（向前看min_decline_days天）
            lookback_start = max(0, i - min_decline_days)
            period_high = df.iloc[lookback_start:i]["high"].max()
            period_low = df.iloc[lookback_start:i]["low"].min()

            # 涨停日之前应处于低位（接近区间低点）
            if period_high == 0:
                continue
            decline = (period_high - prev_row["close"]) / period_high
            if decline < settings.BOTTOM_DECLINE_RATIO:
                continue

            # 检查涨停前成交量是否长期低迷
            pre_avg_vol = df.iloc[lookback_start:i]["volume"].mean()
            if pre_avg_vol == 0:
                continue

            # 检查是否有连板
            consecutive_limits = 1
            for j in range(i + 1, min(i + 5, n)):
                next_row = df.iloc[j]
                cur_prev = df.iloc[j - 1]
                if cur_prev["close"] == 0:
                    break
                next_change = (next_row["close"] - cur_prev["close"]) / cur_prev["close"]
                if next_change >= 0.095:
                    consecutive_limits += 1
                else:
                    break

            # 确保连板后有足够天数形成回调
            end_idx = i + consecutive_limits - 1
            days_since = n - 1 - end_idx
            if days_since < settings.PULLBACK_DAYS_MIN:
                continue
            if days_since > settings.PULLBACK_DAYS_MAX + 5:
                continue

            return {
                "breakout_idx": i,
                "breakout_date": df.iloc[i]["date"],
                "open_price": row["open"],
                "close_price": row["close"],
                "high_price": row["high"],
                "low_price": row["low"],
                "volume_ratio": vol_ratio,
                "change_pct": change_pct,
                "consecutive_limits": consecutive_limits,
                "pre_decline": decline,
                "end_idx": end_idx,  # 连板结束位置
            }

        return None

    def _detect_pullback(self, df: pd.DataFrame, breakout: dict) -> Optional[dict]:
        """
        检测涨停后的缩量回调
        条件：回调3-8天，成交量逐步萎缩至起涨前水平
        """
        end_idx = breakout["end_idx"]  # 连板结束位置
        n = len(df)

        # 回调应该从连板结束后开始
        pullback_start = end_idx + 1
        if pullback_start >= n:
            return None

        # 检查回调天数
        days_since_breakout = n - 1 - end_idx
        if days_since_breakout < settings.PULLBACK_DAYS_MIN:
            return None
        if days_since_breakout > settings.PULLBACK_DAYS_MAX + 5:  # 允许一定宽容度
            return None

        # 回调区间数据
        pullback_data = df.iloc[pullback_start:]
        if pullback_data.empty:
            return None

        pullback_low = pullback_data["low"].min()
        pullback_high = pullback_data["high"].max()

        # 检查成交量萎缩趋势
        breakout_vol = df.iloc[breakout["breakout_idx"]]["volume"]
        pullback_avg_vol = pullback_data["volume"].mean()
        latest_vol = pullback_data.iloc[-1]["volume"]

        # 回调成交量应低于涨停日
        if breakout_vol > 0 and pullback_avg_vol / breakout_vol > 0.6:
            return None

        # 成交量应逐步萎缩（最近几天低于回调初期）
        if len(pullback_data) >= 3:
            early_vol = pullback_data.iloc[:2]["volume"].mean()
            late_vol = pullback_data.iloc[-2:]["volume"].mean()
            if early_vol > 0 and late_vol / early_vol > 1.2:  # 不应放量
                return None

        return {
            "start_idx": pullback_start,
            "days": days_since_breakout,
            "pullback_low": pullback_low,
            "pullback_high": pullback_high,
            "volume_shrink_ratio": pullback_avg_vol / breakout_vol if breakout_vol > 0 else 1,
        }

    def _is_stabilizing(self, df: pd.DataFrame, pullback: dict) -> bool:
        """
        检测企稳信号
        条件（放宽）：
        1. 最近2天中至少1天振幅<阈值
        2. K线实体较小（实体占比<0.7）
        """
        # 检查最近2天是否有企稳迹象
        for offset in range(min(2, len(df))):
            row = df.iloc[-1 - offset]

            if row["close"] == 0:
                continue

            # 振幅检查
            amplitude = (row["high"] - row["low"]) / row["close"]
            if amplitude > settings.STABILIZE_AMPLITUDE:
                continue

            # K线实体不能太大
            body = abs(row["close"] - row["open"])
            total_range = row["high"] - row["low"]
            if total_range > 0 and body / total_range > 0.7:
                continue

            return True

        return False

    def _build_signal(self, code: str, df: pd.DataFrame, breakout: dict, pullback: dict) -> TradeSignal:
        """构建交易信号"""
        latest = df.iloc[-1]
        stock_name = self.data_service.get_stock_name(code)

        # 买入价 = 当前企稳价位
        buy_price = latest["close"]
        # 止损 = 首板开盘价或最低价
        stop_loss = min(breakout["open_price"], breakout["low_price"])
        # 止盈 = 突破回调期间最高价后持有，或反弹到涨停日高点
        take_profit = breakout["high_price"] * 1.1  # 涨停日高点上方10%

        confidence = self._calculate_confidence(breakout, pullback, df)

        return TradeSignal(
            stock_code=code,
            stock_name=stock_name,
            signal_type="BUY",
            confidence_score=confidence,
            current_price=buy_price,
            buy_price=round(buy_price, 2),
            stop_loss_price=round(stop_loss, 2),
            take_profit_price=round(take_profit, 2),
            buy_reason=(
                f"底部放量{'连板' if breakout['consecutive_limits'] > 1 else '首板'}"
                f"（涨幅{breakout['change_pct']*100:.1f}%，量比{breakout['volume_ratio']:.1f}），"
                f"随后缩量回调{pullback['days']}天，今日企稳"
            ),
            sell_condition=(
                f"止损：跌破首板开盘价{stop_loss:.2f}元；"
                f"止盈：反弹突破回调最高价后移动止盈，若不能突破前高则离场"
            ),
            extra_data={
                "breakout_volume_ratio": breakout["volume_ratio"],
                "consecutive_limits": breakout["consecutive_limits"],
                "pullback_days": pullback["days"],
                "pullback_volume_shrink": pullback["volume_shrink_ratio"],
                "pre_decline": breakout["pre_decline"],
                "pattern": "volume_breakout_pullback",
            }
        )

    def _calculate_confidence(self, breakout: dict, pullback: dict, df: pd.DataFrame) -> float:
        """计算置信度"""
        score = 0.0

        # 连板加分
        if breakout["consecutive_limits"] >= 2:
            score += 0.20
        else:
            score += 0.10

        # 涨停量比越大越好
        if breakout["volume_ratio"] >= 3.0:
            score += 0.20
        elif breakout["volume_ratio"] >= 2.0:
            score += 0.15

        # 回调缩量越明显越好
        if pullback["volume_shrink_ratio"] < 0.3:
            score += 0.25
        elif pullback["volume_shrink_ratio"] < 0.5:
            score += 0.15

        # 前期跌幅足够深
        if breakout["pre_decline"] >= 0.50:
            score += 0.20
        elif breakout["pre_decline"] >= 0.30:
            score += 0.10

        # 回调天数适中（5-6天最佳）
        if 4 <= pullback["days"] <= 6:
            score += 0.15
        elif 3 <= pullback["days"] <= 8:
            score += 0.10

        return min(score, 1.0)
