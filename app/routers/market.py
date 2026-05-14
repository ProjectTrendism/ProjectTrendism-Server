from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.market import MarketItem, Settlement
from app.models.keyword import Keyword
from app.schemas.market import (
    MarketItemCreate, MarketItemResponse,
    SellRequest, SellResponse,
    TrendDataPoint, SettlementResponse,
    AdjustNodeRequest, PriceAdjustRequest
)
from app.services.claude_service import analyze_sales_performance
import math, random

router = APIRouter(prefix="/market", tags=["Market"])


def calculate_trend_index(item: MarketItem, current_day: int) -> float:
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


@router.post("/items", status_code=201)
def register_item(body: MarketItemCreate, db: Session = Depends(get_db)):
    item = MarketItem(**body.dict())
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"status": "success", "data": MarketItemResponse.from_orm(item).dict()}


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

    item.stock -= body.quantity
    if item.stock == 0:
        item.status = "SOLD_OUT"
    db.commit()

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


# ── POST /market/analyze/{item_id}  판매 성과 분석 ──────
@router.post("/analyze/{item_id}")
def analyze_item(item_id: int, db: Session = Depends(get_db)):
    item = db.query(MarketItem).filter(MarketItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "ITEM_NOT_FOUND",
            "message": f"아이템 ID {item_id}가 존재하지 않습니다"
        })

    # 키워드 이름 조회
    keyword_names = []
    if item.keyword_ids:
        keywords = db.query(Keyword).filter(Keyword.id.in_(item.keyword_ids)).all()
        keyword_names = [k.name for k in keywords]

    trend_index = calculate_trend_index(item, item.current_day)
    days_on_market = max(0, item.current_day - item.release_day)

    # 매출 계산 (정산 테이블에서)
    settlement = db.query(Settlement).filter(Settlement.season_id == 1).first()
    revenue = settlement.total_revenue if settlement else 0

    # 서버 자체 분석 (Claude 호출 없이 빠르게 제공)
    server_analysis = _build_server_analysis(item, trend_index, days_on_market)

    # Claude AI 분석
    try:
        ai_analysis = analyze_sales_performance(
            item_name=item.item_name,
            keyword_names=keyword_names,
            grade=item.grade,
            trend_index=trend_index,
            revenue=revenue,
            stock_remaining=item.stock,
            discount_rate=0.0,
            days_on_market=days_on_market
        )
    except RuntimeError:
        ai_analysis = None

    return {
        "status": "success",
        "data": {
            "item_id": item_id,
            "item_name": item.item_name,
            "server_analysis": server_analysis,
            "ai_analysis": ai_analysis
        }
    }


def _build_server_analysis(item: MarketItem, trend_index: float, days_on_market: int) -> dict:
    """Claude 호출 없이 서버에서 즉시 계산하는 분석"""
    issues = []
    suggestions = []

    # 등급 분석
    if item.grade in ("C", "B"):
        issues.append({
            "type": "GRADE",
            "severity": "HIGH" if item.grade == "C" else "MEDIUM",
            "message": f"제작 등급이 {item.grade}등급입니다. 등급이 낮으면 트렌드 보정이 약해집니다."
        })
        suggestions.append("키워드의 RGB 특성을 더 정확히 예측해 등급을 올려보세요.")

    # 타이밍 분석
    if days_on_market > 60:
        issues.append({
            "type": "TIMING",
            "severity": "HIGH",
            "message": f"출시 후 {days_on_market}일 경과. 트렌드가 크게 하락했습니다."
        })
        suggestions.append("트렌드 정점(30일)이 지나기 전에 판매를 완료하세요.")
    elif days_on_market > 30:
        issues.append({
            "type": "TIMING",
            "severity": "MEDIUM",
            "message": "트렌드 정점을 지났습니다. 가격이 하락 중이에요."
        })
        suggestions.append("할인 판매를 고려하거나 빠르게 재고를 소진하세요.")

    # 트렌드 분석
    if trend_index < 20:
        issues.append({
            "type": "TREND",
            "severity": "HIGH",
            "message": f"트렌드 지수가 {trend_index}으로 매우 낮습니다."
        })
    elif trend_index >= 80:
        suggestions.append("트렌드 지수가 높습니다! 지금이 최적의 판매 타이밍이에요.")

    # 재고 분석
    if item.stock > 3 and days_on_market > 30:
        issues.append({
            "type": "STOCK",
            "severity": "MEDIUM",
            "message": f"재고 {item.stock}개가 남아있습니다. 할인 판매를 고려하세요."
        })
        suggestions.append("할인율을 20~30%로 설정해 재고를 빠르게 소진하세요.")

    # 종합 점수
    score = 100
    for issue in issues:
        if issue["severity"] == "HIGH":
            score -= 25
        elif issue["severity"] == "MEDIUM":
            score -= 15
    score = max(0, score)

    return {
        "issues": issues,
        "suggestions": suggestions,
        "overall_score": score,
        "trend_status": "상승" if days_on_market <= 30 else "하락",
        "optimal_sell_window": f"Day {item.release_day + 20} ~ Day {item.release_day + 40}"
    }


