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
    """数据源连通性诊断 - 用于定位 AKShare 接口拉不到数据的根因。

    返回各数据源的连通状态、耗时、错误信息，以及当前服务器公网 IP 的地理位置。
    """
    import requests
    import akshare as ak

    result = {"checks": [], "server_ip_info": None}

    # 1. 查公网出口 IP 与地理位置
    try:
        r = requests.get("https://ipinfo.io/json", timeout=5)
        result["server_ip_info"] = r.json() if r.status_code == 200 else {"error": f"HTTP {r.status_code}"}
    except Exception as e:
        result["server_ip_info"] = {"error": str(e)}

    # 2. 测试东方财富实时行情（AKShare get_stock_pool 的真实源）
    def _check_em():
        url = (
            "https://82.push2.eastmoney.com/api/qt/clist/get"
            "?pn=1&pz=20&po=1&np=1&fltt=2&invt=2"
            "&fs=m:1+t:2,m:1+t:23,m:0+t:6,m:0+t:80&fields=f12,f14"
        )
        r = requests.get(url, timeout=8, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        return r.status_code, len(r.text)

    # 3. 测试新浪财经接口（AKShare 部分接口的源）
    def _check_sina():
        r = requests.get("https://hq.sinajs.cn/list=sh600519", timeout=8, headers={
            "Referer": "https://finance.sina.com.cn"
        })
        return r.status_code, len(r.text)

    # 4. 直接调用 AKShare 看是否能拿到数据
    def _check_akshare():
        df = ak.stock_zh_a_spot_em()
        return 200, (0 if df is None else len(df))

    for name, func in [
        ("eastmoney_clist", _check_em),
        ("sina_hq", _check_sina),
        ("akshare_stock_zh_a_spot_em", _check_akshare),
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

