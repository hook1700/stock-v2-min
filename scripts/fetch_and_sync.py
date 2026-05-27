"""
本地拉数据 + 全量入库SQLite + 同步到云服务器
============================
在本地家用宽带机器上运行。
BaoStock 无反爬限制，可直接在云服务器运行，但保留本地拉取+同步的方式做备选。

使用方式：
    cd E:\\myproject\\stock-v2-min
    python scripts/fetch_and_sync.py

可选环境变量（也可直接修改下方 CONFIG）：
    REMOTE_USER   ssh 用户名（默认 way）
    REMOTE_HOST   服务器地址（默认 175.178.172.130）
    REMOTE_DIR    服务器项目根目录（默认 /home/way/stock-v2-min）
    SSH_KEY       本地私钥路径（默认 ./way）
    TOP_N_KLINE   每个股票池前 N 只拉取 K 线（默认 0=全部，建议 500 加快速度）
"""
import os
import sys
import re
import logging
import subprocess
from datetime import date, timedelta
from pathlib import Path

# 把项目根目录加进 sys.path，复用 backend 模块
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import baostock as bs
import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("fetch_and_sync")

# ============== 配置 ==============
CONFIG = {
    "remote_user": os.getenv("REMOTE_USER", "way"),
    "remote_host": os.getenv("REMOTE_HOST", "175.178.172.130"),
    "remote_dir": os.getenv("REMOTE_DIR", "/home/way/stock-v2-min"),
    "ssh_key": os.getenv("SSH_KEY", str(ROOT / "way")),
    "top_n_kline": int(os.getenv("TOP_N_KLINE", "0")),  # 0 表示全部
    "kline_days": 250,
}

# 股票池过滤关键词
STOCK_POOL_EXCLUDE = ["ST", "*ST", "退市", "退"]


def _code_to_bs(code: str) -> str:
    """将纯数字股票代码转换为 BaoStock 格式"""
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


# ============== 数据库操作 ==============
def get_db_session():
    """获取数据库会话"""
    from backend.database import engine, Base, SessionLocal
    from backend.models import StockPool, StockDailyData
    Base.metadata.create_all(bind=engine)
    return SessionLocal()


# ============== 数据采集 ==============
def fetch_stock_list() -> pd.DataFrame:
    """获取全部A股基本信息"""
    logger.info("[1/5] 获取A股股票列表 ...")
    rs = bs.query_stock_basic(code_name="", code="")
    stock_list = []
    while (rs.error_code == '0') and rs.next():
        stock_list.append(rs.get_row_data())

    df = pd.DataFrame(stock_list, columns=rs.fields)
    # 只保留A股上市状态
    df = df[(df["type"] == "1") & (df["status"] == "1")]
    logger.info(f"  共 {len(df)} 只A股")
    return df


def fetch_stock_pool(df_basic: pd.DataFrame) -> list:
    """生成股票池并写入SQLite stock_pool表"""
    logger.info("[2/5] 生成股票池并写入数据库 ...")
    pattern = "|".join(re.escape(x) for x in STOCK_POOL_EXCLUDE)
    df = df_basic[~df_basic["code_name"].str.contains(pattern, na=False)]

    codes = [_code_from_bs(c) for c in df["code"].tolist()]
    names = df["code_name"].tolist()
    logger.info(f"  股票池 {len(codes)} 只")

    # 写入数据库
    session = get_db_session()
    try:
        from backend.models import StockPool
        # 清空旧数据，全量替换
        session.execute(StockPool.__table__.delete())

        today = date.today()
        pool_rows = []
        for i, code in enumerate(codes):
            pool_rows.append({
                "stock_code": code,
                "stock_name": names[i] if i < len(names) else "",
                "industry": "",  # 行业信息后续步骤填充
                "updated_at": today,
            })

        # 批量插入
        session.bulk_insert_mappings(StockPool, pool_rows)
        session.commit()
        logger.info(f"  stock_pool 表写入 {len(pool_rows)} 条 ✓")
    except Exception as e:
        session.rollback()
        logger.error(f"  stock_pool 写入失败: {e}")
    finally:
        session.close()

    return codes


def fetch_klines(codes: list, days: int = 250, top_n: int = 0):
    """拉取K线数据并全量写入 stock_daily_data 表"""
    if top_n > 0:
        codes = codes[:top_n]
    total = len(codes)
    logger.info(f"[3/5] 拉取 K 线并入库 (共 {total} 只, 每只 {days} 天) ...")
    end_date = date.today().strftime("%Y-%m-%d")
    start_date = (date.today() - timedelta(days=int(days * 1.5))).strftime("%Y-%m-%d")

    # 加载名称映射
    session = get_db_session()
    try:
        from backend.models import StockPool
        from sqlalchemy import text
        result = session.execute(text("SELECT stock_code, stock_name FROM stock_pool"))
        name_map = {row[0]: row[1] for row in result}
    finally:
        session.close()

    ok, fail = 0, 0
    batch_size = 50  # 每50只股票提交一次
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

            df = df.rename(columns={
                "turn": "turnover",
                "pctChg": "change_pct",
            })

            # 过滤停牌日
            df = df[df["volume"] > 0]
            df = df.sort_values("date").reset_index(drop=True).tail(days).reset_index(drop=True)

            # 收集全量数据写入数据库
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
                    "change_pct": float(row["change_pct"]) if pd.notna(row["change_pct"]) else None,
                    "turnover": float(row["turnover"]) if pd.notna(row["turnover"]) else None,
                })

            ok += 1
        except Exception as e:
            fail += 1
            logger.debug(f"  {code} 失败: {e}")

        # 每batch_size只股票批量提交一次
        if i % batch_size == 0:
            _flush_kline_batch(db_rows)
            db_rows = []
            logger.info(f"  进度 {i}/{total}  成功 {ok}  失败 {fail}")

    # 提交剩余数据
    if db_rows:
        _flush_kline_batch(db_rows)

    logger.info(f"  K线入库完成: 成功 {ok}  失败 {fail}")


