"""
사전 생성 스크립트 -- 시즌 트렌드 + NPC 시즌 정보 (3-3, 개선판)
- Claude로 N개 시즌치의 트렌드/NPC 정보를 미리 생성한다.
- 트렌드는 'N개를 한 번에' 생성해 시즌 간 다양성을 확보한다.
- seasons 테이블에 status="PENDING" 시즌으로 저장하고,
  season_npc_info 테이블에 시즌별 NPC 정보를 저장한다.
- 중단/재시작 안전: 이미 만들어 둔 PENDING 시즌은 건드리지 않는다.
- 한 시즌은 원자적으로 커밋한다 (Season 1건 + SeasonNPCInfo 25건).

실행 (Windows PowerShell, 프로젝트 루트에서):
    venv\\Scripts\\activate
    python seeds\\pregenerate_seasons.py            # PENDING 시즌을 10개까지 채움
    python seeds\\pregenerate_seasons.py 1           # 1개만
    python seeds\\pregenerate_seasons.py reset       # 기존 PENDING 전부 삭제 후 10개 재생성
    python seeds\\pregenerate_seasons.py reset 5     # 기존 PENDING 전부 삭제 후 5개 재생성
"""
import os
import sys
import time

# 프로젝트 루트를 import path에 추가 (seed.py와 동일 패턴)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models.keyword import Keyword
from app.models.explore import Season, NPC, SeasonNPCInfo
from app.services.claude_service import (
    generate_all_season_trends,
    generate_npc_season_info,
)

# 누락된 테이블 자동 생성
Base.metadata.create_all(bind=engine)


# ── 설정 ────────────────────────────────────────────────
DEFAULT_TARGET = 10          # 기본 목표 PENDING 시즌 개수
SLEEP_BETWEEN_CALLS = 1.0    # API 호출 간 대기 (초, rate limit 방지)


def _load_keywords(db) -> list[dict]:
    """전체 키워드를 dict 목록으로 로드."""
    keywords = db.query(Keyword).all()
    return [
        {
            "id": k.id,
            "name": k.name,
            "category": k.category,
            "description": k.description or "",
        }
        for k in keywords
    ]


def _load_npcs(db) -> list[dict]:
    """활성 NPC를 dict 목록으로 로드."""
    npcs = db.query(NPC).filter(NPC.is_active == True).all()
    return [
        {"id": n.id, "name": n.name, "location": n.location}
        for n in npcs
    ]


def _reset_pending(db) -> int:
    """
    기존 PENDING 시즌과 그 SeasonNPCInfo를 모두 삭제한다.
    ACTIVE/FINISHED 시즌은 건드리지 않는다 (진행 중인 게임 보호).
    """
    pending = db.query(Season).filter(Season.status == "PENDING").all()
    pending_ids = [s.id for s in pending]
    if not pending_ids:
        return 0
    db.query(SeasonNPCInfo).filter(
        SeasonNPCInfo.season_id.in_(pending_ids)
    ).delete(synchronize_session=False)
    db.query(Season).filter(
        Season.id.in_(pending_ids)
    ).delete(synchronize_session=False)
    db.commit()
    return len(pending_ids)


