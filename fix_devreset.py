with open('app/routers/explore.py', encoding='utf-8') as f:
    lines = f.readlines()

# 현재 770줄 주변 상태: db.commit() 다음에 깨진 return 구문
# 올바른 return 블록으로 교체
lines[768] = '    db.commit()\n'
lines[769] = '\n'
lines[770] = '    return {\n'

# 기존 깨진 "message" 줄과 } 줄 제거
del lines[771]  # 깨진 "message" 줄
del lines[771]  # 깨진 } 줄

# 올바른 return 내용 삽입
lines.insert(771, '        "status": "success",\n')
lines.insert(772, '        "data": {"season_id": season.id, "current_day": 1, "current_time": 8},\n')
lines.insert(773, '        "message": "[DEV] 시즌 초기화 완료"\n')
lines.insert(774, '    }\n')

with open('app/routers/explore.py', 'w', encoding='utf-8') as f:
    f.writelines(lines)

# 검증
with open('app/routers/explore.py', encoding='utf-8') as f:
    content = f.read()

try:
    compile(content, 'explore.py', 'exec')
    print('[OK] 문법 오류 없음')
except SyntaxError as e:
    print(f'[FAIL] 문법 오류: {e}')
