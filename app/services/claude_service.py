"""
Claude API 호출 서비스
- 아이템 이름/설명/이미지 프롬프트 자동 생성 (텍스트 사전 생성용)
- 판매 성과 분석 (런타임 호출, 컨텍스트 의존적)
"""
import os
import json
from anthropic import Anthropic, APIError
from dotenv import load_dotenv

load_dotenv()

# Anthropic 클라이언트 (ANTHROPIC_API_KEY 환경변수 자동 인식)
_client = Anthropic()

# 모델 상수
MODEL_NAME = "claude-haiku-4-5"


# ── 아이템 생성 프롬프트 ────────────────────────────────
SYSTEM_PROMPT = """당신은 '판타지 세계의 트렌디 제작 마스터'이자 '최상급 픽셀아트 프롬프트 엔지니어'입니다.
플레이어가 3개 키워드를 조합해 아이템을 만들었을 때, 이름과 설명, 그리고 이미지 생성용 영문 프롬프트를 지어주세요.

# 세계관
- 인간, 엘프, 드워프, 고블린 등이 모여 사는 시골 마을.
- 현대의 MZ세대 트렌드(SNS 핫플, 가성비, 힙한 감성)가 판타지 물건에 결합된 세계관.
- 그래픽 스타일: 스타듀밸리(Stardew Valley), 문라이터(Moonlighter) 같은 따뜻하고 아기자기한 레트로 픽셀 아트.

# 규칙
- 판타지 세계관 + MZ 감성/밈이 섞인 독특한 네이밍
- 아이템 이름: 한국어 12자 이내, 임팩트 있게
- 아이템 설명: 한국어 30~60자, 위트 있고 간결하게
- 등급이 높을수록 (S > A > B > C) 더 전설적이고 퀄리티 높은 느낌 부여
- image_prompt: 이 아이템을 그리기 위한 영문 Stable Diffusion 프롬프트.
  * 반드시 포함할 필수 키워드: "16-bit pixel art, RPG inventory item icon, isolated on solid black background, vibrant colors"
  * 플레이어가 넘겨준 키워드의 시각적 특징(질감, 색상, 형태)을 구체적인 영어 단어로 묘사할 것.
    예: "MZ감성" -> "trendy, hip, modern design", "고블린 가죽" -> "rough green leather"

# 출력 형식 (오직 JSON만 출력, 마크다운 ``` 절대 금지)
{"name": "아이템 이름", "description": "아이템 설명", "image_prompt": "영문 이미지 프롬프트"}
"""


def generate_item_metadata(
    keyword_names: list[str],
    keyword_descriptions: list[str],
    grade: str
) -> dict:
    """
    키워드 3개 + 등급을 받아 아이템 이름/설명/영문 이미지 프롬프트를 생성한다.

    Returns:
        {"name": "...", "description": "...", "image_prompt": "..."}

    Raises:
        RuntimeError: Claude 호출 실패 또는 응답 파싱 실패 시
    """
    keyword_lines = "\n".join(
        f"- {name}: {desc}"
        for name, desc in zip(keyword_names, keyword_descriptions)
    )

    user_message = f"""다음 3개 키워드를 조합해 제작한 아이템의 이름과 설명을 지어주세요.

# 키워드
{keyword_lines}

# 제작 등급
{grade}

JSON 형식으로만 응답하세요."""

    try:
        response = _client.messages.create(
            model=MODEL_NAME,
            max_tokens=400,  # image_prompt(영문) 길이까지 고려해 200 -> 400으로 상향
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
    except APIError as e:
        raise RuntimeError(f"Claude API 호출 실패: {e}") from e

    raw_text = response.content[0].text.strip()

    # 마크다운 코드블록 펜스 제거 (혹시 모를 케이스 방어)
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Claude 응답 JSON 파싱 실패. 원문: {raw_text[:200]}"
        ) from e

    required = ["name", "description", "image_prompt"]
    for field in required:
        if field not in parsed:
            raise RuntimeError(
                f"Claude 응답에 {field} 누락. 원문: {raw_text[:200]}"
            )

    return {
        "name": parsed["name"],
        "description": parsed["description"],
        "image_prompt": parsed["image_prompt"]
    }


# ── 판매 분석 프롬프트 ──────────────────────────────────
ANALYSIS_SYSTEM_PROMPT = """당신은 '판타지 세계의 트렌드 분석가'입니다.
플레이어가 제작한 아이템의 판매 성과를 분석해주세요.

# 규칙
- 판타지 세계관 톤 유지 (상인/분석가 말투)
- 분석은 구체적이고 실행 가능한 조언 포함
- 한국어로 작성
- 반드시 JSON 형식으로만 응답
- JSON 외의 다른 텍스트, 프리앰블 절대 금지
- 마크다운 코드블록(```) 사용 절대 금지

# 출력 형식
{"summary": "한줄 요약 (20자 이내)", "keyword_analysis": "키워드 조합 평가 (50자 이내)", "timing_analysis": "판매 타이밍 평가 (50자 이내)", "price_analysis": "가격 전략 평가 (50자 이내)", "next_action": "다음 시즌 조언 (60자 이내)", "score": 0~100}"""


def analyze_sales_performance(
    item_name: str,
    keyword_names: list[str],
    grade: str,
    trend_index: float,
    revenue: float,
    stock_remaining: int,
    discount_rate: float,
    days_on_market: int
) -> dict:
    """
    아이템 판매 성과를 Claude가 분석한다 (런타임 호출, 컨텍스트 의존적이라 캐시 불가).
    """
    user_message = f"""다음 아이템의 판매 성과를 분석해주세요.

# 아이템 정보
- 이름: {item_name}
- 키워드 조합: {', '.join(keyword_names)}
- 제작 등급: {grade}

# 판매 데이터
- 현재 트렌드 지수: {trend_index} (0~150, 높을수록 인기)
- 총 매출: {revenue} 골드
- 잔여 재고: {stock_remaining}개
- 적용 할인율: {discount_rate * 100}%
- 출시 후 경과일: {days_on_market}일

# 참고
- 트렌드 지수는 30일 차에 정점, 이후 지수적 감소
- S등급은 트렌드 지수 1.5배 보정
- 180일 이후 트렌드 사망

JSON 형식으로만 응답하세요."""

    try:
        response = _client.messages.create(
            model=MODEL_NAME,
            max_tokens=400,
            system=ANALYSIS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
    except APIError as e:
        raise RuntimeError(f"Claude API 호출 실패: {e}") from e

    raw_text = response.content[0].text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Claude 분석 JSON 파싱 실패. 원문: {raw_text[:300]}"
        ) from e

    required = ["summary", "keyword_analysis", "timing_analysis",
                "price_analysis", "next_action"]
    for field in required:
        if field not in parsed:
            raise RuntimeError(f"분석 응답에 {field} 누락")

    return parsed