"""
本地拉数据 + 同步到云服务器
============================
在本地家用宽带机器上运行（绕过云服务器机房 IP 被反爬封禁的问题）。

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
import pickle
import logging
import subprocess
from datetime import date, timedelta
from pathlib import Path

# 把项目根目录加进 sys.path，复用 backend 的 DataService 行为
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import akshare as ak
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


# ============== 数据采集 ==============
STOCK_POOL_EXCLUDE = ["ST", "*ST", "退市", "退"]
MIN_MARKET_CAP = 5e8


def fetch_stock_spot() -> pd.DataFrame:
    logger.info("[1/4] 拉取实时行情 stock_zh_a_spot_em ...")
    df = ak.stock_zh_a_spot_em()
    logger.info(f"  共 {len(df)} 行")
    save_cache("stock_spot", df)
    return df


def fetch_stock_pool(spot_df: pd.DataFrame) -> list:
    logger.info("[2/4] 生成股票池 ...")
    pattern = "|".join(STOCK_POOL_EXCLUDE)
    df = spot_df[~spot_df["名称"].str.contains(pattern, na=False)]
    if "总市值" in df.columns:
        df = df[df["总市值"] >= MIN_MARKET_CAP]
    codes = df["代码"].tolist()
    logger.info(f"  股票池 {len(codes)} 只")
    save_cache("stock_pool", codes)
    return codes


def fetch_klines(codes: list, days: int = 250, top_n: int = 0):
    if top_n > 0:
        codes = codes[:top_n]
    total = len(codes)
    logger.info(f"[3/4] 拉取 K 线 (前 {total} 只, 每只 {days} 天) ...")
    end_date = date.today().strftime("%Y%m%d")
    start_date = (date.today() - timedelta(days=int(days * 1.5))).strftime("%Y%m%d")

    ok, fail = 0, 0
    for i, code in enumerate(codes, 1):
        try:
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date=start_date,
                end_date=end_date,
                adjust="qfq",
            )
            if df is None or df.empty:
                fail += 1
                continue
            df = df.rename(columns={
                "日期": "date", "开盘": "open", "收盘": "close",
                "最高": "high", "最低": "low", "成交量": "volume",
                "成交额": "amount", "换手率": "turnover",
                "涨跌幅": "change_pct", "振幅": "amplitude",
            })
            df["date"] = pd.to_datetime(df["date"])
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
    logger.info("[4/4] 拉取申万行业数据 ...")
    try:
        df = ak.sw_index_spot()
        if df is not None and not df.empty:
            save_cache("shenwan_sectors", df)
            logger.info(f"  申万板块 {len(df)} 个")
    except Exception as e:
        logger.warning(f"  申万拉取失败: {e}")


# ============== 同步到服务器 ==============
def sync_to_remote():
    user = CONFIG["remote_user"]
    host = CONFIG["remote_host"]
    remote = CONFIG["remote_dir"]
    key = CONFIG["ssh_key"]

    logger.info(f"同步缓存到 {user}@{host}:{remote}/backend/data/cache/")

    # 优先用 scp（Windows 自带），简单可靠
    src = str(CACHE_DIR) + "/*.pkl"
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
    logger.info(f"开始拉取 ({date.today()})")
    logger.info("=" * 50)

    spot_df = fetch_stock_spot()
    codes = fetch_stock_pool(spot_df)
    fetch_klines(codes, days=CONFIG["kline_days"], top_n=CONFIG["top_n_kline"])
    fetch_sectors()

    logger.info("-" * 50)
    sync_to_remote()
    logger.info("=" * 50)
    logger.info("全部完成！现在可以在服务器上调 /api/system/run-all 了")
    logger.info("=" * 50)


if __name__ == "__main__":
    main()
