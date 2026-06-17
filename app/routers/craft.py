from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from app.database import get_db
from app.models.keyword import Keyword
from app.models.craft import (
    CraftCombination, RecipeBook, GeneratedItem, GeneratedItemCache
)
from app.schemas.craft import (
    CombineRequest, CombineResponse,
    PredictRequest, PredictResponse,
    RecipeBookEntry
)
from app.services.claude_service import generate_item_metadata
import uuid
import os
import glob
import hashlib

router = APIRouter(prefix="/craft", tags=["Craft"])


# ── 정적 이미지 폴백 ────────────────────────────────────
# 사전 생성 이미지가 아직 없는 조합일 때, 기존에 생성된 이미지 중 하나를 재활용한다.
# (placeholder.png 한 장만 계속 보여주는 것보다 시연 품질이 좋음)
# main.py와 동일 규칙: 프로젝트 루트/static/items
_STATIC_ITEMS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "static", "items"
)
_PLACEHOLDER_URL = "/static/items/placeholder.png"


def _list_item_images(grade: str | None = None) -> list[str]:
    """static/items 안의 사전 생성 아이템 이미지 파일명 목록.
    grade가 주어지면 해당 등급(item_*_{grade}.png)만, 없으면 전체 item_*.png."""
    try:
        pattern = f"item_*_{grade}.png" if grade else "item_*.png"
        files = [os.path.basename(p) for p in glob.glob(os.path.join(_STATIC_ITEMS_DIR, pattern))]
        return sorted(files)
    except Exception:
        return []


def _pick_fallback_image(cache_key: str, grade: str) -> str:
    """이미지가 없을 때 기존 생성 이미지 중 하나를 '결정적으로' 골라 재활용.
    - 같은 cache_key는 항상 같은 이미지를 반환 (세션마다 그림이 바뀌는 깜빡임 방지).
    - 같은 등급 이미지를 우선 사용 -> 없으면 전체 아이템 이미지 -> 그것도 없으면 placeholder.
    """
    candidates = _list_item_images(grade) or _list_item_images(None)
    if not candidates:
        return _PLACEHOLDER_URL
    # cache_key 기반 결정성 인덱스 (pregenerate._make_seed와 동일한 md5 방식, 비-salt)
    idx = int(hashlib.md5(cache_key.encode("utf-8")).hexdigest()[:8], 16) % len(candidates)
    return f"/static/items/{candidates[idx]}"


# ── 유틸리티 함수 ───────────────────────────────────────
def calc_estimated_value(r, g, b) -> float:
    """RGB 합산으로 아이템 예상 가치 계산 (combine 시 prefix 가격용)."""
    return round((r * 0.4 + g * 0.35 + b * 0.25) * 10, 1)


def calc_final_value(estimated_value: float, grade: str) -> float:
    """등급에 따른 최종 가치 계산."""
    multiplier = {"S": 2.0, "A": 1.5, "B": 1.0, "C": 0.5}
    return round(estimated_value * multiplier[grade], 1)


def _make_cache_key(keyword_ids: list[int], grade: str) -> str:
    """캐시 키 생성. pregenerate.py와 동일한 규칙: '1,11,21|S' 형식."""
    sorted_ids = sorted(keyword_ids)
    return f"{','.join(map(str, sorted_ids))}|{grade}"


