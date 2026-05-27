"""股票数据API端点"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import KLineDataResponse
from backend.services.data_service import DataService
from backend.analysis.technical import compute_ma

router = APIRouter()
data_service = DataService()


@router.get("/list")
async def get_stock_list(
    keyword: Optional[str] = Query(None, description="股票代码或名称模糊搜索"),
    scan_date: Optional[str] = Query(None, description="数据日期，格式YYYY-MM-DD"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
):
    """
    获取股票列表，支持按代码/名称模糊搜索和日期过滤
    """
    # 获取股票池
    stock_pool = data_service.get_stock_pool()
    if not stock_pool:
        return {"items": [], "total": 0, "page": page, "page_size": page_size}

    # 获取spot数据（包含名称）
    spot_df = data_service.get_stock_spot()

    # 构建股票列表
    results = []
    for code in stock_pool:
        name = ""
        if spot_df is not None and not spot_df.empty:
            match = spot_df[spot_df["代码"] == code]
            if not match.empty:
                name = match.iloc[0]["名称"]

        results.append({"code": code, "name": name})

    # 关键词过滤（代码或名称模糊匹配）
    if keyword:
        keyword_lower = keyword.lower()
        results = [
            r for r in results
            if keyword_lower in r["code"].lower() or keyword_lower in r["name"].lower()
        ]

    # 如果指定了日期，获取该日期的K线收盘价
    target_date = None
    if scan_date:
        try:
            target_date = date.fromisoformat(scan_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为YYYY-MM-DD")

    total = len(results)

    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    paged_results = results[start:end]

    # 为分页结果补充价格数据
    items = []
    for r in paged_results:
        item = {
            "stock_code": r["code"],
            "stock_name": r["name"],
            "latest_price": None,
            "change_pct": None,
            "volume": None,
            "turnover": None,
            "data_date": None,
        }

        # 获取K线数据
        kline = data_service.get_daily_kline(r["code"], days=10)
        if kline is not None and not kline.empty:
            if target_date:
                # 查找指定日期的数据
                date_match = kline[kline["date"].dt.date == target_date]
                if not date_match.empty:
                    row = date_match.iloc[-1]
                    item["latest_price"] = round(float(row["close"]), 2)
                    item["change_pct"] = round(float(row["change_pct"]), 2) if "change_pct" in row else None
                    item["volume"] = int(row["volume"])
                    item["turnover"] = round(float(row["turnover"]), 2) if "turnover" in row and row["turnover"] == row["turnover"] else None
                    item["data_date"] = target_date.isoformat()
            else:
                # 取最新一天
                row = kline.iloc[-1]
                item["latest_price"] = round(float(row["close"]), 2)
                item["change_pct"] = round(float(row["change_pct"]), 2) if "change_pct" in row else None
                item["volume"] = int(row["volume"])
                item["turnover"] = round(float(row["turnover"]), 2) if "turnover" in row and row["turnover"] == row["turnover"] else None
                item["data_date"] = row["date"].strftime("%Y-%m-%d") if hasattr(row["date"], "strftime") else str(row["date"])

        items.append(item)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


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
