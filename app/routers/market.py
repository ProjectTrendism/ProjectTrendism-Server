from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app.models.market import MarketItem, Settlement, MarketState
from app.models.keyword import Keyword
from app.models.explore import Season
from app.models.frequency import KeywordFrequency
from app.schemas.market import (
    MarketItemCreate, MarketItemResponse,
    SellRequest, SellResponse,
    TrendDataPoint, SettlementResponse,
    AdjustNodeRequest, PriceAdjustRequest, AdvanceDayRequest
)
from app.services.claude_service import analyze_sales_performance
import math
import random

# 키워드 희귀도별 재료비 (keyword 1개당 G)
KEYWORD_RARITY_COST = {"COMMON": 150, "RARE": 450, "LEGEND": 900}
DEFAULT_KEYWORD_COST = 200

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


def get_or_create_market_state(db: Session, season_id: int) -> MarketState:
    state = db.query(MarketState).filter(MarketState.season_id == season_id).first()
    if not state:
        state = MarketState(season_id=season_id, current_day=0)
        db.add(state)
        db.commit()
        db.refresh(state)
    return state


PRICE_SENSITIVITY = 1.0  # 가격 탄력성. 클수록 가격이 base_value에서 멀어질 때 수요가 더 민감하게 변함
FIRE_SALE_PENALTY = 0.3  # /sell(즉시청산) 고정 페널티. current_price 대비 이 비율만큼 깎고 즉시 판매
TREND_MIN_THRESHOLD = 5.0  # 이 수치 미만이면 당일 구매자 0명 (재고 묶임)


def _keyword_heat_bonus(keyword_ids: list, season_id: int, db: Session) -> float:
    """아이템 키워드들의 시즌 열기 레벨 평균 → 트렌드 배율 반환.
    HOT=×1.4 / WARM=×1.2 / COLD 또는 미탐험=×0.8"""
    if not keyword_ids:
        return 1.0
    total = 0.0
    for kid in keyword_ids:
        freq = db.query(KeywordFrequency).filter(
            KeywordFrequency.season_id == season_id,
            KeywordFrequency.keyword_id == kid
        ).first()
        if not freq:
            total += 0.8  # 탐험하지 않은 키워드 → 페널티
            continue
        npc_count = len(freq.npc_sources or [])
        if npc_count >= 3 or freq.mention_count >= 5:
            total += 1.4  # HOT
        elif npc_count >= 2 or freq.mention_count >= 3:
            total += 1.2  # WARM
        else:
            total += 0.9  # COLD
    return total / len(keyword_ids)


def _saturation_factor(current_day: int) -> float:
    """날이 갈수록 시장 포화 → 구매자 점감. 최소 30% 유지."""
    return max(0.3, 1.0 - current_day * 0.005)


def calculate_daily_demand(item: MarketItem, trend_index: float, stock: int, base_buyers: int = 5) -> tuple[int, int]:
    """advance-day 판매 resolve용.
    - trend_index < TREND_MIN_THRESHOLD: 구매자 없음 (판매 실패 가능)
    - 수요에 시장 변동 노이즈(gauss) 적용 → 흉일/호일 발생"""
    if trend_index < TREND_MIN_THRESHOLD or stock <= 0:
        return 0, 0

    grade_multiplier = {"S": 2.0, "A": 1.5, "B": 1.0, "C": 0.5}
    g_mult = grade_multiplier.get(item.grade, 1.0)

    price_ratio = item.current_price / item.base_value if item.base_value > 0 else 1.0
    price_factor = max(0.0, min(1.5, 1.0 - PRICE_SENSITIVITY * (price_ratio - 1.0)))

    raw_buyers = base_buyers * (trend_index / 100) * g_mult * price_factor

    # 시장 변동 노이즈: 평균 1.0, 표준편차 0.45 → 약 25% 확률로 0.5 미만(부진)
    market_factor = max(0.0, random.gauss(1.0, 0.45))
    buyers = max(0, round(raw_buyers * market_factor))

    buy_prob = min(0.8, trend_index / 120)
    sold = min(round(buyers * buy_prob), buyers, stock)

    return buyers, sold


def _calc_season_material_cost(db: Session, season_id: int) -> float:
    """해당 시즌에 등록된 아이템들의 material_cost 합산"""
    total = db.query(func.sum(MarketItem.material_cost)).filter(
        MarketItem.season_id == season_id
    ).scalar()
    return float(total or 0)


def accumulate_settlement(db: Session, season_id: int, revenue: float) -> Settlement:
    material = _calc_season_material_cost(db, season_id)
    settlement = db.query(Settlement).filter(Settlement.season_id == season_id).first()
    if not settlement:
        rent = 500
        marketing = 0
        management = 200
        settlement = Settlement(
            season_id=season_id,
            total_revenue=revenue,
            material_cost=material,
            rent_cost=rent,
            marketing_cost=marketing,
            management_cost=management,
            net_profit=revenue - material - rent - marketing - management
        )
        db.add(settlement)
    else:
        settlement.total_revenue = (settlement.total_revenue or 0) + revenue
        settlement.material_cost = material
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
    return settlement


@router.post("/items", status_code=201)
def register_item(body: MarketItemCreate, db: Session = Depends(get_db)):
    active_season = db.query(Season).filter(Season.status == "ACTIVE").first()
    active_season_id = active_season.id if active_season else 1
    market_state = get_or_create_market_state(db, active_season_id)

    item_data = body.dict()
    item_data["release_day"] = market_state.current_day
    item_data["season_id"] = active_season_id
    item_data["current_price"] = item_data["base_value"]

    # 키워드 희귀도 기반 재료비 계산
    keyword_ids = item_data.get("keyword_ids") or []
    material = 0
    for kid in keyword_ids:
        kw = db.query(Keyword).filter(Keyword.id == kid).first()
        rarity = kw.rarity if kw else None
        material += KEYWORD_RARITY_COST.get(rarity, DEFAULT_KEYWORD_COST)
    item_data["material_cost"] = material

    item = MarketItem(**item_data)
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"status": "success", "data": MarketItemResponse.from_orm(item).dict()}


