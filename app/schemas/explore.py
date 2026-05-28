from pydantic import BaseModel, Field
from typing import Optional

class SeasonStatus(BaseModel):
    id:           int
    current_day:  int
    current_time: int
    phase:        str
    status:       str
    trend_theme:  str = ""
    
    class Config:
        from_attributes = True

class ActionRequest(BaseModel):
    action_type: str  # "TALK" / "SCAN" / "EAVESDROP" / "VIRAL"
    target_id:  int   # NPC id 또는 오브젝트 id

class ActionResult(BaseModel):
    success:      bool
    message:      str
    keyword_id:   Optional[int] = None
    keyword_name: Optional[str] = None
    keyword_rarity: Optional[str] = None
    warning:      Optional[str] = None  # 22시 경고 등

class EventResponse(BaseModel):
    id:          int
    name:        str
    description: str
    event_type:  str
    keyword_rewards: list[int]

    class Config:
        from_attributes = True

class InventoryItem(BaseModel):
    keyword_id:   int
    keyword_name: str
    category:     str
    rarity:       str
    quantity:     int

class DayEndResult(BaseModel):
    day_completed: int
    next_day:      Optional[int]
    events_tomorrow: list[str]
    phase_changed: bool
    message:       str