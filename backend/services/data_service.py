"""数据服务层 - 封装BaoStock数据获取与缓存"""
import logging
import time
import pickle
from datetime import date, datetime, timedelta
from pathlib import Path
from functools import wraps
from typing import Optional

import re
import baostock as bs
import pandas as pd
import numpy as np

from backend.config import settings

logger = logging.getLogger(__name__)


# ============================================================
# BaoStock 登录管理
# BaoStock 是免费开源的证券数据接口，无需注册、无反爬限制
# ============================================================
_bs_logged_in = False


def _ensure_bs_login():
    """确保 BaoStock 已登录"""
    global _bs_logged_in
    if not _bs_logged_in:
        lg = bs.login()
        if lg.error_code == '0':
            logger.info("BaoStock 登录成功")
            _bs_logged_in = True
        else:
            logger.error(f"BaoStock 登录失败: {lg.error_msg}")
            raise RuntimeError(f"BaoStock 登录失败: {lg.error_msg}")


def _bs_logout():
    """登出 BaoStock"""
    global _bs_logged_in
    if _bs_logged_in:
        bs.logout()
        _bs_logged_in = False


def _code_to_bs(code: str) -> str:
    """将纯数字股票代码转换为 BaoStock 格式 (sh.600000 / sz.000001)"""
    if code.startswith(("sh.", "sz.")):
        return code
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    else:
        return f"sz.{code}"


def _code_from_bs(bs_code: str) -> str:
    """将 BaoStock 格式代码转换为纯数字代码"""
    if "." in bs_code:
        return bs_code.split(".")[1]
    return bs_code



def retry(max_retries: int = 3, base_delay: float = 1.0):
    """BaoStock调用重试装饰器"""
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
                    # 重试时重新登录
                    global _bs_logged_in
                    _bs_logged_in = False
                    try:
                        _ensure_bs_login()
                    except Exception:
                        pass
            return None
        return wrapper
    return decorator


