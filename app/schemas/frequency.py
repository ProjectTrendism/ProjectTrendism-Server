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
    id:        int
    name:      str
    location:  str
    is_active: bool

    # ── 2026-05 신설: 시즌 인스턴스(SeasonNPCInfo) 연동 ──
    # Unity 외형 매핑 키. 시드에 없으면 None.
    portrait_id:           Optional[str] = None
    # 이번 시즌 대사. SeasonNPCInfo가 있으면 그 값, 없으면 NPC.dialogue 폴백.
    season_dialogue:       str = ""
    # 플레이어가 현재까지 파악한 신뢰도. 초기 None(미파악) -> UI에서 "???" 표시.
    perceived_reliability: Optional[int] = None
    # 이번 시즌 이 NPC와 대화했는지.
    talked:                bool = False

    class Config:
        from_attributes = True
