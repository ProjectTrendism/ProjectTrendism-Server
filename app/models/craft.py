from sqlalchemy import Column, Integer, String, Float, JSON, Boolean
from app.database import Base

class CraftCombination(Base):
    """키워드 조합 임시 저장 (예측 전까지 target_color 보관)"""
    __tablename__ = "craft_combinations"

    id            = Column(Integer, primary_key=True, index=True)
    combination_id = Column(String, unique=True, index=True)  # UUID
    keyword_ids   = Column(JSON)        # [1, 2, 3]
    target_r      = Column(Float)       # 실제 RGB (클라이언트에 숨김)
    target_g      = Column(Float)
    target_b      = Column(Float)
    estimated_value = Column(Float)
    is_used       = Column(Boolean, default=False)  # 예측 완료 여부


class RecipeBook(Base):
    """제작 성공 기록 도감"""
    __tablename__ = "recipe_book"

    id            = Column(Integer, primary_key=True, index=True)
    keyword_ids   = Column(JSON)        # [1, 2, 3] 정렬된 조합
    keyword_names = Column(JSON)        # ["엘프 버섯", "차가운", "MZ감성"]
    best_grade    = Column(String)      # 이 조합으로 달성한 최고 등급
    success_count = Column(Integer, default=0)
    hint_unlocked = Column(Boolean, default=False)  # 3회 이상 성공 시 힌트 공개