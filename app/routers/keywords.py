from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from app.database import get_db
from app.models.keyword import Keyword
from app.schemas.keyword import KeywordCreate, KeywordResponse

router = APIRouter(prefix="/keywords", tags=["Keywords"])

@router.get("")
def get_keywords(
    category: Optional[str] = None,
    rarity:   Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = db.query(Keyword).filter(Keyword.is_active == True)
    if category:
        query = query.filter(Keyword.category == category)
    if rarity:
        query = query.filter(Keyword.rarity == rarity)
    keywords = query.all()
    return {"status": "success", "data": [KeywordResponse.from_orm(k).dict() for k in keywords]}

@router.get("/{keyword_id}")
def get_keyword(keyword_id: int, db: Session = Depends(get_db)):
    kw = db.query(Keyword).filter(Keyword.id == keyword_id).first()
    if not kw:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "KEYWORD_NOT_FOUND",
            "message": f"키워드 ID {keyword_id}가 존재하지 않습니다"
        })
    return {"status": "success", "data": KeywordResponse.from_orm(kw).dict()}

@router.post("", status_code=201)
def create_keyword(body: KeywordCreate, db: Session = Depends(get_db)):
    kw = Keyword(**body.dict())
    db.add(kw)
    db.commit()
    db.refresh(kw)
    return {"status": "success", "data": KeywordResponse.from_orm(kw).dict()}