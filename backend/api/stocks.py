"""股票数据API端点"""
import logging
from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from backend.schemas import KLineDataResponse
from backend.services.data_service import DataService
from backend.analysis.technical import compute_ma

logger = logging.getLogger(__name__)

router = APIRouter()
data_service = DataService()


def _get_latest_trade_date() -> str:
    """获取最新交易日日期字符串（YYYY-MM-DD）"""
    import baostock as bs
    today = date.today()
    try:
        rs = bs.query_trade_dates(
            start_date=(today - timedelta(days=15)).strftime("%Y-%m-%d"),
            end_date=today.strftime("%Y-%m-%d"),
        )
        trade_dates = []
        while (rs.error_code == '0') and rs.next():
            row = rs.get_row_data()
            if row[1] == '1':
                trade_dates.append(row[0])
        if trade_dates:
            return trade_dates[-1]
    except Exception as e:
        logger.warning(f"获取最新交易日失败: {e}")
    # 降级：返回最近的工作日
    d = today
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.strftime("%Y-%m-%d")


@router.get("/list")
async def get_stock_list(
    keyword: Optional[str] = Query(None, description="股票代码或名称模糊搜索"),
    scan_date: Optional[str] = Query(None, description="数据日期，格式YYYY-MM-DD，默认最新交易日"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: Optional[str] = Query(None, description="排序字段，支持组合排序，逗号分隔。如: change_pct,-volume,turnover"),
):
    """
    获取股票列表，支持按代码/名称模糊搜索、日期过滤和组合排序。

    排序规则：
    - sort_by 支持字段: change_pct(涨跌幅), volume(成交量), turnover(换手率)
    - 字段前加 '-' 表示倒序(降序)，不加表示正序(升序)
    - 多字段用逗号分隔，优先级从左到右
    - 示例: sort_by=change_pct (涨跌幅升序)
    - 示例: sort_by=-change_pct (涨跌幅降序)
    - 示例: sort_by=-change_pct,volume (先按涨跌幅降序，再按成交量升序)
    """
    # 获取股票池
    stock_pool = data_service.get_stock_pool()
    if not stock_pool:
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "scan_date": None}

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

    # 默认使用最新交易日作为日期过滤条件
    if scan_date:
        try:
            target_date = date.fromisoformat(scan_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为YYYY-MM-DD")
        actual_scan_date = scan_date
    else:
        actual_scan_date = _get_latest_trade_date()
        target_date = date.fromisoformat(actual_scan_date)

    # 为所有过滤后的股票补充价格数据（排序前需要完整数据）
    items = []
    for r in results:
        item = {
            "stock_code": r["code"],
            "stock_name": r["name"],
            "latest_price": None,
            "change_pct": None,
            "volume": None,
            "turnover": None,
            "data_date": None,
        }

        kline = data_service.get_daily_kline(r["code"], days=10)
        if kline is not None and not kline.empty:
            # 查找指定日期的数据
            date_match = kline[kline["date"].dt.date == target_date]
            if not date_match.empty:
                row = date_match.iloc[-1]
                item["latest_price"] = round(float(row["close"]), 2)
                item["change_pct"] = round(float(row["change_pct"]), 2) if "change_pct" in row.index and row["change_pct"] == row["change_pct"] else None
                item["volume"] = int(row["volume"])
                item["turnover"] = round(float(row["turnover"]), 2) if "turnover" in row.index and row["turnover"] == row["turnover"] else None
                item["data_date"] = actual_scan_date

        # 只保留有该日期数据的股票
        if item["data_date"] is not None:
            items.append(item)

    # 组合排序
    if sort_by:
        sort_fields = _parse_sort_fields(sort_by)
        if sort_fields:
            items = _multi_sort(items, sort_fields)

    total = len(items)

    # 分页
    start = (page - 1) * page_size
    end = start + page_size
    paged_items = items[start:end]

    return {
        "items": paged_items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "scan_date": actual_scan_date,
    }


# 允许排序的字段白名单
SORTABLE_FIELDS = {"change_pct", "volume", "turnover"}


def _parse_sort_fields(sort_by: str) -> list[tuple[str, bool]]:
    """
    解析排序参数，返回 [(field, ascending), ...] 列表
    字段前加 '-' 表示降序
    """
    sort_fields = []
    for part in sort_by.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("-"):
            field = part[1:]
            ascending = False
        else:
            field = part
            ascending = True
        if field in SORTABLE_FIELDS:
            sort_fields.append((field, ascending))
    return sort_fields


def _multi_sort(items: list[dict], sort_fields: list[tuple[str, bool]]) -> list[dict]:
    """
    多字段组合排序
    sort_fields: [(field, ascending), ...]
    None值排在最后
    """
    from functools import cmp_to_key

    def compare(a, b):
        for field, ascending in sort_fields:
            val_a = a.get(field)
            val_b = b.get(field)
            # None值排在最后
            if val_a is None and val_b is None:
                continue
            if val_a is None:
                return 1
            if val_b is None:
                return -1
            if val_a < val_b:
                return -1 if ascending else 1
            elif val_a > val_b:
                return 1 if ascending else -1
        return 0

    return sorted(items, key=cmp_to_key(compare))


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
