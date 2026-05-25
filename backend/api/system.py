"""系统状态API端点"""
import time
from fastapi import APIRouter

from backend.schemas import SystemStatus, RunResult
from backend.services.recommendation_service import RecommendationService
from backend.services.strategy_runner import StrategyRunner
from backend.scheduler import scheduler

router = APIRouter()
rec_service = RecommendationService()


@router.get("/status", response_model=SystemStatus)
async def get_system_status():
    """获取系统运行状态"""
    latest_log = rec_service.get_latest_scheduler_log()

    # 获取下一次执行时间
    next_run = None
    job = scheduler.get_job("daily_stock_scan")
    if job and job.next_run_time:
        next_run = job.next_run_time

    # 获取今日推荐总数
    from datetime import date
    today_recs = rec_service.get_recommendations_by_date(date.today())
    total_today = len(today_recs)

    return SystemStatus(
        scheduler_running=scheduler.running,
        last_run_time=latest_log.run_time if latest_log else None,
        last_run_status=latest_log.status if latest_log else "NEVER_RUN",
        next_run_time=next_run,
        total_recommendations_today=total_today,
    )


@router.post("/run-all", response_model=RunResult)
async def run_all_strategies():
    """手动触发全部策略执行"""
    runner = StrategyRunner()
    result = await runner.run_all()

    return RunResult(
        success=result["success"],
        message=result["message"],
        strategies_completed=result["strategies_completed"],
        sector_completed=result["sector_completed"],
        duration_seconds=result["duration"],
    )


@router.get("/datasource-check")
async def datasource_check():
    """数据源连通性诊断 - 检测 BaoStock 接口是否可用。

    返回 BaoStock 的连通状态、耗时、错误信息，以及当前服务器公网 IP 的地理位置。
    """
    import requests
    import baostock as bs

    result = {"checks": [], "server_ip_info": None}

    # 1. 查公网出口 IP 与地理位置
    try:
        r = requests.get("https://ipinfo.io/json", timeout=5)
        result["server_ip_info"] = r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        result["server_ip_info"] = {"error": str(e)}

    # 2. 测试 BaoStock 登录
    def _check_bs_login():
        lg = bs.login()
        if lg.error_code == '0':
            bs.logout()
            return 200, 1
        return 500, 0

    # 3. 测试 BaoStock 获取交易日历
    def _check_bs_trade_dates():
        lg = bs.login()
        if lg.error_code != '0':
            return 500, 0
        rs = bs.query_trade_dates(start_date="2024-01-01", end_date="2024-01-31")
        count = 0
        while (rs.error_code == '0') and rs.next():
            count += 1
        bs.logout()
        return 200, count

    # 4. 测试 BaoStock K 线数据
    def _check_bs_kline():
        lg = bs.login()
        if lg.error_code != '0':
            return 500, 0
        rs = bs.query_history_k_data_plus(
            "sh.600519", "date,close",
            start_date="2024-01-01", end_date="2024-01-10",
            frequency="d", adjustflag="2"
        )
        count = 0
        while (rs.error_code == '0') and rs.next():
            count += 1
        bs.logout()
        return 200, count

    for name, func in [
        ("baostock_login", _check_bs_login),
        ("baostock_trade_dates", _check_bs_trade_dates),
        ("baostock_kline", _check_bs_kline),
    ]:
        item = {"name": name, "ok": False}
        t0 = time.time()
        try:
            status, size = func()
            item["http_status"] = status
            item["payload_size"] = size
            item["ok"] = status == 200 and size > 0
        except Exception as e:
            item["error"] = f"{type(e).__name__}: {e}"
        item["elapsed_ms"] = int((time.time() - t0) * 1000)
        result["checks"].append(item)

    return result

