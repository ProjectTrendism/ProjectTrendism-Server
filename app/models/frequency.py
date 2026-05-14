from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, ForeignKey
from sqlalchemy.sql import func
from app.database import Base


class KeywordFrequency(Base):
    """키워드 빈도수 추적 — NPC 대화에서 등장한 횟수"""
    __tablename__ = "keyword_frequency"

    id         = Column(Integer, primary_key=True, index=True)
    season_id  = Column(Integer, default=1)
    keyword_id = Column(Integer, ForeignKey("keywords.id"))
    mention_count = Column(Integer, default=0)   # NPC들이 언급한 횟수
    drop_count    = Column(Integer, default=0)   # 실제 드랍된 횟수
    npc_sources   = Column(JSON, default=list)   # 언급한 NPC id 목록 (중복 제거)


class HiddenKeyword(Base):
    """히든 키워드 — 특정 조건 충족 시에만 획득 가능"""
    __tablename__ = "hidden_keywords"

    id              = Column(Integer, primary_key=True, index=True)
    keyword_id      = Column(Integer, ForeignKey("keywords.id"))
    unlock_type     = Column(String, default="NPC_COMBO")
    # NPC_COMBO: 특정 NPC 조합 대화 완료
    # EVENT: 특정 이벤트 참여
    # FREQUENCY: 특정 키워드 빈도 임계치 도달
    unlock_condition = Column(JSON, default=dict)
    # NPC_COMBO: {"required_npcs": [1, 6, 10]}
    # EVENT: {"required_event_id": 4}
    # FREQUENCY: {"target_keyword_id": 4, "threshold": 5}
    hint_text       = Column(String, default="")
    is_unlocked     = Column(Boolean, default=False)
