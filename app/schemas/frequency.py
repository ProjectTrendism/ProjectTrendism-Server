from pydantic import BaseModel
from typing import Optional

class KeywordFrequencyResponse(BaseModel):
    keyword_id:    int
    keyword_name:  str
    mention_count: int
    drop_count:    int
    npc_sources:   list[int]
    heat_level:    str   # "HOT" / "WARM" / "COLD"

class HiddenKeywordHint(BaseModel):
    id:           int
    hint_text:    str
    unlock_type:  str
    is_unlocked:  bool
    keyword_name: Optional[str] = None  # 언락 후에만 공개

class NPCListItem(BaseModel):
    id:       int
    name:     str
    location: str
    is_active: bool

    class Config:
        from_attributes = True
