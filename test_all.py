"""
Fantasy Trend -- full update test
Run with server up: python test_all.py
"""
import requests
import json
import sys

BASE = "http://localhost:8000"
PASS = 0
FAIL = 0


def test(name, method, path, expected_status=200, json_body=None, check=None):
    global PASS, FAIL
    url = f"{BASE}{path}"
    try:
        if method == "GET":
            r = requests.get(url, timeout=15)
        elif method == "POST":
            r = requests.post(url, json=json_body, timeout=15)
        elif method == "PATCH":
            r = requests.patch(url, json=json_body, timeout=15)
        else:
            print(f"  [FAIL] [{name}] unknown method: {method}")
            FAIL += 1
            return None

        data = r.json()

        if r.status_code != expected_status:
            print(f"  [FAIL] [{name}] status {r.status_code} (expected {expected_status})")
            print(f"         {json.dumps(data, ensure_ascii=False)[:200]}")
            FAIL += 1
            return data

        if check and not check(data):
            print(f"  [FAIL] [{name}] validation failed")
            print(f"         {json.dumps(data, ensure_ascii=False)[:200]}")
            FAIL += 1
            return data

        print(f"  [ OK ] [{name}]")
        PASS += 1
        return data

    except requests.ConnectionError:
        print(f"  [FAIL] [{name}] connection refused -- is uvicorn running?")
        FAIL += 1
        sys.exit(1)
    except Exception as e:
        print(f"  [FAIL] [{name}] error: {e}")
        FAIL += 1
        return None


