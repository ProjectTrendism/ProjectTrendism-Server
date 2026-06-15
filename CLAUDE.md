# ProjectTrendism Server -- Claude Code 작업 규칙

## 절대 규칙
- 추측 금지. 코드를 직접 열어 원인 규명 후 보고. 가설은 직접 확인 전까지 보고 금지.
- 완료 선언 전 정적 검증 필수 (ast.parse / 검증 스크립트 실행).
- 작업 환경에서 고친 건 실제 서버 경로에도 별도 반영 필요.

## API 응답 형식 (변경 금지)
- 성공: {"status": "success", "data": {...}}
- 실패: {"status": "error", "error_code": "...", "message": "..."}

## 보안 (위반 금지)
- r_value / g_value / b_value 는 클라이언트 응답에 절대 포함 금지.
- 등급 계산은 서버에서만 수행.
- ANTHROPIC_API_KEY 는 .env 에만. 코드/로그/커밋에 절대 노출 금지.

## Unity 연동
- Unity C# 파일은 targeted patch 만. wholesale 재작성 절대 금지
  (로컬에서 추가한 필드 덮어쓰기 방지).
- 응답 DTO는 envelope wrapper 포함 (예: CombineEnvelope).
  JsonUtility.FromJson 은 중첩 JSON 자동 unwrap 불가.

## 출력 규약
- 코드/CLI/테스트 출력에 이모지 금지. ASCII 로 대체
  (화살표 -->, 게이지 [####....], 체크 [OK]/[FAIL], 구분선 ====/----).

## 환경 (Windows / 한국어 로케일)
- 한글 포함 파일은 Set-Content (CP949 기본) 금지.
  [System.IO.File]::WriteAllText() + 명시적 UTF-8 사용.
- 새 PowerShell 창에서 venv 활성화 먼저: .\\venv\\Scripts\\Activate.ps1
- 포트: IDA 8000 / ProjectTrendism 8001.

## 이미지 생성
- Pollinations AI (https://image.pollinations.ai). 무료, API 키 불필요, seed 로 결정성.
- 캐시 키: '1,11,21|S' / 파일명: item_1_11_21_S.png / 저장: project_root/static/items/.
- 배치 사전생성: seeds/pregenerate.py.
