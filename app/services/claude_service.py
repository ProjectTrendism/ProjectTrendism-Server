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

# ══════════════════════════════════════════════════════════
#  시즌 트렌드 시스템 (3번 -- 탐험 시즌, 사전 생성용)
# ══════════════════════════════════════════════════════════

def _parse_claude_json(raw_text: str, required: list[str], context: str) -> dict:
    """
    Claude 응답에서 마크다운 펜스를 제거하고 JSON을 파싱.검증한다.
    generate_item_metadata / analyze_sales_performance의 펜스 제거 로직과 동일.
    """
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Claude 응답 JSON 파싱 실패({context}). 원문: {text[:300]}"
        ) from e

    for field in required:
        if field not in parsed:
            raise RuntimeError(
                f"Claude 응답에 {field} 누락({context}). 원문: {text[:300]}"
            )
    return parsed


# ── 시즌 트렌드 생성 ────────────────────────────────────
SEASON_TREND_SYSTEM_PROMPT = """당신은 '판타지 마을의 트렌드를 결정하는 시대정신'입니다.
매 시즌, 이 판타지 마을에 어떤 감성이 유행할지를 정합니다.

# 세계관
- 인간/엘프/드워프/고블린이 사는 시골 마을. 현대 MZ 트렌드가 판타지에 섞인 세계관.

# 규칙
- trend_theme: 이번 시즌 유행을 한 문장으로. 한국어 40자 이내. 위트있고 구체적으로.
- rising_keyword_ids: 제공된 키워드 목록 중 이번 시즌 '급상승'하는 키워드 정확히 3개의 id.
  * 서로 다른 category(BASE/STYLE/CONCEPT)가 섞이도록 고를 것.
  * trend_theme과 의미가 통하는 키워드를 고를 것.
- 매 시즌 다른 조합이 나오도록 다양하게 선택할 것.

# 출력 형식 (오직 JSON만 출력, 마크다운 ``` 절대 금지)
{"trend_theme": "...", "rising_keyword_ids": [12, 5, 23]}
"""


