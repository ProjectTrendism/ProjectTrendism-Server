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
    discount_rate: float = Field(0.0, ge=0.0, le=0.7)  # 최대 70% 할인

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
    node:      str   # "marketing" / "rent" / "management"
    new_value: float = Field(..., ge=0)