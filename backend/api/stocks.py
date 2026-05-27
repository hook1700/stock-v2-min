"""股票数据API端点"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, desc, asc
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import StockDailyData
from backend.schemas import KLineDataResponse
from backend.services.data_service import DataService
from backend.analysis.technical import compute_ma

logger = logging.getLogger(__name__)

router = APIRouter()
data_service = DataService()

# 允许排序的字段白名单
SORTABLE_FIELDS = {"change_pct", "volume", "turnover"}


@router.get("/list")
async def get_stock_list(
    keyword: Optional[str] = Query(None, description="股票代码或名称模糊搜索"),
    scan_date: Optional[str] = Query(None, description="数据日期，格式YYYY-MM-DD，默认数据库最新日期"),
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    sort_by: Optional[str] = Query(None, description="排序字段，支持组合排序，逗号分隔。如: change_pct,-volume,turnover"),
    db: Session = Depends(get_db),
):
    """
    获取股票列表，直接查询数据库，支持模糊搜索、日期过滤和组合排序。

    排序规则：
    - sort_by 支持字段: change_pct(涨跌幅), volume(成交量), turnover(换手率)
    - 字段前加 '-' 表示倒序(降序)，不加表示正序(升序)
    - 多字段用逗号分隔，优先级从左到右
    - 示例: sort_by=-change_pct (涨跌幅降序)
    - 示例: sort_by=-change_pct,volume (先按涨跌幅降序，再按成交量升序)
    """
    # 确定查询日期：如果未指定，使用数据库中最新的日期
    if scan_date:
        try:
            target_date = date.fromisoformat(scan_date)
        except ValueError:
            raise HTTPException(status_code=400, detail="日期格式错误，应为YYYY-MM-DD")
    else:
        # 获取数据库中最新的交易日期
        latest = db.query(func.max(StockDailyData.trade_date)).scalar()
        if latest is None:
            return {"items": [], "total": 0, "page": page, "page_size": page_size, "scan_date": None}
        target_date = latest

    actual_scan_date = target_date.isoformat() if isinstance(target_date, date) else str(target_date)

    # 构建查询
    query = db.query(StockDailyData).filter(StockDailyData.trade_date == target_date)

    # 关键词过滤
    if keyword:
        keyword_like = f"%{keyword}%"
        query = query.filter(
            (StockDailyData.stock_code.like(keyword_like)) |
            (StockDailyData.stock_name.like(keyword_like))
        )

    # 组合排序
    if sort_by:
        order_clauses = _build_order_clauses(sort_by)
        if order_clauses:
            query = query.order_by(*order_clauses)

    # 获取总数
    total = query.count()

    # 分页
    offset = (page - 1) * page_size
    rows = query.offset(offset).limit(page_size).all()

    # 构建响应
    items = []
    for row in rows:
        items.append({
            "stock_code": row.stock_code,
            "stock_name": row.stock_name,
            "latest_price": round(row.close, 2) if row.close else None,
            "change_pct": round(row.change_pct, 2) if row.change_pct is not None else None,
            "volume": int(row.volume) if row.volume else None,
            "turnover": round(row.turnover, 2) if row.turnover is not None else None,
            "data_date": actual_scan_date,
        })

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "scan_date": actual_scan_date,
    }


@router.get("/dates")
async def get_available_dates(db: Session = Depends(get_db)):
    """获取数据库中可用的交易日期列表（降序）"""
    dates = db.query(StockDailyData.trade_date).distinct().order_by(
        desc(StockDailyData.trade_date)
    ).limit(30).all()
    return {"dates": [d[0].isoformat() for d in dates]}


def _build_order_clauses(sort_by: str):
    """解析排序参数，返回SQLAlchemy排序子句列表"""
    from sqlalchemy import case

    # 字段名到模型属性的映射
    field_map = {
        "change_pct": StockDailyData.change_pct,
        "volume": StockDailyData.volume,
        "turnover": StockDailyData.turnover,
    }

    clauses = []
    for part in sort_by.split(","):
        part = part.strip()
        if not part:
            continue
        if part.startswith("-"):
            field = part[1:]
            direction = desc
        else:
            field = part
            direction = asc

        if field in field_map:
            col = field_map[field]
            # SQLite不支持NULLS LAST，用case表达式将NULL排到最后
            clauses.append(case((col.is_(None), 1), else_=0))
            clauses.append(direction(col))

    return clauses


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
