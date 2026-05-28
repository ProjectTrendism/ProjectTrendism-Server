with open('app/routers/explore.py', encoding='utf-8') as f:
    txt = f.read()

old = '''    # 22시 이후 보안관 체포
    if season.current_time >= 22:
        inventory = db.query(PlayerInventory).filter(
            PlayerInventory.season_id == season.id
        ).all()

        seized_count = min(random.randint(1, 2), len(inventory))
        for i in range(seized_count):
            if inventory:
                item = random.choice(inventory)
                inventory.remove(item)
                db.delete(item)
        db.commit()

        return {
            "status": "success",
            "data": {
                "success": False,
                "message": f"보안관에게 체포됐습니다! 키워드 {seized_count}개를 압수당하고 강제 귀가합니다.",
                "warning": "강제 귀가"
            }
        }'''

new = '''    # 22시 이후 보안관 체포
    if season.current_time >= 22:
        inventory = db.query(PlayerInventory).filter(
            PlayerInventory.season_id == season.id
        ).all()

        seized_count = min(random.randint(1, 2), len(inventory))
        for i in range(seized_count):
            if inventory:
                item = random.choice(inventory)
                inventory.remove(item)
                db.delete(item)

        # 체포 후 자동으로 다음 날로 이동 (영구 체포 루프 방지)
        season.current_day += 1
        season.current_time = 8
        db.commit()

        return {
            "status": "success",
            "data": {
                "success": False,
                "message": f"보안관에게 체포됐습니다! 키워드 {seized_count}개를 압수당하고 강제 귀가합니다.",
                "warning": "강제 귀가",
                "auto_day_end": True,
                "next_day": season.current_day
            }
        }'''

if old in txt:
    with open('app/routers/explore.py', 'w', encoding='utf-8') as f:
        f.write(txt.replace(old, new))
    print('[OK] 체포 후 자동 day-end 추가 완료')
else:
    print('[FAIL] 대상 문자열을 찾지 못했습니다')
