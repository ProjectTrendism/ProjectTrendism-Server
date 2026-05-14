from pydantic import BaseModel, Field
from typing import Optional


class CombineRequest(BaseModel):
    keyword_ids: list[int] = Field(..., min_length=3, max_length=3)


class CombineResponse(BaseModel):
    combination_id: str
    estimated_value: float
    preview_name:   str   # "엘프 버섯 + 차가운 + MZ감성"


class PredictRequest(BaseModel):
    """
    RGB 예측 메커닉 제거 (2026-05).
    클라이언트가 로컬에서 계산한 grade를 그대로 전달.
    백엔드는 grade에 맞는 캐시 항목을 조회해서 응답.
    """
    combination_id: str
    grade: str = Field(..., pattern="^[SABC]$")


class PredictResponse(BaseModel):
    grade:            str   # S / A / B / C
    final_value:      float
    item_id:          int
    item_name:        str   # AI 생성
    item_description: str   # AI 생성
    image_url:        Optional[str] = None  # 사전 생성 이미지 경로 (없으면 null)


class RecipeBookEntry(BaseModel):
    id:             int
    keyword_names:  list[str]
    best_grade:     str
    success_count:  int
    hint_unlocked:  bool

    class Config:
        from_attributes = True