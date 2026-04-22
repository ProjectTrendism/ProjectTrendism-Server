"""
Claude API 호출 서비스
- 아이템 이름/설명 자동 생성
- 판타지 세계관 + MZ 트렌드 감성
"""
import os
import json
from anthropic import Anthropic, APIError
from dotenv import load_dotenv

load_dotenv()

# Anthropic 클라이언트 (ANTHROPIC_API_KEY 환경변수 자동 인식)
_client = Anthropic()

# 모델 상수 — 바꾸고 싶을 때 여기만 수정
MODEL_NAME = "claude-haiku-4-5"


SYSTEM_PROMPT = """당신은 '판타지 세계의 트렌디 제작 마스터'입니다.
플레이어가 3개 키워드를 조합해 아이템을 만들었을 때, 이름과 설명을 지어주세요.

# 규칙
- 판타지 세계관 + MZ 감성/밈이 섞인 독특한 네이밍
- 아이템 이름: 한국어 12자 이내, 임팩트 있게
- 아이템 설명: 한국어 30~60자, 위트 있고 간결하게
- 등급이 높을수록 (S > A > B > C) 더 전설적이고 드라마틱한 톤
  - S: 전설급, 서사적, "~의 ~", "전설의 ~"
  - A: 고급, 멋있음
  - B: 평범, 무난
  - C: 어설픔, 아쉬움, 살짝 유머러스
- 반드시 JSON 형식으로만 응답
- JSON 외의 다른 텍스트, 설명, 프리앰블 절대 금지
- 마크다운 코드블록(```) 사용 절대 금지, 순수 JSON만 출력

# 출력 형식 (엄격히 지킬 것 - 이것만 출력)
{"name": "아이템 이름", "description": "아이템 설명"}

# 잘못된 예시 (절대 이렇게 하지 말 것)
````json
{"name": "...", "description": "..."}
```"""


def generate_item_metadata(
    keyword_names: list[str],
    keyword_descriptions: list[str],
    grade: str
) -> dict:
    """
    키워드 3개 + 등급을 받아 아이템 이름/설명을 생성한다.

    Args:
        keyword_names: ["엘프 버섯", "차가운", "MZ감성"]
        keyword_descriptions: ["숲 깊은 곳에서 채취한 희귀 버섯", "서늘하고 청량한 질감", "MZ세대가 열광하는 트렌드"]
        grade: "S" | "A" | "B" | "C"

    Returns:
        {"name": "...", "description": "..."}

    Raises:
        RuntimeError: Claude 호출 실패 또는 응답 파싱 실패 시
    """
    # 플레이어 키워드 정보를 Claude에게 전달할 프롬프트로 구성
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
            max_tokens=200,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
    except APIError as e:
        raise RuntimeError(f"Claude API 호출 실패: {e}") from e

    # Claude 응답에서 텍스트 추출
    raw_text = response.content[0].text.strip()

    # 마크다운 코드블록 펜스 제거 (```json ... ``` 또는 ``` ... ```)
    if raw_text.startswith("```"):
        # 첫 줄 (```json 또는 ```) 제거
        raw_text = raw_text.split("\n", 1)[1] if "\n" in raw_text else raw_text
        # 마지막 ``` 제거
        if raw_text.endswith("```"):
            raw_text = raw_text[:-3]
        raw_text = raw_text.strip()

    # JSON 파싱
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Claude 응답 JSON 파싱 실패. 원문: {raw_text[:200]}"
        ) from e

    # 필수 필드 검증
    if "name" not in parsed or "description" not in parsed:
        raise RuntimeError(
            f"Claude 응답에 name/description 누락. 원문: {raw_text[:200]}"
        )

    return {
        "name": parsed["name"],
        "description": parsed["description"]
    }