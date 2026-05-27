"""
마이그레이션 (2026-05): 탐험 시즌 시스템 1단계
- season_npc_info 테이블 신규 생성
- npcs 테이블에 portrait_id 컬럼 추가

기존 game.db 데이터(키워드/NPC/사전생성 캐시 등)를 보존한 채 스키마만 갱신한다.
DB를 처음부터 새로 만들 거라면 이 스크립트 대신
game.db 삭제 후 `python seeds/seed.py`를 실행하면 된다.

실행 (Windows PowerShell, 프로젝트 루트에서):
    venv\\Scripts\\activate
    python seeds\\migrate_season_npc.py
"""
import sys
import os

# -- import 경로 보정 --------------------------------------------
# `python seeds\migrate_season_npc.py`로 실행하면 Python이 스크립트가 위치한
# seeds/ 디렉토리를 sys.path 최상위에 자동 삽입한다.
# 이때 seeds/ 안에 표준 패키지(sqlalchemy가 내부적으로 import하는 util 등)와
# 이름이 같은 .py 파일이 있으면 그 파일이 정식 패키지를 가려(name shadowing)
# "partially initialized module" ImportError가 발생한다.
# 따라서 seeds/ 디렉토리를 sys.path에서 모두 제거하고 프로젝트 루트를 최상위에 둔다.
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.dirname(_THIS_DIR)
sys.path[:] = [p for p in sys.path if os.path.abspath(p or ".") != _THIS_DIR]
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
# ----------------------------------------------------------------

from sqlalchemy import inspect, text
from app.database import engine, Base

# explore 모델을 import 해야 SeasonNPCInfo가 Base.metadata에 등록된다.
import app.models.explore  # noqa: F401


def migrate():
    print("=" * 60)
    print("  탐험 시즌 시스템 마이그레이션 (2026-05)")
    print("=" * 60)

    inspector = inspect(engine)
    existing_tables = inspector.get_table_names()

    season_npc_existed = "season_npc_info" in existing_tables
    npcs_existed = "npcs" in existing_tables

    # -- 1) 누락 테이블 생성 (season_npc_info) --
    # create_all은 이미 존재하는 테이블은 건드리지 않으므로 안전하다.
    Base.metadata.create_all(bind=engine)
    if season_npc_existed:
        print("  [SKIP] season_npc_info 테이블이 이미 존재합니다")
    else:
        print("  [ OK ] season_npc_info 테이블 생성 완료")

    # -- 2) npcs.portrait_id 컬럼 추가 --
    if not npcs_existed:
        print("  [WARN] npcs 테이블이 없습니다. 먼저 seeds/seed.py를 실행하세요")
    else:
        columns = [c["name"] for c in inspector.get_columns("npcs")]
        if "portrait_id" in columns:
            print("  [SKIP] npcs.portrait_id 컬럼이 이미 존재합니다")
        else:
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE npcs ADD COLUMN portrait_id VARCHAR"))
                conn.commit()
            print("  [ OK ] npcs.portrait_id 컬럼 추가 완료")

    print("=" * 60)
    print("  [DONE] 마이그레이션 완료")
    print("=" * 60)


if __name__ == "__main__":
    migrate()