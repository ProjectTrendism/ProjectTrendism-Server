from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.explore import Season, NPC, Event, PlayerInventory, SeasonNPCInfo
from app.models.keyword import Keyword
from app.models.frequency import KeywordFrequency, HiddenKeyword
from app.schemas.explore import (
    SeasonStatus, ActionRequest, ActionResult,
    EventResponse, InventoryItem, DayEndResult
)
from app.schemas.frequency import NPCListItem
import random

router = APIRouter(prefix="/explore", tags=["Explore"])


# ── 빈도수 업데이트 헬퍼 ─────────────────────────────────
def _update_frequency(season_id: int, keyword_id: int, npc_id: int | None, db: Session):
    """키워드 드랍 시 빈도수 테이블 업데이트"""
    freq = db.query(KeywordFrequency).filter(
        KeywordFrequency.season_id == season_id,
        KeywordFrequency.keyword_id == keyword_id
    ).first()

    if not freq:
        freq = KeywordFrequency(
            season_id=season_id,
            keyword_id=keyword_id,
            mention_count=1,
            drop_count=1,
            npc_sources=[npc_id] if npc_id else []
        )
        db.add(freq)
    else:
        freq.mention_count += 1
        freq.drop_count += 1
        if npc_id and npc_id not in (freq.npc_sources or []):
            sources = list(freq.npc_sources or [])
            sources.append(npc_id)
            freq.npc_sources = sources

    db.flush()


def _check_hidden_unlocks(season_id: int, keyword_id: int, npc_id: int | None, db: Session):
    """히든 키워드 해금 조건 체크"""
    unlocked_items = []

    hidden_keywords = db.query(HiddenKeyword).filter(
        HiddenKeyword.is_unlocked == False
    ).all()

    for hk in hidden_keywords:
        condition = hk.unlock_condition or {}
        should_unlock = False

        if hk.unlock_type == "FREQUENCY":
            target_kw_id = condition.get("target_keyword_id")
            threshold = condition.get("threshold", 5)
            freq = db.query(KeywordFrequency).filter(
                KeywordFrequency.season_id == season_id,
                KeywordFrequency.keyword_id == target_kw_id
            ).first()
            if freq and freq.mention_count >= threshold:
                should_unlock = True

        elif hk.unlock_type == "NPC_COMBO":
            required_npcs = set(condition.get("required_npcs", []))
            # 이번 시즌에서 대화한 NPC 목록 (빈도수 테이블의 npc_sources 통합)
            all_sources = set()
            freqs = db.query(KeywordFrequency).filter(
                KeywordFrequency.season_id == season_id
            ).all()
            for f in freqs:
                all_sources.update(f.npc_sources or [])
            if required_npcs.issubset(all_sources):
                should_unlock = True

        if should_unlock:
            hk.is_unlocked = True
            # 히든 키워드를 인벤토리에 자동 추가
            existing = db.query(PlayerInventory).filter(
                PlayerInventory.season_id == season_id,
                PlayerInventory.keyword_id == hk.keyword_id
            ).first()
            if not existing:
                db.add(PlayerInventory(
                    season_id=season_id,
                    keyword_id=hk.keyword_id
                ))
            keyword = db.query(Keyword).filter(Keyword.id == hk.keyword_id).first()
            unlocked_items.append({
                "keyword_id": hk.keyword_id,
                "keyword_name": keyword.name if keyword else "???",
                "hint_text": hk.hint_text
            })

    if unlocked_items:
        db.flush()

    return unlocked_items


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


# ── GET /explore/npcs  NPC 목록 조회 ────────────────────
@router.get("/npcs")
def get_npcs(location: str | None = None, db: Session = Depends(get_db)):
    query = db.query(NPC).filter(NPC.is_active == True)
    if location:
        query = query.filter(NPC.location == location)
    npcs = query.all()

    # 현재 활성 시즌의 NPC 인스턴스를 한 번에 조회 (N+1 방지)
    season = db.query(Season).filter(Season.status == "ACTIVE").first()
    info_map = {}
    if season:
        infos = db.query(SeasonNPCInfo).filter(
            SeasonNPCInfo.season_id == season.id
        ).all()
        info_map = {info.npc_id: info for info in infos}

    result = []
    for n in npcs:
        info = info_map.get(n.id)
        result.append(NPCListItem(
            id=n.id,
            name=n.name,
            location=n.location,
            is_active=n.is_active,
            portrait_id=n.portrait_id,
            # 시즌 인스턴스가 있으면 그 대사, 없으면 기존 고정 대사로 폴백
            season_dialogue=(info.season_dialogue if info else n.dialogue) or "",
            # 인스턴스 없으면 미파악(None)
            perceived_reliability=(info.perceived_reliability if info else None),
            talked=(info.talked if info else False),
        ).dict())

    return {"status": "success", "data": result}


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

    # NPC가 보유한 모든 키워드의 mention_count 증가 (대화하면 언급은 항상 발생)
    for kw_id in (npc.keyword_drops or []):
        freq = db.query(KeywordFrequency).filter(
            KeywordFrequency.season_id == season.id,
            KeywordFrequency.keyword_id == kw_id
        ).first()
        if not freq:
            freq = KeywordFrequency(
                season_id=season.id,
                keyword_id=kw_id,
                mention_count=1,
                drop_count=0,
                npc_sources=[npc_id]
            )
            db.add(freq)
        else:
            freq.mention_count += 1
            if npc_id not in (freq.npc_sources or []):
                sources = list(freq.npc_sources or [])
                sources.append(npc_id)
                freq.npc_sources = sources
    db.flush()

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

        # 드랍 카운트 업데이트
        freq = db.query(KeywordFrequency).filter(
            KeywordFrequency.season_id == season.id,
            KeywordFrequency.keyword_id == keyword_id
        ).first()
        if freq:
            freq.drop_count += 1
        db.flush()

        # 히든 키워드 해금 체크
        unlocked = _check_hidden_unlocks(season.id, keyword_id, npc_id, db)
        db.commit()

        result = {
            "success": True,
            "message": f"{npc.name}: {npc.dialogue}",
            "keyword_id": keyword_id,
            "keyword_name": keyword.name if keyword else None,
            "keyword_rarity": keyword.rarity if keyword else None,
            "warning": warning
        }
        if unlocked:
            result["hidden_unlocked"] = unlocked

        return {"status": "success", "data": result}

    # 히든 키워드 체크 (드랍 없어도 NPC 대화로 해금 가능)
    unlocked = _check_hidden_unlocks(season.id, None, npc_id, db)
    db.commit()

    result = {
        "success": True,
        "message": f"{npc.name}: {npc.dialogue}",
        "keyword_id": None,
        "keyword_name": None,
        "warning": warning
    }
    if unlocked:
        result["hidden_unlocked"] = unlocked

    return {"status": "success", "data": result}


