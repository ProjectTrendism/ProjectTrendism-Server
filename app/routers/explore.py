from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.explore import Season, NPC, Event, PlayerInventory
from app.models.keyword import Keyword
from app.schemas.explore import (
    SeasonStatus, ActionRequest, ActionResult,
    EventResponse, InventoryItem, DayEndResult
)
import random

router = APIRouter(prefix="/explore", tags=["Explore"])


# ── POST /explore/start  시즌 시작 ──────────────────────
@router.post("/start")
def start_season(db: Session = Depends(get_db)):
    existing = db.query(Season).filter(Season.status == "ACTIVE").first()
    if existing:
        return {
            "status": "success",
            "data": SeasonStatus.from_orm(existing).dict(),
            "message": "이미 진행 중인 시즌이 있습니다"
        }

    season = Season(current_day=1, current_time=8, phase="EXPLORE", status="ACTIVE")
    db.add(season)
    db.commit()
    db.refresh(season)

    return {
        "status": "success",
        "data": SeasonStatus.from_orm(season).dict(),
        "message": "시즌 1일차 탐험 시작!"
    }


# ── GET /explore/status  현재 상태 조회 ─────────────────
@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    season = db.query(Season).filter(Season.status == "ACTIVE").first()
    if not season:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "NO_ACTIVE_SEASON",
            "message": "진행 중인 시즌이 없습니다. /explore/start 로 시작하세요"
        })

    warning = None
    if season.current_time >= 22:
        warning = "⚠️ 22시 이후! 보안관이 활성화됩니다. 귀가하세요!"

    return {
        "status": "success",
        "data": {
            **SeasonStatus.from_orm(season).dict(),
            "warning": warning
        }
    }


# ── POST /explore/action  행동 처리 ─────────────────────
@router.post("/action")
def do_action(body: ActionRequest, db: Session = Depends(get_db)):
    season = db.query(Season).filter(Season.status == "ACTIVE").first()
    if not season:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "NO_ACTIVE_SEASON",
            "message": "진행 중인 시즌이 없습니다"
        })

    # 22시 이후 보안관 체포
    if season.current_time >= 22:
        # 랜덤 키워드 1~2개 압수
        inventory = db.query(PlayerInventory).filter(
            PlayerInventory.season_id == season.id
        ).all()

        seized_count = min(random.randint(1, 2), len(inventory))
        for i in range(seized_count):
            if inventory:
                item = random.choice(inventory)
                inventory.remove(item)
                db.delete(item)
        db.commit()

        return {
            "status": "success",
            "data": {
                "success": False,
                "message": f"보안관에게 체포됐습니다! 키워드 {seized_count}개를 압수당하고 강제 귀가합니다.",
                "warning": "강제 귀가"
            }
        }

    # 행동 시간 소모 (행동당 1시간)
    season.current_time += 1
    db.commit()

    warning = None
    if season.current_time >= 21:
        warning = "⚠️ 곧 22시입니다! 서둘러 귀가하세요!"

    # 행동 처리
    if body.action_type == "TALK":
        return _handle_talk(body.target_id, season, warning, db)
    elif body.action_type == "SCAN":
        return _handle_scan(season, warning, db)
    elif body.action_type == "EAVESDROP":
        return _handle_eavesdrop(body.target_id, season, warning, db)
    else:
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "error_code": "INVALID_ACTION",
            "message": "유효한 행동: TALK / SCAN / EAVESDROP"
        })


def _handle_talk(npc_id: int, season: Season, warning, db: Session):
    npc = db.query(NPC).filter(NPC.id == npc_id, NPC.is_active == True).first()
    if not npc:
        return {"status": "success", "data": {
            "success": False,
            "message": "NPC를 찾을 수 없습니다",
            "warning": warning
        }}

    # 키워드 드랍 확률 계산
    if random.random() < npc.drop_rate and npc.keyword_drops:
        keyword_id = random.choice(npc.keyword_drops)
        keyword = db.query(Keyword).filter(Keyword.id == keyword_id).first()

        # 인벤토리에 추가
        existing = db.query(PlayerInventory).filter(
            PlayerInventory.season_id == season.id,
            PlayerInventory.keyword_id == keyword_id
        ).first()

        if existing:
            existing.quantity += 1
        else:
            db.add(PlayerInventory(
                season_id=season.id,
                keyword_id=keyword_id
            ))
        db.commit()

        return {"status": "success", "data": {
            "success": True,
            "message": f"{npc.name}: {npc.dialogue}",
            "keyword_id": keyword_id,
            "keyword_name": keyword.name if keyword else None,
            "keyword_rarity": keyword.rarity if keyword else None,
            "warning": warning
        }}

    return {"status": "success", "data": {
        "success": True,
        "message": f"{npc.name}: {npc.dialogue}",
        "keyword_id": None,
        "keyword_name": None,
        "warning": warning
    }}