@router.post("/advance-day")
def advance_day(body: AdvanceDayRequest, db: Session = Depends(get_db)):
    active_season = db.query(Season).filter(Season.status == "ACTIVE").first()
    active_season_id = active_season.id if active_season else 1
    market_state = get_or_create_market_state(db, active_season_id)

    active_items = db.query(MarketItem).filter(
        MarketItem.season_id == active_season_id,
        MarketItem.status == "ACTIVE"
    ).all()

    sales_by_item = {item.id: {"sold_today": 0, "revenue_today": 0.0} for item in active_items}
    total_revenue = 0.0

    for _ in range(body.days):
        market_state.current_day += 1
        saturation = _saturation_factor(market_state.current_day)

        for item in active_items:
            if item.status != "ACTIVE" or item.stock <= 0:
                continue

            base_index = calculate_trend_index(item, market_state.current_day)
            heat_bonus = _keyword_heat_bonus(
                item.keyword_ids or [], active_season_id, db
            )
            # 키워드 열기 평균이 1.0 미만 (COLD/미탐험) → 해당 일 구매자 없음
            if heat_bonus < 1.0:
                continue
            effective_index = base_index * heat_bonus
            effective_buyers = max(1, round(5 * saturation))
            _, sold = calculate_daily_demand(item, effective_index, item.stock, effective_buyers)
            if sold <= 0:
                continue

            revenue_today = round(sold * item.current_price, 1)

            item.stock -= sold
            if item.stock == 0:
                item.status = "SOLD_OUT"

            sales_by_item[item.id]["sold_today"] += sold
            sales_by_item[item.id]["revenue_today"] = round(
                sales_by_item[item.id]["revenue_today"] + revenue_today, 1
            )
            total_revenue += revenue_today

    if total_revenue > 0:
        accumulate_settlement(db, active_season_id, round(total_revenue, 1))

    db.commit()

    items_data = [
        {
            "item_id": item.id,
            "trend_index": calculate_trend_index(item, market_state.current_day),
            "remaining_stock": item.stock,
            "status": item.status,
            "sold_today": sales_by_item[item.id]["sold_today"],
            "revenue_today": sales_by_item[item.id]["revenue_today"]
        }
        for item in active_items
    ]

    return {
        "status": "success",
        "data": {
            "current_day": market_state.current_day,
            "items": items_data
        }
    }


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
    # 서버 클럭(MarketState, item의 시즌 기준) 날짜로 현재 트렌드 지수를 계산
    market_state = get_or_create_market_state(db, item.season_id)
    current_index = calculate_trend_index(item, market_state.current_day)

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

    if item.status == "DEAD":
        raise HTTPException(status_code=409, detail={
            "status": "error",
            "error_code": "ITEM_DEAD",
            "message": "이전 사이클에서 판매되지 않은 상품입니다. 유행이 완전히 지나 판매 불가능합니다."
        })

    if item.stock < body.quantity:
        raise HTTPException(status_code=409, detail={
            "status": "error",
            "error_code": "ITEM_OUT_OF_STOCK",
            "message": f"재고가 부족합니다 (현재 재고: {item.stock})"
        })

    # 즉시청산: trend/할인율 안 쓰고, current_price에 고정 페널티만 적용
    sold = min(body.quantity, item.stock)
    revenue = round(sold * item.current_price * (1 - FIRE_SALE_PENALTY), 1)

    item.stock -= sold
    if item.stock == 0:
        item.status = "SOLD_OUT"

    accumulate_settlement(db, item.season_id, revenue)
    db.commit()

    # trend_index는 가격에 영향 없는 informational 값 -- 서버 클럭(item의 시즌) 기준
    market_state = get_or_create_market_state(db, item.season_id)
    trend_index = calculate_trend_index(item, market_state.current_day)

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

    # 재료비는 등록된 아이템에서 실시간 합산 (누락 방지)
    material = _calc_season_material_cost(db, season_id)
    settlement.material_cost = material
    settlement.net_profit = (
        (settlement.total_revenue or 0)
        - material
        - (settlement.rent_cost or 500)
        - (settlement.marketing_cost or 0)
        - (settlement.management_cost or 200)
    )
    db.commit()

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

    market_state = get_or_create_market_state(db, item.season_id)
    trend_index = calculate_trend_index(item, market_state.current_day)
    days_on_market = max(0, market_state.current_day - item.release_day)

    # 매출 계산 (정산 테이블에서)
    active_season = db.query(Season).filter(Season.status == "ACTIVE").first()
    active_season_id = active_season.id if active_season else 1
    settlement = db.query(Settlement).filter(Settlement.season_id == active_season_id).first()
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

    simulation = []
    cumulative_revenue = 0.0
    remaining_stock = item.stock

    for d in range(1, days + 1):
        current_day = item.release_day + d
        trend = calculate_trend_index(item, current_day)

        # advance-day(POST /market/advance-day)와 동일한 결정적 수요 공식 재사용 -- 예측=실제.
        buyers, sold = calculate_daily_demand(item, trend, remaining_stock, base_buyers)

        if sold > 0:
            remaining_stock -= sold
            day_revenue = sold * item.current_price
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

    old_price = item.current_price
    item.current_price = body.new_price
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