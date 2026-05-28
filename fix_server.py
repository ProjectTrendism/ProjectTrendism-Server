import re

# ── explore.py ──
with open('app/routers/explore.py', 'r', encoding='utf-8') as f:
    txt = f.read()

before = len(txt)
txt = txt.replace('\u26a0\ufe0f 22\uc2dc \uc774\ud6c4! \ubcf4\uc548\uad00\uc774 \ud65c\uc131\ud654\ub429\ub2c8\ub2e4. \uadc0\uac00\ud558\uc138\uc694!',
                  '[!] 22\uc2dc \uc774\ud6c4! \ubcf4\uc548\uad00\uc774 \ud65c\uc131\ud654\ub429\ub2c8\ub2e4. \uadc0\uac00\ud558\uc138\uc694!')
txt = txt.replace('\u26a0\ufe0f \uace7 22\uc2dc\uc785\ub2c8\ub2e4! \uc11c\ub458\ub7ec \uadc0\uac00\ud558\uc138\uc694!',
                  '[!] \uace7 22\uc2dc\uc785\ub2c8\ub2e4! \uc11c\ub458\ub7ec \uadc0\uac00\ud558\uc138\uc694!')
txt = txt.replace('if random.random() < npc.drop_rate and keyword_pool:',
                  'if keyword_pool:')

with open('app/routers/explore.py', 'w', encoding='utf-8') as f:
    f.write(txt)
print('[OK] explore.py')

# ── market.py ──
with open('app/routers/market.py', 'r', encoding='utf-8') as f:
    txt = f.read()

# import 추가
old_import = 'from app.models.market import MarketItem, Settlement\nfrom app.models.keyword import Keyword'
new_import = 'from app.models.market import MarketItem, Settlement\nfrom app.models.keyword import Keyword\nfrom app.models.explore import Season'
txt = txt.replace(old_import, new_import)

# sell_item season_id=1 하드코딩 수정
old1 = (
    '    settlement = db.query(Settlement).filter(Settlement.season_id == 1).first()\n'
    '    if not settlement:\n'
    '        settlement = Settlement(\n'
    '            season_id=1,'
)
new1 = (
    '    active_season = db.query(Season).filter(Season.status == "ACTIVE").first()\n'
    '    active_season_id = active_season.id if active_season else 1\n'
    '    settlement = db.query(Settlement).filter(Settlement.season_id == active_season_id).first()\n'
    '    if not settlement:\n'
    '        settlement = Settlement(\n'
    '            season_id=active_season_id,'
)
txt = txt.replace(old1, new1)

# analyze season_id=1 하드코딩 수정 (남은 1개)
old2 = '    settlement = db.query(Settlement).filter(Settlement.season_id == 1).first()'
new2 = (
    '    active_season = db.query(Season).filter(Season.status == "ACTIVE").first()\n'
    '    active_season_id = active_season.id if active_season else 1\n'
    '    settlement = db.query(Settlement).filter(Settlement.season_id == active_season_id).first()'
)
txt = txt.replace(old2, new2)

with open('app/routers/market.py', 'w', encoding='utf-8') as f:
    f.write(txt)
print('[OK] market.py')

# ── 검증 ──
for fname, pattern in [
    ('app/routers/explore.py', 'drop_rate'),
    ('app/routers/market.py', 'season_id == 1'),
]:
    with open(fname, encoding='utf-8') as f:
        content = f.read()
    if pattern in content:
        print(f'[FAIL] {fname} 에 {pattern} 남아있음')
    else:
        print(f'[OK] {fname} {pattern} 제거 확인')

print('[OK] 전체 완료')