def _handle_scan(season: Season, warning, db: Session):
    # 스캔: 랜덤 키워드 낮은 확률로 획득
    if random.random() < 0.4:
        keyword = db.query(Keyword).filter(
            Keyword.rarity == "COMMON"
        ).order_by(Keyword.id).first()

        if keyword:
            existing = db.query(PlayerInventory).filter(
                PlayerInventory.season_id == season.id,
                PlayerInventory.keyword_id == keyword.id
            ).first()

            if existing:
                existing.quantity += 1
            else:
                db.add(PlayerInventory(
                    season_id=season.id,
                    keyword_id=keyword.id
                ))
            db.commit()

            return {"status": "success", "data": {
                "success": True,
                "message": "숨겨진 재료를 발견했습니다!",
                "keyword_id": keyword.id,
                "keyword_name": keyword.name,
                "keyword_rarity": keyword.rarity,
                "warning": warning
            }}

    return {"status": "success", "data": {
        "success": False,
        "message": "아무것도 발견하지 못했습니다",
        "warning": warning
    }}


def _handle_eavesdrop(npc_id: int, season: Season, warning, db: Session):
    npc = db.query(NPC).filter(NPC.id == npc_id, NPC.is_active == True).first()
    if not npc:
        return {"status": "success", "data": {
            "success": False,
            "message": "도청 대상을 찾을 수 없습니다",
            "warning": warning
        }}

    # 도청: 높은 확률로 RARE 이상 키워드 획득
    if random.random() < 0.8 and npc.keyword_drops:
        keyword_id = random.choice(npc.keyword_drops)
        keyword = db.query(Keyword).filter(Keyword.id == keyword_id).first()

        existing = db.query(PlayerInventory).filter(
            PlayerInventory.season_id == season.id,
            PlayerInventory.keyword_id == keyword_id
        ).first()

        if existing:
            existing.quantity += 1
        else:
            db.add(PlayerInventory(
                season_id=season.id,
                keyword_id=keyword_id
            ))
        db.commit()

        return {"status": "success", "data": {
            "success": True,
            "message": f"도청 성공! 대화 내용을 엿들었습니다.",
            "keyword_id": keyword_id,
            "keyword_name": keyword.name if keyword else None,
            "keyword_rarity": keyword.rarity if keyword else None,
            "warning": warning
        }}

    return {"status": "success", "data": {
        "success": False,
        "message": "도청에 실패했습니다",
        "warning": warning
    }}


# ── GET /explore/events/{day}  이벤트 조회 ──────────────
@router.get("/events/{day}")
def get_events(day: int, db: Session = Depends(get_db)):
    fixed = db.query(Event).filter(
        Event.event_type == "FIXED",
        Event.trigger_day == day,
        Event.is_active == True
    ).all()

    random_events = db.query(Event).filter(
        Event.event_type == "RANDOM",
        Event.is_active == True
    ).all()

    triggered = [e for e in random_events if random.random() < e.trigger_prob]

    all_events = fixed + triggered

    return {
        "status": "success",
        "data": [EventResponse.from_orm(e).dict() for e in all_events]
    }


# ── GET /explore/inventory  인벤토리 조회 ───────────────
@router.get("/inventory")
def get_inventory(db: Session = Depends(get_db)):
    season = db.query(Season).filter(Season.status == "ACTIVE").first()
    if not season:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "NO_ACTIVE_SEASON",
            "message": "진행 중인 시즌이 없습니다"
        })

    inventory = db.query(PlayerInventory).filter(
        PlayerInventory.season_id == season.id
    ).all()

    result = []
    for item in inventory:
        keyword = db.query(Keyword).filter(Keyword.id == item.keyword_id).first()
        if keyword:
            result.append(InventoryItem(
                keyword_id=item.keyword_id,
                keyword_name=keyword.name,
                category=keyword.category,
                rarity=keyword.rarity,
                quantity=item.quantity
            ).dict())

    return {"status": "success", "data": result}


# ── POST /explore/day-end  일차 종료 ────────────────────
@router.post("/day-end")
def end_day(db: Session = Depends(get_db)):
    season = db.query(Season).filter(Season.status == "ACTIVE").first()
    if not season:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "NO_ACTIVE_SEASON",
            "message": "진행 중인 시즌이 없습니다"
        })

    completed_day = season.current_day

    if season.current_day >= 7:
        # 7일 완료 → 제작 파트로 전환
        season.phase = "CRAFT"
        season.status = "FINISHED"
        db.commit()
        return {
            "status": "success",
            "data": DayEndResult(
                day_completed=completed_day,
                next_day=None,
                events_tomorrow=[],
                phase_changed=True,
                message="7일간의 탐험 완료! 제작 파트로 이동합니다."
            ).dict()
        }

    # 다음 날로
    season.current_day += 1
    season.current_time = 8  # 시간 리셋
    db.commit()

    # 내일 이벤트 미리보기
    tomorrow_events = db.query(Event).filter(
        Event.event_type == "FIXED",
        Event.trigger_day == season.current_day,
        Event.is_active == True
    ).all()

    return {
        "status": "success",
        "data": DayEndResult(
            day_completed=completed_day,
            next_day=season.current_day,
            events_tomorrow=[e.name for e in tomorrow_events],
            phase_changed=False,
            message=f"Day {completed_day} 완료! Day {season.current_day} 시작."
        ).dict()
    }