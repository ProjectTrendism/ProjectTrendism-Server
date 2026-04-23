# ProjectTrendism · Server

판타지 세계관에 MZ 트렌드 감성을 얹은 경영 시뮬레이션 게임의 백엔드 서버입니다. 플레이어는 판타지 마을을 탐험하며 수집한 키워드를 조합해 아이템을 제작하고, 시장에 내놓아 트렌드 곡선에 따라 판매합니다. 본 저장소는 FastAPI 기반 REST API 서버를 담고 있으며, Unity 클라이언트와 연동됩니다.

**주요 특징**
- 키워드 3개를 조합하면 서버가 RGB 기반으로 아이템 가치를 산정하고, 플레이어의 RGB 예측 정확도로 등급(S/A/B/C)을 매깁니다.
- 등급이 정해지면 **Claude Haiku 4.5 API** 가 키워드 조합과 등급에 맞춰 아이템 이름과 설명을 자동 생성합니다. 같은 조합도 매번 다른 아이템이 나와 시연용 다양성이 확보됩니다.
- 출시한 아이템은 시간에 따라 로그 상승 → 지수 하락하는 트렌드 곡선을 그리며, 플레이어는 마케팅/임대/관리 비용을 조절해 시즌 순이익을 관리합니다.
- 7일 × 하루 8~22시 구조의 탐험 파트에서는 NPC 대화·도청·스캔으로 키워드를 수집하고, 22시 이후에는 보안관에게 체포되어 키워드를 압수당할 위험이 있습니다.

## 팀

- 김건중 · 시스템/백엔드 (세종대 컴퓨터공학, 2026-1 창의학기제)
- 김동우 · Unity 클라이언트

## 기술 스택

| 영역 | 사용 기술 |
|---|---|
| 언어 | Python 3.12 |
| 웹 프레임워크 | FastAPI |
| ORM / DB | SQLAlchemy 2.0 / SQLite (개발), PostgreSQL (배포 예정) |
| AI | Anthropic Claude API (`claude-haiku-4-5`) |
| 배포 | Docker, Docker Compose |
| 개발 터널 | ngrok |

## 아키텍처

```
app/
├── main.py              # FastAPI 앱 엔트리, 라우터 등록, CORS
├── database.py          # SQLAlchemy 엔진·세션, get_db 의존성
├── models/              # SQLAlchemy 테이블 정의
│   ├── keyword.py
│   ├── craft.py         # CraftCombination, RecipeBook, GeneratedItem
│   ├── market.py        # MarketItem, Settlement
│   └── explore.py       # Season, NPC, Event, PlayerInventory
├── schemas/             # Pydantic 요청·응답 스키마
├── routers/             # API 엔드포인트
│   ├── keywords.py      # /keywords
│   ├── craft.py         # /craft/combine, /craft/predict, /craft/recipe-book
│   ├── market.py        # /market/items, /market/sell, /market/settlement
│   └── explore.py       # /explore/start, /explore/action, /explore/day-end
└── services/
    └── claude_service.py  # Claude API 호출 및 아이템 메타데이터 생성
seeds/
├── keywords.json        # 30종 키워드 시드 데이터
└── seed.py              # DB 초기 삽입 스크립트
```

### 레이어 책임

- **routers**: HTTP 요청을 받아 응답 형식을 조립하는 얇은 레이어. 검증 실패 시 `HTTPException`으로 `{status, error_code, message}` 구조의 에러를 반환합니다.
- **models**: DB 테이블. 외부 RGB 값 등 비공개 데이터는 응답 스키마에서 제외해 클라이언트로 새지 않도록 합니다.
- **schemas**: Pydantic 모델. 응답에는 `status`/`data` 래퍼를 라우터에서 일관되게 감쌉니다.
- **services**: 외부 API 호출, 복잡한 도메인 로직. 현재는 Claude 연동이 여기 있습니다.

### 응답 형식 (모든 엔드포인트 공통)

```json
// 성공
{ "status": "success", "data": { ... } }

// 실패
{ "status": "error", "error_code": "ITEM_NOT_FOUND", "message": "..." }
```

