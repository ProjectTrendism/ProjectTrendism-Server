from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, DateTime
from sqlalchemy.sql import func
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

    # ── AI 생성 메타데이터 (best_grade 기준으로 대표 이름/설명 저장) ──
    generated_name        = Column(String, nullable=True)   # "청량숲의 감성버섯"
    generated_description = Column(String, nullable=True)   # "엘프가 가꾼 차가운..."


class GeneratedItem(Base):
    """제작 히스토리 (제작 1회마다 1 레코드)"""
    __tablename__ = "generated_items"

    id            = Column(Integer, primary_key=True, index=True)
    recipe_id     = Column(Integer, nullable=False)    # RecipeBook.id 참조
    keyword_ids   = Column(JSON)                       # [1, 2, 3]
    keyword_names = Column(JSON)                       # ["엘프 버섯", "차가운", "MZ감성"]
    grade         = Column(String, nullable=False)     # S / A / B / C
    final_value   = Column(Float, nullable=False)
    generated_name        = Column(String, nullable=False)
    generated_description = Column(String, nullable=False)
    created_at    = Column(DateTime, server_default=func.now())