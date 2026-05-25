"""
本地拉数据 + 同步到云服务器
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
import pickle
import logging
import subprocess
from datetime import date, timedelta
from pathlib import Path

# 把项目根目录加进 sys.path，复用 backend 的 DataService 行为
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
    "top_n_kline": int(os.getenv("TOP_N_KLINE", "500")),  # 0 表示全部
    "kline_days": 250,
}

CACHE_DIR = ROOT / "backend" / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def cache_path(key: str, d: date = None) -> Path:
    if d is None:
        d = date.today()
    return CACHE_DIR / f"{key}_{d.isoformat()}.pkl"


def save_cache(key: str, data, d: date = None):
    path = cache_path(key, d)
    with open(path, "wb") as f:
        pickle.dump(data, f)
    logger.info(f"  → 缓存写入 {path.name}")


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


# ============== 数据采集 ==============
STOCK_POOL_EXCLUDE = ["ST", "*ST", "退市", "退"]
MIN_MARKET_CAP = 5e8


def fetch_stock_list() -> pd.DataFrame:
    """获取全部A股基本信息"""
    logger.info("[1/4] 获取A股股票列表 ...")
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
    """生成股票池（排除ST/退市）"""
    logger.info("[2/4] 生成股票池 ...")
    pattern = "|".join(re.escape(x) for x in STOCK_POOL_EXCLUDE)
    df = df_basic[~df_basic["code_name"].str.contains(pattern, na=False)]
    codes = [_code_from_bs(c) for c in df["code"].tolist()]
    logger.info(f"  股票池 {len(codes)} 只")
    save_cache("stock_pool", codes)

    # 同时生成一个基础的 spot DataFrame（包含代码和名称）
    spot_rows = []
    for _, row in df.iterrows():
        spot_rows.append({
            "代码": _code_from_bs(row["code"]),
            "名称": row.get("code_name", ""),
            "最新价": 0,
            "总市值": 0,
            "市盈率-动态": 0,
            "市净率": 0,
            "换手率": 0,
        })
    spot_df = pd.DataFrame(spot_rows)
    save_cache("stock_spot", spot_df)

    return codes


def fetch_klines(codes: list, days: int = 250, top_n: int = 0):
    if top_n > 0:
        codes = codes[:top_n]
    total = len(codes)
    logger.info(f"[3/4] 拉取 K 线 (前 {total} 只, 每只 {days} 天) ...")
    end_date = date.today().strftime("%Y-%m-%d")
    start_date = (date.today() - timedelta(days=int(days * 1.5))).strftime("%Y-%m-%d")

    ok, fail = 0, 0
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
            save_cache(f"kline_{code}_{days}", df)
            ok += 1
        except Exception as e:
            fail += 1
            logger.debug(f"  {code} 失败: {e}")

        if i % 50 == 0:
            logger.info(f"  进度 {i}/{total}  成功 {ok}  失败 {fail}")

    logger.info(f"  K线完成: 成功 {ok}  失败 {fail}")


def fetch_sectors():
    """获取行业分类信息"""
    logger.info("[4/4] 获取行业分类数据 ...")
    try:
        # BaoStock 通过 query_stock_industry 获取行业信息
        # 这里抽样前200只股票获取行业分布
        stock_pool_path = cache_path("stock_pool")
        if stock_pool_path.exists():
            with open(stock_pool_path, "rb") as f:
                codes = pickle.load(f)
        else:
            codes = []

        sample_codes = codes[:200]
        industry_map = {}

        for code in sample_codes:
            bs_code = _code_to_bs(code)
            rs_ind = bs.query_stock_industry(code=bs_code)
            while (rs_ind.error_code == '0') and rs_ind.next():
                row = rs_ind.get_row_data()
                ind_name = row[3] if len(row) > 3 else ""
                ind_code = row[2] if len(row) > 2 else ""
                if ind_name and ind_name not in industry_map:
                    industry_map[ind_name] = {
                        "板块代码": ind_code or ind_name,
                        "板块名称": ind_name,
                        "stock_count": 0,
                    }
                if ind_name:
                    industry_map[ind_name]["stock_count"] = \
                        industry_map.get(ind_name, {}).get("stock_count", 0) + 1

        if industry_map:
            df = pd.DataFrame(list(industry_map.values()))
            save_cache("shenwan_sectors", df)
            logger.info(f"  行业板块 {len(df)} 个")
        else:
            logger.warning("  未获取到行业数据")
    except Exception as e:
        logger.warning(f"  行业数据拉取失败: {e}")


# ============== 同步到服务器 ==============
def sync_to_remote():
    user = CONFIG["remote_user"]
    host = CONFIG["remote_host"]
    remote = CONFIG["remote_dir"]
    key = CONFIG["ssh_key"]

    logger.info(f"同步缓存到 {user}@{host}:{remote}/backend/data/cache/")

    cmd_scp = (
        f'scp -i "{key}" -o StrictHostKeyChecking=no '
        f'{CACHE_DIR}\\*.pkl '
        f'{user}@{host}:{remote}/backend/data/cache/'
    )

    logger.info(f"$ {cmd_scp}")
    ret = subprocess.call(cmd_scp, shell=True)
    if ret != 0:
        logger.error("scp 同步失败！请检查 SSH 私钥路径和服务器连通性。")
        sys.exit(1)
    logger.info("同步成功 ✓")


def main():
    logger.info("=" * 50)
    logger.info(f"开始拉取 ({date.today()}) - 数据源: BaoStock")
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
        fetch_sectors()
    finally:
        bs.logout()
        logger.info("BaoStock 已登出")

    logger.info("-" * 50)
    sync_to_remote()
    logger.info("=" * 50)
    logger.info("全部完成！现在可以在服务器上调 /api/system/run-all 了")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
