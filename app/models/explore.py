from sqlalchemy import Column, Integer, String, Float, JSON, Boolean, ForeignKey
from app.database import Base

class Season(Base):
    """시즌 상태 관리"""
    __tablename__ = "seasons"

    id           = Column(Integer, primary_key=True, index=True)
    current_day  = Column(Integer, default=1)       # 1~7
    current_time = Column(Integer, default=8)       # 8~22 (시간)
    phase        = Column(String, default="EXPLORE") # EXPLORE / CRAFT / SELL
    status       = Column(String, default="ACTIVE")  # ACTIVE / FINISHED

class NPC(Base):
    """NPC 마스터 데이터"""
    __tablename__ = "npcs"

    id            = Column(Integer, primary_key=True, index=True)
    name          = Column(String, nullable=False)
    location      = Column(String, default="마을")
    dialogue      = Column(String, default="")       # 대화 내용
    keyword_drops = Column(JSON, default=list)       # 줄 수 있는 keyword_id 목록
    drop_rate     = Column(Float, default=0.7)       # 키워드 드랍 확률
    is_active     = Column(Boolean, default=True)

class Event(Base):
    """이벤트 마스터 데이터"""
    __tablename__ = "events"

    id              = Column(Integer, primary_key=True, index=True)
    name            = Column(String, nullable=False)
    description     = Column(String, default="")
    event_type      = Column(String, default="RANDOM")  # FIXED / RANDOM
    trigger_day     = Column(Integer, nullable=True)    # 고정 이벤트 발생 일차
    trigger_prob    = Column(Float, default=0.3)        # 랜덤 이벤트 확률
    keyword_rewards = Column(JSON, default=list)        # 보상 keyword_id 목록
    is_active       = Column(Boolean, default=True)

class PlayerInventory(Base):
    """플레이어 보유 키워드"""
    __tablename__ = "player_inventory"

    id         = Column(Integer, primary_key=True, index=True)
    season_id  = Column(Integer, default=1)
    keyword_id = Column(Integer, ForeignKey("keywords.id"))
    quantity   = Column(Integer, default=1)