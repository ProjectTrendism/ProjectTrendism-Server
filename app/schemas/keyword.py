from pydantic import BaseModel, Field
from typing import Optional

class KeywordCreate(BaseModel):
    name:        str
    category:    str = Field(..., pattern="^(BASE|STYLE|CONCEPT)$")
    r_value:     float = Field(50.0, ge=0, le=100)
    g_value:     float = Field(50.0, ge=0, le=100)
    b_value:     float = Field(50.0, ge=0, le=100)
    rarity:      str = Field("COMMON", pattern="^(COMMON|RARE|LEGEND)$")
    description: str = ""

class KeywordResponse(BaseModel):
    id:          int
    name:        str
    category:    str
    rarity:      str
    description: str

    class Config:
        from_attributes = True