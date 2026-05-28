"""
카테고리 룰 적용 시 영향도 분석 스크립트 (일회성, 분석용).
- 카테고리별 키워드 분포 확인
- 기존 GeneratedItemCache 중 카테고리 룰 만족 비율 계산
- 룰 적용 시 추가로 생성해야 할 항목 수 산출
사용: python analyze_category_rule.py
"""
import sys
from sqlalchemy import func
from app.database import SessionLocal
from app.models.keyword import Keyword
from app.models.craft import GeneratedItemCache


def main():
    db = SessionLocal()

    # ─── 1. 카테고리별 키워드 수 ───────────────────────
    print("=" * 60)
    print("[1] 카테고리별 키워드 분포")
    print("=" * 60)
    cat_count = (
        db.query(Keyword.category, func.count(Keyword.id))
        .group_by(Keyword.category)
        .all()
    )
    for cat, cnt in cat_count:
        print(f"  {cat:10s}: {cnt}")
    total_kw = sum(c for _, c in cat_count)
    print(f"  {'TOTAL':10s}: {total_kw}")

    # ─── 2. 카테고리별 키워드 ID/이름 ─────────────────
    print()
    print("=" * 60)
    print("[2] 카테고리별 키워드 ID/이름")
    print("=" * 60)

    def fetch_by_cat(cat):
        return db.query(Keyword).filter(Keyword.category == cat).order_by(Keyword.id).all()

    bases = fetch_by_cat("BASE")
    styles = fetch_by_cat("STYLE")
    concepts = fetch_by_cat("CONCEPT")

    print(f"[BASE]    ({len(bases)}개)")
    for k in bases:
        print(f"  id={k.id:3d}  name={k.name}")
    print(f"\n[STYLE]   ({len(styles)}개)")
    for k in styles:
        print(f"  id={k.id:3d}  name={k.name}")
    print(f"\n[CONCEPT] ({len(concepts)}개)")
    for k in concepts:
        print(f"  id={k.id:3d}  name={k.name}")

    base_ids = {k.id for k in bases}
    style_ids = {k.id for k in styles}
    concept_ids = {k.id for k in concepts}

    # ─── 3. 기존 캐시의 카테고리 룰 만족도 ─────────────
    print()
    print("=" * 60)
    print("[3] 기존 GeneratedItemCache 룰 매칭 분석")
    print("=" * 60)

    all_cache = db.query(GeneratedItemCache).all()
    rule_match = 0
    rule_violate = 0
    pattern_counter = {}
    sample_match = []
    sample_violate = []

    for c in all_cache:
        try:
            ids_str, grade = c.keyword_ids_key.split("|")
            ids = [int(x) for x in ids_str.split(",")]
        except Exception:
            continue

        n_base = sum(1 for i in ids if i in base_ids)
        n_style = sum(1 for i in ids if i in style_ids)
        n_concept = sum(1 for i in ids if i in concept_ids)

        pattern = (n_base, n_style, n_concept)
        pattern_counter[pattern] = pattern_counter.get(pattern, 0) + 1

        if pattern == (1, 1, 1):
            rule_match += 1
            if len(sample_match) < 3:
                sample_match.append(f"{c.keyword_ids_key}  ({c.name})")
        else:
            rule_violate += 1
            if len(sample_violate) < 3:
                sample_violate.append(f"{c.keyword_ids_key}  ({c.name})")

    total = len(all_cache)
    print(f"  전체 캐시 row             : {total}")
    print(f"  카테고리 룰 만족 (1/1/1)  : {rule_match}  ({rule_match/total*100:.1f}%)")
    print(f"  룰 위반                   : {rule_violate}  ({rule_violate/total*100:.1f}%)")

    print(f"\n  [패턴별 분포] (Base수, Style수, Concept수): 개수")
    for pattern, cnt in sorted(pattern_counter.items(), key=lambda x: -x[1]):
        marker = "  <-- 룰 매칭" if pattern == (1, 1, 1) else ""
        print(f"    {pattern}: {cnt}{marker}")

    print(f"\n  [룰 만족 샘플]")
    for s in sample_match:
        print(f"    {s}")
    print(f"  [룰 위반 샘플]")
    for s in sample_violate:
        print(f"    {s}")

    # ─── 4. 룰 적용 시 필요 항목 vs 활용 가능 ───────
    print()
    print("=" * 60)
    print("[4] 카테고리 룰 적용 시 사전생성 시뮬레이션")
    print("=" * 60)

    grades = 4
    rule_total = len(base_ids) * len(style_ids) * len(concept_ids) * grades
    rule_image_match = sum(
        1 for c in all_cache
        if (
            tuple(sorted([int(x) for x in c.keyword_ids_key.split("|")[0].split(",")]))
            and (
                (lambda ids: (
                    sum(1 for i in ids if i in base_ids) == 1 and
                    sum(1 for i in ids if i in style_ids) == 1 and
                    sum(1 for i in ids if i in concept_ids) == 1
                ))([int(x) for x in c.keyword_ids_key.split("|")[0].split(",")])
            )
            and c.image_url is not None
        )
    )

    print(f"  룰 기준 전체 필요 항목 : {len(base_ids)} x {len(style_ids)} x {len(concept_ids)} x 4 = {rule_total}")
    print(f"  기존 캐시 중 룰 매칭   : {rule_match}")
    print(f"    -> 그중 image_url 있음: {rule_image_match}")
    print(f"  추가 사전생성 필요     : {rule_total - rule_match}  (텍스트+이미지)")
    print(f"                       또는 {rule_total - rule_image_match}  (이미지만 보강 시)")

    # ─── 5. 현재 무모드(combinations) 기준 ───────────
    from math import comb
    raw_total = comb(total_kw, 3) * grades
    print()
    print("=" * 60)
    print("[5] 비교: 현재 카테고리 무관 모드 (combinations)")
    print("=" * 60)
    print(f"  무모드 전체 필요 항목  : C({total_kw}, 3) x 4 = {raw_total}")
    print(f"  현재 진행률            : {total}/{raw_total} = {total/raw_total*100:.1f}%")
    print(f"  남은 항목              : {raw_total - total}")

    print()
    print("=" * 60)
    print("[요약] 결정 참고 데이터")
    print("=" * 60)
    print(f"  룰 적용시 총 1200~ 추정 항목 (B*S*C*4)")
    print(f"  - 룰 적용 + 현 자산 재활용: 추가 {rule_total - rule_match}개 생성")
    print(f"  - 룰 무시 + 현 자산 계속  : 추가 {raw_total - total}개 생성")
    print(f"  - 비율: 룰 적용이 약 {(raw_total - total) / max(rule_total - rule_match, 1):.1f}배 효율")
    print("=" * 60)

    db.close()


if __name__ == "__main__":
    main()