def main():
    global PASS, FAIL

    print("=" * 60)
    print("  Fantasy Trend -- Update Test Suite")
    print("=" * 60)

    # ── 0. server ──
    print("\n[0] Server health check")
    print("-" * 40)
    test("server status", "GET", "/",
         check=lambda d: d.get("status") == "ok")

    # ── 1. NPC list ──
    print("\n[1] NPC list (25 total, 5 locations)")
    print("-" * 40)
    test("all NPCs", "GET", "/explore/npcs",
         check=lambda d: d["status"] == "success" and len(d["data"]) == 25)

    for loc in ["maul", "sup", "donggul", "samak", "sijang"]:
        loc_kr = {"maul": "마을", "sup": "숲", "donggul": "동굴",
                  "samak": "사막", "sijang": "시장"}[loc]
        test(f"{loc_kr} NPC x5", "GET", f"/explore/npcs?location={loc_kr}",
             check=lambda d: len(d["data"]) == 5)

    # ── 2. season start ──
    print("\n[2] Season start")
    print("-" * 40)
    test("start season", "POST", "/explore/start",
         check=lambda d: d["status"] == "success")

    test("status check", "GET", "/explore/status",
         check=lambda d: d["data"]["current_day"] == 1 and d["data"]["current_time"] == 8)

    # ── 3. NPC talk + frequency ──
    print("\n[3] NPC talk (frequency tracking)")
    print("-" * 40)

    for i in range(3):
        test(f"Ella talk #{i+1}", "POST", "/explore/action",
             json_body={"action_type": "TALK", "target_id": 6},
             check=lambda d: d["data"]["success"] == True)

    for i in range(2):
        test(f"Noel talk #{i+1}", "POST", "/explore/action",
             json_body={"action_type": "TALK", "target_id": 9},
             check=lambda d: d["status"] == "success")

    for i in range(2):
        test(f"Clara talk #{i+1}", "POST", "/explore/action",
             json_body={"action_type": "TALK", "target_id": 13},
             check=lambda d: d["status"] == "success")

    # ── 4. eavesdrop ──
    print("\n[4] Eavesdrop")
    print("-" * 40)
    test("Shadow eavesdrop", "POST", "/explore/action",
         json_body={"action_type": "EAVESDROP", "target_id": 25},
         check=lambda d: d["status"] == "success")

    test("Grook eavesdrop", "POST", "/explore/action",
         json_body={"action_type": "EAVESDROP", "target_id": 12},
         check=lambda d: d["status"] == "success")

    # ── 5. scan ──
    print("\n[5] Scan")
    print("-" * 40)
    test("area scan", "POST", "/explore/action",
         json_body={"action_type": "SCAN", "target_id": 0},
         check=lambda d: d["status"] == "success")

    # ── 6. keyword frequency ──
    print("\n[6] Keyword frequency (HOT / WARM / COLD)")
    print("-" * 40)
    freq_data = test("frequency list", "GET", "/explore/frequency",
                     check=lambda d: d["status"] == "success" and len(d["data"]) > 0)
    if freq_data:
        print("     ---- frequency status ----")
        for item in freq_data["data"][:8]:
            tag = {"HOT": "[HOT ]", "WARM": "[WARM]", "COLD": "[COLD]"}[item["heat_level"]]
            print(f"     {tag} {item['keyword_name']}: "
                  f"mention={item['mention_count']}, "
                  f"npc={item['npc_count']}")

    # ── 7. hidden keywords ──
    print("\n[7] Hidden keyword hints")
    print("-" * 40)
    hidden_data = test("hidden keywords", "GET", "/explore/hidden",
                       check=lambda d: d["status"] == "success" and len(d["data"]) == 5)
    if hidden_data:
        for h in hidden_data["data"]:
            lock = "[OPEN]" if h["is_unlocked"] else "[LOCK]"
            print(f"     {lock} [{h['unlock_type']}] {h['keyword_name']}: {h['hint_text'][:35]}...")

    # ── 8. inventory ──
    print("\n[8] Inventory")
    print("-" * 40)
    inv_data = test("inventory list", "GET", "/explore/inventory",
                    check=lambda d: d["status"] == "success")
    if inv_data and inv_data["data"]:
        for item in inv_data["data"]:
            print(f"     - {item['keyword_name']} ({item['rarity']}): x{item['quantity']}")
    else:
        print("     (empty -- normal depending on drop RNG)")

    # ── 9. events ──
    print("\n[9] Events")
    print("-" * 40)
    ev1 = test("Day 1 events", "GET", "/explore/events/1",
               check=lambda d: d["status"] == "success")
    if ev1 and ev1["data"]:
        for e in ev1["data"]:
            print(f"     [{e['event_type']}] {e['name']}: {e['description'][:30]}...")

    test("Day 3 events", "GET", "/explore/events/3",
         check=lambda d: d["status"] == "success")

    test("Day 7 events", "GET", "/explore/events/7",
         check=lambda d: d["status"] == "success")

    # ── 10. day end ──
    print("\n[10] Day end")
    print("-" * 40)
    test("end Day 1", "POST", "/explore/day-end",
         check=lambda d: d["data"]["day_completed"] == 1 and d["data"]["next_day"] == 2)

    # ── 11. craft: combine ──
    print("\n[11] Craft -- keyword combine")
    print("-" * 40)
    combine_data = test("combine 3 keywords", "POST", "/craft/combine",
                        json_body={"keyword_ids": [1, 14, 21]},
                        check=lambda d: d["status"] == "success" and "combination_id" in d["data"])

    # ── 12. craft: predict + grade feedback ──
    print("\n[12] Craft -- RGB predict + grade feedback")
    print("-" * 40)
    predict_data = None
    if combine_data:
        combo_id = combine_data["data"]["combination_id"]
        predict_data = test("predict (with feedback)", "POST", "/craft/predict",
                            json_body={
                                "combination_id": combo_id,
                                "predict_r": 60,
                                "predict_g": 70,
                                "predict_b": 50
                            },
                            check=lambda d: (d["status"] == "success"
                                             and "feedback" in d["data"]
                                             and "grade_message" in d["data"]["feedback"]
                                             and "accuracy" in d["data"]["feedback"]
                                             and "worst_channel" in d["data"]["feedback"]))
        if predict_data and "data" in predict_data and "feedback" in predict_data.get("data", {}):
            pd = predict_data["data"]
            fb = pd["feedback"]
            print(f"     grade: {pd['grade']} (distance: {pd['distance']})")
            print(f"     item : {pd['item_name']}")
            print(f"     desc : {pd['item_description']}")
            print(f"     ---- feedback ----")
            print(f"     {fb['grade_message']}")
            print(f"     accuracy : {fb['accuracy']}%")
            print(f"     worst ch : {fb['worst_channel']} / best ch: {fb['best_channel']}")
            if fb.get("hint"):
                print(f"     hint     : {fb['hint']}")
            if fb.get("direction_hints"):
                print(f"     direction : {', '.join(fb['direction_hints'])}")

    # ── 13. craft history ──
    print("\n[13] Craft history")
    print("-" * 40)
    hist = test("history list", "GET", "/craft/history",
                check=lambda d: d["status"] == "success")
    if hist and hist.get("data"):
        for h in hist["data"]:
            print(f"     [{h['grade']}] {h['generated_name']} (value: {h['final_value']})")

    # ── 14. recipe book ──
    print("\n[14] Recipe book")
    print("-" * 40)
    test("recipe book", "GET", "/craft/recipe-book",
         check=lambda d: d["status"] == "success")

    # ── 15. market: register ──
    print("\n[15] Market -- register item")
    print("-" * 40)
    _pd = predict_data.get("data", {}) if predict_data else {}
    item_name = _pd.get("item_name", "test item")
    final_value = _pd.get("final_value", 500.0)
    grade = _pd.get("grade", "B")

    market_data = test("register item", "POST", "/market/items",
                       json_body={
                           "item_name": item_name,
                           "keyword_ids": [1, 14, 21],
                           "grade": grade,
                           "base_value": final_value,
                           "stock": 10,
                           "release_day": 0
                       },
                       expected_status=201,
                       check=lambda d: d["status"] == "success")

    market_item_id = market_data["data"]["id"] if market_data else None

    if market_item_id:
        # ── 16. trend ──
        print("\n[16] Trend chart")
        print("-" * 40)
        test("30-day trend", "GET", f"/market/trend/{market_item_id}?days=30",
             check=lambda d: d["status"] == "success" and len(d["data"]["chart_data"]) == 30)

        # ── 17. buyer simulation ──
        print("\n[17] Buyer simulation")
        print("-" * 40)
        sim_data = test("60-day simulation", "GET",
                        f"/market/simulate/{market_item_id}?days=60&base_buyers=8",
                        check=lambda d: (d["status"] == "success"
                                         and "summary" in d["data"]
                                         and "daily_data" in d["data"]))
        if sim_data:
            s = sim_data["data"]["summary"]
            print(f"     total sold    : {s['total_sold']}")
            print(f"     total revenue : {s['total_revenue']} gold")
            print(f"     sellout day   : Day {s['sellout_day'] or 'N/A'}")
            print(f"     peak visitors : Day {s['peak_buyers_day']} ({s['peak_buyers_count']} visitors)")
            print(f"     ---- daily (first 5) ----")
            for dd in sim_data["data"]["daily_data"][:5]:
                bar_len = min(dd["buyers_visited"], 20)
                bar = "#" * bar_len + "." * (20 - bar_len)
                print(f"     Day {dd['day']:>3} [{bar}] "
                      f"visit={dd['buyers_visited']:>2}, "
                      f"sold={dd['units_sold']}, "
                      f"stock={dd['remaining_stock']}")

        # ── 18. price adjust ──
        print("\n[18] Price adjustment")
        print("-" * 40)
        new_price = round(final_value * 0.8, 1)
        price_data = test("20% price cut", "PATCH", "/market/price",
                          json_body={"item_id": market_item_id, "new_price": new_price},
                          check=lambda d: (d["status"] == "success"
                                           and d["data"]["new_price"] == new_price))
        if price_data:
            print(f"     {price_data['data']['message']}")

        # ── 19. sell ──
        print("\n[19] Sell")
        print("-" * 40)
        sell_data = test("sell 2 units (10% discount)", "POST", "/market/sell",
                         json_body={"item_id": market_item_id, "quantity": 2, "discount_rate": 0.1},
                         check=lambda d: d["status"] == "success" and d["data"]["remaining_stock"] == 8)
        if sell_data:
            print(f"     revenue   : {sell_data['data']['revenue']} gold")
            print(f"     remaining : {sell_data['data']['remaining_stock']}")

        # ── 20. sales analysis ──
        print("\n[20] Sales analysis (server + AI)")
        print("-" * 40)
        analysis = test("sales analysis", "POST", f"/market/analyze/{market_item_id}",
                        check=lambda d: d["status"] == "success" and "server_analysis" in d["data"])
        if analysis:
            sa = analysis["data"]["server_analysis"]
            print(f"     ---- server analysis ----")
            print(f"     score       : {sa['overall_score']}/100")
            print(f"     trend       : {sa['trend_status']}")
            print(f"     sell window : {sa['optimal_sell_window']}")
            for issue in sa.get("issues", []):
                print(f"     [!] [{issue['severity']}] {issue['message']}")
            for sug in sa.get("suggestions", []):
                print(f"     --> {sug}")

            ai = analysis["data"].get("ai_analysis")
            if ai:
                print(f"     ---- AI analysis ----")
                print(f"     summary  : {ai.get('summary', '-')}")
                print(f"     keyword  : {ai.get('keyword_analysis', '-')}")
                print(f"     timing   : {ai.get('timing_analysis', '-')}")
                print(f"     pricing  : {ai.get('price_analysis', '-')}")
                print(f"     advice   : {ai.get('next_action', '-')}")
                print(f"     AI score : {ai.get('score', '-')}/100")
            else:
                print("     (AI analysis skipped -- no API key or call failed)")

        # ── 21. settlement ──
        print("\n[21] Settlement")
        print("-" * 40)
        sett = test("season 1 settlement", "GET", "/market/settlement/1",
                    check=lambda d: d["status"] == "success" and d["data"]["total_revenue"] > 0)
        if sett:
            sd = sett["data"]
            print(f"     revenue    : {sd['total_revenue']}")
            print(f"     net profit : {sd['net_profit']}")
            print(f"     costs      : rent={sd['rent_cost']}, mgmt={sd['management_cost']}")

    # ── results ──
    print("\n" + "=" * 60)
    total = PASS + FAIL
    pct = int(PASS / total * 100) if total > 0 else 0
    bar_len = pct // 5
    bar = "#" * bar_len + "." * (20 - bar_len)
    print(f"  [{bar}] {pct}%")
    print(f"  total: {total} | [ OK ] {PASS} | [FAIL] {FAIL}")
    if FAIL == 0:
        print("  ** ALL TESTS PASSED **")
    else:
        print(f"  ** {FAIL} FAILED -- check logs above **")
    print("=" * 60)


if __name__ == "__main__":
    main()
