"""Local checks against a running server (default http://127.0.0.1:8080)."""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from zoneinfo import ZoneInfo

from ledger import DEFAULT_BASE_URL, fetch_export_rows, fetch_rates, normalize_orders

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8080"
IST = ZoneInfo("Asia/Kolkata")
MONEY = Decimal("0.01")


def post_ask(question: str) -> tuple[int, dict | None]:
    data = json.dumps({"question": question}).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE.rstrip('/')}/ask",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode())
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode()
        try:
            return exc.code, json.loads(raw) if raw else None
        except json.JSONDecodeError:
            return exc.code, {"raw": raw}


def expected_north_march_revenue() -> float:
    rates = fetch_rates(DEFAULT_BASE_URL)
    orders = normalize_orders(fetch_export_rows(DEFAULT_BASE_URL), rates)
    total = Decimal("0")
    for o in orders:
        if o.status != "paid" or o.region != "North":
            continue
        if o.year != 2026 or o.month != 3:
            continue
        total += o.amount_usd
    return float(total.quantize(MONEY, rounding=ROUND_HALF_UP))


def expected_top_product_west() -> str:
    rates = fetch_rates(DEFAULT_BASE_URL)
    orders = normalize_orders(fetch_export_rows(DEFAULT_BASE_URL), rates)
    buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for o in orders:
        if o.status == "paid" and o.region == "West":
            buckets[o.product] += o.amount_usd
    return max(buckets.items(), key=lambda kv: (kv[1], kv[0]))[0]


def expected_distinct_toaster_customers() -> int:
    rates = fetch_rates(DEFAULT_BASE_URL)
    orders = normalize_orders(fetch_export_rows(DEFAULT_BASE_URL), rates)
    return len({o.customer for o in orders if o.status == "paid" and o.product == "Toaster"})


def main() -> None:
    failures = 0
    want_rev = expected_north_march_revenue()
    want_prod = expected_top_product_west()
    want_customers = expected_distinct_toaster_customers()

    cases = [
        (
            "What was the total revenue in USD from the North region in March 2026?",
            want_rev,
        ),
        (
            "North region March 2026 total sales in USD?",
            want_rev,
        ),
        (
            "How much revenue did North generate during Mar 2026?",
            want_rev,
        ),
        (
            "Which product had the highest paid revenue in the West region?",
            want_prod,
        ),
        (
            "Top product by revenue in West",
            want_prod,
        ),
        (
            "How many different customers placed at least one paid order for a Toaster?",
            want_customers,
        ),
        (
            "Number of unique customers with a paid Toaster order",
            want_customers,
        ),
    ]

    for question, expected in cases:
        status, body = post_ask(question)
        got = None if not body else body.get("answer")
        ok = status == 200 and got == expected
        label = "OK" if ok else "FAIL"
        print(f"{label}: {question!r}")
        print(f"     got={got!r} expected={expected!r} status={status}")
        if not ok:
            failures += 1

    # Refund sanity: number type, not error
    status, body = post_ask(
        "What was the total refund amount in USD for the South region in January 2026?"
    )
    if status != 200 or not isinstance(body, dict) or not isinstance(body.get("answer"), (int, float)):
        print(f"FAIL refund probe: {status} {body}")
        failures += 1
    else:
        print(f"OK refund probe -> {body['answer']}")

    if failures:
        print(f"\n{failures} check(s) failed")
        sys.exit(1)
    print("\nAll local checks passed.")


if __name__ == "__main__":
    main()
