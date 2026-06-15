from pydantic import BaseModel, Field
from typing import Optional

class MarketItemCreate(BaseModel):
    item_name:   str
    keyword_ids: list[int]
    grade:       str
    base_value:  float
    stock:       int = 1
    release_day: int = 0

class MarketItemResponse(BaseModel):
    id:          int
    item_name:   str
    grade:       str
    base_value:  float
    stock:       int
    status:      str
    class Config:
        from_attributes = True

class SellRequest(BaseModel):
    item_id:       int
    quantity:      int = Field(1, ge=1)
    discount_rate: float = Field(0.0, ge=0.0, le=0.7)
    # 판매 페이즈의 '현재 날짜'. 클라이언트가 트렌드 곡선상의 어느 시점에 파는지 전달.
    # None이면 서버에 저장된 item.current_day(기본 0)를 사용 -> 0이면 트렌드 0이라 수익 0이 됨.
    current_day:   Optional[int] = None

class SellResponse(BaseModel):
    revenue:         float
    remaining_stock: int
    trend_index:     float

class TrendDataPoint(BaseModel):
    day:   int
    index: float

class SettlementResponse(BaseModel):
    id:               int
    season_id:        int
    total_revenue:    float
    material_cost:    float
    rent_cost:        float
    marketing_cost:   float
    management_cost:  float
    net_profit:       float
    penalty:          bool
    class Config:
        from_attributes = True

class AdjustNodeRequest(BaseModel):
    node:      str
    new_value: float = Field(..., ge=0)

class SalesAnalysisResponse(BaseModel):
    summary:          str
    keyword_analysis: str
    timing_analysis:  str
    price_analysis:   str
    next_action:      str
    score:            int

class BuyerSimulationDay(BaseModel):
    day:           int
    trend_index:   float
    buyers:        int
    sold:          int
    cumulative_revenue: float

class PriceAdjustRequest(BaseModel):
    item_id:   int
    new_price: float = Field(..., gt=0)