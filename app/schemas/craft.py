from pydantic import BaseModel, Field
from typing import Optional

class CombineRequest(BaseModel):
    keyword_ids: list[int] = Field(..., min_length=3, max_length=3)

class CombineResponse(BaseModel):
    combination_id: str
    estimated_value: float
    preview_name:   str   # "엘프 버섯 + 차가운 + MZ감성"

class PredictRequest(BaseModel):
    combination_id: str
    predict_r:      float = Field(..., ge=0, le=100)
    predict_g:      float = Field(..., ge=0, le=100)
    predict_b:      float = Field(..., ge=0, le=100)

class PredictResponse(BaseModel):
    grade:          str   # S / A / B / C
    distance:       float # 예측값과 실제값의 오차
    final_value:    float
    item_id:        int
    item_name:        str   # AI 생성: "청량숲의 감성버섯"
    item_description: str   # AI 생성: "엘프가 가꾼 차가운..."

class RecipeBookEntry(BaseModel):
    id:             int
    keyword_names:  list[str]
    best_grade:     str
    success_count:  int
    hint_unlocked:  bool

    class Config:
        from_attributes = True