from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import Base, engine
from app.routers import keywords, craft, market, explore

Base.metadata.create_all(bind=engine)

app = FastAPI(title="Fantasy Trend Game API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(keywords.router)
app.include_router(craft.router)
app.include_router(market.router)
app.include_router(explore.router)

@app.get("/")
def root():
    return {"status": "ok", "message": "Fantasy Trend API is running"}