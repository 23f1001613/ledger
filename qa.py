"""Parse plain-English ledger questions and compute answers."""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

from ledger import Order, STORE

MONEY_QUANT = Decimal("0.01")

MONTHS = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}


@dataclass
class Intent:
    metric: str
    region: str | None = None
    product: str | None = None
    customer: str | None = None
    status: str | None = None
    year: int | None = None
    month: int | None = None
    rank_by: str = "revenue"  # revenue | units


def money(value: Decimal) -> float:
    return float(value.quantize(MONEY_QUANT, rounding=ROUND_HALF_UP))


def _find_product(q: str, products: list[str]) -> str | None:
    # Longest match first so "Rice Cooker" beats partials.
    for name in sorted(products, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", q, flags=re.IGNORECASE):
            return name
    return None


def _find_region(q: str, regions: list[str]) -> str | None:
    for name in sorted(regions, key=len, reverse=True):
        if re.search(rf"\b{re.escape(name)}\b", q, flags=re.IGNORECASE):
            return name
    return None


def _find_customer(q: str) -> str | None:
    m = re.search(r"\b(C\d{3,})\b", q, flags=re.IGNORECASE)
    return m.group(1).upper() if m else None


def _find_month(q: str) -> int | None:
    for name, num in MONTHS.items():
        if re.search(rf"\b{name}\b", q, flags=re.IGNORECASE):
            return num
    m = re.search(r"\b(20\d{2})[-/](0?[1-9]|1[0-2])\b", q)
    if m:
        return int(m.group(2))
    return None


def _find_year(q: str) -> int | None:
    m = re.search(r"\b(20\d{2})\b", q)
    return int(m.group(1)) if m else None


def parse_question(question: str) -> Intent:
    q = question.strip()
    ql = q.lower()

    products = STORE.products or [
        "Air Fryer",
        "Blender",
        "Grinder",
        "Juicer",
        "Kettle",
        "Mixer",
        "Rice Cooker",
        "Toaster",
    ]
    regions = STORE.regions or ["North", "South", "East", "West", "Central"]

    region = _find_region(q, regions)
    product = _find_product(q, products)
    customer = _find_customer(q)
    month = _find_month(q)
    year = _find_year(q)

    status: str | None = None
    if re.search(r"\bvoid(ed)?\b", ql):
        status = "void"
    elif re.search(r"\brefund", ql) or re.search(r"\breturned?\b", ql):
        status = "refunded"
    elif re.search(r"\bpaid\b", ql):
        status = "paid"

    rank_by = "units" if re.search(r"\b(units?|quantity|qty|volume)\b", ql) else "revenue"

    # Metric detection (order matters).
    if re.search(
        r"\b(which|what)\b.*\b(product|item)\b|\btop\b.*\bproduct\b|"
        r"\bbest[- ]?sell|\bmost\b.*\b(sold|revenue|sales)\b.*\bproduct\b|"
        r"\bhighest[- ]selling\b|\bproduct\b.*\b(most|highest)\b",
        ql,
    ):
        metric = "top_product"
    elif re.search(
        r"\b(which|what|who)\b.*\bcustomer\b|\btop\b.*\bcustomer\b|"
        r"\bcustomer\b.*\b(most|highest|spent|spend|revenue)\b|"
        r"\bhighest[- ]spending\b",
        ql,
    ):
        metric = "top_customer"
    elif re.search(r"\baverage\b|\bavg\b|\bmean\b", ql) and re.search(
        r"\b(order|revenue|sale|value|aov)\b", ql
    ):
        metric = "avg_order_value"
    elif re.search(
        r"\b(how many|number of|count of|# of)\b.*\b(different |unique |distinct )?customers?\b|"
        r"\b(different|unique|distinct)\s+customers?\b|"
        r"\bcustomers?\b.*\b(how many|number|count)\b",
        ql,
    ):
        metric = "distinct_customers"
    elif (
        re.search(r"\bhow many\b|\bnumber of\b|\bcount of\b|\border count\b|\b# of\b", ql)
        or (
            re.search(r"\bcount\b", ql)
            and re.search(r"\border", ql)
            and not re.search(r"\brevenue\b|\bsales?\b|\bamount\b", ql)
        )
    ) and (
        re.search(r"\border", ql)
        or (status is not None and not product)
    ):
        metric = "order_count"
    elif re.search(
        r"\bunits?\b|\bquantity\b|\bqty\b|\bsold\b|\bhow many\b",
        ql,
    ) and not re.search(
        r"\brevenue\b|\bsales?\b|\bearnings?\b|\btotal (in )?usd\b|\bamount\b",
        ql,
    ):
        metric = "units_sold"
    elif status == "refunded" or re.search(r"\brefund", ql):
        metric = "total_refunds"
    else:
        # Default: money total for paid revenue / sales.
        metric = "total_revenue"

    # For revenue questions, force paid unless status was explicitly named as void.
    if metric == "total_revenue" and status not in ("void", "refunded"):
        status = "paid"
    if metric == "total_refunds":
        status = "refunded"
    if metric in ("units_sold", "avg_order_value", "distinct_customers") and status is None:
        status = "paid"
    if metric in ("top_product", "top_customer") and status is None:
        status = "paid"

    return Intent(
        metric=metric,
        region=region,
        product=product,
        customer=customer,
        status=status,
        year=year,
        month=month,
        rank_by=rank_by,
    )


def filter_orders(orders: list[Order], intent: Intent) -> list[Order]:
    out: list[Order] = []
    for o in orders:
        if intent.region and o.region.lower() != intent.region.lower():
            continue
        if intent.product and o.product.lower() != intent.product.lower():
            continue
        if intent.customer and o.customer.upper() != intent.customer.upper():
            continue
        if intent.status and o.status != intent.status:
            continue
        if intent.year is not None and o.year != intent.year:
            continue
        if intent.month is not None and o.month != intent.month:
            continue
        out.append(o)
    return out


def answer_question(question: str) -> Any:
    if not STORE.ready:
        raise RuntimeError(STORE.error or "Ledger not loaded")

    intent = parse_question(question)
    rows = filter_orders(STORE.orders, intent)

    if intent.metric == "total_revenue":
        total = sum((o.amount_usd for o in rows), Decimal("0"))
        return money(total)

    if intent.metric == "total_refunds":
        total = sum((o.amount_usd for o in rows), Decimal("0"))
        return money(total)

    if intent.metric == "order_count":
        return len(rows)

    if intent.metric == "distinct_customers":
        return len({o.customer for o in rows})

    if intent.metric == "units_sold":
        return sum(o.qty for o in rows)

    if intent.metric == "avg_order_value":
        if not rows:
            return 0.0
        total = sum((o.amount_usd for o in rows), Decimal("0"))
        return money(total / Decimal(len(rows)))

    if intent.metric == "top_product":
        buckets: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
        if intent.rank_by == "units":
            for o in rows:
                buckets[o.product] += Decimal(o.qty)
        else:
            for o in rows:
                buckets[o.product] += o.amount_usd
        if not buckets:
            return ""
        # Tie-break: alphabetical product name for stability.
        return max(buckets.items(), key=lambda kv: (kv[1], kv[0]))[0]

    if intent.metric == "top_customer":
        buckets = defaultdict(lambda: Decimal("0"))
        if intent.rank_by == "units":
            for o in rows:
                buckets[o.customer] += Decimal(o.qty)
        else:
            for o in rows:
                buckets[o.customer] += o.amount_usd
        if not buckets:
            return ""
        return max(buckets.items(), key=lambda kv: (kv[1], kv[0]))[0]

    raise ValueError(f"Unknown metric: {intent.metric}")
