"""板块轮动分析模块"""
import logging
from datetime import date
from typing import Optional
from dataclasses import dataclass, field

import pandas as pd
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


@dataclass
class SectorSignal:
    """板块信号数据"""
    sector_code: str
    sector_name: str
    signal: str              # OPPORTUNITY / RISK / NEUTRAL
    score: float             # -1.0 ~ 1.0
    momentum_20d: float = 0.0
    momentum_5d: float = 0.0
    volume_trend: str = ""   # expanding / contracting
    relative_strength: float = 0.0
    pe_percentile: float = 0.0
    reasoning: str = ""
    recommended_stocks: list = field(default_factory=list)


class SectorRotationAnalyzer:
    """
    申万板块轮动分析
    评分模型：
    - 20日动量 (25%)
    - 动量加速度 5d vs 20d (15%)
    - 量能趋势 (15%)
    - 相对强度 vs 大盘 (20%)
    - 估值分位 (15%)
    - 趋势连续性 (10%)
    """

    def __init__(self, data_service):
        self.data_service = data_service

    def analyze(self, scan_date: date = None) -> list[SectorSignal]:
        """执行板块轮动分析"""
        if scan_date is None:
            scan_date = date.today()

        sectors_df = self.data_service.get_shenwan_sectors()
        if sectors_df is None or sectors_df.empty:
            logger.error("无法获取申万板块数据")
            return []

        signals = []

        for _, sector_row in sectors_df.iterrows():
            try:
                signal = self._analyze_sector(sector_row)
                if signal is not None:
                    signals.append(signal)
            except Exception as e:
                logger.debug(f"板块分析异常 {sector_row.get('指数代码', 'unknown')}: {e}")
                continue

        # 按得分排序
        signals.sort(key=lambda s: s.score, reverse=True)

        # 对机会板块选股
        opportunity_count = 0
        for signal in signals:
            if signal.signal == "OPPORTUNITY" and opportunity_count < settings.SECTOR_TOP_N:
                self._pick_sector_stocks(signal)
                opportunity_count += 1

        logger.info(
            f"板块轮动分析完成: "
            f"机会{sum(1 for s in signals if s.signal == 'OPPORTUNITY')}个, "
            f"风险{sum(1 for s in signals if s.signal == 'RISK')}个"
        )
        return signals

    def _analyze_sector(self, sector_row) -> Optional[SectorSignal]:
        """分析单个板块"""
        # 获取板块基本信息
        sector_code = str(sector_row.get("指数代码", sector_row.get("index_code", "")))
        sector_name = str(sector_row.get("指数名称", sector_row.get("index_name", "")))

        if not sector_code or not sector_name:
            return None

        # 获取板块历史数据
        history = self.data_service.get_sector_history(sector_code, days=60)

        # 计算各维度评分
        scores = {}

        # 维度1: 20日动量
        momentum_20d = self._calc_momentum(sector_row, history, days=20)
        scores["momentum_20d"] = self._normalize_momentum(momentum_20d)

        # 维度2: 动量加速度 (5日 vs 20日)
        momentum_5d = self._calc_momentum(sector_row, history, days=5)
        acceleration = momentum_5d - momentum_20d / 4  # 5日动量 vs 20日等比缩放
        scores["acceleration"] = np.clip(acceleration / 5.0, -1, 1)

        # 维度3: 量能趋势
        volume_trend_score, volume_trend_str = self._calc_volume_trend(history)
        scores["volume"] = volume_trend_score

        # 维度4: 相对强度
        relative_strength = self._calc_relative_strength(sector_row, history)
        scores["relative_strength"] = relative_strength

        # 维度5: 估值分位（使用当前PE与历史比较）
        pe_percentile = self._calc_pe_percentile(sector_row)
        scores["valuation"] = 1.0 - pe_percentile  # 估值越低越好

        # 维度6: 趋势连续性
        trend_score = self._calc_trend_continuity(history)
        scores["trend"] = trend_score

        # 加权综合评分
        weights = {
            "momentum_20d": 0.25,
            "acceleration": 0.15,
            "volume": 0.15,
            "relative_strength": 0.20,
            "valuation": 0.15,
            "trend": 0.10,
        }

        total_score = sum(scores.get(k, 0) * v for k, v in weights.items())
        total_score = np.clip(total_score, -1.0, 1.0)

        # 分类信号
        if total_score >= 0.3:
            signal_type = "OPPORTUNITY"
        elif total_score <= -0.3:
            signal_type = "RISK"
        else:
            signal_type = "NEUTRAL"

        # 生成分析理由
        reasoning = self._generate_reasoning(
            sector_name, signal_type, scores, momentum_20d, momentum_5d
        )

        return SectorSignal(
            sector_code=sector_code,
            sector_name=sector_name,
            signal=signal_type,
            score=round(total_score, 4),
            momentum_20d=round(momentum_20d, 2),
            momentum_5d=round(momentum_5d, 2),
            volume_trend=volume_trend_str,
            relative_strength=round(relative_strength, 4),
            pe_percentile=round(pe_percentile, 4),
            reasoning=reasoning,
        )

    def _calc_momentum(self, sector_row, history: Optional[pd.DataFrame], days: int) -> float:
        """计算N日动量（涨跌幅%）"""
        if history is not None and len(history) >= days:
            current = history.iloc[-1].get("close", history.iloc[-1].get("收盘", 0))
            past = history.iloc[-days].get("close", history.iloc[-days].get("收盘", 0))
            if past > 0:
                return (current - past) / past * 100
        # 降级：使用实时数据
        change = sector_row.get("涨跌幅", sector_row.get("change_pct", 0))
        return float(change) if change else 0.0

    def _normalize_momentum(self, momentum: float) -> float:
        """将动量标准化到 [-1, 1] 范围"""
        # 假设正常动量范围为 -20% ~ +20%
        return np.clip(momentum / 20.0, -1, 1)

    def _calc_volume_trend(self, history: Optional[pd.DataFrame]) -> tuple:
        """计算量能趋势"""
        if history is None or len(history) < 10:
            return 0.0, "neutral"

        vol_col = "volume" if "volume" in history.columns else "成交量"
        if vol_col not in history.columns:
            return 0.0, "neutral"

        recent_vol = history[vol_col].tail(5).mean()
        prev_vol = history[vol_col].iloc[-10:-5].mean()

        if prev_vol == 0:
            return 0.0, "neutral"

        ratio = recent_vol / prev_vol
        if ratio > 1.2:
            return min((ratio - 1) * 2, 1.0), "expanding"
        elif ratio < 0.8:
            return max((ratio - 1) * 2, -1.0), "contracting"
        else:
            return 0.0, "neutral"

    def _calc_relative_strength(self, sector_row, history: Optional[pd.DataFrame]) -> float:
        """计算相对大盘的强度"""
        # 简化：使用板块涨跌幅与全市场均值的偏差
        change = float(sector_row.get("涨跌幅", sector_row.get("change_pct", 0)) or 0)
        # 归一化
        return np.clip(change / 5.0, -1, 1)

    def _calc_pe_percentile(self, sector_row) -> float:
        """计算PE分位数（0-1，越低越便宜）"""
        pe = sector_row.get("市盈率", sector_row.get("pe", 0))
        if not pe or pe <= 0:
            return 0.5  # 无数据返回中性

        # 简化估值：PE < 15 认为低估，15-30 中性，> 30 高估
        pe = float(pe)
        if pe < 15:
            return pe / 30.0  # 0 ~ 0.5
        elif pe < 30:
            return 0.5 + (pe - 15) / 30.0  # 0.5 ~ 1.0
        else:
            return min(pe / 60.0, 1.0)

    def _calc_trend_continuity(self, history: Optional[pd.DataFrame]) -> float:
        """计算趋势连续性（连续上涨/下跌天数）"""
        if history is None or len(history) < 5:
            return 0.0

        close_col = "close" if "close" in history.columns else "收盘"
        if close_col not in history.columns:
            return 0.0

        closes = history[close_col].tail(10).values
        if len(closes) < 2:
            return 0.0

        # 计算连续上涨天数
        consecutive_up = 0
        for i in range(len(closes) - 1, 0, -1):
            if closes[i] > closes[i - 1]:
                consecutive_up += 1
            else:
                break

        # 归一化到 [-1, 1]
        return np.clip(consecutive_up / 5.0, -1, 1)

    def _pick_sector_stocks(self, signal: SectorSignal):
        """在机会板块中选择推荐股票"""
        from backend.strategies.base import TradeSignal

        constituents = self.data_service.get_sector_constituents(signal.sector_code)
        if not constituents:
            return

        candidates = []

        for code in constituents[:50]:  # 只分析前50只
            try:
                df = self.data_service.get_daily_kline(code, days=60)
                if df is None or len(df) < 20:
                    continue

                score = self._score_stock_in_sector(df, code)
                if score > 0:
                    candidates.append((code, score, df))
            except Exception:
                continue

        # 取前3只
        candidates.sort(key=lambda x: x[1], reverse=True)

        for code, score, df in candidates[:3]:
            latest = df.iloc[-1]
            stock_name = self.data_service.get_stock_name(code)

            # 简单计算买卖点
            ma20 = df["close"].tail(20).mean()
            buy_price = latest["close"]
            stop_loss = ma20 * 0.95  # 20日线下方5%
            take_profit = buy_price * 1.15  # 目标15%

            trade_signal = TradeSignal(
                stock_code=code,
                stock_name=stock_name,
                signal_type="BUY",
                confidence_score=score,
                current_price=latest["close"],
                buy_price=round(buy_price, 2),
                stop_loss_price=round(stop_loss, 2),
                take_profit_price=round(take_profit, 2),
                buy_reason=f"板块轮动机会（{signal.sector_name}），技术面评分{score:.2f}",
                sell_condition=f"止损{stop_loss:.2f}元，目标{take_profit:.2f}元",
            )
            signal.recommended_stocks.append(trade_signal)

    def _score_stock_in_sector(self, df: pd.DataFrame, code: str) -> float:
        """板块内个股评分"""
        score = 0.0
        n = len(df)

        if n < 20:
            return 0.0

        close = df["close"]
        volume = df["volume"]

        # 近20日涨幅（适中为佳）
        return_20d = (close.iloc[-1] - close.iloc[-20]) / close.iloc[-20]
        if 0 < return_20d < 0.15:
            score += 0.3
        elif return_20d >= 0.15:
            score += 0.1  # 涨太多有回调风险

        # 近5日量比（温和放量为佳）
        recent_vol = volume.tail(5).mean()
        prev_vol = volume.iloc[-20:-5].mean()
        if prev_vol > 0:
            vol_ratio = recent_vol / prev_vol
            if 1.0 <= vol_ratio <= 2.0:
                score += 0.3
            elif vol_ratio < 1.0:
                score += 0.1

        # 价格在20日线上方
        ma20 = close.tail(20).mean()
        if close.iloc[-1] > ma20:
            score += 0.2

        # 乖离率适中（不过热）
        deviation = (close.iloc[-1] - ma20) / ma20
        if 0 < deviation < 0.08:
            score += 0.2

        return score

    def _generate_reasoning(self, sector_name: str, signal_type: str,
                           scores: dict, momentum_20d: float, momentum_5d: float) -> str:
        """生成分析理由"""
        parts = []

        if signal_type == "OPPORTUNITY":
            parts.append(f"{sector_name}板块当前具有投资机会")
        elif signal_type == "RISK":
            parts.append(f"{sector_name}板块当前风险较高")
        else:
            parts.append(f"{sector_name}板块当前信号中性")

        parts.append(f"20日动量{momentum_20d:.1f}%")
        parts.append(f"5日动量{momentum_5d:.1f}%")

        if scores.get("relative_strength", 0) > 0.3:
            parts.append("相对强度突出")
        elif scores.get("relative_strength", 0) < -0.3:
            parts.append("相对弱势")

        if scores.get("valuation", 0) > 0.6:
            parts.append("估值偏低有安全边际")
        elif scores.get("valuation", 0) < 0.3:
            parts.append("估值偏高需注意")

        return "；".join(parts)