# ── POST /craft/combine ─────────────────────────────────
@router.post("/combine")
def combine_keywords(body: CombineRequest, db: Session = Depends(get_db)):
    """키워드 3개로 조합 생성. RGB 값은 estimated_value 계산용으로만 사용."""
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

    if len(set(body.keyword_ids)) != 3:
        raise HTTPException(status_code=400, detail={
            "status": "error",
            "error_code": "INVALID_COMBINATION",
            "message": "키워드 3개가 모두 달라야 합니다"
        })

    # RGB는 estimated_value 산정에만 사용 (클라이언트에 노출 안 함)
    target_r = sum(k.r_value for k in keywords) / 3
    target_g = sum(k.g_value for k in keywords) / 3
    target_b = sum(k.b_value for k in keywords) / 3

    estimated_value = calc_estimated_value(target_r, target_g, target_b)
    combination_id = str(uuid.uuid4())
    preview_name = " + ".join(k.name for k in keywords)

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
    """
    클라이언트가 계산한 grade를 받아 캐시에서 AI 생성 메타데이터를 조회.
    RGB 예측 메커닉 제거됨 (2026-05).
    """
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

    # 클라이언트가 결정한 grade를 그대로 사용
    grade = body.grade
    final_value = calc_final_value(combo.estimated_value, grade)

    # 키워드 정보 조회 (캐시 미스 시 Claude 호출용)
    keywords = db.query(Keyword).filter(Keyword.id.in_(combo.keyword_ids)).all()
    keyword_names = [k.name for k in keywords]
    keyword_descriptions = [k.description for k in keywords]

    # ── 캐시 우선 조회 ──
    cache_key = _make_cache_key(combo.keyword_ids, grade)
    cached = db.query(GeneratedItemCache).filter_by(
        keyword_ids_key=cache_key
    ).first()

    if cached:
        # 캐시 히트: 즉시 응답 (Claude API 호출 없음)
        item_name = cached.name
        item_description = cached.description
        # 이미지가 비어 있는 캐시행(텍스트만 생성된 경우)도 기존 이미지로 폴백
        image_url = cached.image_url or _pick_fallback_image(cache_key, grade)
        cache_status = "HIT"
    else:
        # 캐시 미스: Claude만 동기 호출, 이미지는 None
        try:
            ai_result = generate_item_metadata(
                keyword_names=keyword_names,
                keyword_descriptions=keyword_descriptions,
                grade=grade
            )
        except RuntimeError as e:
            raise HTTPException(status_code=502, detail={
                "status": "error",
                "error_code": "AI_GENERATION_FAILED",
                "message": f"아이템 생성 중 오류가 발생했습니다: {str(e)}"
            })

        item_name = ai_result["name"]
        item_description = ai_result["description"]
        # 사전 생성 이미지가 아직 없으므로 기존 이미지 중 하나를 재활용 (placeholder 대체)
        image_url = _pick_fallback_image(cache_key, grade)

        # 다음 동일 요청에서 Claude 재호출 안 하도록 캐시에 저장
        # image_url은 None으로 둔다 -> 나중에 진짜 이미지를 생성하면 그 값을 채울 수 있고,
        #   런타임에는 _pick_fallback_image가 매번 같은 그림을 결정적으로 돌려준다.
        try:
            new_cache = GeneratedItemCache(
                keyword_ids_key=cache_key,
                grade=grade,
                name=item_name,
                description=item_description,
                image_url=None
            )
            db.add(new_cache)
            db.commit()
        except IntegrityError:
            db.rollback()
            existing = db.query(GeneratedItemCache).filter_by(
                keyword_ids_key=cache_key
            ).first()
            if existing:
                item_name = existing.name
                item_description = existing.description
        cache_status = "MISS"

    # 조합 사용 완료 처리
    combo.is_used = True
    db.commit()

    # 도감 업데이트
    sorted_ids = sorted(combo.keyword_ids)
    recipe = db.query(RecipeBook).filter(
        RecipeBook.keyword_ids == sorted_ids
    ).first()

    if not recipe:
        recipe = RecipeBook(
            keyword_ids=sorted_ids,
            keyword_names=keyword_names,
            best_grade=grade,
            success_count=1,
            hint_unlocked=False,
            generated_name=item_name,
            generated_description=item_description
        )
        db.add(recipe)
    else:
        recipe.success_count += 1
        grade_order = {"S": 0, "A": 1, "B": 2, "C": 3}
        if grade_order[grade] < grade_order[recipe.best_grade]:
            recipe.best_grade = grade
            recipe.generated_name = item_name
            recipe.generated_description = item_description
        if recipe.success_count >= 3:
            recipe.hint_unlocked = True

    db.commit()
    db.refresh(recipe)

    # 히스토리 레코드
    history = GeneratedItem(
        recipe_id=recipe.id,
        keyword_ids=combo.keyword_ids,
        keyword_names=keyword_names,
        grade=grade,
        final_value=final_value,
        generated_name=item_name,
        generated_description=item_description
    )
    db.add(history)
    db.commit()

    return {
        "status": "success",
        "data": {
            "grade": grade,
            "final_value": final_value,
            "item_id": recipe.id,
            "item_name": item_name,
            "item_description": item_description,
            "image_url": image_url,
            "_cache": cache_status   # 디버그용
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


# ── GET /craft/history  제작 히스토리 (시연용, 이미지 포함) ─
@router.get("/history")
def get_craft_history(
    grade: str | None = None,
    limit: int = 20,
    db: Session = Depends(get_db)
):
    query = db.query(GeneratedItem).order_by(GeneratedItem.created_at.desc())
    if grade:
        query = query.filter(GeneratedItem.grade == grade)
    items = query.limit(limit).all()

    # 각 히스토리 항목의 image_url은 캐시 테이블에서 join 조회
    result = []
    for item in items:
        cache_key = _make_cache_key(item.keyword_ids, item.grade)
        cached = db.query(GeneratedItemCache).filter_by(
            keyword_ids_key=cache_key
        ).first()
        image_url = (cached.image_url if cached else None) or _pick_fallback_image(cache_key, item.grade)

        result.append({
            "id": item.id,
            "recipe_id": item.recipe_id,
            "keyword_names": item.keyword_names,
            "grade": item.grade,
            "final_value": item.final_value,
            "generated_name": item.generated_name,
            "generated_description": item.generated_description,
            "image_url": image_url,
            "created_at": item.created_at.isoformat() if item.created_at else None
        })

    return {"status": "success", "data": result}