## 주요 게임 로직

### 1. 키워드 시스템

모든 키워드는 `BASE`(재료) / `STYLE`(가공) / `CONCEPT`(컨셉) 3개 카테고리, `COMMON` / `RARE` / `LEGEND` 3단계 희귀도를 갖습니다. 각 키워드는 숨겨진 `r_value`, `g_value`, `b_value` (0~100) 를 보유하며, 이 값은 **절대 클라이언트로 노출되지 않습니다**.

### 2. 제작: RGB 예측 게임

1. 플레이어가 서로 다른 키워드 3개를 선택 → `POST /craft/combine`
2. 서버가 3개 키워드의 RGB 평균을 계산해 `target_color` 로 내부 저장, 예상 가치(`estimated_value`)와 `combination_id` 발급
3. 플레이어가 target_color 가 뭘지 **예측**해서 RGB 값 제출 → `POST /craft/predict`
4. 서버가 예측값과 실제값의 3D 유클리드 거리로 등급 결정
   - 거리 ≤ 10 → **S** (2.0배 가치)
   - 거리 ≤ 25 → **A** (1.5배)
   - 거리 ≤ 45 → **B** (1.0배)
   - 그 외 → **C** (0.5배)
5. 등급이 결정되면 Claude API 를 호출해 아이템 이름·설명을 생성
6. 결과를 `RecipeBook` (도감, 조합당 대표 1건) 과 `GeneratedItem` (히스토리, 제작마다 1건) 에 각각 저장

AI 생성 예시:
- S등급 — `엘프의 바삭한 Z세대 버섯칩` / *숲의 정령이 키운 희귀 버섯을 비결의 가공법으로 바삭하게 구워낸 전설의 스낵. 먹는 자의 감성을 깨운다.*
- C등급 — `바삭한 엘프버섯칩` / *숲에서 캔 버섯을 튀겨 만든 스낵. SNS에서 'ASMR 영상'으로 인기. 먹으면 숲내음이 난다고 주장하는 사람들이 있음.*

등급에 따라 톤이 명확히 달라지도록 시스템 프롬프트를 튜닝했습니다.

### 3. 판매: 트렌드 곡선

아이템은 출시일(`release_day`) 기준으로 시간에 따라 인기도 지수가 변합니다.

- **상승기** (0 ≤ elapsed ≤ 30일): 로그 곡선으로 서서히 상승해 30일차에 피크
- **하락기** (30일 < elapsed ≤ 180일): 지수 감소(`exp(-0.025 × (elapsed - 30))`)
- **180일 초과**: 트렌드 사망 (지수 0)

등급에 따른 부스트(S 1.5 / A 1.2 / B 1.0 / C 0.7)가 곱해지며, 실제 판매가는 `base_value × (trend_index / 100) × (1 - discount_rate)` 로 계산됩니다. 판매 수익은 `Settlement` 테이블에 누적되어 시즌 말 순이익이 결정됩니다.

### 4. 탐험: 7일 × 시간 제한

한 시즌은 7일로 구성되며, 하루는 8시부터 22시까지 진행됩니다. 매 행동(`TALK` / `SCAN` / `EAVESDROP`)마다 1시간이 소모되고, 22시 이후에는 보안관에게 체포되어 보유 키워드 1~2개를 압수당하고 강제 귀가합니다. 7일차가 끝나면 자동으로 제작 파트로 전환됩니다.

## 실행 방법

### 1. 의존성 설치

```bash
# 가상환경 생성 및 활성화
python -m venv venv
venv\Scripts\activate           # Windows
# source venv/bin/activate      # macOS/Linux

# 패키지 설치
pip install fastapi uvicorn sqlalchemy python-dotenv pydantic anthropic
```

### 2. 환경 변수 설정

`.env.example` 을 복사해 `.env` 를 만들고 값을 채웁니다.

```env
DATABASE_URL=sqlite:///./game.db
ENVIRONMENT=development
SECRET_KEY=change-me
ANTHROPIC_API_KEY=sk-ant-api03-...
```

