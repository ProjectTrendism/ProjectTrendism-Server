from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.market import MarketItem, Settlement
from app.schemas.market import (
    MarketItemCreate, MarketItemResponse,
    SellRequest, SellResponse,
    TrendDataPoint, SettlementResponse,
    AdjustNodeRequest
)
import math

router = APIRouter(prefix="/market", tags=["Market"])


def calculate_trend_index(item: MarketItem, current_day: int) -> float:
    """
    트렌드 곡선 계산
    - 상승기: 로그 곡선
    - 하락기: 지수 감소
    - 180일 후 사망
    """
    elapsed = current_day - item.release_day
    if elapsed < 0:
        return 0.0
    if elapsed > 180:
        return 0.0

    grade_boost = {"S": 1.5, "A": 1.2, "B": 1.0, "C": 0.7}
    boost = grade_boost.get(item.grade, 1.0)

    peak_day = 30
    peak_value = 100 * boost
    decay_rate = 0.025

    if elapsed <= peak_day:
        index = peak_value * math.log1p(elapsed) / math.log1p(peak_day)
    else:
        index = peak_value * math.exp(-decay_rate * (elapsed - peak_day))

    return round(index, 2)


# ── POST /market/items  아이템 판매 등록 ────────────────
@router.post("/items", status_code=201)
def register_item(body: MarketItemCreate, db: Session = Depends(get_db)):
    item = MarketItem(**body.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {
        "status": "success",
        "data": MarketItemResponse.from_orm(item).dict()
    }


# ── GET /market/trend/{item_id}  트렌드 차트 데이터 ─────
@router.get("/trend/{item_id}")
def get_trend(item_id: int, days: int = 60, db: Session = Depends(get_db)):
    item = db.query(MarketItem).filter(MarketItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "ITEM_NOT_FOUND",
            "message": f"아이템 ID {item_id}가 존재하지 않습니다"
        })

    chart_data = [
        TrendDataPoint(day=d, index=calculate_trend_index(item, d))
        for d in range(item.release_day, item.release_day + days)
    ]
    current_index = calculate_trend_index(item, item.current_day)

    return {
        "status": "success",
        "data": {
            "item_id": item_id,
            "item_name": item.item_name,
            "grade": item.grade,
            "current_index": current_index,
            "chart_data": [p.dict() for p in chart_data]
        }
    }


# ── POST /market/sell  판매 처리 ────────────────────────
@router.post("/sell")
def sell_item(body: SellRequest, db: Session = Depends(get_db)):
    item = db.query(MarketItem).filter(MarketItem.id == body.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "ITEM_NOT_FOUND",
            "message": f"아이템 ID {body.item_id}가 존재하지 않습니다"
        })

    if item.stock < body.quantity:
        raise HTTPException(status_code=409, detail={
            "status": "error",
            "error_code": "ITEM_OUT_OF_STOCK",
            "message": f"재고가 부족합니다 (현재 재고: {item.stock})"
        })

    trend_index = calculate_trend_index(item, item.current_day)
    sell_price = item.base_value * (trend_index / 100) * (1 - body.discount_rate)
    revenue = round(sell_price * body.quantity, 1)

    # 재고 차감
    item.stock -= body.quantity
    if item.stock == 0:
        item.status = "SOLD_OUT"
    db.commit()

    # 정산 업데이트
    settlement = db.query(Settlement).filter(Settlement.season_id == 1).first()
    if not settlement:
        settlement = Settlement(
            season_id=1,
            total_revenue=revenue,
            material_cost=0,
            rent_cost=500,
            marketing_cost=0,
            management_cost=200,
            net_profit=revenue - 500 - 200
        )
        db.add(settlement)
    else:
        settlement.total_revenue = (settlement.total_revenue or 0) + revenue
        settlement.material_cost = settlement.material_cost or 0
        settlement.rent_cost = settlement.rent_cost or 500
        settlement.marketing_cost = settlement.marketing_cost or 0
        settlement.management_cost = settlement.management_cost or 200
        settlement.net_profit = (
            settlement.total_revenue
            - settlement.material_cost
            - settlement.rent_cost
            - settlement.marketing_cost
            - settlement.management_cost
        )
    db.commit()

    return {
        "status": "success",
        "data": {
            "revenue": revenue,
            "remaining_stock": item.stock,
            "trend_index": trend_index
        }
    }


# ── GET /market/settlement/{season_id}  정산 조회 ───────
@router.get("/settlement/{season_id}")
def get_settlement(season_id: int, db: Session = Depends(get_db)):
    settlement = db.query(Settlement).filter(
        Settlement.season_id == season_id
    ).first()

    if not settlement:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "SETTLEMENT_NOT_FOUND",
            "message": f"시즌 {season_id} 정산 데이터가 없습니다"
        })

    penalty = settlement.net_profit < settlement.penalty_threshold

    return {
        "status": "success",
        "data": {
            "season_id": settlement.season_id,
            "total_revenue": settlement.total_revenue,
            "material_cost": settlement.material_cost,
            "rent_cost": settlement.rent_cost,
            "marketing_cost": settlement.marketing_cost,
            "management_cost": settlement.management_cost,
            "net_profit": settlement.net_profit,
            "penalty": penalty
        }
    }


# ── PATCH /market/settlement/{season_id}/adjust  노드 조절 ─
@router.patch("/settlement/{season_id}/adjust")
def adjust_node(season_id: int, body: AdjustNodeRequest, db: Session = Depends(get_db)):
    settlement = db.query(Settlement).filter(
        Settlement.season_id == season_id
    ).first()

    if not settlement:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "SETTLEMENT_NOT_FOUND",
            "message": f"시즌 {season_id} 정산 데이터가 없습니다"
        })

    if body.node == "marketing":
        settlement.marketing_cost = body.new_value
    elif body.node == "rent":
        settlement.rent_cost = body.new_value
    elif body.node == "management":
        settlement.management_cost = body.new_value
    else:
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "error_code": "INVALID_NODE",
            "message": "조절 가능한 노드: marketing, rent, management"
        })

    settlement.net_profit = (
        settlement.total_revenue
        - settlement.material_cost
        - settlement.rent_cost
        - settlement.marketing_cost
        - settlement.management_cost
    )
    db.commit()

    return get_settlement(season_id, db)