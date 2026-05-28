with open('app/routers/explore.py', encoding='utf-8') as f:
    txt = f.read()

old = '    if sdata["info"] is not None and not sdata["info"].talked:\n        sdata["info"].talked = True'
new = (
    '    if sdata["info"] is not None and not sdata["info"].talked:\n'
    '        sdata["info"].talked = True\n'
    '        if sdata["info"].perceived_reliability is None:\n'
    '            sdata["info"].perceived_reliability = sdata["info"].true_reliability'
)

if old in txt:
    with open('app/routers/explore.py', 'w', encoding='utf-8') as f:
        f.write(txt.replace(old, new))
    print('[OK] 신뢰도 공개 로직 추가 완료')
else:
    print('[FAIL] 대상 문자열을 찾지 못했습니다')
