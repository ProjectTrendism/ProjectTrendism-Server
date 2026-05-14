import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.database import Base, engine
from app.routers import keywords, craft, market, explore
import app.models  # noqa: F401  (모든 모델 클래스를 Base.metadata에 등록)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fantasy Trend Game API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Static files 마운트 (사전 생성된 아이템 이미지) ─────
# 프로젝트 루트의 static 폴더를 /static URL로 노출
# pregenerate.py가 static/items/item_X_Y_Z_GRADE.png를 저장하면
# 클라이언트(Unity)는 https://<server>/static/items/xxx.png 로 다운로드
_STATIC_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "static"
)
os.makedirs(_STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")

app.include_router(keywords.router)
app.include_router(craft.router)
app.include_router(market.router)
app.include_router(explore.router)


@app.get("/")
def root():
    return {"status": "ok", "message": "Fantasy Trend API is running"}