class DataService:
    """统一数据获取服务，带日级缓存（基于BaoStock）"""

    def __init__(self):
        self._cache_dir = settings.CACHE_DIR
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        _ensure_bs_login()

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
        _ensure_bs_login()

        # 通过 BaoStock 获取全部 A 股列表
        rs = bs.query_stock_basic(code_name="", code="")
        stock_list = []
        while (rs.error_code == '0') and rs.next():
            row = rs.get_row_data()
            stock_list.append(row)

        if not stock_list:
            logger.error("BaoStock 获取股票列表为空")
            return []

        df = pd.DataFrame(stock_list, columns=rs.fields)

        # 只保留 A 股（type=1 股票，status=1 上市）
        df = df[(df["type"] == "1") & (df["status"] == "1")]

        # 排除ST、*ST、退市股票（需转义正则特殊字符）
        exclude_pattern = "|".join(re.escape(x) for x in settings.STOCK_POOL_EXCLUDE)
        df = df[~df["code_name"].str.contains(exclude_pattern, na=False)]

        # 转为纯数字代码
        codes = [_code_from_bs(c) for c in df["code"].tolist()]

        self._save_cache("stock_pool", codes)
        logger.info(f"股票池获取完成，共{len(codes)}只股票")
        return codes

    @retry(max_retries=3)
    def get_stock_spot(self) -> pd.DataFrame:
        """
        获取全部A股行情数据（日级缓存）
        BaoStock不提供实时行情，使用最近交易日的收盘数据替代
        返回包含代码、名称、最新价、市值等的DataFrame
        """
        cached = self._load_cache("stock_spot")
        if cached is not None:
            return cached

        logger.info("正在获取A股行情数据（BaoStock最近交易日）...")
        _ensure_bs_login()

        # 获取全部股票基本信息
        rs = bs.query_stock_basic(code_name="", code="")
        stock_list = []
        while (rs.error_code == '0') and rs.next():
            row = rs.get_row_data()
            stock_list.append(row)

        if not stock_list:
            return pd.DataFrame()

        df_basic = pd.DataFrame(stock_list, columns=rs.fields)
        df_basic = df_basic[(df_basic["type"] == "1") & (df_basic["status"] == "1")]

        # 获取最近交易日
        today_str = date.today().strftime("%Y-%m-%d")
        rs_trade = bs.query_trade_dates(start_date=(date.today() - timedelta(days=10)).strftime("%Y-%m-%d"),
                                         end_date=today_str)
        trade_dates = []
        while (rs_trade.error_code == '0') and rs_trade.next():
            row = rs_trade.get_row_data()
            if row[1] == '1':  # is_trading_day
                trade_dates.append(row[0])

        if not trade_dates:
            latest_trade_date = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
        else:
            latest_trade_date = trade_dates[-1]

        # 使用 query_all_stock 获取当日所有股票行情概览
        rs_all = bs.query_all_stock(day=latest_trade_date)
        all_stocks = []
        while (rs_all.error_code == '0') and rs_all.next():
            all_stocks.append(rs_all.get_row_data())

        if all_stocks:
            df_all = pd.DataFrame(all_stocks, columns=rs_all.fields)
            # 只保留 A 股
            df_all = df_all[df_all["code"].str.match(r"^(sh\.6|sz\.0|sz\.3)")]
        else:
            df_all = pd.DataFrame()

        # 构建兼容的 spot DataFrame
        result_rows = []
        for _, row in df_basic.iterrows():
            bs_code = row["code"]
            pure_code = _code_from_bs(bs_code)
            name = row.get("code_name", "")
            r = {
                "代码": pure_code,
                "名称": name,
                "最新价": 0,
                "总市值": 0,
                "市盈率-动态": 0,
                "市净率": 0,
                "换手率": 0,
            }
            # 如果有行情数据，合并 tradeStatus
            if not df_all.empty:
                match = df_all[df_all["code"] == bs_code]
                if not match.empty:
                    trade_row = match.iloc[0]
                    r["最新价"] = float(trade_row.get("close", 0) or 0)
            result_rows.append(r)

        spot_df = pd.DataFrame(result_rows)
        self._save_cache("stock_spot", spot_df)
        return spot_df

    @retry(max_retries=3)
    def get_daily_kline(self, code: str, days: int = 250) -> Optional[pd.DataFrame]:
        """
        获取单只股票日K线数据（前复权）
        返回DataFrame: [date, open, close, high, low, volume, amount, turnover, change_pct]
        """
        cache_key = f"kline_{code}_{days}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        try:
            _ensure_bs_login()
            end_date = date.today().strftime("%Y-%m-%d")
            start_date = (date.today() - timedelta(days=int(days * 1.5))).strftime("%Y-%m-%d")
            bs_code = _code_to_bs(code)

            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume,amount,turn,pctChg",
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag="2",  # 前复权
            )

            data_list = []
            while (rs.error_code == '0') and rs.next():
                data_list.append(rs.get_row_data())

            if not data_list:
                return None

            df = pd.DataFrame(data_list, columns=rs.fields)

            # 转换数据类型
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # 标准化列名（与原接口保持一致）
            df = df.rename(columns={
                "high": "high",
                "low": "low",
                "open": "open",
                "close": "close",
                "volume": "volume",
                "amount": "amount",
                "turn": "turnover",
                "pctChg": "change_pct",
            })

            # 过滤无效数据（停牌日 volume=0）
            df = df[df["volume"] > 0]
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
            _ensure_bs_login()
            bs_code = _code_to_bs(code)

            # 获取实时行情中的基本信息
            spot_df = self.get_stock_spot()
            name = ""
            current_price = 0
            if spot_df is not None:
                stock_row = spot_df[spot_df["代码"] == code]
                if not stock_row.empty:
                    row = stock_row.iloc[0]
                    name = row.get("名称", "")
                    current_price = row.get("最新价", 0)

            result = {
                "code": code,
                "name": name,
                "pe": 0,
                "pb": 0,
                "market_cap": 0,
                "current_price": current_price,
                "turnover": 0,
                "dividend_yield": 0,
                "debt_ratio": 0,
                "profit_growth_3y": 0,
            }

            # 通过 BaoStock 获取季频盈利能力数据
            year = date.today().year
            quarter = (date.today().month - 1) // 3
            if quarter == 0:
                year -= 1
                quarter = 4

            # 尝试获取最近几个季度的数据
            for q_offset in range(4):
                q = quarter - q_offset
                y = year
                while q <= 0:
                    q += 4
                    y -= 1
                rs_profit = bs.query_profit_data(code=bs_code, year=y, quarter=q)
                profit_list = []
                while (rs_profit.error_code == '0') and rs_profit.next():
                    profit_list.append(rs_profit.get_row_data())
                if profit_list:
                    df_profit = pd.DataFrame(profit_list, columns=rs_profit.fields)
                    if not df_profit.empty:
                        latest = df_profit.iloc[-1]
                        result["debt_ratio"] = float(latest.get("liabilityToAsset", 0) or 0) / 100.0
                    break

            # 获取估值数据（PE/PB）通过 query_dupont_data 或直接用 K 线计算
            # BaoStock 提供 query_stock_industry 获取行业
            rs_ind = bs.query_stock_industry(code=bs_code)
            ind_list = []
            while (rs_ind.error_code == '0') and rs_ind.next():
                ind_list.append(rs_ind.get_row_data())
            if ind_list:
                df_ind = pd.DataFrame(ind_list, columns=rs_ind.fields)
                if not df_ind.empty:
                    result["industry"] = df_ind.iloc[-1].get("industry", "")

            # 获取股息率数据通过 query_dividend_data
            rs_div = bs.query_dividend_data(code=bs_code, year=str(year), yearType="report")
            div_list = []
            while (rs_div.error_code == '0') and rs_div.next():
                div_list.append(rs_div.get_row_data())
            if div_list and current_price > 0:
                df_div = pd.DataFrame(div_list, columns=rs_div.fields)
                # 计算年度股息率
                total_dividend = df_div["perStockDiv"].astype(float).sum()
                result["dividend_yield"] = total_dividend / current_price if current_price > 0 else 0

            self._save_cache(cache_key, result)
            return result

        except Exception as e:
            logger.debug(f"获取{code}基本面失败: {e}")
            return None

    @retry(max_retries=3)
    def get_shenwan_sectors(self) -> Optional[pd.DataFrame]:
        """
        获取申万一级行业分类及成分股数据
        BaoStock 提供行业分类查询，通过 query_stock_industry 获取
        返回DataFrame: [板块代码, 板块名称, ...]
        """
        cached = self._load_cache("shenwan_sectors")
        if cached is not None:
            return cached

        try:
            _ensure_bs_login()
            # BaoStock 通过 query_stock_industry 获取行业分类
            # 获取股票池中所有股票的行业信息
            stock_pool = self.get_stock_pool()
            if not stock_pool:
                return None

            # 抽样获取行业信息（全量太慢）
            sample_codes = stock_pool[:500]
            industry_map = {}

            for code in sample_codes:
                bs_code = _code_to_bs(code)
                rs_ind = bs.query_stock_industry(code=bs_code)
                while (rs_ind.error_code == '0') and rs_ind.next():
                    row = rs_ind.get_row_data()
                    ind_name = row[3] if len(row) > 3 else ""  # industry 字段
                    ind_code = row[2] if len(row) > 2 else ""  # industryClassification
                    if ind_name and ind_name not in industry_map:
                        industry_map[ind_name] = {
                            "板块代码": ind_code or ind_name,
                            "板块名称": ind_name,
                            "stock_count": 0,
                        }
                    if ind_name:
                        industry_map[ind_name]["stock_count"] = \
                            industry_map.get(ind_name, {}).get("stock_count", 0) + 1

            if not industry_map:
                return None

            df = pd.DataFrame(list(industry_map.values()))
            self._save_cache("shenwan_sectors", df)
            return df

        except Exception as e:
            logger.warning(f"获取行业数据失败: {e}")
            return None

    @retry(max_retries=3)
    def get_sector_constituents(self, sector_code: str) -> Optional[list]:
        """获取行业板块成分股代码列表"""
        cache_key = f"sector_cons_{sector_code}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        try:
            _ensure_bs_login()
            # 通过遍历股票池获取属于该行业的股票
            stock_pool = self.get_stock_pool()
            if not stock_pool:
                return None

            codes_in_sector = []
            for code in stock_pool:
                bs_code = _code_to_bs(code)
                rs_ind = bs.query_stock_industry(code=bs_code)
                while (rs_ind.error_code == '0') and rs_ind.next():
                    row = rs_ind.get_row_data()
                    ind_name = row[3] if len(row) > 3 else ""
                    ind_code = row[2] if len(row) > 2 else ""
                    if ind_name == sector_code or ind_code == sector_code:
                        codes_in_sector.append(code)
                        break

            if codes_in_sector:
                self._save_cache(cache_key, codes_in_sector)
            return codes_in_sector if codes_in_sector else None

        except Exception as e:
            logger.debug(f"获取板块{sector_code}成分股失败: {e}")
        return None

    @retry(max_retries=3)
    def get_sector_history(self, sector_code: str, days: int = 60) -> Optional[pd.DataFrame]:
        """
        获取板块历史数据
        BaoStock 不直接支持行业指数K线，通过成分股均值模拟
        """
        cache_key = f"sector_hist_{sector_code}_{days}"
        cached = self._load_cache(cache_key)
        if cached is not None:
            return cached

        try:
            # 获取该板块成分股
            constituents = self.get_sector_constituents(sector_code)
            if not constituents:
                return None

            # 取前10只成分股的K线计算板块均值
            sample = constituents[:10]
            all_klines = []
            for code in sample:
                kdf = self.get_daily_kline(code, days)
                if kdf is not None and not kdf.empty:
                    kdf = kdf[["date", "close", "change_pct"]].copy()
                    kdf = kdf.rename(columns={"close": f"close_{code}", "change_pct": f"pct_{code}"})
                    all_klines.append(kdf)

            if not all_klines:
                return None

            # 合并数据，按日期取均值
            merged = all_klines[0][["date"]].copy()
            for kdf in all_klines:
                merged = merged.merge(kdf, on="date", how="outer")

            merged = merged.sort_values("date").reset_index(drop=True)

            # 计算板块平均涨跌幅
            pct_cols = [c for c in merged.columns if c.startswith("pct_")]
            close_cols = [c for c in merged.columns if c.startswith("close_")]

            df_result = pd.DataFrame()
            df_result["date"] = merged["date"]
            df_result["close"] = merged[close_cols].mean(axis=1) if close_cols else 0
            df_result["change_pct"] = merged[pct_cols].mean(axis=1) if pct_cols else 0

            df_result = df_result.dropna(subset=["close"]).tail(days).reset_index(drop=True)
            self._save_cache(cache_key, df_result)
            return df_result

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
            _ensure_bs_login()
            date_str = check_date.strftime("%Y-%m-%d")
            rs = bs.query_trade_dates(start_date=date_str, end_date=date_str)
            while (rs.error_code == '0') and rs.next():
                row = rs.get_row_data()
                return row[1] == '1'  # is_trading_day
        except Exception:
            pass
        # 降级：仅判断工作日
        return check_date.weekday() < 5
