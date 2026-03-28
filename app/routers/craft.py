from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.keyword import Keyword
from app.models.craft import CraftCombination, RecipeBook
from app.schemas.craft import (
    CombineRequest, CombineResponse,
    PredictRequest, PredictResponse,
    RecipeBookEntry
)
import uuid, math

router = APIRouter(prefix="/craft", tags=["Craft"])


def calc_estimated_value(r, g, b) -> float:
    """RGB 합산으로 아이템 예상 가치 계산"""
    return round((r * 0.4 + g * 0.35 + b * 0.25) * 10, 1)


def calc_grade(distance: float) -> str:
    """예측 오차에 따른 등급 산정"""
    if distance <= 10:
        return "S"
    elif distance <= 25:
        return "A"
    elif distance <= 45:
        return "B"
    else:
        return "C"


def calc_final_value(estimated_value: float, grade: str) -> float:
    """등급에 따른 최종 가치 계산"""
    multiplier = {"S": 2.0, "A": 1.5, "B": 1.0, "C": 0.5}
    return round(estimated_value * multiplier[grade], 1)


# ── POST /craft/combine ─────────────────────────────────
@router.post("/combine")
def combine_keywords(body: CombineRequest, db: Session = Depends(get_db)):
    # 키워드 3개 조회
    keywords = []
    for kid in body.keyword_ids:
        kw = db.query(Keyword).filter(Keyword.id == kid).first()
        if not kw:
            raise HTTPException(status_code=404, detail={
                "status": "error",
                "error_code": "KEYWORD_NOT_FOUND",
                "message": f"키워드 ID {kid}가 존재하지 않습니다"
            })
        keywords.append(kw)

    # 중복 체크
    if len(set(body.keyword_ids)) != 3:
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "error_code": "INVALID_COMBINATION",
            "message": "키워드 3개가 모두 달라야 합니다"
        })

    # RGB 평균 계산 (target_color — 클라이언트에 숨김)
    target_r = sum(k.r_value for k in keywords) / 3
    target_g = sum(k.g_value for k in keywords) / 3
    target_b = sum(k.b_value for k in keywords) / 3

    estimated_value = calc_estimated_value(target_r, target_g, target_b)
    combination_id = str(uuid.uuid4())
    preview_name = " + ".join(k.name for k in keywords)

    # DB 저장
    combo = CraftCombination(
        combination_id=combination_id,
        keyword_ids=body.keyword_ids,
        target_r=target_r,
        target_g=target_g,
        target_b=target_b,
        estimated_value=estimated_value,
    )
    db.add(combo)
    db.commit()

    return {
        "status": "success",
        "data": {
            "combination_id": combination_id,
            "estimated_value": estimated_value,
            "preview_name": preview_name
        }
    }


# ── POST /craft/predict ─────────────────────────────────
@router.post("/predict")
def predict_result(body: PredictRequest, db: Session = Depends(get_db)):
    combo = db.query(CraftCombination).filter(
        CraftCombination.combination_id == body.combination_id
    ).first()

    if not combo:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "COMBINATION_NOT_FOUND",
            "message": "조합 ID가 존재하지 않습니다"
        })

    if combo.is_used:
        raise HTTPException(status_code=410, detail={
            "status": "error",
            "error_code": "COMBINATION_EXPIRED",
            "message": "이미 사용된 조합입니다"
        })

    # 오차 계산 (3D 유클리드 거리)
    distance = math.sqrt(
        (body.predict_r - combo.target_r) ** 2 +
        (body.predict_g - combo.target_g) ** 2 +
        (body.predict_b - combo.target_b) ** 2
    )

    grade = calc_grade(distance)
    final_value = calc_final_value(combo.estimated_value, grade)

    # 조합 사용 완료 처리
    combo.is_used = True
    db.commit()

    # 도감 업데이트
    sorted_ids = sorted(combo.keyword_ids)
    recipe = db.query(RecipeBook).filter(
        RecipeBook.keyword_ids == sorted_ids
    ).first()

    keywords = db.query(Keyword).filter(Keyword.id.in_(combo.keyword_ids)).all()
    keyword_names = [k.name for k in keywords]

    if not recipe:
        recipe = RecipeBook(
            keyword_ids=sorted_ids,
            keyword_names=keyword_names,
            best_grade=grade,
            success_count=1,
            hint_unlocked=False
        )
        db.add(recipe)
    else:
        recipe.success_count += 1
        grade_order = {"S": 0, "A": 1, "B": 2, "C": 3}
        if grade_order[grade] < grade_order[recipe.best_grade]:
            recipe.best_grade = grade
        if recipe.success_count >= 3:
            recipe.hint_unlocked = True

    db.commit()
    db.refresh(recipe)

    return {
        "status": "success",
        "data": {
            "grade": grade,
            "distance": round(distance, 2),
            "final_value": final_value,
            "item_id": recipe.id
        }
    }


# ── GET /craft/recipe-book ──────────────────────────────
@router.get("/recipe-book")
def get_recipe_book(db: Session = Depends(get_db)):
    recipes = db.query(RecipeBook).all()
    return {
        "status": "success",
        "data": [RecipeBookEntry.from_orm(r).dict() for r in recipes]
    }