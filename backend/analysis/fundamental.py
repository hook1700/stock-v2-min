"""基本面分析工具"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def calculate_dividend_yield(annual_dividend: float, current_price: float) -> float:
    """计算股息率"""
    if current_price <= 0:
        return 0.0
    return annual_dividend / current_price


def is_low_valuation(pe: float, pb: float,
                     pe_industry_avg: float = 20.0,
                     pb_industry_avg: float = 2.0) -> bool:
    """判断是否低估值"""
    if pe <= 0 or pb <= 0:
        return False
    return pe < pe_industry_avg and pb < pb_industry_avg


def is_financially_healthy(debt_ratio: float, profit_growth_3y: float) -> bool:
    """
    判断财务是否健康
    条件：资产负债率<60%，3年净利润复合增速>0
    """
    return debt_ratio < 0.60 and profit_growth_3y > 0


def compute_pe_percentile(current_pe: float, pe_history: list) -> float:
    """
    计算当前PE在历史PE中的百分位
    返回 0-1，越低表示越便宜
    """
    if not pe_history or current_pe <= 0:
        return 0.5

    lower_count = sum(1 for pe in pe_history if pe < current_pe)
    return lower_count / len(pe_history)


def composite_dividend_score(dividend_yield: float, pe: float, pb: float,
                             market_cap: float) -> float:
    """
    计算综合红利评分
    权重：股息率30% + 估值30% + 财务健康20% + 市值稳定性20%
    """
    score = 0.0

    # 股息率 (0-0.3)
    if dividend_yield >= 0.08:
        score += 0.30
    elif dividend_yield >= 0.06:
        score += 0.25
    elif dividend_yield >= 0.04:
        score += 0.15

    # 估值 (0-0.3)
    if 0 < pe <= 10:
        score += 0.30
    elif pe <= 15:
        score += 0.20
    elif pe <= 20:
        score += 0.10

    # PB (0-0.2)
    if 0 < pb <= 1:
        score += 0.20
    elif pb <= 2:
        score += 0.10

    # 市值稳定性 (0-0.2)
    if market_cap >= 1e11:
        score += 0.20
    elif market_cap >= 5e10:
        score += 0.15
    elif market_cap >= 1e10:
        score += 0.10

    return min(score, 1.0)