def _save_one_season(db, label: str, trend: dict,
                     keywords: list[dict], npcs: list[dict]) -> None:
    """
    이미 생성된 트렌드를 받아 NPC 정보를 생성하고, 시즌 1개를 원자적으로 저장한다.
    Season 1건 + SeasonNPCInfo (NPC 수)건을 한 트랜잭션으로 커밋한다.
    """
    print(f"\n[{label}] 생성 시작 (NPC {len(npcs)}명)")
    print(f"  - 트렌드 테마   : {trend['trend_theme']}")
    print(f"  - 급상승 키워드 : {trend['rising_keyword_ids']}")

    # 급상승 키워드 dict 추출
    rising_set = set(trend["rising_keyword_ids"])
    rising_keywords = [k for k in keywords if k["id"] in rising_set]

    # NPC 시즌 정보 생성
    npc_infos = generate_npc_season_info(
        trend_theme=trend["trend_theme"],
        rising_keywords=rising_keywords,
        all_keywords=keywords,
        npcs=npcs,
    )
    disinformer_count = sum(1 for n in npc_infos if n["is_disinformer"])
    print(f"  - NPC 정보      : {len(npc_infos)}명 "
          f"(거짓 정보원 {disinformer_count}명)")
    time.sleep(SLEEP_BETWEEN_CALLS)

    # DB 저장 (원자적: flush로 season.id 확보 후 한 번에 commit)
    try:
        season = Season(
            current_day=1,
            current_time=8,
            phase="EXPLORE",
            status="PENDING",
            trend_theme=trend["trend_theme"],
            rising_keyword_ids=trend["rising_keyword_ids"],
        )
        db.add(season)
        db.flush()  # season.id 확보 (아직 커밋 아님)

        for info in npc_infos:
            db.add(SeasonNPCInfo(
                season_id=season.id,
                npc_id=info["npc_id"],
                season_dialogue=info["season_dialogue"],
                talked=False,
                assigned_keywords=info["assigned_keywords"],
                true_reliability=info["true_reliability"],
                is_disinformer=info["is_disinformer"],
                perceived_reliability=None,
            ))

        db.commit()
        print(f"  [ OK ] 저장 완료 (season_id={season.id})")
    except Exception:
        db.rollback()
        raise


def pregenerate(target_count: int, do_reset: bool = False) -> None:
    print("=" * 60)
    print("  시즌 트렌드 + NPC 정보 사전 생성 (3-3 개선판)")
    print("=" * 60)

    db = SessionLocal()
    try:
        keywords = _load_keywords(db)
        npcs = _load_npcs(db)

        if not keywords:
            print("  [FAIL] 키워드가 없습니다. seeds/seed.py를 먼저 실행하세요")
            return
        if not npcs:
            print("  [FAIL] NPC가 없습니다. seeds/seed.py를 먼저 실행하세요")
            return

        print(f"  키워드 {len(keywords)}개, NPC {len(npcs)}명 로드 완료")

        # reset 모드: 기존 PENDING 시즌 정리
        if do_reset:
            removed = _reset_pending(db)
            print(f"  [RESET] 기존 PENDING 시즌 {removed}개 삭제 완료")

        # 이미 만들어 둔 PENDING 시즌 개수 확인 (멱등성)
        existing_pending = db.query(Season).filter(
            Season.status == "PENDING"
        ).count()
        print(f"  현재 PENDING 시즌: {existing_pending}개 / 목표: {target_count}개")

        to_create = target_count - existing_pending
        if to_create <= 0:
            print(f"  [SKIP] 이미 목표({target_count}개)를 채웠습니다")
            print("=" * 60)
            return

        # 트렌드를 한 번에 생성 (시즌 간 다양성 확보)
        print(f"  --> 트렌드 {to_create}개를 한 번에 생성합니다...")
        try:
            trends = generate_all_season_trends(keywords, to_create)
        except Exception as e:
            print(f"  [FAIL] 트렌드 일괄 생성 실패: {e}")
            print("=" * 60)
            return
        print(f"  [ OK ] 트렌드 {len(trends)}개 생성 완료")
        time.sleep(SLEEP_BETWEEN_CALLS)

        success = 0
        for i in range(to_create):
            label = f"시즌 {existing_pending + i + 1}"
            try:
                _save_one_season(db, label, trends[i], keywords, npcs)
                success += 1
            except Exception as e:
                print(f"  [FAIL] {label} 생성 실패: {e}")
                print("  이전까지 생성된 시즌은 저장됐습니다. "
                      "다시 실행하면 이어서 생성합니다")
                break

        print("=" * 60)
        print(f"  [DONE] {success}개 시즌 생성 완료 "
              f"(총 PENDING {existing_pending + success}개)")
        print("=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    args = sys.argv[1:]
    do_reset = "reset" in args

    target = DEFAULT_TARGET
    for a in args:
        if a == "reset":
            continue
        try:
            target = int(a)
        except ValueError:
            print(f"  [FAIL] 알 수 없는 인자: {a}")
            sys.exit(1)

    pregenerate(target, do_reset)