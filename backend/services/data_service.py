"""数据服务层 - 封装AKShare数据获取与缓存"""
import logging
import time
import pickle
from datetime import date, datetime, timedelta
from pathlib import Path
from functools import wraps
from typing import Optional

import akshare as ak
import pandas as pd
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


def retry(max_retries: int = 3, base_delay: float = 1.0):
    """AKShare调用重试装饰器"""
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            for attempt in range(max_retries):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    if attempt == max_retries - 1:
                        logger.error(f"{func.__name__} 调用失败（重试{max_retries}次）: {e}")
                        return None
                    wait = base_delay * (2 ** attempt)
                    logger.warning(f"{func.__name__} 第{attempt+1}次失败，{wait}秒后重试: {e}")
                    time.sleep(wait)
            return None
        return wrapper
    return decorator


class DataService:
    """统一数据获取服务，带日级缓存"""

    def __init__(self):
        self._cache_dir = settings.CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_path(self, key: str, cache_date: date = None) -> Path:
        """获取缓存文件路径"""
        if cache_date is None:
            cache_date = date.today()
        return self._cache_dir / f"{key}_{cache_date.isoformat()}.pkl"

    def _load_cache(self, key: str, cache_date: date = None):
        """加载缓存"""
        path = self._get_cache_path(key, cache_date)
        if path.exists():
            try:
                with open(path, "rb") as f:
                    return pickle.load(f)
            except Exception:
                return None
        return None

    def _save_cache(self, key: str, data, cache_date: date = None):
        """保存缓存"""
        path = self._get_cache_path(key, cache_date)
        try:
            with open(path, "wb") as f:
                pickle.dump(data, f)
        except Exception as e:
            logger.warning(f"缓存保存失败 {key}: {e}")

    def _clean_old_cache(self, days: int = 7):
        """清理过期缓存文件"""
        cutoff = datetime.now() - timedelta(days=days)
        for f in self._cache_dir.glob("*.pkl"):
            if datetime.fromtimestamp(f.stat().st_mtime) < cutoff:
                f.unlink()

    @retry(max_retries=3)
    def get_stock_pool(self) -> list[str]:
        """
        获取全部A股股票池（排除ST/退市）
        返回股票代码列表
        """
        cached = self._load_cache("stock_pool")
        if cached is not None:
            return cached

        logger.info("正在获取A股股票池...")
        df = ak.stock_zh_a_spot_em()

        # 排除ST、*ST、退市股票
        exclude_pattern = "|".join(settings.STOCK_POOL_EXCLUDE)
        df = df[~df["名称"].str.contains(exclude_pattern, na=False)]

        # 排除市值过小的股票
        if "总市值" in df.columns:
            df = df[df["总市值"] >= settings.MIN_MARKET_CAP]

        codes = df["代码"].tolist()
        self._save_cache("stock_pool", codes)
        logger.info(f"股票池获取完成，共{len(codes)}只股票")
        return codes

    @retry(max_retries=3)
    def get_stock_spot(self) -> pd.DataFrame:
        """
        获取全部A股实时行情（日级缓存）
        返回包含代码、名称、最新价、市值等的DataFrame
        """
        cached = self._load_cache("stock_spot")
        if cached is not None:
            return cached

        df = ak.stock_zh_a_spot_em()
        self._save_cache("stock_spot", df)
        return df

    @retry(max_retries=3)
    def get_daily_kline(self, code: str, days: int = 250) -> Optional[pd.DataFrame]:
        """
        获取单只股票日K线数据（前复权）
        返回DataFrame: [日期, 开盘, 收盘, 最高, 最低, 成交量, 成交额, 换手率]
        """
        cache_key = f"kline_{code}_{days}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        try:
            end_date = date.today().strftime("%Y%m%d")
            start_date = (date.today() - timedelta(days=int(days * 1.5))).strftime("%Y%m%d")

            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq"
            )

            if df is None or df.empty:
                return None

            # 标准化列名
            df = df.rename(columns={
                "日期": "date",
                "开盘": "open",
                "收盘": "close",
                "最高": "high",
                "最低": "low",
                "成交量": "volume",
                "成交额": "amount",
                "换手率": "turnover",
                "涨跌幅": "change_pct",
                "振幅": "amplitude",
            })

            df["date"] = pd.to_datetime(df["date"])
            df = df.sort_values("date").reset_index(drop=True)

            # 只保留最近N天
            df = df.tail(days).reset_index(drop=True)

            self._save_cache(cache_key, df)
            return df

        except Exception as e:
            logger.debug(f"获取{code}K线失败: {e}")
            return None

    @retry(max_retries=3)
    def get_stock_name(self, code: str) -> str:
        """获取股票名称"""
        try:
            spot_df = self.get_stock_spot()
            if spot_df is not None:
                match = spot_df[spot_df["代码"] == code]
                if not match.empty:
                    return match.iloc[0]["名称"]
        except Exception:
            pass
        return code

    @retry(max_retries=2)
    def get_fundamentals(self, code: str) -> Optional[dict]:
        """
        获取股票基本面数据
        返回: {pe, pb, dividend_yield, debt_ratio, profit_growth_3y, market_cap, industry}
        """
        cache_key = f"fundamental_{code}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        try:
            # 获取实时行情中的PE/PB
            spot_df = self.get_stock_spot()
            if spot_df is None:
                return None

            stock_row = spot_df[spot_df["代码"] == code]
            if stock_row.empty:
                return None

            row = stock_row.iloc[0]
            result = {
                "code": code,
                "name": row.get("名称", ""),
                "pe": row.get("市盈率-动态", 0),
                "pb": row.get("市净率", 0),
                "market_cap": row.get("总市值", 0),
                "current_price": row.get("最新价", 0),
                "turnover": row.get("换手率", 0),
                "dividend_yield": 0,
                "debt_ratio": 0,
                "profit_growth_3y": 0,
            }

            # 尝试获取股息率等更详细信息
            try:
                indicator_df = ak.stock_a_indicator_lg(symbol=code)
                if indicator_df is not None and not indicator_df.empty:
                    latest = indicator_df.iloc[-1]
                    result["pe_ttm"] = latest.get("pe_ttm", result["pe"])
                    result["pb"] = latest.get("pb", result["pb"])
                    result["dividend_yield"] = latest.get("dv_ttm", 0)
                    if result["dividend_yield"]:
                        result["dividend_yield"] = result["dividend_yield"] / 100.0
            except Exception:
                pass

            self._save_cache(cache_key, result)
            return result

        except Exception as e:
            logger.debug(f"获取{code}基本面失败: {e}")
            return None

    @retry(max_retries=3)
    def get_shenwan_sectors(self) -> Optional[pd.DataFrame]:
        """
        获取申万一级行业分类及行情
        返回DataFrame: [板块代码, 板块名称, 涨跌幅, ...]
        """
        cached = self._load_cache("shenwan_sectors")
        if cached is not None:
            return cached

        try:
            # 获取申万一级行业指数实时行情
            df = ak.sw_index_spot()
            if df is not None and not df.empty:
                self._save_cache("shenwan_sectors", df)
                return df
        except Exception as e:
            logger.warning(f"获取申万行业数据失败: {e}")

        # 备用方案
        try:
            df = ak.index_stock_info()
            sw_df = df[df["index_code"].str.startswith("8011")]
            self._save_cache("shenwan_sectors", sw_df)
            return sw_df
        except Exception as e:
            logger.error(f"备用方案获取申万数据也失败: {e}")
            return None

    @retry(max_retries=3)
    def get_sector_constituents(self, sector_code: str) -> Optional[list]:
        """获取申万板块成分股代码列表"""
        cache_key = f"sector_cons_{sector_code}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.sw_index_cons(index_code=sector_code)
            if df is not None and not df.empty:
                codes = df["stock_code"].tolist()
                self._save_cache(cache_key, codes)
                return codes
        except Exception as e:
            logger.debug(f"获取板块{sector_code}成分股失败: {e}")
        return None

    @retry(max_retries=3)
    def get_sector_history(self, sector_code: str, days: int = 60) -> Optional[pd.DataFrame]:
        """获取申万板块指数历史数据"""
        cache_key = f"sector_hist_{sector_code}_{days}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        try:
            df = ak.sw_index_daily(
                index_code=sector_code,
                start_date=(date.today() - timedelta(days=int(days * 1.5))).strftime("%Y%m%d"),
                end_date=date.today().strftime("%Y%m%d"),
            )
            if df is not None and not df.empty:
                df = df.tail(days).reset_index(drop=True)
                self._save_cache(cache_key, df)
                return df
        except Exception as e:
            logger.debug(f"获取板块{sector_code}历史失败: {e}")
        return None

    def is_trading_day(self, check_date: date = None) -> bool:
        """判断是否为交易日"""
        if check_date is None:
            check_date = date.today()

        # 周末直接返回False
        if check_date.weekday() >= 5:
            return False

        try:
            calendar = ak.tool_trade_date_hist_sina()
            trading_dates = set(pd.to_datetime(calendar["trade_date"]).dt.date)
            return check_date in trading_dates
        except Exception:
            # 降级：仅判断工作日
            return check_date.weekday() < 5