def _flush_kline_batch(rows: list):
    """批量写入K线数据到数据库"""
    if not rows:
        return
    session = get_db_session()
    try:
        from backend.models import StockDailyData
        from sqlalchemy import text

        # 使用 INSERT OR REPLACE（SQLite专用）实现upsert
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
        logger.error(f"  批量写入失败: {e}")
    finally:
        session.close()


def fetch_sectors(codes: list):
    """获取行业分类信息并更新stock_pool表的industry字段"""
    logger.info("[4/5] 获取行业分类数据 ...")
    try:
        # 抽样前300只股票获取行业信息
        sample_codes = codes[:300]
        industry_data = {}  # code -> industry_name

        for i, code in enumerate(sample_codes):
            bs_code = _code_to_bs(code)
            rs_ind = bs.query_stock_industry(code=bs_code)
            while (rs_ind.error_code == '0') and rs_ind.next():
                row = rs_ind.get_row_data()
                ind_name = row[3] if len(row) > 3 else ""
                if ind_name:
                    industry_data[code] = ind_name

            if (i + 1) % 50 == 0:
                logger.info(f"  行业进度: {i+1}/{len(sample_codes)}")

        if not industry_data:
            logger.warning("  未获取到行业数据")
            return

        # 更新数据库中的industry字段
        session = get_db_session()
        try:
            from sqlalchemy import text
            for code, industry in industry_data.items():
                session.execute(
                    text("UPDATE stock_pool SET industry = :ind WHERE stock_code = :code"),
                    {"ind": industry, "code": code}
                )
            session.commit()
            logger.info(f"  行业信息更新 {len(industry_data)} 只股票 ✓")
        except Exception as e:
            session.rollback()
            logger.error(f"  行业信息更新失败: {e}")
        finally:
            session.close()

    except Exception as e:
        logger.warning(f"  行业数据拉取失败: {e}")


def fetch_fundamentals(codes: list):
    """获取基本面数据并写入 stock_fundamentals 表（可选）"""
    logger.info("[5/5] 获取基本面数据 ...")

    # 创建 stock_fundamentals 表（如果不存在）
    session = get_db_session()
    try:
        from sqlalchemy import text
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
    session = get_db_session()
    try:
        from sqlalchemy import text
        result = session.execute(text("""
            SELECT stock_code, close FROM stock_daily_data
            WHERE trade_date = (SELECT MAX(trade_date) FROM stock_daily_data)
        """))
        price_map = {row[0]: float(row[1]) if row[1] else 0 for row in result}
    finally:
        session.close()

    # 抽样获取基本面（高股息策略需要）
    sample_codes = codes[:200]
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
        session = get_db_session()
        try:
            from sqlalchemy import text
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
            logger.info(f"  基本面数据写入 {len(fund_rows)} 条 ✓")
        except Exception as e:
            session.rollback()
            logger.error(f"  基本面数据写入失败: {e}")
        finally:
            session.close()


# ============== 同步到服务器 ==============
def sync_to_remote():
    user = CONFIG["remote_user"]
    host = CONFIG["remote_host"]
    remote = CONFIG["remote_dir"]
    key = CONFIG["ssh_key"]

    db_path = ROOT / "backend" / "data" / "stock_v2.db"
    if not db_path.exists():
        logger.error("数据库文件不存在，无法同步")
        return

    logger.info(f"同步数据库到 {user}@{host}:{remote}/backend/data/")

    # 只同步一个db文件即可
    cmd_db = (
        f'scp -i "{key}" -o StrictHostKeyChecking=no '
        f'"{db_path}" '
        f'{user}@{host}:{remote}/backend/data/stock_v2.db'
    )

    logger.info(f"$ {cmd_db}")
    ret = subprocess.call(cmd_db, shell=True)
    if ret == 0:
        logger.info("数据库同步成功 ✓")
    else:
        logger.error("数据库同步失败！请检查 SSH 私钥路径和服务器连通性。")
        sys.exit(1)


def main():
    logger.info("=" * 50)
    logger.info(f"开始拉取 ({date.today()}) - 数据源: BaoStock → SQLite")
    logger.info("=" * 50)

    # 登录 BaoStock
    lg = bs.login()
    if lg.error_code != '0':
        logger.error(f"BaoStock 登录失败: {lg.error_msg}")
        sys.exit(1)
    logger.info("BaoStock 登录成功")

    try:
        df_basic = fetch_stock_list()
        codes = fetch_stock_pool(df_basic)
        fetch_klines(codes, days=CONFIG["kline_days"], top_n=CONFIG["top_n_kline"])
        fetch_sectors(codes)
        fetch_fundamentals(codes)
    finally:
        bs.logout()
        logger.info("BaoStock 已登出")

    logger.info("-" * 50)
    sync_to_remote()
    logger.info("=" * 50)
    logger.info("全部完成！数据已入库SQLite，可以运行策略了")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
