with open('app/routers/explore.py', encoding='utf-8') as f:
    txt = f.read()

results = []

# ── 1. /explore/start 근본 수정 ──
old1 = (
    '@router.post("/start")\n'
    'def start_season(db: Session = Depends(get_db)):\n'
    '    # 이미 진행 중인 시즌이 있으면 그대로 반환\n'
    '    existing = db.query(Season).filter(Season.status == "ACTIVE").first()\n'
    '    if existing:\n'
    '        return {\n'
    '            "status": "success",\n'
    '            "data": SeasonStatus.from_orm(existing).dict(),\n'
    '            "message": "이미 진행 중인 시즌이 있습니다"\n'
    '        }'
)
new1 = (
    '@router.post("/start")\n'
    'def start_season(db: Session = Depends(get_db)):\n'
    '    # 이미 진행 중인 시즌이 있으면 초기화 후 재시작 (새 탐험 세션)\n'
    '    existing = db.query(Season).filter(Season.status == "ACTIVE").first()\n'
    '    if existing:\n'
    '        existing.current_day = 1\n'
    '        existing.current_time = 8\n'
    '        existing.phase = "EXPLORE"\n'
    '        db.query(PlayerInventory).filter(PlayerInventory.season_id == existing.id).delete()\n'
    '        db.query(SeasonNPCInfo).filter(SeasonNPCInfo.season_id == existing.id).update({"talked": False, "perceived_reliability": None})\n'
    '        db.query(KeywordFrequency).filter(KeywordFrequency.season_id == existing.id).delete()\n'
    '        db.query(HiddenKeywordUnlock).filter(HiddenKeywordUnlock.season_id == existing.id).delete()\n'
    '        db.commit()\n'
    '        db.refresh(existing)\n'
    '        return {\n'
    '            "status": "success",\n'
    '            "data": SeasonStatus.from_orm(existing).dict(),\n'
    '            "message": "시즌 탐험 시작!"\n'
    '        }'
)
if old1 in txt:
    txt = txt.replace(old1, new1)
    results.append('[OK] /explore/start 수정')
else:
    results.append('[SKIP] /explore/start - 이미 수정됐거나 대상 없음')

# ── 2. /explore/dev-reset 추가 ──
dev_reset = '''

# ── POST /explore/dev-reset  테스트용 시즌 초기화 ──
@router.post("/dev-reset")
def dev_reset(db: Session = Depends(get_db)):
    season = db.query(Season).filter(Season.status == "ACTIVE").first()
    if not season:
        raise HTTPException(status_code=404, detail={
            "status": "error",
            "error_code": "NO_ACTIVE_SEASON",
            "message": "진행 중인 시즌이 없습니다"
        })

    season.current_day = 1
    season.current_time = 8
    season.phase = "EXPLORE"

    db.query(SeasonNPCInfo).filter(
        SeasonNPCInfo.season_id == season.id
    ).update({"talked": False, "perceived_reliability": None})

    db.query(PlayerInventory).filter(
        PlayerInventory.season_id == season.id
    ).delete()

    db.query(KeywordFrequency).filter(
        KeywordFrequency.season_id == season.id
    ).delete()

    db.query(HiddenKeywordUnlock).filter(
        HiddenKeywordUnlock.season_id == season.id
    ).delete()

    db.commit()

    return {
        "status": "success",
        "data": {"season_id": season.id, "current_day": 1, "current_time": 8},
        "message": "[DEV] 시즌 초기화 완료"
    }
'''

if '/explore/dev-reset' not in txt:
    txt = txt + dev_reset
    results.append('[OK] /explore/dev-reset 추가')
else:
    results.append('[SKIP] /explore/dev-reset - 이미 존재')

with open('app/routers/explore.py', 'w', encoding='utf-8') as f:
    f.write(txt)

for r in results:
    print(r)
print('[OK] 완료')
