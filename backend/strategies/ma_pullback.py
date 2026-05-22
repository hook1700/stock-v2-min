"""策略2: 均线多头排列回踩策略（Moving Average Pullback）"""
import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from backend.strategies.base import BaseStrategy, TradeSignal
from backend.analysis.technical import (
    compute_ma, compute_volume_ratio, is_bullish_ma_alignment,
    is_ma_trending_up, detect_volume_shrink, compute_deviation_rate
)
from backend.config import settings

logger = logging.getLogger(__name__)


class MAPullbackStrategy(BaseStrategy):
    """
    均线多头排列回踩策略
    核心逻辑：只做上升趋势中的回调，在价格回踩关键均线时低吸。
    选股条件：5/10/20/60日均线多头排列，首次缩量回踩20/60日均线后企稳。
    """

    @property
    def strategy_id(self) -> int:
        return 2

    @property
    def strategy_name(self) -> str:
        return "均线多头排列回踩"

    @property
    def description(self) -> str:
        return "顺势低吸策略，在强势股回踩关键均线时买入。适合稳健派投资者。"

    def scan(self, stock_pool: list[str], scan_date: date) -> list[TradeSignal]:
        signals = []
        total = len(stock_pool)

        for i, code in enumerate(stock_pool):
            if i % 100 == 0:
                logger.info(f"[均线回踩] 扫描进度: {i}/{total}")

            try:
                df = self.data_service.get_daily_kline(code, days=120)
                if df is None or len(df) < 65:
                    continue

                signal = self._analyze_stock(code, df)
                if signal is not None:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"[均线回踩] {code} 分析异常: {e}")
                continue

        signals.sort(key=lambda s: s.confidence_score, reverse=True)
        logger.info(f"[均线回踩] 扫描完成，发现{len(signals)}个信号")
        return signals

    def _analyze_stock(self, code: str, df: pd.DataFrame) -> Optional[TradeSignal]:
        """分析单只股票"""

        # 计算均线
        df = df.copy()
        for period in settings.MA_PERIODS:
            df[f"ma{period}"] = compute_ma(df["close"], period)

        # 去除NaN行
        df = df.dropna(subset=[f"ma{settings.MA_PERIODS[-1]}"]).reset_index(drop=True)
        if len(df) < 20:
            return None

        # 条件1: 均线多头排列
        ma_cols = [f"ma{p}" for p in settings.MA_PERIODS]
        if not is_bullish_ma_alignment(df, ma_cols):
            return None

        # 条件2: 均线持续向上
        for col in ["ma20", "ma60"]:
            if not is_ma_trending_up(df, col, lookback=settings.MA_ALIGNMENT_DAYS):
                return None

        # 条件3: 价格回踩20日或60日均线
        pullback = self._detect_pullback(df)
        if pullback is None:
            return None

        # 条件4: 回踩时成交量萎缩
        if not self._is_volume_contracting(df, pullback):
            return None

        # 构建信号
        return self._build_signal(code, df, pullback)

    def _detect_pullback(self, df: pd.DataFrame) -> Optional[dict]:
        """
        检测回踩20日或60日均线
        条件：价格接近均线（±1%），且是从上方回落
        """
        latest = df.iloc[-1]
        close = latest["close"]

        # 检查回踩20日线
        ma20 = latest["ma20"]
        deviation_20 = compute_deviation_rate(close, ma20)

        # 回踩60日线
        ma60 = latest["ma60"]
        deviation_60 = compute_deviation_rate(close, ma60)

        tolerance = settings.MA_PULLBACK_TOLERANCE

        target_ma = None
        target_ma_name = ""
        target_ma_value = 0

        # 优先检查回踩20日线（更敏感）
        if -tolerance <= deviation_20 <= tolerance * 2:
            target_ma = "ma20"
            target_ma_name = "20日均线"
            target_ma_value = ma20
        elif -tolerance <= deviation_60 <= tolerance * 2:
            target_ma = "ma60"
            target_ma_name = "60日均线"
            target_ma_value = ma60
        else:
            return None

        # 确认是从上方回落（前几天价格高于均线）
        lookback = min(10, len(df) - 1)
        recent_above_count = 0
        for i in range(-lookback, -1):
            if df.iloc[i]["close"] > df.iloc[i][target_ma] * 1.02:
                recent_above_count += 1

        if recent_above_count < lookback * 0.5:
            return None

        # 确认是首次或第二次回踩（找历史回踩次数）
        pullback_count = self._count_recent_pullbacks(df, target_ma)
        if pullback_count > 2:
            return None

        return {
            "target_ma": target_ma,
            "target_ma_name": target_ma_name,
            "target_ma_value": target_ma_value,
            "deviation": deviation_20 if target_ma == "ma20" else deviation_60,
            "pullback_count": pullback_count,
        }

    def _count_recent_pullbacks(self, df: pd.DataFrame, ma_col: str) -> int:
        """统计近期回踩均线次数"""
        count = 0
        is_near_ma = False
        tolerance = settings.MA_PULLBACK_TOLERANCE * 2

        for i in range(max(0, len(df) - 40), len(df)):
            row = df.iloc[i]
            deviation = compute_deviation_rate(row["close"], row[ma_col])

            if -tolerance <= deviation <= tolerance:
                if not is_near_ma:
                    count += 1
                    is_near_ma = True
            else:
                is_near_ma = False

        return count

    def _is_volume_contracting(self, df: pd.DataFrame, pullback: dict) -> bool:
        """检测回踩过程中的成交量是否萎缩"""
        # 最近3天的成交量 vs 之前10天的均量
        recent_vol = df["volume"].tail(3).mean()
        prev_vol = df["volume"].iloc[-13:-3].mean()

        if prev_vol == 0:
            return False

        return recent_vol / prev_vol < settings.VOLUME_SHRINK_RATIO

    def _build_signal(self, code: str, df: pd.DataFrame, pullback: dict) -> TradeSignal:
        """构建交易信号"""
        latest = df.iloc[-1]
        stock_name = self.data_service.get_stock_name(code)

        ma_value = pullback["target_ma_value"]

        # 买入价 = 当前价格（均线附近）
        buy_price = latest["close"]
        # 止损 = 均线下方3%
        stop_loss = ma_value * 0.97
        # 止盈 = 乖离率达15%时
        take_profit = ma_value * 1.15

        confidence = self._calculate_confidence(df, pullback)

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
                f"均线多头排列，第{pullback['pullback_count']}次缩量回踩"
                f"{pullback['target_ma_name']}（{ma_value:.2f}元），"
                f"乖离率{pullback['deviation']*100:.1f}%，量能萎缩"
            ),
            sell_condition=(
                f"止损：放量跌破{pullback['target_ma_name']}超3%"
                f"（即{stop_loss:.2f}元）；"
                f"止盈：乖离率>15%或有效跌破5日线"
            ),
            extra_data={
                "target_ma": pullback["target_ma"],
                "ma_value": ma_value,
                "deviation": pullback["deviation"],
                "pullback_count": pullback["pullback_count"],
                "pattern": "ma_pullback",
            }
        )

    def _calculate_confidence(self, df: pd.DataFrame, pullback: dict) -> float:
        """计算置信度"""
        score = 0.0

        # 首次回踩比多次回踩更可靠
        if pullback["pullback_count"] == 1:
            score += 0.30
        elif pullback["pullback_count"] == 2:
            score += 0.15

        # 均线发散度（间距适中最佳）
        latest = df.iloc[-1]
        ma5 = latest.get("ma5", 0)
        ma60 = latest.get("ma60", 0)
        if ma60 > 0:
            spread = (ma5 - ma60) / ma60
            if 0.05 <= spread <= 0.20:
                score += 0.20
            elif spread > 0:
                score += 0.10

        # 缩量程度
        recent_vol = df["volume"].tail(3).mean()
        prev_vol = df["volume"].iloc[-13:-3].mean()
        if prev_vol > 0:
            vol_ratio = recent_vol / prev_vol
            if vol_ratio < 0.4:
                score += 0.25
            elif vol_ratio < 0.6:
                score += 0.15

        # 回踩精确度（越接近均线越好）
        deviation = abs(pullback["deviation"])
        if deviation < 0.005:
            score += 0.25
        elif deviation < 0.01:
            score += 0.15

        return min(score, 1.0)
