"""板块轮动API端点"""
from fastapi import APIRouter

from backend.schemas import (
    SectorRotationResponse, SectorAnalysisSchema, SectorStockPickSchema
)
from backend.services.recommendation_service import RecommendationService

router = APIRouter()
rec_service = RecommendationService()


@router.get("/rotation", response_model=SectorRotationResponse)
async def get_sector_rotation():
    """获取板块轮动分析结果"""
    data = rec_service.get_latest_sector_analysis()

    if not data["sectors"]:
        return SectorRotationResponse()

    sectors = data["sectors"]
    picks = data["picks"]

    # 按板块分组推荐股票
    picks_by_sector = {}
    for pick in picks:
        if pick.sector_code not in picks_by_sector:
            picks_by_sector[pick.sector_code] = []
        picks_by_sector[pick.sector_code].append(
            SectorStockPickSchema.model_validate(pick)
        )

    opportunity_sectors = []
    risk_sectors = []
    neutral_sectors = []

    for sector in sectors:
        sector_schema = SectorAnalysisSchema(
            sector_code=sector.sector_code,
            sector_name=sector.sector_name,
            signal=sector.signal,
            score=sector.score,
            momentum_20d=sector.momentum_20d,
            momentum_5d=sector.momentum_5d,
            volume_trend=sector.volume_trend,
            relative_strength=sector.relative_strength,
            pe_percentile=sector.pe_percentile,
            ma_signal=sector.ma_signal or "HOLD",
            reasoning=sector.reasoning,
            recommended_stocks=picks_by_sector.get(sector.sector_code, []),
        )

        if sector.signal == "OPPORTUNITY":
            opportunity_sectors.append(sector_schema)
        elif sector.signal == "RISK":
            risk_sectors.append(sector_schema)
        else:
            neutral_sectors.append(sector_schema)

    return SectorRotationResponse(
        scan_date=data["scan_date"],
        opportunity_sectors=opportunity_sectors,
        risk_sectors=risk_sectors,
        neutral_sectors=neutral_sectors,
    )
