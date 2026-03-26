import json, sys, os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models.keyword import Keyword

Base.metadata.create_all(bind=engine)

def seed():
    db = SessionLocal()
    try:
        existing = db.query(Keyword).count()
        if existing > 0:
            print(f"이미 {existing}개 데이터 존재. 건너뜁니다.")
            return

        with open("seeds/keywords.json", "r", encoding="utf-8") as f:
            data = json.load(f)

        for item in data:
            db.add(Keyword(**item))
        db.commit()
        print(f"{len(data)}개 키워드 삽입 완료!")
    finally:
        db.close()

if __name__ == "__main__":
    seed()