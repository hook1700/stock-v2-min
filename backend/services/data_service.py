"""数据服务层 - 从SQLite数据库获取数据供策略使用"""
import logging
from datetime import date, timedelta
from typing import Optional

import pandas as pd
import numpy as np
from sqlalchemy import text

from backend.config import settings
from backend.database import SessionLocal

logger = logging.getLogger(__name__)


class DataService:
    """统一数据获取服务（基于SQLite，数据由定时脚本预先写入）"""

    def __init__(self):
        pass

    def _get_session(self):
        return SessionLocal()

    def get_stock_pool(self) -> list[str]:
        """
        从stock_pool表获取全部A股股票池（排除ST/退市）
        返回股票代码列表
        """
        session = self._get_session()
        try:
            result = session.execute(
                text("SELECT stock_code FROM stock_pool ORDER BY stock_code")
            )
            codes = [row[0] for row in result]
            if codes:
                logger.info(f"从数据库加载股票池，共{len(codes)}只股票")
            else:
                logger.warning("数据库股票池为空，请先运行 fetch_and_sync.py 拉取数据")
            return codes
        except Exception as e:
            logger.error(f"查询股票池失败: {e}")
            return []
        finally:
            session.close()

    def get_stock_spot(self) -> pd.DataFrame:
        """
        获取全部A股行情数据（最近交易日收盘数据）
        从stock_daily_data表取最近一个交易日的数据
        """
        session = self._get_session()
        try:
            # 获取最近交易日
            result = session.execute(
                text("SELECT MAX(trade_date) FROM stock_daily_data")
            )
            latest_date = result.scalar()
            if latest_date is None:
                logger.warning("stock_daily_data表为空")
                return pd.DataFrame()

            # 查询该日所有股票数据
            result = session.execute(
                text("""
                    SELECT stock_code, stock_name, close, volume, amount, change_pct, turnover
                    FROM stock_daily_data
                    WHERE trade_date = :d
                    ORDER BY stock_code
                """),
                {"d": latest_date}
            )
            rows = result.fetchall()
            if not rows:
                return pd.DataFrame()

            spot_df = pd.DataFrame(rows, columns=[
                "代码", "名称", "最新价", "成交量", "成交额", "涨跌幅", "换手率"
            ])
            # 补充兼容字段
            spot_df["总市值"] = 0
            spot_df["市盈率-动态"] = 0
            spot_df["市净率"] = 0

            logger.info(f"行情数据加载完成（{latest_date}），共{len(spot_df)}只股票")
            return spot_df
        except Exception as e:
            logger.error(f"查询行情数据失败: {e}")
            return pd.DataFrame()
        finally:
            session.close()

    def get_daily_kline(self, code: str, days: int = 250) -> Optional[pd.DataFrame]:
        """
        从stock_daily_data表获取单只股票日K线数据（前复权）
        返回DataFrame: [date, open, close, high, low, volume, amount, turnover, change_pct]
        """
        session = self._get_session()
        try:
            # 查询该股票最近N天的数据
            result = session.execute(
                text("""
                    SELECT trade_date, open, high, low, close, volume, amount, turnover, change_pct
                    FROM stock_daily_data
                    WHERE stock_code = :code AND volume > 0
                    ORDER BY trade_date DESC
                    LIMIT :limit
                """),
                {"code": code, "limit": days}
            )
            rows = result.fetchall()

            if not rows:
                return None

            df = pd.DataFrame(rows, columns=[
                "date", "open", "high", "low", "close", "volume", "amount", "turnover", "change_pct"
            ])

            # 转换数据类型
            df["date"] = pd.to_datetime(df["date"])
            for col in ["open", "high", "low", "close", "volume", "amount", "turnover", "change_pct"]:
                df[col] = pd.to_numeric(df[col], errors="coerce")

            # 按日期正序排列
            df = df.sort_values("date").reset_index(drop=True)

            return df

        except Exception as e:
            logger.debug(f"获取{code}K线失败: {e}")
            return None
        finally:
            session.close()

    def get_stock_name(self, code: str) -> str:
        """获取股票名称"""
        session = self._get_session()
        try:
            result = session.execute(
                text("SELECT stock_name FROM stock_pool WHERE stock_code = :code"),
                {"code": code}
            )
            row = result.fetchone()
            if row:
                return row[0]
        except Exception:
            pass
        finally:
            session.close()
        return code

    def get_fundamentals(self, code: str) -> Optional[dict]:
        """
        获取股票基本面数据
        从数据库K线数据中近似计算，基础数据由fetch脚本写入
        """
        session = self._get_session()
        try:
            # 获取股票名称和行业
            pool_result = session.execute(
                text("SELECT stock_name, industry FROM stock_pool WHERE stock_code = :code"),
                {"code": code}
            )
            pool_row = pool_result.fetchone()
            name = pool_row[0] if pool_row else ""
            industry = pool_row[1] if pool_row else ""

            # 获取最新收盘价
            price_result = session.execute(
                text("""
                    SELECT close, turnover FROM stock_daily_data
                    WHERE stock_code = :code AND volume > 0
                    ORDER BY trade_date DESC LIMIT 1
                """),
                {"code": code}
            )
            price_row = price_result.fetchone()
            current_price = float(price_row[0]) if price_row and price_row[0] else 0
            turnover = float(price_row[1]) if price_row and price_row[1] else 0

            result = {
                "code": code,
                "name": name,
                "pe": 0,
                "pb": 0,
                "market_cap": 0,
                "current_price": current_price,
                "turnover": turnover,
                "dividend_yield": 0,
                "debt_ratio": 0,
                "profit_growth_3y": 0,
                "industry": industry,
            }

            # 尝试从 stock_fundamentals 表获取更多数据（如果有的话）
            try:
                fund_result = session.execute(
                    text("""
                        SELECT pe, pb, dividend_yield, debt_ratio, market_cap
                        FROM stock_fundamentals
                        WHERE stock_code = :code
                        ORDER BY updated_at DESC LIMIT 1
                    """),
                    {"code": code}
                )
                fund_row = fund_result.fetchone()
                if fund_row:
                    result["pe"] = float(fund_row[0] or 0)
                    result["pb"] = float(fund_row[1] or 0)
                    result["dividend_yield"] = float(fund_row[2] or 0)
                    result["debt_ratio"] = float(fund_row[3] or 0)
                    result["market_cap"] = float(fund_row[4] or 0)
            except Exception:
                # stock_fundamentals 表可能不存在，忽略
                pass

            return result

        except Exception as e:
            logger.debug(f"获取{code}基本面失败: {e}")
            return None
        finally:
            session.close()

    def get_shenwan_sectors(self) -> Optional[pd.DataFrame]:
        """
        获取申万一级行业分类数据
        从stock_pool表的industry字段聚合
        """
        session = self._get_session()
        try:
            result = session.execute(
                text("""
                    SELECT industry, COUNT(*) as stock_count
                    FROM stock_pool
                    WHERE industry IS NOT NULL AND industry != ''
                    GROUP BY industry
                    ORDER BY stock_count DESC
                """)
            )
            rows = result.fetchall()
            if not rows:
                return None

            df = pd.DataFrame(rows, columns=["板块名称", "stock_count"])
            df["板块代码"] = df["板块名称"]
            return df[["板块代码", "板块名称", "stock_count"]]

        except Exception as e:
            logger.warning(f"获取行业数据失败: {e}")
            return None
        finally:
            session.close()

    def get_sector_constituents(self, sector_code: str) -> Optional[list]:
        """获取行业板块成分股代码列表"""
        session = self._get_session()
        try:
            result = session.execute(
                text("""
                    SELECT stock_code FROM stock_pool
                    WHERE industry = :sector
                    ORDER BY stock_code
                """),
                {"sector": sector_code}
            )
            codes = [row[0] for row in result]
            return codes if codes else None
        except Exception as e:
            logger.debug(f"获取板块{sector_code}成分股失败: {e}")
            return None
        finally:
            session.close()

    def get_sector_history(self, sector_code: str, days: int = 60) -> Optional[pd.DataFrame]:
        """
        获取板块历史数据
        通过成分股均值模拟板块走势
        """
        try:
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

            pct_cols = [c for c in merged.columns if c.startswith("pct_")]
            close_cols = [c for c in merged.columns if c.startswith("close_")]

            df_result = pd.DataFrame()
            df_result["date"] = merged["date"]
            df_result["close"] = merged[close_cols].mean(axis=1) if close_cols else 0
            df_result["change_pct"] = merged[pct_cols].mean(axis=1) if pct_cols else 0

            df_result = df_result.dropna(subset=["close"]).tail(days).reset_index(drop=True)
            return df_result

        except Exception as e:
            logger.debug(f"获取板块{sector_code}历史失败: {e}")
            return None

    def is_trading_day(self, check_date: date = None) -> bool:
        """判断是否为交易日（从数据库判断）"""
        if check_date is None:
            check_date = date.today()

        # 周末直接返回False
        if check_date.weekday() >= 5:
            return False

        session = self._get_session()
        try:
            # 检查数据库中该日期是否有数据
            result = session.execute(
                text("""
                    SELECT COUNT(*) FROM stock_daily_data
                    WHERE trade_date = :d
                    LIMIT 1
                """),
                {"d": check_date}
            )
            count = result.scalar()
            if count and count > 0:
                return True

            # 如果数据库中没有该日期数据，可能是还没拉取
            # 回退逻辑：检查最近5天是否有数据（说明数据库有效）
            result2 = session.execute(
                text("""
                    SELECT MAX(trade_date) FROM stock_daily_data
                    WHERE trade_date <= :d
                """),
                {"d": check_date}
            )
            max_date = result2.scalar()
            if max_date is None:
                # 数据库完全为空，降级为仅判断工作日
                return check_date.weekday() < 5

            # 如果查询日期就是数据库中最新日期（今天数据已入库），就是交易日
            # 否则如果是工作日，也认为是交易日（今天数据可能尚未入库）
            return check_date.weekday() < 5

        except Exception:
            return check_date.weekday() < 5
        finally:
            session.close()