def _handle_scan(season: Season, warning, db: Session):
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

            _update_frequency(season.id, keyword.id, None, db)
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

    # 도청도 mention_count 증가
    for kw_id in (npc.keyword_drops or []):
        freq = db.query(KeywordFrequency).filter(
            KeywordFrequency.season_id == season.id,
            KeywordFrequency.keyword_id == kw_id
        ).first()
        if not freq:
            freq = KeywordFrequency(
                season_id=season.id,
                keyword_id=kw_id,
                mention_count=1,
                drop_count=0,
                npc_sources=[npc_id]
            )
            db.add(freq)
        else:
            freq.mention_count += 1
            if npc_id not in (freq.npc_sources or []):
                sources = list(freq.npc_sources or [])
                sources.append(npc_id)
                freq.npc_sources = sources
    db.flush()

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

        # 드랍 카운트
        freq = db.query(KeywordFrequency).filter(
            KeywordFrequency.season_id == season.id,
            KeywordFrequency.keyword_id == keyword_id
        ).first()
        if freq:
            freq.drop_count += 1

        unlocked = _check_hidden_unlocks(season.id, keyword_id, npc_id, db)
        db.commit()

        result = {
            "success": True,
            "message": f"도청 성공! 대화 내용을 엿들었습니다.",
            "keyword_id": keyword_id,
            "keyword_name": keyword.name if keyword else None,
            "keyword_rarity": keyword.rarity if keyword else None,
            "warning": warning
        }
        if unlocked:
            result["hidden_unlocked"] = unlocked

        return {"status": "success", "data": result}

    unlocked = _check_hidden_unlocks(season.id, None, npc_id, db)
    db.commit()

    result = {
        "success": False,
        "message": "도청에 실패했습니다",
        "warning": warning
    }
    if unlocked:
        result["hidden_unlocked"] = unlocked

    return {"status": "success", "data": result}


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


# ── GET /explore/frequency  키워드 빈도수 조회 ──────────
@router.get("/frequency")
def get_frequency(db: Session = Depends(get_db)):
    season = db.query(Season).filter(Season.status == "ACTIVE").first()
    if not season:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "NO_ACTIVE_SEASON",
            "message": "진행 중인 시즌이 없습니다"
        })

    freqs = db.query(KeywordFrequency).filter(
        KeywordFrequency.season_id == season.id
    ).order_by(KeywordFrequency.mention_count.desc()).all()

    result = []
    for f in freqs:
        keyword = db.query(Keyword).filter(Keyword.id == f.keyword_id).first()
        if not keyword:
            continue

        # 열기 레벨 판정
        npc_count = len(f.npc_sources or [])
        if npc_count >= 3 or f.mention_count >= 5:
            heat = "HOT"
        elif npc_count >= 2 or f.mention_count >= 3:
            heat = "WARM"
        else:
            heat = "COLD"

        result.append({
            "keyword_id": f.keyword_id,
            "keyword_name": keyword.name,
            "mention_count": f.mention_count,
            "drop_count": f.drop_count,
            "npc_count": npc_count,
            "heat_level": heat
        })

    return {"status": "success", "data": result}


# ── GET /explore/hidden  히든 키워드 힌트 조회 ──────────
@router.get("/hidden")
def get_hidden_hints(db: Session = Depends(get_db)):
    hiddens = db.query(HiddenKeyword).all()
    result = []
    for h in hiddens:
        keyword = db.query(Keyword).filter(Keyword.id == h.keyword_id).first()
        result.append({
            "id": h.id,
            "hint_text": h.hint_text,
            "unlock_type": h.unlock_type,
            "is_unlocked": h.is_unlocked,
            "keyword_name": keyword.name if (h.is_unlocked and keyword) else "???"
        })
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

    season.current_day += 1
    season.current_time = 8
    db.commit()

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
