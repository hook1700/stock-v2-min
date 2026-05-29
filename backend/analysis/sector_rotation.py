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
    ma_signal: str = "HOLD"  # BUY_STRONG / BUY / WARN / SELL / HOLD
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

        # 计算板块均线信号
        ma_signal = detect_signal(history)

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
            ma_signal=ma_signal,
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
        """在机会板块中选择推荐股票，结合量价形态策略"""
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

                # 基础评分
                base_score = self._score_stock_in_sector(df, code)

                # 量价形态判定
                vol_signal = detect_consolidation_and_surge(df)

                # 根据量价形态调整评分和信号类型
                if vol_signal == "BOTH":
                    final_score = base_score + 0.5  # 最优形态加分最多
                    stock_signal_type = "BOTH"
                elif vol_signal == "VOLUME_BREAKOUT":
                    final_score = base_score + 0.3  # 放量突破加分
                    stock_signal_type = "VOLUME_BREAKOUT"
                else:
                    final_score = base_score
                    stock_signal_type = "SECTOR_BUY"  # 仅来自板块信号

                if final_score > 0:
                    candidates.append((code, final_score, df, stock_signal_type))
            except Exception:
                continue

        # 取前3只
        candidates.sort(key=lambda x: x[1], reverse=True)

        for code, score, df, stock_signal_type in candidates[:3]:
            latest = df.iloc[-1]
            stock_name = self.data_service.get_stock_name(code)

            # 简单计算买卖点
            ma20 = df["close"].tail(20).mean()
            buy_price = latest["close"]
            stop_loss = ma20 * 0.95  # 20日线下方5%
            take_profit = buy_price * 1.15  # 目标15%

            # 根据形态类型生成不同的买入理由
            if stock_signal_type == "BOTH":
                reason = f"板块({signal.sector_name})机会 + 横盘洗盘放量拉升形态，评分{score:.2f}"
            elif stock_signal_type == "VOLUME_BREAKOUT":
                reason = f"板块({signal.sector_name})机会 + 放量突破，评分{score:.2f}"
            else:
                reason = f"板块轮动机会（{signal.sector_name}），技术面评分{score:.2f}"

            trade_signal = TradeSignal(
                stock_code=code,
                stock_name=stock_name,
                signal_type=stock_signal_type,
                confidence_score=score,
                current_price=latest["close"],
                buy_price=round(buy_price, 2),
                stop_loss_price=round(stop_loss, 2),
                take_profit_price=round(take_profit, 2),
                buy_reason=reason,
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


def detect_signal(history: pd.DataFrame) -> str:
    """
    板块均线信号策略（策略五）
    基于 MA5/MA15/MA50 三均线交叉判定板块趋势信号。

    参数:
        history: 板块历史K线 DataFrame，需包含 'close' 列，按日期升序排列

    返回:
        信号字符串: BUY_STRONG / BUY / WARN / SELL / HOLD

    信号优先级: BUY_STRONG > BUY > WARN > SELL > HOLD
    """
    if history is None or len(history) < settings.SECTOR_MA_LONG + 1:
        return "HOLD"

    close_col = "close" if "close" in history.columns else "收盘"
    if close_col not in history.columns:
        return "HOLD"

    closes = history[close_col].values

    ma_short = settings.SECTOR_MA_SHORT   # MA5
    ma_mid = settings.SECTOR_MA_MID       # MA15
    ma_long = settings.SECTOR_MA_LONG     # MA50

    # 计算均线值（当日和前一日）
    ma5_today = closes[-ma_short:].mean()
    ma5_yesterday = closes[-(ma_short + 1):-1].mean()

    ma15_today = closes[-ma_mid:].mean()
    ma15_yesterday = closes[-(ma_mid + 1):-1].mean()

    ma50_today = closes[-ma_long:].mean()
    ma50_yesterday = closes[-(ma_long + 1):-1].mean()

    current_close = closes[-1]

    # 判定上穿/下穿
    # 上穿：前一日 short <= long，当日 short > long
    ma5_cross_up_ma15 = (ma5_yesterday <= ma15_yesterday) and (ma5_today > ma15_today)
    ma5_cross_up_ma50 = (ma5_yesterday <= ma50_yesterday) and (ma5_today > ma50_today)
    ma5_cross_down_ma15 = (ma5_yesterday >= ma15_yesterday) and (ma5_today < ma15_today)
    ma5_cross_down_ma50 = (ma5_yesterday >= ma50_yesterday) and (ma5_today < ma50_today)

    # 按优先级判定信号
    # 1. BUY_STRONG: MA5 同日上穿 MA15 且同日上穿 MA50
    if ma5_cross_up_ma15 and ma5_cross_up_ma50:
        return "BUY_STRONG"

    # 2. BUY: MA5 上穿 MA15（金叉）且收盘价 > MA50
    if ma5_cross_up_ma15 and current_close > ma50_today:
        return "BUY"

    # 3. WARN: MA5 下穿 MA15（死叉）
    if ma5_cross_down_ma15:
        return "WARN"

    # 4. SELL: MA5 下穿 MA50
    if ma5_cross_down_ma50:
        return "SELL"

    # 5. HOLD: 无以上信号
    return "HOLD"


def detect_consolidation_and_surge(
    df: pd.DataFrame,
    consolidation_days: int = None,
    consolidation_amplitude: float = None,
    surge_days: int = None,
    volume_ratio: float = None,
    min_surge_pct: float = None,
) -> Optional[str]:
    """
    个股量价形态策略（策略六）
    识别「横盘洗盘 → 放量拉升」经典形态。

    参数:
        df: 个股日K线 DataFrame，需包含 'close'和'volume' 列，按日期升序排列
        consolidation_days: 横盘观察天数（默认从配置读取）
        consolidation_amplitude: 横盘最大振幅百分比（默认从配置读取）
        surge_days: 放量观察天数（默认从配置读取）
        volume_ratio: 放量倍数阈值（默认从配置读取）
        min_surge_pct: 最低累计涨幅百分比（默认从配置读取）

    返回:
        signal_type: "BOTH" / "VOLUME_BREAKOUT" / None
        - BOTH: 横盘洗盘 + 放量拉升都满足（最优形态）
        - VOLUME_BREAKOUT: 仅满足放量突破条件
        - None: 未触发任何形态
    """
    # 使用配置默认值
    consolidation_days = consolidation_days or settings.CONSOLIDATION_DAYS
    consolidation_amplitude = consolidation_amplitude or settings.CONSOLIDATION_AMPLITUDE
    surge_days = surge_days or settings.SURGE_DAYS
    volume_ratio = volume_ratio or settings.VOLUME_SURGE_RATIO
    min_surge_pct = min_surge_pct or settings.MIN_SURGE_PCT

    # 数据长度检查
    min_required = consolidation_days + surge_days
    if df is None or len(df) < min_required:
        return None

    close_col = "close" if "close" in df.columns else "收盘"
    vol_col = "volume" if "volume" in df.columns else "成交量"

    if close_col not in df.columns or vol_col not in df.columns:
        return None

    closes = df[close_col].values
    volumes = df[vol_col].values

    # ====== 放量拉升判定 ======
    # 最近 surge_days 日
    surge_closes = closes[-surge_days:]
    surge_volumes = volumes[-surge_days:]

    # 前 consolidation_days 日（早于放量期）
    pre_period_end = len(closes) - surge_days
    pre_period_start = pre_period_end - consolidation_days

    if pre_period_start < 0:
        return None

    pre_closes = closes[pre_period_start:pre_period_end]
    pre_volumes = volumes[pre_period_start:pre_period_end]

    # 放量条件：近 surge_days 日均量 > 前 consolidation_days 日均量 × volume_ratio
    avg_surge_vol = surge_volumes.mean()
    avg_pre_vol = pre_volumes.mean()

    if avg_pre_vol <= 0:
        return None

    volume_breakout = avg_surge_vol > avg_pre_vol * volume_ratio

    # 涨幅条件：近 surge_days 日累计涨幅 > min_surge_pct%
    # 累计涨幅 = (最后一日收盘 - 放量期前一日收盘) / 放量期前一日收盘 * 100%
    pre_close = closes[-(surge_days + 1)]  # 放量期前一日收盘价
    if pre_close <= 0:
        return None

    surge_pct = (surge_closes[-1] - pre_close) / pre_close * 100
    price_surge = surge_pct > min_surge_pct

    is_volume_surge = volume_breakout and price_surge

    # ====== 横盘洗盘判定 ======
    # 观察前 consolidation_days 日收盘价振幅
    # 振幅 = (最高收盘 - 最低收盘) / 最低收盘 * 100%
    max_close = pre_closes.max()
    min_close = pre_closes.min()

    if min_close <= 0:
        return None

    amplitude = (max_close - min_close) / min_close * 100
    is_consolidation = amplitude < consolidation_amplitude

    # ====== 输出信号类型 ======
    if is_consolidation and is_volume_surge:
        return "BOTH"
    elif is_volume_surge:
        return "VOLUME_BREAKOUT"
    else:
        return None
