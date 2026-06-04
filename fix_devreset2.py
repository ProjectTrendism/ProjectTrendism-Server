with open('app/routers/explore.py', encoding='utf-8') as f:
    lines = f.readlines()

print(f'총 줄 수: {len(lines)}')
print('마지막 10줄:')
for i, line in enumerate(lines[-10:]):
    print(f'{len(lines)-10+i+1}: {repr(line)}')

# 768줄(0-indexed: 767)부터 끝까지를 올바른 내용으로 교체
# db.commit() 이후 return 블록 완성
end_idx = None
for i in range(len(lines)-1, -1, -1):
    if 'db.commit()' in lines[i]:
        end_idx = i
        break

print(f'\ndb.commit() 위치: {end_idx+1}줄')

if end_idx:
    lines = lines[:end_idx+1]
    lines.append('\n')
    lines.append('    return {\n')
    lines.append('        "status": "success",\n')
    lines.append('        "data": {"season_id": season.id, "current_day": 1, "current_time": 8},\n')
    lines.append('        "message": "[DEV] 시즌 초기화 완료"\n')
    lines.append('    }\n')
    
    with open('app/routers/explore.py', 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    try:
        compile(open('app/routers/explore.py', encoding='utf-8').read(), 'explore.py', 'exec')
        print('[OK] 문법 오류 없음')
    except SyntaxError as e:
        print(f'[FAIL] {e}')