`ANTHROPIC_API_KEY` 는 [Anthropic Console](https://console.anthropic.com) 에서 발급받아 붙여넣습니다. `.env` 는 `.gitignore` 에 포함되어 있으므로 절대 커밋하지 마세요.

### 3. DB 초기화 및 시드 삽입

```bash
python seeds/seed.py
```

30개 키워드가 `keywords` 테이블에 삽입됩니다. 다른 테이블은 서버 최초 실행 시 자동 생성됩니다.

### 4. 서버 실행

```bash
uvicorn app.main:app --reload
```

서버는 기본적으로 `http://127.0.0.1:8000` 에서 동작합니다. `http://127.0.0.1:8000/docs` 로 접속하면 Swagger UI 에서 모든 API 를 시험해볼 수 있습니다.

## API 개요

| 엔드포인트 | 설명 |
|---|---|
| `GET /keywords` | 키워드 목록 조회 (category, rarity 필터) |
| `POST /keywords` | 키워드 신규 등록 (개발용) |
| `POST /craft/combine` | 키워드 3개 조합, combination_id 발급 |
| `POST /craft/predict` | RGB 예측 → 등급 산정 → AI 이름/설명 생성 |
| `GET /craft/recipe-book` | 제작 도감 조회 |
| `POST /market/items` | 판매 아이템 등록 |
| `GET /market/trend/{item_id}` | 트렌드 곡선 차트 데이터 |
| `POST /market/sell` | 판매 처리 |
| `GET /market/settlement/{season_id}` | 시즌 정산 조회 |
| `PATCH /market/settlement/{season_id}/adjust` | 마케팅/임대/관리 비용 조정 |
| `POST /explore/start` | 시즌 시작 |
| `GET /explore/status` | 현재 일/시간 조회 |
| `POST /explore/action` | 탐험 행동 수행 (TALK/SCAN/EAVESDROP) |
| `GET /explore/events/{day}` | 해당 일차 이벤트 조회 |
| `GET /explore/inventory` | 플레이어 키워드 인벤토리 |
| `POST /explore/day-end` | 일차 종료, 다음 날로 |

상세 스키마는 `/docs` (Swagger UI) 를 참고하세요.

## 진행 현황

현재 중간 개발 단계로, 4개 도메인(키워드·제작·판매·탐험)의 기본 API 가 구축되어 있고 Unity 클라이언트와의 연동 테스트까지 완료된 상태입니다.

**완료된 작업**
- 4개 도메인의 핵심 API 엔드포인트 구현
- 키워드 시드 데이터 30개 작성
- Claude API 연동: 제작 단계에서 등급별 톤이 차별화된 아이템 이름·설명 자동 생성
- Unity 클라이언트 연동 (ngrok 터널 + 오프라인 fallback)

**진행 예정**
- NPC 확장 (5명 → 20~30명) 및 키워드 빈도수 기반 힌트 시스템
- 판매 실패 원인 분석 API (Claude API 활용)
- 실시간 구매자 수 시뮬레이션, 플레이어 가격 조정 기능
- 등급 결과에 대한 피드백 메시지 ("왜 이 등급?")

**알려진 제약**
- 현재 멀티플레이어/계정 시스템 없음 (단일 플레이어 기준)
- 배포용 PostgreSQL 마이그레이션 미완
- `requirements.txt` 는 아직 정리되지 않아 수동 `pip install` 이 필요 (후속 작업 예정)

## 교수님 피드백

2026-1 중간 피드백을 받아 아래 방향으로 개선 중입니다.

1. 탐험 파트의 밀도 보강 (NPC·키워드 힌트 시스템)
2. 제작 결과의 피드백 강화 (AI 생성 — **완료**, 등급 이유 설명 — 예정)
3. 판매 파트의 시뮬레이션 및 플레이어 개입 포인트 추가

세부 반영 계획은 개발 로드맵 내부 문서에서 관리합니다.

## 라이선스

본 저장소는 학부 과정 프로젝트의 일부입니다. 외부 공개 범위·상용 이용 여부는 팀과 학과 방침에 따릅니다.
