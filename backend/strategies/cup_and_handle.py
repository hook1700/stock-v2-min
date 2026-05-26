"""策略1: 杯柄形态突破策略（Cup and Handle）"""
import logging
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

from backend.strategies.base import BaseStrategy, TradeSignal
from backend.analysis.technical import (
    compute_ma, compute_volume_ratio, find_local_extrema
)
from backend.config import settings

logger = logging.getLogger(__name__)


class CupAndHandleStrategy(BaseStrategy):
    """
    杯柄形态突破策略
    核心逻辑：股价形成U型"杯状"底部后，在杯口右侧窄幅震荡形成"柄"，
    放量突破柄部高点时即为主升浪启动点。
    """

    @property
    def strategy_id(self) -> int:
        return 1

    @property
    def strategy_name(self) -> str:
        return "杯柄形态突破"

    @property
    def description(self) -> str:
        return "捕捉主升浪起涨点，适合顺势而为。识别U型杯底+窄幅柄部+放量突破的经典形态。"

    def scan(self, stock_pool: list[str], scan_date: date) -> list[TradeSignal]:
        signals = []
        total = len(stock_pool)

        for i, code in enumerate(stock_pool):
            if i % 100 == 0:
                logger.info(f"[杯柄策略] 扫描进度: {i}/{total}")

            try:
                df = self.data_service.get_daily_kline(code, days=180)
                if df is None or len(df) < 60:
                    continue

                signal = self._analyze_stock(code, df)
                if signal is not None:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"[杯柄策略] {code} 分析异常: {e}")
                continue

        signals.sort(key=lambda s: s.confidence_score, reverse=True)
        logger.info(f"[杯柄策略] 扫描完成，发现{len(signals)}个信号")
        return signals

    def _analyze_stock(self, code: str, df: pd.DataFrame) -> Optional[TradeSignal]:
        """分析单只股票是否符合杯柄形态"""

        close = df["close"].values
        volume = df["volume"].values
        high = df["high"].values
        low = df["low"].values

        # 步骤1: 检测杯底
        cup = self._detect_cup(close, high, low)
        if cup is None:
            return None

        # 步骤2: 检测柄部
        handle = self._detect_handle(df, cup)
        if handle is None:
            return None

        # 步骤3: 检测今日是否放量突破
        if not self._is_breakout(df, handle):
            return None

        # 构建交易信号
        return self._build_signal(code, df, cup, handle)

    def _detect_cup(self, close: np.ndarray, high: np.ndarray, low: np.ndarray) -> Optional[dict]:
        """
        检测杯底形态
        条件：U型底，深度>15%，持续1-6个月
        """
        n = len(close)
        if n < settings.CUP_MIN_DAYS:
            return None

        # 使用局部极值寻找潜在的杯沿
        try:
            max_indices, min_indices = find_local_extrema(pd.Series(close), order=10)
        except Exception:
            return None

        if len(max_indices) < 2 or len(min_indices) < 1:
            return None

        # 从后往前寻找有效的杯底模式
        best_cup = None
        best_score = 0

        for i in range(len(max_indices) - 1):
            left_peak_idx = max_indices[i]
            for j in range(i + 1, len(max_indices)):
                right_peak_idx = max_indices[j]

                # 杯底持续时间检查
                duration = right_peak_idx - left_peak_idx
                if duration < settings.CUP_MIN_DAYS or duration > settings.CUP_MAX_DAYS:
                    continue

                # 找两峰之间的最低点
                cup_region = close[left_peak_idx:right_peak_idx + 1]
                local_min_idx = np.argmin(cup_region) + left_peak_idx

                left_peak_price = close[left_peak_idx]
                right_peak_price = close[right_peak_idx]
                bottom_price = close[local_min_idx]

                # 深度检查（左侧下跌幅度）
                depth = (left_peak_price - bottom_price) / left_peak_price
                if depth < settings.CUP_MIN_DEPTH:
                    continue

                # 右侧恢复检查（至少恢复到杯深的70%）
                recovery = (right_peak_price - bottom_price) / (left_peak_price - bottom_price)
                if recovery < 0.7:
                    continue

                # 两侧杯沿高度相近（误差15%内）
                lip_diff = abs(left_peak_price - right_peak_price) / left_peak_price
                if lip_diff > 0.15:
                    continue

                # 检查U型平滑度（不是V型）- 底部区域应有足够宽度
                bottom_region_start = local_min_idx - 3
                bottom_region_end = local_min_idx + 3
                if bottom_region_start >= left_peak_idx and bottom_region_end <= right_peak_idx:
                    bottom_range = close[bottom_region_start:bottom_region_end + 1]
                    bottom_volatility = (max(bottom_range) - min(bottom_range)) / bottom_price
                    if bottom_volatility > 0.15:  # 底部太尖锐，像V型
                        continue

                # 评分
                score = depth * recovery * (1 - lip_diff)

                # 优先选择最近形成的杯底
                recency_bonus = right_peak_idx / n
                score *= (0.5 + 0.5 * recency_bonus)

                if score > best_score:
                    best_score = score
                    best_cup = {
                        "left_peak_idx": left_peak_idx,
                        "bottom_idx": local_min_idx,
                        "right_peak_idx": right_peak_idx,
                        "left_peak_price": left_peak_price,
                        "bottom_price": bottom_price,
                        "right_peak_price": right_peak_price,
                        "depth": depth,
                        "duration": duration,
                        "recovery": recovery,
                        "score": score,
                    }

        return best_cup

    def _detect_handle(self, df: pd.DataFrame, cup: dict) -> Optional[dict]:
        """
        检测柄部形态
        条件：在杯口右侧，回撤<1/3杯深，持续1-4周，成交量萎缩
        """
        right_peak_idx = cup["right_peak_idx"]
        n = len(df)

        # 柄部应在右侧杯沿之后
        handle_start = right_peak_idx
        remaining = n - handle_start

        if remaining < settings.HANDLE_MIN_DAYS:
            return None

        # 柄部区域
        handle_end = min(handle_start + settings.HANDLE_MAX_DAYS, n - 1)
        handle_data = df.iloc[handle_start:handle_end + 1]

        if len(handle_data) < settings.HANDLE_MIN_DAYS:
            return None

        handle_high = handle_data["high"].max()
        handle_low = handle_data["low"].min()
        handle_close_start = handle_data.iloc[0]["close"]

        # 柄部回撤检查：不超过杯身深度的1/3
        cup_height = cup["right_peak_price"] - cup["bottom_price"]
        handle_retrace = handle_close_start - handle_low

        if cup_height > 0 and handle_retrace / cup_height > settings.HANDLE_RETRACE_MAX:
            return None

        # 柄部成交量应萎缩
        cup_avg_volume = df.iloc[cup["left_peak_idx"]:cup["right_peak_idx"]]["volume"].mean()
        handle_avg_volume = handle_data["volume"].mean()

        if cup_avg_volume > 0:
            volume_shrink = handle_avg_volume / cup_avg_volume
            if volume_shrink > 0.8:  # 柄部成交量应明显低于杯身
                return None
        else:
            volume_shrink = 1.0

        return {
            "start_idx": handle_start,
            "end_idx": handle_end,
            "high": handle_high,
            "low": handle_low,
            "volume_shrink": volume_shrink,
            "retrace_ratio": handle_retrace / cup_height if cup_height > 0 else 0,
            "duration": handle_end - handle_start,
        }

    def _is_breakout(self, df: pd.DataFrame, handle: dict) -> bool:
        """
        检测最近3天是否有放量突破柄部高点
        条件：收盘价>柄部高点，量比>1.5
        """
        # 检查最近3天是否有突破
        for offset in range(min(3, len(df))):
            idx = -1 - offset
            row = df.iloc[idx]

            # 收盘价突破柄部高点
            if row["close"] <= handle["high"]:
                continue

            # 量比检查
            vol_start = max(0, len(df) + idx - 5)
            vol_end = len(df) + idx
            if vol_end <= vol_start:
                continue
            avg_vol = df["volume"].iloc[vol_start:vol_end].mean()
            if avg_vol > 0 and row["volume"] / avg_vol >= settings.VOLUME_RATIO_THRESHOLD:
                return True

        return False

    def _build_signal(self, code: str, df: pd.DataFrame, cup: dict, handle: dict) -> TradeSignal:
        """构建交易信号"""
        latest = df.iloc[-1]
        stock_name = self.data_service.get_stock_name(code)

        # 买入价 = 柄部高点（突破位）
        buy_price = handle["high"]
        # 止损价 = 柄部最低点
        stop_loss = handle["low"]
        # 止盈目标 = 突破位 + 杯身深度（等幅投影）
        cup_height = cup["right_peak_price"] - cup["bottom_price"]
        take_profit = buy_price + cup_height

        # 置信度评分
        confidence = self._calculate_confidence(cup, handle, df)

        return TradeSignal(
            stock_code=code,
            stock_name=stock_name,
            signal_type="BUY",
            confidence_score=confidence,
            current_price=latest["close"],
            buy_price=round(buy_price, 2),
            stop_loss_price=round(stop_loss, 2),
            take_profit_price=round(take_profit, 2),
            buy_reason=(
                f"杯柄形态突破：杯底深度{cup['depth']*100:.1f}%，"
                f"持续{cup['duration']}天，柄部回撤{handle['retrace_ratio']*100:.1f}%，"
                f"今日放量突破柄部高点{buy_price:.2f}元"
            ),
            sell_condition=(
                f"止损：跌破柄部低点{stop_loss:.2f}元；"
                f"止盈：目标价{take_profit:.2f}元或跌破5日线"
            ),
            extra_data={
                "cup_depth": cup["depth"],
                "cup_duration": cup["duration"],
                "handle_retrace": handle["retrace_ratio"],
                "handle_volume_shrink": handle["volume_shrink"],
                "pattern": "cup_and_handle",
            }
        )

    def _calculate_confidence(self, cup: dict, handle: dict, df: pd.DataFrame) -> float:
        """计算置信度得分 (0-1)"""
        score = 0.0

        # 杯底深度适中（20-40%最佳）
        if 0.20 <= cup["depth"] <= 0.40:
            score += 0.25
        elif cup["depth"] > 0.15:
            score += 0.15

        # 杯底对称性（恢复度接近1）
        if cup["recovery"] >= 0.9:
            score += 0.20
        elif cup["recovery"] >= 0.8:
            score += 0.10

        # 柄部回撤小
        if handle["retrace_ratio"] < 0.2:
            score += 0.20
        elif handle["retrace_ratio"] < 0.3:
            score += 0.10

        # 柄部缩量明显
        if handle["volume_shrink"] < 0.5:
            score += 0.20
        elif handle["volume_shrink"] < 0.7:
            score += 0.10

        # 突破量比大
        vol_ratio = compute_volume_ratio(df["volume"], period=5).iloc[-1]
        if vol_ratio >= 2.0:
            score += 0.15
        elif vol_ratio >= 1.5:
            score += 0.10

        return min(score, 1.0)
