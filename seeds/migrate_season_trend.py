"""
마이그레이션 (2026-05): 탐험 시즌 트렌드 시스템 (3-1)
- seasons 테이블에 trend_theme 컬럼 추가
- seasons 테이블에 rising_keyword_ids 컬럼 추가

기존 game.db 데이터를 보존한 채 스키마만 갱신한다.

실행 (Windows PowerShell, 프로젝트 루트에서):
    venv\\Scripts\\activate
    python seeds\\migrate_season_trend.py
"""
import sys
import os

# 프로젝트 루트를 import path에 추가 (seed.py와 동일 패턴)
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import inspect, text
from app.database import engine
import app.models.explore  # noqa: F401  -- 모델 로드


def migrate():
    print("=" * 60)
    print("  탐험 시즌 트렌드 마이그레이션 (3-1)")
    print("=" * 60)

    inspector = inspect(engine)

    if "seasons" not in inspector.get_table_names():
        print("  [WARN] seasons 테이블이 없습니다. 먼저 seeds/seed.py를 실행하세요")
        print("=" * 60)
        return

    columns = [c["name"] for c in inspector.get_columns("seasons")]

    # -- 1) seasons.trend_theme --
    if "trend_theme" in columns:
        print("  [SKIP] seasons.trend_theme 컬럼이 이미 존재합니다")
    else:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE seasons ADD COLUMN trend_theme VARCHAR DEFAULT ''"
            ))
            conn.commit()
        print("  [ OK ] seasons.trend_theme 컬럼 추가 완료")

    # -- 2) seasons.rising_keyword_ids --
    # SQLite는 JSON을 TEXT affinity로 저장한다. 기존 row는 NULL이 되며,
    # 코드에서는 (season.rising_keyword_ids or []) 로 방어한다.
    if "rising_keyword_ids" in columns:
        print("  [SKIP] seasons.rising_keyword_ids 컬럼이 이미 존재합니다")
    else:
        with engine.connect() as conn:
            conn.execute(text(
                "ALTER TABLE seasons ADD COLUMN rising_keyword_ids JSON"
            ))
            conn.commit()
        print("  [ OK ] seasons.rising_keyword_ids 컬럼 추가 완료")

    print("=" * 60)
    print("  [DONE] 마이그레이션 완료")
    print("=" * 60)


if __name__ == "__main__":
    migrate()