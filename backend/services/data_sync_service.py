"""数据同步服务 - 从BaoStock拉取数据写入SQLite

支持两种模式：
1. 全量同步（数据库为空时）：拉取股票池 + 250天K线 + 行业分类 + 基本面
2. 增量同步（有数据时）：只拉取最新缺失日期的数据
"""
import re
import logging
import time
from datetime import date, timedelta
from typing import Optional

import baostock as bs
import pandas as pd
from sqlalchemy import text

from backend.config import settings
from backend.database import SessionLocal, engine, Base

logger = logging.getLogger(__name__)

# 股票池过滤关键词
STOCK_POOL_EXCLUDE = ["ST", "*ST", "退市", "退"]


def _code_to_bs(code: str) -> str:
    """纯数字代码 -> BaoStock格式 (sh.600519)"""
    if code.startswith(("sh.", "sz.")):
        return code
    if code.startswith(("6", "9")):
        return f"sh.{code}"
    else:
        return f"sz.{code}"


def _code_from_bs(bs_code: str) -> str:
    """BaoStock格式 -> 纯数字代码"""
    if "." in bs_code:
        return bs_code.split(".")[1]
    return bs_code


class DataSyncService:
    """BaoStock数据同步服务"""

    def __init__(self):
        self._logged_in = False

    def _login(self):
        """登录BaoStock"""
        if self._logged_in:
            return True
        lg = bs.login()
        if lg.error_code != '0':
            logger.error(f"BaoStock登录失败: {lg.error_msg}")
            return False
        self._logged_in = True
        logger.info("BaoStock登录成功")
        return True

    def _logout(self):
        """登出BaoStock"""
        if self._logged_in:
            bs.logout()
            self._logged_in = False
            logger.info("BaoStock已登出")

    def is_db_empty(self) -> bool:
        """检查stock_daily_data表是否为空"""
        session = SessionLocal()
        try:
            result = session.execute(text("SELECT COUNT(*) FROM stock_daily_data LIMIT 1"))
            count = result.scalar()
            return count == 0
        except Exception:
            return True
        finally:
            session.close()

    def is_stock_pool_empty(self) -> bool:
        """检查stock_pool表是否为空"""
        session = SessionLocal()
        try:
            result = session.execute(text("SELECT COUNT(*) FROM stock_pool LIMIT 1"))
            count = result.scalar()
            return count == 0
        except Exception:
            return True
        finally:
            session.close()

    def get_latest_date_in_db(self) -> Optional[date]:
        """获取数据库中最新的交易日期"""
        session = SessionLocal()
        try:
            result = session.execute(text("SELECT MAX(trade_date) FROM stock_daily_data"))
            max_date = result.scalar()
            if max_date is None:
                return None
            if isinstance(max_date, str):
                return date.fromisoformat(max_date)
            return max_date
        except Exception:
            return None
        finally:
            session.close()

    def sync_on_startup(self):
        """启动时同步数据（主入口）"""
        logger.info("=" * 50)
        logger.info("检查数据库状态，准备数据同步...")
        logger.info("=" * 50)

        # 确保表结构存在
        from backend.models import (
            StockPool, StockDailyData, StockRecommendation,
            SectorAnalysis, SectorStockPick, SchedulerLog
        )
        Base.metadata.create_all(bind=engine)

        if self.is_stock_pool_empty() or self.is_db_empty():
            logger.info("数据库为空，执行全量同步...")
            self.sync_full()
        else:
            latest = self.get_latest_date_in_db()
            today = date.today()
            if latest and latest < today:
                logger.info(f"数据库最新日期: {latest}，今日: {today}，执行增量同步...")
                self.sync_incremental()
            else:
                logger.info(f"数据库已是最新 (最新日期: {latest})，跳过同步")

    def sync_full(self):
        """全量同步：股票池 + K线 + 行业 + 基本面"""
        start_time = time.time()

        if not self._login():
            return

        try:
            # Step 1: 获取股票池
            codes = self._fetch_stock_pool()
            if not codes:
                logger.error("获取股票池失败，中止同步")
                return

            # Step 2: 拉取K线数据
            self._fetch_klines(codes, days=settings.KLINE_DAYS)

            # Step 3: 获取行业分类
            self._fetch_sectors(codes)

            # Step 4: 获取基本面数据
            self._fetch_fundamentals(codes)

            duration = time.time() - start_time
            logger.info(f"全量同步完成，耗时 {duration:.1f} 秒")

        except Exception as e:
            logger.error(f"全量同步异常: {e}", exc_info=True)
        finally:
            self._logout()

    def sync_incremental(self):
        """增量同步：只拉取缺失日期的数据"""
        start_time = time.time()

        latest_date = self.get_latest_date_in_db()
        today = date.today()

        if latest_date is None:
            logger.info("数据库无数据，降级为全量同步")
            self.sync_full()
            return

        if latest_date >= today:
            logger.info("数据已是最新，无需同步")
            return

        if not self._login():
            return

        try:
            # 获取股票池（如果为空则重新拉取）
            codes = self._get_stock_pool_codes()
            if not codes:
                codes = self._fetch_stock_pool()
            if not codes:
                logger.error("股票池为空，无法增量同步")
                return

            # 拉取从 latest_date+1 到 today 的K线数据
            start_date_str = (latest_date + timedelta(days=1)).strftime("%Y-%m-%d")
            end_date_str = today.strftime("%Y-%m-%d")
            logger.info(f"增量同步: {start_date_str} ~ {end_date_str}，股票数: {len(codes)}")

            self._fetch_klines_range(codes, start_date_str, end_date_str)

            duration = time.time() - start_time
            logger.info(f"增量同步完成，耗时 {duration:.1f} 秒")

        except Exception as e:
            logger.error(f"增量同步异常: {e}", exc_info=True)
        finally:
            self._logout()

    def _get_stock_pool_codes(self) -> list[str]:
        """从数据库获取已有股票池"""
        session = SessionLocal()
        try:
            result = session.execute(text("SELECT stock_code FROM stock_pool ORDER BY stock_code"))
            return [row[0] for row in result]
        except Exception:
            return []
        finally:
            session.close()

    def _fetch_stock_pool(self) -> list[str]:
        """从BaoStock获取全部A股并写入stock_pool表"""
        logger.info("[1/4] 获取A股股票列表...")

        rs = bs.query_stock_basic(code_name="", code="")
        stock_list = []
        while (rs.error_code == '0') and rs.next():
            stock_list.append(rs.get_row_data())

        if not stock_list:
            logger.error("BaoStock返回空股票列表")
            return []

        df = pd.DataFrame(stock_list, columns=rs.fields)
        # 只保留A股上市状态
        df = df[(df["type"] == "1") & (df["status"] == "1")]

        # 过滤ST/退市
        pattern = "|".join(re.escape(x) for x in STOCK_POOL_EXCLUDE)
        df = df[~df["code_name"].str.contains(pattern, na=False)]

        codes = [_code_from_bs(c) for c in df["code"].tolist()]
        names = df["code_name"].tolist()
        logger.info(f"  股票池: {len(codes)} 只")

        # 写入数据库
        session = SessionLocal()
        try:
            from backend.models import StockPool
            session.execute(text("DELETE FROM stock_pool"))

            today = date.today()
            batch = []
            for i, code in enumerate(codes):
                batch.append({
                    "stock_code": code,
                    "stock_name": names[i] if i < len(names) else "",
                    "industry": "",
                    "updated_at": today,
                })

            if batch:
                from backend.models import StockPool
                session.bulk_insert_mappings(StockPool, batch)
                session.commit()
                logger.info(f"  stock_pool 写入 {len(batch)} 条")
        except Exception as e:
            session.rollback()
            logger.error(f"  stock_pool 写入失败: {e}")
        finally:
            session.close()

        return codes

    def _fetch_klines(self, codes: list[str], days: int = 250):
        """全量拉取K线数据"""
        total = len(codes)
        logger.info(f"[2/4] 拉取K线数据 (共 {total} 只, 每只 {days} 天)...")

        end_date = date.today().strftime("%Y-%m-%d")
        start_date = (date.today() - timedelta(days=int(days * 1.5))).strftime("%Y-%m-%d")

        self._fetch_klines_range(codes, start_date, end_date)

    def _fetch_klines_range(self, codes: list[str], start_date: str, end_date: str):
        """拉取指定日期范围内的K线数据并写入数据库"""
        total = len(codes)

        # 加载名称映射
        session = SessionLocal()
        try:
            result = session.execute(text("SELECT stock_code, stock_name FROM stock_pool"))
            name_map = {row[0]: row[1] for row in result}
        finally:
            session.close()

        ok, fail = 0, 0
        batch_size = 50
        db_rows = []

        for i, code in enumerate(codes, 1):
            try:
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
                    fail += 1
                    continue

                df = pd.DataFrame(data_list, columns=rs.fields)
                df["date"] = pd.to_datetime(df["date"])
                for col in ["open", "high", "low", "close", "volume", "amount", "turn", "pctChg"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")

                # 过滤停牌日
                df = df[df["volume"] > 0]

                stock_name = name_map.get(code, "")
                for _, row in df.iterrows():
                    db_rows.append({
                        "trade_date": row["date"].date() if hasattr(row["date"], "date") else row["date"],
                        "stock_code": code,
                        "stock_name": stock_name,
                        "open": float(row["open"]) if pd.notna(row["open"]) else None,
                        "close": float(row["close"]) if pd.notna(row["close"]) else None,
                        "high": float(row["high"]) if pd.notna(row["high"]) else None,
                        "low": float(row["low"]) if pd.notna(row["low"]) else None,
                        "volume": float(row["volume"]) if pd.notna(row["volume"]) else None,
                        "amount": float(row["amount"]) if pd.notna(row["amount"]) else None,
                        "change_pct": float(row["pctChg"]) if pd.notna(row["pctChg"]) else None,
                        "turnover": float(row["turn"]) if pd.notna(row["turn"]) else None,
                    })

                ok += 1
            except Exception as e:
                fail += 1
                logger.debug(f"  {code} 拉取失败: {e}")

            # 每batch_size只股票提交一次
            if i % batch_size == 0:
                self._flush_kline_batch(db_rows)
                db_rows = []
                logger.info(f"  K线进度: {i}/{total}  成功 {ok}  失败 {fail}")

        # 提交剩余数据
        if db_rows:
            self._flush_kline_batch(db_rows)

        logger.info(f"  K线同步完成: 成功 {ok}  失败 {fail}")

    def _flush_kline_batch(self, rows: list):
        """批量写入K线数据"""
        if not rows:
            return
        session = SessionLocal()
        try:
            for row in rows:
                session.execute(
                    text("""
                        INSERT OR REPLACE INTO stock_daily_data
                        (trade_date, stock_code, stock_name, open, close, high, low,
                         volume, amount, change_pct, turnover)
                        VALUES (:trade_date, :stock_code, :stock_name, :open, :close, :high, :low,
                                :volume, :amount, :change_pct, :turnover)
                    """),
                    row
                )
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"  批量写入K线失败: {e}")
        finally:
            session.close()

    def _fetch_sectors(self, codes: list[str]):
        """获取行业分类信息"""
        logger.info("[3/4] 获取行业分类...")

        try:
            # 抽样获取行业信息（前500只）
            sample_codes = codes[:500]
            industry_data = {}

            for i, code in enumerate(sample_codes):
                try:
                    bs_code = _code_to_bs(code)
                    rs_ind = bs.query_stock_industry(code=bs_code)
                    while (rs_ind.error_code == '0') and rs_ind.next():
                        row = rs_ind.get_row_data()
                        ind_name = row[3] if len(row) > 3 else ""
                        if ind_name:
                            industry_data[code] = ind_name
                except Exception:
                    continue

                if (i + 1) % 100 == 0:
                    logger.info(f"  行业进度: {i+1}/{len(sample_codes)}")

            if not industry_data:
                logger.warning("  未获取到行业数据")
                return

            # 更新数据库
            session = SessionLocal()
            try:
                for code, industry in industry_data.items():
                    session.execute(
                        text("UPDATE stock_pool SET industry = :ind WHERE stock_code = :code"),
                        {"ind": industry, "code": code}
                    )
                session.commit()
                logger.info(f"  行业信息更新 {len(industry_data)} 只股票")
            except Exception as e:
                session.rollback()
                logger.error(f"  行业信息更新失败: {e}")
            finally:
                session.close()

        except Exception as e:
            logger.warning(f"  行业数据拉取失败: {e}")

    def _fetch_fundamentals(self, codes: list[str]):
        """获取基本面数据写入stock_fundamentals表"""
        logger.info("[4/4] 获取基本面数据...")

        # 创建 stock_fundamentals 表
        session = SessionLocal()
        try:
            session.execute(text("""
                CREATE TABLE IF NOT EXISTS stock_fundamentals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    stock_code TEXT NOT NULL,
                    pe REAL DEFAULT 0,
                    pb REAL DEFAULT 0,
                    dividend_yield REAL DEFAULT 0,
                    debt_ratio REAL DEFAULT 0,
                    market_cap REAL DEFAULT 0,
                    updated_at DATE,
                    UNIQUE(stock_code)
                )
            """))
            session.commit()
        except Exception as e:
            session.rollback()
            logger.warning(f"  创建fundamentals表失败: {e}")
            return
        finally:
            session.close()

        # 获取最新收盘价
        session = SessionLocal()
        try:
            result = session.execute(text("""
                SELECT stock_code, close FROM stock_daily_data
                WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily_data)
            """))
            price_map = {row[0]: float(row[1]) if row[1] else 0 for row in result}
        finally:
            session.close()

        # 抽样获取基本面（前300只，覆盖高股息策略需要的数据）
        sample_codes = codes[:300]
        fund_rows = []
        today = date.today()
        year = today.year
        quarter = (today.month - 1) // 3
        if quarter == 0:
            year -= 1
            quarter = 4

        for i, code in enumerate(sample_codes):
            try:
                bs_code = _code_to_bs(code)
                current_price = price_map.get(code, 0)
                pe, pb, dividend_yield, debt_ratio, market_cap = 0, 0, 0, 0, 0

                # 获取盈利数据
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
                            latest_p = df_profit.iloc[-1]
                            debt_ratio = float(latest_p.get("liabilityToAsset", 0) or 0) / 100.0
                            eps = float(latest_p.get("epsTTM", 0) or 0)
                            if eps > 0 and current_price > 0:
                                pe = current_price / eps
                            bps = float(latest_p.get("netAssetPerShare", 0) or 0)
                            if bps > 0 and current_price > 0:
                                pb = current_price / bps
                            total_share = float(latest_p.get("liqAShareTotal", 0) or 0)
                            if total_share > 0 and current_price > 0:
                                market_cap = current_price * total_share * 10000
                        break

                # 获取股息率
                for div_year in [year, year - 1]:
                    try:
                        rs_div = bs.query_dividend_data(code=bs_code, year=str(div_year), yearType="report")
                        div_list = []
                        while (rs_div.error_code == '0') and rs_div.next():
                            div_list.append(rs_div.get_row_data())
                        if div_list and current_price > 0:
                            df_div = pd.DataFrame(div_list, columns=rs_div.fields)
                            total_dividend = pd.to_numeric(df_div["perStockDiv"], errors="coerce").sum()
                            if total_dividend > 0:
                                dividend_yield = total_dividend / current_price
                                break
                    except Exception:
                        continue

                fund_rows.append({
                    "stock_code": code,
                    "pe": pe,
                    "pb": pb,
                    "dividend_yield": dividend_yield,
                    "debt_ratio": debt_ratio,
                    "market_cap": market_cap,
                    "updated_at": today,
                })

            except Exception as e:
                logger.debug(f"  {code} 基本面获取失败: {e}")

            if (i + 1) % 50 == 0:
                logger.info(f"  基本面进度: {i+1}/{len(sample_codes)}")

        # 批量写入
        if fund_rows:
            session = SessionLocal()
            try:
                for row in fund_rows:
                    session.execute(
                        text("""
                            INSERT OR REPLACE INTO stock_fundamentals
                            (stock_code, pe, pb, dividend_yield, debt_ratio, market_cap, updated_at)
                            VALUES (:stock_code, :pe, :pb, :dividend_yield, :debt_ratio, :market_cap, :updated_at)
                        """),
                        row
                    )
                session.commit()
                logger.info(f"  基本面数据写入 {len(fund_rows)} 条")
            except Exception as e:
                session.rollback()
                logger.error(f"  基本面数据写入失败: {e}")
            finally:
                session.close()
