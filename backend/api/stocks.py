"""股票数据API端点"""
from fastapi import APIRouter, HTTPException

from backend.schemas import KLineDataResponse
from backend.services.data_service import DataService
from backend.analysis.technical import compute_ma

router = APIRouter()
data_service = DataService()


@router.get("/{code}/kline", response_model=KLineDataResponse)
async def get_stock_kline(code: str, days: int = 180):
    """获取股票K线数据"""
    if days < 10 or days > 500:
        raise HTTPException(status_code=400, detail="days参数范围: 10-500")

    df = data_service.get_daily_kline(code, days=days)
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail=f"未找到股票{code}的K线数据")

    stock_name = data_service.get_stock_name(code)

    # 转换K线数据格式
    kline_data = []
    for _, row in df.iterrows():
        kline_data.append([
            row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"]),
            round(row["open"], 2),
            round(row["close"], 2),
            round(row["low"], 2),
            round(row["high"], 2),
            int(row["volume"]),
        ])

    # 计算均线数据
    ma_data = {}
    for period in [5, 10, 20, 60]:
        ma = compute_ma(df["close"], period)
        ma_data[f"ma{period}"] = [
            round(v, 2) if not (v != v) else None  # NaN check
            for v in ma.values
        ]

    return KLineDataResponse(
        stock_code=code,
        stock_name=stock_name,
        data=kline_data,
        ma_data=ma_data,
    )


@router.get("/{code}/info")
async def get_stock_info(code: str):
    """获取股票基本信息"""
    fund = data_service.get_fundamentals(code)
    if fund is None:
        raise HTTPException(status_code=404, detail=f"未找到股票{code}的信息")

    return fund
