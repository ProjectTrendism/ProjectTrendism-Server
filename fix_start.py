with open('app/routers/explore.py', encoding='utf-8') as f:
    txt = f.read()

old = (
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

new = (
    '@router.post("/start")\n'
    'def start_season(db: Session = Depends(get_db)):\n'
    '    # 이미 진행 중인 시즌이 있으면 초기화 후 재시작 (새 탐험 세션)\n'
    '    existing = db.query(Season).filter(Season.status == "ACTIVE").first()\n'
    '    if existing:\n'
    '        existing.current_day = 1\n'
    '        existing.current_time = 8\n'
    '        existing.phase = "EXPLORE"\n'
    '\n'
    '        db.query(PlayerInventory).filter(\n'
    '            PlayerInventory.season_id == existing.id\n'
    '        ).delete()\n'
    '\n'
    '        db.query(SeasonNPCInfo).filter(\n'
    '            SeasonNPCInfo.season_id == existing.id\n'
    '        ).update({"talked": False, "perceived_reliability": None})\n'
    '\n'
    '        db.query(KeywordFrequency).filter(\n'
    '            KeywordFrequency.season_id == existing.id\n'
    '        ).delete()\n'
    '\n'
    '        db.query(HiddenKeywordUnlock).filter(\n'
    '            HiddenKeywordUnlock.season_id == existing.id\n'
    '        ).delete()\n'
    '\n'
    '        db.commit()\n'
    '        db.refresh(existing)\n'
    '\n'
    '        return {\n'
    '            "status": "success",\n'
    '            "data": SeasonStatus.from_orm(existing).dict(),\n'
    '            "message": "시즌 탐험 시작!"\n'
    '        }'
)

if old in txt:
    with open('app/routers/explore.py', 'w', encoding='utf-8') as f:
        f.write(txt.replace(old, new))
    print('[OK] /explore/start 근본 수정 완료')
else:
    print('[FAIL] 대상 문자열을 찾지 못했습니다')
