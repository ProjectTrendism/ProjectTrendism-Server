from sqlalchemy import Column, Integer, String, Float, JSON, ForeignKey
from app.database import Base

class MarketItem(Base):
    """판매 중인 아이템"""
    __tablename__ = "market_items"

    id            = Column(Integer, primary_key=True, index=True)
    item_name     = Column(String, nullable=False)
    keyword_ids   = Column(JSON)         # [1, 11, 21]
    grade         = Column(String)       # S / A / B / C
    base_value    = Column(Float)        # 제작 시 산정된 최종 가치
    stock         = Column(Integer, default=1)
    release_day   = Column(Integer, default=0)  # 출시 시점 (게임 내 일수)
    current_day   = Column(Integer, default=0)  # 현재 일수
    status        = Column(String, default="ACTIVE")  # ACTIVE / SOLD_OUT / DEAD

class Settlement(Base):
    """시즌별 정산"""
    __tablename__ = "settlements"

    id              = Column(Integer, primary_key=True, index=True)
    season_id       = Column(Integer, default=1)
    total_revenue   = Column(Float, default=0)
    material_cost   = Column(Float, default=0)
    rent_cost       = Column(Float, default=500)
    marketing_cost  = Column(Float, default=0)
    management_cost = Column(Float, default=200)
    net_profit      = Column(Float, default=0)
    penalty_threshold = Column(Float, default=500)