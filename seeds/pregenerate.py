"""
사전 생성 스크립트 — Claude(텍스트) + Pollinations AI(이미지)
- 모든 키워드 3개 조합 x 4 등급에 대해 메타데이터/이미지 미리 생성
- GeneratedItemCache 테이블에 저장 (게임 런타임은 이 캐시를 조회)
- 중단/재시작 안전 (이미 캐시에 있으면 스킵)
- Pollinations에 seed 전달 -> 동일 캐시 키는 항상 동일 이미지

실행 방법 (Windows):
    cd D:\\세종대\\컴공\\4학년1학기\\창의학기제\\fantasy-trend-server
    venv\\Scripts\\activate
    python seeds\\pregenerate.py

백그라운드 실행 (Windows):
    start /B python seeds\\pregenerate.py > pregen.log 2>&1
"""
import os
import sys
import time
import hashlib
import urllib.request
import urllib.parse
from itertools import combinations

# 프로젝트 루트를 import path에 추가
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.database import SessionLocal, engine, Base
from app.models.keyword import Keyword
from app.models.craft import GeneratedItemCache
from app.services.claude_service import generate_item_metadata

# 누락된 테이블 자동 생성
Base.metadata.create_all(bind=engine)


# ── 설정 ────────────────────────────────────────────────
IMAGE_TIMEOUT = 60          # Pollinations 응답 대기 (초)
IMAGE_MAX_RETRIES = 3       # 이미지 다운로드 재시도 횟수
SLEEP_BETWEEN_CALLS = 1.0   # Rate limit 방지용 항목 간 대기 (초)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)


# ── 유틸 ────────────────────────────────────────────────
def _make_seed(cache_key: str) -> int:
    """캐시 키 기반 결정성 seed (8자리 정수).
    같은 cache_key는 항상 같은 seed -> 재실행해도 같은 이미지."""
    h = hashlib.md5(cache_key.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % (10 ** 8)


def _make_cache_key(sorted_ids: list[int], grade: str) -> str:
    """app/routers/craft.py의 _make_cache_key()와 동일한 규칙."""
    return f"{','.join(map(str, sorted_ids))}|{grade}"


def download_free_image(
    prompt: str,
    filename: str,
    seed: int
) -> str | None:
    """
    Pollinations AI를 사용해 이미지 생성/다운로드.
    - seed: 결정성 확보 (같은 seed -> 같은 이미지)
    - timeout: 무한 대기 방지
    - 재시도 IMAGE_MAX_RETRIES 회, 지수적 백오프
    - 최종 실패 시 None 반환 (호출 측에서 처리)
    """
    encoded_prompt = urllib.parse.quote(prompt)
    url = (
        f"https://image.pollinations.ai/prompt/{encoded_prompt}"
        f"?width=512&height=512&nologo=true&seed={seed}"
    )

    save_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "static", "items"
    )
    os.makedirs(save_dir, exist_ok=True)
    save_path = os.path.join(save_dir, filename)

    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})

    for attempt in range(1, IMAGE_MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=IMAGE_TIMEOUT) as response, \
                 open(save_path, "wb") as out_file:
                out_file.write(response.read())
            return f"/static/items/{filename}"
        except Exception as e:
            print(f"    [WARN] 다운로드 실패 ({attempt}/{IMAGE_MAX_RETRIES}): {e}")
            if attempt < IMAGE_MAX_RETRIES:
                # 지수적 백오프: 2초, 4초, 8초
                wait = 2 ** attempt
                print(f"    [INFO] {wait}초 대기 후 재시도...")
                time.sleep(wait)

    print("    [FAIL] 최대 재시도 횟수 초과 -> image_url=None으로 진행")
    return None


# ── 메인 ────────────────────────────────────────────────
def run_pregeneration():
    db = SessionLocal()
    keywords = db.query(Keyword).all()

    # 모든 키워드 3개 조합 생성
    # 만약 카테고리별 1개씩만 조합하는 룰이라면 여기를 itertools.product로 교체
    all_combos = list(combinations(keywords, 3))
    grades = ["S", "A", "B", "C"]
    total_items = len(all_combos) * len(grades)

    print("=" * 60)
    print(f"[INFO] 총 조합 수: {len(all_combos)}개")
    print(f"[INFO] 등급 수: {len(grades)} (S/A/B/C)")
    print(f"[INFO] 총 생성 항목: {total_items}개")
    print("=" * 60)

    succeeded = 0
    text_failed = 0
    image_failed = 0
    skipped = 0

    for i, combo in enumerate(all_combos):
        sorted_ids = sorted([k.id for k in combo])
        kw_names = [k.name for k in combo]
        kw_descs = [k.description for k in combo]

        for grade in grades:
            cache_key = _make_cache_key(sorted_ids, grade)

            # 1) 캐시 체크: 이미 생성된 항목이면 스킵
            existing = db.query(GeneratedItemCache).filter_by(
                keyword_ids_key=cache_key
            ).first()
            if existing:
                skipped += 1
                continue

            print(f"\n[{i+1}/{len(all_combos)}] [{cache_key}] {', '.join(kw_names)}")

            # 2) 텍스트 생성 (Claude)
            try:
                ai_text = generate_item_metadata(kw_names, kw_descs, grade)
                print(f"  [OK]   텍스트: {ai_text['name']}")
            except Exception as e:
                print(f"  [FAIL] 텍스트 생성 실패: {e}")
                text_failed += 1
                # 텍스트 실패 시 캐시 저장 안 함 -> 다음 실행에서 재시도
                continue

            # 3) 이미지 생성 (Pollinations, seed 결정성)
            seed = _make_seed(cache_key)
            filename = f"item_{cache_key.replace('|', '_').replace(',', '_')}.png"
            image_url = download_free_image(ai_text["image_prompt"], filename, seed)

            if image_url:
                print(f"  [OK]   이미지: {filename}")
            else:
                print(f"  [WARN] 이미지 실패 -> 텍스트만 저장 (별도 retry 스크립트로 보완)")
                image_failed += 1

            # 4) 캐시 저장 (이미지 실패해도 텍스트는 저장해서 Claude 재호출 방지)
            new_item = GeneratedItemCache(
                keyword_ids_key=cache_key,
                grade=grade,
                name=ai_text["name"],
                description=ai_text["description"],
                image_url=image_url,
            )
            db.add(new_item)
            db.commit()
            succeeded += 1

            # Rate limit 방지
            time.sleep(SLEEP_BETWEEN_CALLS)

    print("\n" + "=" * 60)
    print("[DONE] 사전 생성 완료")
    print(f"  - 성공:           {succeeded}")
    print(f"  - 텍스트 실패:    {text_failed}")
    print(f"  - 이미지만 실패:  {image_failed}")
    print(f"  - 기존 캐시 스킵: {skipped}")
    print("=" * 60)
    db.close()


if __name__ == "__main__":
    run_pregeneration()