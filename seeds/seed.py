import json, sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models.keyword import Keyword
from app.models.explore import NPC, Event
from app.models.frequency import KeywordFrequency, HiddenKeyword

# 모든 테이블 생성
Base.metadata.create_all(bind=engine)


def _seed_table(db, model, json_path, label):
    """범용 시드 헬퍼"""
    existing = db.query(model).count()
    if existing > 0:
        print(f"  [{label}] 이미 {existing}개 데이터 존재. 건너뜁니다.")
        return 0

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for item in data:
        db.add(model(**item))
    db.commit()
    print(f"  [{label}] {len(data)}개 삽입 완료!")
    return len(data)


def seed():
    db = SessionLocal()
    try:
        print("=== 시드 데이터 삽입 시작 ===")
        _seed_table(db, Keyword, "seeds/keywords.json", "키워드")
        _seed_table(db, NPC, "seeds/npcs.json", "NPC")
        _seed_table(db, Event, "seeds/events.json", "이벤트")
        _seed_table(db, HiddenKeyword, "seeds/hidden_keywords.json", "히든 키워드")
        print("=== 시드 데이터 삽입 완료 ===")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