# ── GET /market/simulate/{item_id}  구매자 시뮬레이션 ───
@router.get("/simulate/{item_id}")
def simulate_buyers(
    item_id: int,
    days: int = 60,
    base_buyers: int = 10,
    db: Session = Depends(get_db)
):
    item = db.query(MarketItem).filter(MarketItem.id == item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "ITEM_NOT_FOUND",
            "message": f"아이템 ID {item_id}가 존재하지 않습니다"
        })

    grade_multiplier = {"S": 2.0, "A": 1.5, "B": 1.0, "C": 0.5}
    g_mult = grade_multiplier.get(item.grade, 1.0)

    simulation = []
    cumulative_revenue = 0.0
    remaining_stock = item.stock

    for d in range(days):
        current_day = item.release_day + d
        trend = calculate_trend_index(item, current_day)

        # 구매자 수 = base × (trend/100) × grade보정 × 약간의 랜덤
        if trend <= 0 or remaining_stock <= 0:
            buyers = 0
            sold = 0
        else:
            raw_buyers = base_buyers * (trend / 100) * g_mult
            noise = random.uniform(0.7, 1.3)
            buyers = max(0, int(raw_buyers * noise))

            # 실제 판매 (구매자 중 일부만 구매)
            buy_prob = min(0.8, trend / 120)
            sold = 0
            for _ in range(min(buyers, remaining_stock)):
                if random.random() < buy_prob:
                    sold += 1

            sold = min(sold, remaining_stock)
            remaining_stock -= sold
            day_revenue = sold * item.base_value * (trend / 100)
            cumulative_revenue += day_revenue

        simulation.append({
            "day": current_day,
            "trend_index": trend,
            "buyers_visited": buyers,
            "units_sold": sold,
            "remaining_stock": remaining_stock,
            "cumulative_revenue": round(cumulative_revenue, 1)
        })

        if remaining_stock <= 0:
            break

    # 요약 통계
    total_sold = item.stock - remaining_stock
    peak_day = max(simulation, key=lambda x: x["buyers_visited"])

    return {
        "status": "success",
        "data": {
            "item_id": item_id,
            "item_name": item.item_name,
            "grade": item.grade,
            "initial_stock": item.stock + total_sold,
            "summary": {
                "total_sold": total_sold,
                "remaining_stock": remaining_stock,
                "total_revenue": round(cumulative_revenue, 1),
                "sellout_day": next(
                    (s["day"] for s in simulation if s["remaining_stock"] == 0),
                    None
                ),
                "peak_buyers_day": peak_day["day"],
                "peak_buyers_count": peak_day["buyers_visited"]
            },
            "daily_data": simulation
        }
    }


# ── PATCH /market/price  가격 직접 조정 ─────────────────
@router.patch("/price")
def adjust_price(body: PriceAdjustRequest, db: Session = Depends(get_db)):
    item = db.query(MarketItem).filter(MarketItem.id == body.item_id).first()
    if not item:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "ITEM_NOT_FOUND",
            "message": f"아이템 ID {body.item_id}가 존재하지 않습니다"
        })

    old_price = item.base_value
    item.base_value = body.new_price
    db.commit()

    change_pct = round((body.new_price - old_price) / old_price * 100, 1) if old_price > 0 else 0

    return {
        "status": "success",
        "data": {
            "item_id": item.id,
            "item_name": item.item_name,
            "old_price": old_price,
            "new_price": body.new_price,
            "change_percent": change_pct,
            "message": f"가격이 {old_price} → {body.new_price} 골드로 변경되었습니다 ({change_pct:+.1f}%)"
        }
    }