def generate_season_trend(keywords: list[dict]) -> dict:
    """
    이번 시즌의 트렌드 테마와 급상승 키워드를 결정한다 (사전 생성용).

    Args:
        keywords: [{"id": int, "name": str, "category": str, "description": str}, ...]

    Returns:
        {"trend_theme": str, "rising_keyword_ids": list[int]}

    Raises:
        RuntimeError: Claude 호출 실패 또는 응답 파싱.검증 실패 시
    """
    keyword_lines = "\n".join(
        f"- id={k['id']} [{k['category']}] {k['name']}: {k['description']}"
        for k in keywords
    )

    user_message = f"""아래 키워드 목록을 보고 이번 시즌의 트렌드를 정해주세요.

# 전체 키워드 목록
{keyword_lines}

JSON 형식으로만 응답하세요."""

    try:
        response = _client.messages.create(
            model=MODEL_NAME,
            max_tokens=300,
            system=SEASON_TREND_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
    except APIError as e:
        raise RuntimeError(f"Claude API 호출 실패(시즌 트렌드): {e}") from e

    parsed = _parse_claude_json(
        response.content[0].text,
        required=["trend_theme", "rising_keyword_ids"],
        context="시즌 트렌드"
    )

    # rising_keyword_ids 검증: 실재하는 키워드 id만 남긴다 (환각 방어)
    rising = parsed["rising_keyword_ids"]
    if not isinstance(rising, list) or not rising:
        raise RuntimeError(f"rising_keyword_ids가 비정상입니다: {rising}")

    valid_ids = {k["id"] for k in keywords}
    rising = [int(kid) for kid in rising if int(kid) in valid_ids]
    if not rising:
        raise RuntimeError("rising_keyword_ids에 유효한 키워드 id가 없습니다")

    return {
        "trend_theme": str(parsed["trend_theme"]),
        "rising_keyword_ids": rising,
    }


# ── 시즌 NPC 정보 생성 ──────────────────────────────────
SEASON_NPC_SYSTEM_PROMPT = """당신은 '판타지 마을 주민들의 입소문을 설계하는 연출가'입니다.
이번 시즌 트렌드가 정해졌을 때, 마을 NPC들이 플레이어에게 어떤 말을 흘릴지 설계합니다.

# 핵심 개념: 신뢰도
- 각 NPC는 true_reliability(0~100)를 가집니다. 높을수록 정확한 정보를 줍니다.
- 신뢰도 높음(70 이상): 실제 급상승 키워드를 정확히 언급. is_disinformer=false.
- 신뢰도 낮음(40 이하): 급상승이 '아닌' 엉뚱한 키워드를 유행이라 잘못 말함. is_disinformer=true.
- 중간(41~69): 급상승 키워드와 평범한 키워드를 섞어 언급. is_disinformer=false.
- 전체 NPC 중 약 30%는 신뢰도 낮은 거짓 정보원(is_disinformer=true)으로 배치할 것.

# 규칙
- season_dialogue: NPC가 플레이어에게 건네는 대사. 한국어 30~60자. NPC 성격이 드러나게.
  * 신뢰도 높은 NPC는 자신감 있고 구체적으로, 낮은 NPC는 모호하거나 허세 섞인 말투로.
- assigned_keywords: NPC가 이번 시즌 플레이어에게 줄(드랍할) keyword_id 2~3개.
  * is_disinformer=false면 급상승 키워드 위주로 배정.
  * is_disinformer=true면 급상승이 '아닌' 키워드 위주로 배정.
- 모든 NPC의 대사는 서로 다르게, 같은 트렌드라도 다양한 표현으로 작성할 것.
- 요청된 모든 npc_id에 대해 빠짐없이 생성할 것.

# 출력 형식 (오직 JSON만 출력, 마크다운 ``` 절대 금지)
{"npcs": [{"npc_id": 1, "season_dialogue": "...", "assigned_keywords": [3, 7], "true_reliability": 80, "is_disinformer": false}]}
"""


def generate_npc_season_info(
    trend_theme: str,
    rising_keywords: list[dict],
    all_keywords: list[dict],
    npcs: list[dict],
) -> list[dict]:
    """
    이번 시즌 NPC들의 대사/배정 키워드/신뢰도를 생성한다 (사전 생성용).

    Args:
        trend_theme:     이번 시즌 트렌드 테마
        rising_keywords: 급상승 키워드 [{"id", "name", "category"}, ...]
        all_keywords:    전체 키워드 [{"id", "name", "category"}, ...]
        npcs:            정보를 생성할 NPC [{"id", "name", "location"}, ...]

    Returns:
        [{"npc_id", "season_dialogue", "assigned_keywords",
          "true_reliability", "is_disinformer"}, ...]

    Raises:
        RuntimeError: Claude 호출 실패, 파싱 실패, 또는 요청 NPC 누락 시
    """
    rising_lines = "\n".join(
        f"- id={k['id']} [{k['category']}] {k['name']}" for k in rising_keywords
    )
    all_lines = "\n".join(
        f"- id={k['id']} [{k['category']}] {k['name']}" for k in all_keywords
    )
    npc_lines = "\n".join(
        f"- npc_id={n['id']} {n['name']} (위치: {n['location']})" for n in npcs
    )

    user_message = f"""이번 시즌 트렌드에 맞춰 아래 NPC들의 입소문을 설계해주세요.

# 이번 시즌 트렌드
{trend_theme}

# 급상승 키워드 (진짜 유행)
{rising_lines}

# 전체 키워드 목록 (assigned_keywords는 이 안에서만 선택)
{all_lines}

# 정보를 생성할 NPC ({len(npcs)}명)
{npc_lines}

위 {len(npcs)}명 전원에 대해 JSON 형식으로만 응답하세요."""

    try:
        response = _client.messages.create(
            model=MODEL_NAME,
            max_tokens=5000,
            system=SEASON_NPC_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
    except APIError as e:
        raise RuntimeError(f"Claude API 호출 실패(NPC 시즌 정보): {e}") from e

    parsed = _parse_claude_json(
        response.content[0].text,
        required=["npcs"],
        context="NPC 시즌 정보"
    )

    npc_list = parsed["npcs"]
    if not isinstance(npc_list, list) or not npc_list:
        raise RuntimeError(f"npcs가 비정상입니다: {npc_list}")

    valid_keyword_ids = {k["id"] for k in all_keywords}
    requested_npc_ids = {n["id"] for n in npcs}

    result = []
    for item in npc_list:
        for field in ["npc_id", "season_dialogue", "assigned_keywords",
                      "true_reliability", "is_disinformer"]:
            if field not in item:
                raise RuntimeError(f"NPC 항목에 {field} 누락: {item}")

        npc_id = int(item["npc_id"])
        if npc_id not in requested_npc_ids:
            # 요청하지 않은 npc_id는 무시 (환각 방어)
            continue

        # assigned_keywords: 실재하는 keyword_id만 남긴다
        assigned = [
            int(kid) for kid in item["assigned_keywords"]
            if int(kid) in valid_keyword_ids
        ]

        # true_reliability: 0~100 범위로 클램프
        reliability = max(0, min(100, int(item["true_reliability"])))

        result.append({
            "npc_id": npc_id,
            "season_dialogue": str(item["season_dialogue"]),
            "assigned_keywords": assigned,
            "true_reliability": reliability,
            "is_disinformer": bool(item["is_disinformer"]),
        })

    # 요청한 NPC가 응답에서 빠졌는지 확인
    returned_ids = {r["npc_id"] for r in result}
    missing = requested_npc_ids - returned_ids
    if missing:
        raise RuntimeError(f"응답에서 NPC {sorted(missing)} 누락")

    return result

    # ══════════════════════════════════════════════════════════
#  시즌 트렌드 일괄 생성 (3-3 개선 -- 시즌 간 다양성 확보)
#  claude_service.py 맨 끝에 이어붙일 것.
#  기존 generate_season_trend()는 더 이상 쓰이지 않음 (지워도 무방).
# ══════════════════════════════════════════════════════════

ALL_SEASON_TRENDS_SYSTEM_PROMPT = """당신은 '판타지 마을의 여러 시즌에 걸친 트렌드 흐름을 설계하는 시대정신'입니다.
여러 시즌의 트렌드를 한 번에 설계합니다. 핵심은 '시즌마다 확연히 다른 트렌드'입니다.

# 세계관
- 인간/엘프/드워프/고블린이 사는 시골 마을. 현대 MZ 트렌드가 판타지에 섞인 세계관.

# 가장 중요한 규칙: 시즌 간 다양성
- 각 시즌의 트렌드는 서로 확연히 달라야 합니다. 컨셉/분위기/색감이 겹치면 안 됩니다.
- rising_keyword_ids는 시즌 간 최대한 겹치지 않게, 제공된 키워드 전체를 골고루 활용하세요.
  특정 키워드가 여러 시즌에 반복 등장하지 않도록 분산할 것.
- 서로 다른 방향으로 폭넓게 펼칠 것. 예: 한 시즌이 '어두운/신비'면
  다른 시즌은 '밝은/활기', 또 다른 시즌은 '빈티지/클래식', '귀여운/아기자기',
  '강렬한/화려한' 등 전혀 다른 결로 갈 것.

# 각 시즌 규칙
- trend_theme: 그 시즌 유행을 한 문장으로. 한국어 40자 이내. 위트있고 구체적으로.
- rising_keyword_ids: 그 시즌 급상승 키워드 정확히 3개의 id.
  서로 다른 category(BASE/STYLE/CONCEPT)가 섞이도록 고를 것.

# 출력 형식 (오직 JSON만 출력, 마크다운 ``` 절대 금지)
{"seasons": [{"trend_theme": "...", "rising_keyword_ids": [12, 5, 23]}, {"trend_theme": "...", "rising_keyword_ids": [3, 18, 27]}]}
"""


def generate_all_season_trends(keywords: list[dict], count: int) -> list[dict]:
    """
    count개 시즌의 트렌드를 한 번의 호출로 생성한다 (시즌 간 다양성 확보).

    시즌별로 따로 호출하면 각 호출이 서로를 몰라 비슷한 트렌드로 수렴하므로,
    한 컨텍스트에 묶어 Claude가 시즌 간 중복을 직접 통제하게 한다.

    Args:
        keywords: [{"id", "name", "category", "description"}, ...]
        count:    생성할 시즌 개수

    Returns:
        [{"trend_theme": str, "rising_keyword_ids": list[int]}, ...]  (count개)

    Raises:
        RuntimeError: Claude 호출 실패, 파싱 실패, 또는 개수 부족 시
    """
    if count < 1:
        return []

    keyword_lines = "\n".join(
        f"- id={k['id']} [{k['category']}] {k['name']}: {k['description']}"
        for k in keywords
    )

    user_message = f"""아래 키워드 목록을 보고 서로 확연히 다른 {count}개 시즌의 트렌드를 설계해주세요.

# 전체 키워드 목록
{keyword_lines}

정확히 {count}개 시즌을 JSON 형식으로만 응답하세요."""

    try:
        response = _client.messages.create(
            model=MODEL_NAME,
            max_tokens=2000,
            system=ALL_SEASON_TRENDS_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}]
        )
    except APIError as e:
        raise RuntimeError(f"Claude API 호출 실패(시즌 트렌드 일괄): {e}") from e

    parsed = _parse_claude_json(
        response.content[0].text,
        required=["seasons"],
        context="시즌 트렌드 일괄"
    )

    seasons = parsed["seasons"]
    if not isinstance(seasons, list) or len(seasons) < count:
        got = len(seasons) if isinstance(seasons, list) else seasons
        raise RuntimeError(f"요청한 {count}개보다 적은 시즌이 생성됨: {got}")

    valid_ids = {k["id"] for k in keywords}
    result = []
    for idx, s in enumerate(seasons[:count]):
        if "trend_theme" not in s or "rising_keyword_ids" not in s:
            raise RuntimeError(f"{idx + 1}번째 시즌에 필수 필드 누락: {s}")

        # 실재하는 키워드 id만 통과 (환각 방어)
        rising = [
            int(kid) for kid in s["rising_keyword_ids"]
            if int(kid) in valid_ids
        ]
        if not rising:
            raise RuntimeError(
                f"{idx + 1}번째 시즌에 유효한 rising_keyword_ids가 없습니다: {s}"
            )

        result.append({
            "trend_theme": str(s["trend_theme"]),
            "rising_keyword_ids": rising,
        })

    return result