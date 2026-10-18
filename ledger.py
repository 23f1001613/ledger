"""Fetch and normalize the Acme Appliances order ledger."""

from __future__ import annotations

import json
import os
import urllib.request
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

DEFAULT_BASE_URL = (
    "https://exam.sanand.workers.dev/questionData"
    "?email=23f1001613%40ds.study.iitm.ac.in"
    "&quizSign=FUIbr4Obif%2B4Mi8i8s06ozyDxu4MtoGZjdPWO5t9ADPoQ7j%2BXjNmxag5UZYZfl8puja2"
    "%2BJAZTCTr1hhphEDybQ%2Ber9NBbCjo1%2BaRCC0rTWkg3%2FM30gQSRMP4na%2BbUFPQTNlwOHjoqrEreo7g7fGIXHhqjfwbS"
    "%2FMMlgG5SllUVRgvFHt6S%2B8PY5Jg0OrubdkKQcg6zNfsmI4gFciM%2BDU5s3hOerV3q21EvNc%2FfvMNArrHgELYfWiDpAbvQauu6dU1rsWl8KXENcSlT0zaMKPp1HG5ASJfeNqmON1xmExK8Y6kELOr%2B6OArDdphlShPUPQj581E3oVQoCl3f20vg8e0g%3D%3D"
    "&questionId=q-ledger-agent-server"
)

IST = ZoneInfo("Asia/Kolkata")


@dataclass(frozen=True)
class Order:
    id: str
    customer: str
    region: str
    product: str
    qty: int
    amount: Decimal
    currency: str
    status: str
    created_at: datetime
    updated_at: datetime
    amount_usd: Decimal
    year: int
    month: int


def _http_get(url: str) -> bytes:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "ledger-agent-server/1.0", "Accept": "*/*"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read()


def _api_url(base: str, path: str) -> str:
    # path like "/export" or "/rates"
    from urllib.parse import quote

    sep = "&" if "?" in base else "?"
    return f"{base}{sep}path={quote(path)}"


def fetch_rates(base_url: str) -> dict[str, Decimal]:
    raw = json.loads(_http_get(_api_url(base_url, "/rates")))
    return {k: Decimal(str(v)) for k, v in raw["usd_per_unit"].items()}


def fetch_export_rows(base_url: str) -> list[dict[str, Any]]:
    text = _http_get(_api_url(base_url, "/export")).decode("utf-8")
    rows: list[dict[str, Any]] = []
    for line in text.splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def _parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def dedupe_latest(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    best: dict[str, dict[str, Any]] = {}
    for row in rows:
        oid = row["id"]
        prev = best.get(oid)
        if prev is None or row["updated_at"] > prev["updated_at"]:
            best[oid] = row
    return list(best.values())


def normalize_orders(
    rows: list[dict[str, Any]], rates: dict[str, Decimal]
) -> list[Order]:
    orders: list[Order] = []
    for row in dedupe_latest(rows):
        created = _parse_dt(row["created_at"])
        updated = _parse_dt(row["updated_at"])
        local = created.astimezone(IST)
        currency = row["currency"]
        amount = Decimal(str(row["amount"]))
        rate = rates[currency]
        orders.append(
            Order(
                id=row["id"],
                customer=row["customer"],
                region=row["region"],
                product=row["product"],
                qty=int(row["qty"]),
                amount=amount,
                currency=currency,
                status=row["status"],
                created_at=created,
                updated_at=updated,
                amount_usd=amount * rate,
                year=local.year,
                month=local.month,
            )
        )
    return orders


class LedgerStore:
    def __init__(self) -> None:
        self.orders: list[Order] = []
        self.rates: dict[str, Decimal] = {}
        self.products: list[str] = []
        self.regions: list[str] = []
        self.ready: bool = False
        self.error: str | None = None

    def load(self, base_url: str | None = None) -> None:
        base = (base_url or os.environ.get("LEDGER_BASE_URL") or DEFAULT_BASE_URL).rstrip(
            "&"
        )
        try:
            self.rates = fetch_rates(base)
            rows = fetch_export_rows(base)
            self.orders = normalize_orders(rows, self.rates)
            self.products = sorted({o.product for o in self.orders})
            self.regions = sorted({o.region for o in self.orders})
            self.ready = True
            self.error = None
        except Exception as exc:  # noqa: BLE001 — surface load failures in /health
            self.ready = False
            self.error = str(exc)
            raise


STORE = LedgerStore()
