"""技术分析工具函数"""
import numpy as np
import pandas as pd
from typing import Optional


def compute_ma(close_prices: pd.Series, period: int) -> pd.Series:
    """计算移动平均线"""
    return close_prices.rolling(window=period, min_periods=period).mean()


def compute_ema(close_prices: pd.Series, period: int) -> pd.Series:
    """计算指数移动平均线"""
    return close_prices.ewm(span=period, adjust=False).mean()


def compute_volume_ratio(volumes: pd.Series, period: int = 5) -> pd.Series:
    """计算量比（当日成交量 / 前N日平均成交量）"""
    avg_vol = volumes.rolling(window=period, min_periods=period).mean().shift(1)
    return volumes / avg_vol


def compute_amplitude(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """计算振幅 = (最高 - 最低) / 昨收"""
    prev_close = close.shift(1)
    return (high - low) / prev_close


def compute_change_pct(close: pd.Series) -> pd.Series:
    """计算涨跌幅"""
    return close.pct_change()


def is_limit_up(close: pd.Series, prev_close: pd.Series, threshold: float = 0.095) -> pd.Series:
    """判断是否涨停（涨幅>=9.5%）"""
    change = (close - prev_close) / prev_close
    return change >= threshold


def find_local_extrema(prices: pd.Series, order: int = 5) -> tuple:
    """
    寻找局部极值点
    order: 左右各需要多少个点来确认极值

    返回: (maxima_indices, minima_indices)
    """
    from scipy.signal import argrelextrema

    prices_arr = prices.values

    # 局部最大值
    max_indices = argrelextrema(prices_arr, np.greater_equal, order=order)[0]
    # 局部最小值
    min_indices = argrelextrema(prices_arr, np.less_equal, order=order)[0]

    return max_indices, min_indices


def compute_trend_strength(close: pd.Series, period: int = 20) -> float:
    """
    计算趋势强度（线性回归斜率的标准化）
    返回值 > 0 表示上升趋势，< 0 表示下降趋势
    """
    if len(close) < period:
        return 0.0

    recent = close.tail(period).values
    x = np.arange(len(recent))
    slope = np.polyfit(x, recent, 1)[0]

    # 标准化：用价格均值归一化斜率
    mean_price = np.mean(recent)
    if mean_price == 0:
        return 0.0

    return slope / mean_price * 100  # 百分比形式


def is_bullish_ma_alignment(df: pd.DataFrame, ma_cols: list, tolerance: float = 0.005) -> bool:
    """
    判断均线是否多头排列（允许小幅容差）
    ma_cols: ["ma5", "ma10", "ma20", "ma60"] 从短到长
    tolerance: 允许相邻均线之间的容差比例（默认0.5%），即短均线略低于长均线但差距在容差内也算通过

    规则：至少3对相邻均线满足 短MA >= 长MA * (1 - tolerance)
    """
    if df.empty:
        return False

    latest = df.iloc[-1]
    for col in ma_cols:
        if col not in df.columns or pd.isna(latest[col]):
            return False

    # 统计满足条件的相邻对数
    pairs_ok = 0
    total_pairs = len(ma_cols) - 1

    for i in range(total_pairs):
        short_ma = latest[ma_cols[i]]
        long_ma = latest[ma_cols[i + 1]]
        # 允许短均线略低于长均线（在容差范围内）
        if short_ma >= long_ma * (1 - tolerance):
            pairs_ok += 1

    # 至少3对中有2对满足（即允许1对不满足），或全部满足
    min_required = max(total_pairs - 1, 2)
    return pairs_ok >= min_required


def is_ma_trending_up(df: pd.DataFrame, ma_col: str, lookback: int = 5) -> bool:
    """判断均线是否整体趋势向上（允许个别天走平或微降）"""
    if len(df) < lookback + 1 or ma_col not in df.columns:
        return False

    ma_values = df[ma_col].tail(lookback + 1).values
    # 只要求整体方向向上：末尾值 > 起始值，且中间不低于起始值太多
    if pd.isna(ma_values[0]) or pd.isna(ma_values[-1]):
        return False

    # 整体上升：最后一天的MA > 第一天的MA
    if ma_values[-1] <= ma_values[0]:
        return False

    # 中间允许微幅回落，但不能低于起始值的 99.5%
    min_val = np.nanmin(ma_values)
    if min_val < ma_values[0] * 0.995:
        return False

    return True


def compute_deviation_rate(close: float, ma_value: float) -> float:
    """计算乖离率 = (收盘价 - MA) / MA"""
    if ma_value == 0:
        return 0.0
    return (close - ma_value) / ma_value


def detect_volume_shrink(volumes: pd.Series, lookback: int = 5, threshold: float = 0.6) -> bool:
    """
    检测成交量是否萎缩
    threshold: 当前成交量低于前N日均量的百分比
    """
    if len(volumes) < lookback + 1:
        return False

    current_vol = volumes.iloc[-1]
    avg_vol = volumes.iloc[-(lookback + 1):-1].mean()

    if avg_vol == 0:
        return False

    return current_vol / avg_vol < threshold


def detect_u_shape(prices: np.ndarray, min_depth: float = 0.15) -> Optional[dict]:
    """
    检测U型底部形态
    返回: {left_peak_idx, bottom_idx, right_peak_idx, depth, duration} or None
    """
    if len(prices) < 20:
        return None

    # 找到最高点和最低点
    max_idx = np.argmax(prices)
    min_idx = np.argmin(prices[max_idx:]) + max_idx if max_idx < len(prices) - 1 else -1

    if min_idx <= max_idx:
        return None

    # 检查最低点右侧是否有回升
    right_max_idx = np.argmax(prices[min_idx:]) + min_idx
    if right_max_idx <= min_idx:
        return None

    left_peak = prices[max_idx]
    bottom = prices[min_idx]
    right_peak = prices[right_max_idx]

    # 计算深度
    depth = (left_peak - bottom) / left_peak

    if depth < min_depth:
        return None

    # 检查右侧是否恢复到合理水平（至少恢复到杯深的70%）
    recovery = (right_peak - bottom) / (left_peak - bottom)
    if recovery < 0.7:
        return None

    return {
        "left_peak_idx": max_idx,
        "bottom_idx": min_idx,
        "right_peak_idx": right_max_idx,
        "depth": depth,
        "left_peak_price": left_peak,
        "bottom_price": bottom,
        "right_peak_price": right_peak,
        "duration": right_max_idx - max_idx,
    }
