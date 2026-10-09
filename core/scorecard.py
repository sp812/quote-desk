"""Vendor scorecard: price, quality, delivery, commercial terms and coverage, each scored 0-100 by code.

The award itself follows the RFQ rule (lowest landed price per line among qualified, on-spec vendors).
The scorecard is a second lens for approvers: who is strong overall, and what the trade-offs are.
Every score is a formula the buyer can read, not a model's opinion."""
from __future__ import annotations

from .extract import load_rfx_lines, load_questionnaire
from .normalize import num

REQUESTED_PAYMENT_DAYS = 45      # RFQ asks for 45 days from GRN
MAX_LEAD_TIME_DAYS = 10          # questionnaire Q6 limit
PRICE_POINTS_PER_PCT = 5         # each 1% above the cheapest like-for-like price costs 5 points (20% above scores 0)

DIMENSIONS = {
    "price": "Price: the vendor's on-spec quoted items at their landed price, against the lowest on-spec landed price any vendor offered "
             "for the same items, weighted by annual quantity. 100 = cheapest on everything it quoted; each 1% above the cheapest costs "
             f"{PRICE_POINTS_PER_PCT} points, so 20% above scores 0.",
    "quality": "Quality: share of mandatory questionnaire answers that pass (an unclear answer counts half). "
               "Any failed mandatory answer means the vendor can't be awarded under the RFQ rule.",
    "delivery": f"Delivery: lead time against the {MAX_LEAD_TIME_DAYS}-day limit. 100 at or under the limit, 10 points off per extra day, "
                "50 if not stated.",
    "commercial": f"Commercial: payment terms against the {REQUESTED_PAYMENT_DAYS} days requested. 100 at or above, pro rata below, "
                  "50 if not stated.",
    "coverage": "Coverage: share of the 30 RFQ items the vendor priced. A vendor that covers more items reduces the number of suppliers to manage.",
}
DEFAULT_WEIGHTS = {"price": 40, "quality": 25, "delivery": 15, "commercial": 10, "coverage": 10}


def _rank(vals: dict) -> dict:
    order = sorted(vals, key=lambda k: -vals[k])
    return {k: i + 1 for i, k in enumerate(order)}


def build(st, weights: dict | None = None) -> list[dict]:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    wsum = sum(w.values()) or 1
    lines = {l["line_id"]: int(l["annual_qty"]) for l in load_rfx_lines()}
    mandatory = [q["q_id"] for q in load_questionnaire() if q["type"].lower() == "mandatory"]
    best: dict[str, float] = {}
    for n in st.norms:   # cheapest like-for-like (on-spec) landed price per item, across all vendors
        if n.status != "missing" and n.landed is not None and n.spec_compliant:
            best[n.line_id] = min(best.get(n.line_id, n.landed), n.landed)
    out = []
    for v, ex in st.extractions.items():
        ns = [n for n in st.norms if n.vendor == v and n.status != "missing" and n.landed is not None]
        like = [n for n in ns if n.spec_compliant and n.line_id in best]
        own = sum(n.landed * lines.get(n.line_id, 0) for n in like)
        ref = sum(best[n.line_id] * lines.get(n.line_id, 0) for n in like)
        premium = (own / ref - 1) if ref else None
        price = round(max(0.0, 100 - 100 * PRICE_POINTS_PER_PCT * premium), 1) if premium is not None else 0.0

        res = st.q_evals.get(v, {}).get("results", {})
        pts = sum({"pass": 1, "unclear": .5}.get(res.get(q, {}).get("status"), 0) for q in mandatory)
        quality = round(100 * pts / len(mandatory), 1) if (mandatory and res) else 0.0
        failed = [q for q in mandatory if res.get(q, {}).get("status") == "fail"]

        t = ex.get("terms", {}) or {}
        lt = num(t.get("lead_time_days"))
        delivery = 50.0 if lt is None else float(max(0, min(100, 100 - (float(lt) - MAX_LEAD_TIME_DAYS) * 10)))
        pdays = num(t.get("payment_days"))
        commercial = 50.0 if pdays is None else round(min(100, 100 * float(pdays) / REQUESTED_PAYMENT_DAYS), 1)
        coverage = round(100 * len(ns) / len(lines), 1)

        confident = sum(1 for n in ns if n.status == "ok" and n.spec_compliant)
        scores = dict(price=price, quality=quality, delivery=delivery, commercial=commercial, coverage=coverage)
        total = round(sum(scores[k] * w[k] for k in scores) / wsum, 1)
        out.append(dict(vendor=v, vendor_name=st.vendor_names[v], status=st.status.get(v), **scores, total=total,
                        price_premium=premium, items_priced=len(ns), failed_mandatory=failed,
                        lead_time_days=lt, payment_days=pdays,
                        lower_spec_items=sum(1 for n in ns if not n.spec_compliant),
                        read_confidently=confident, eligible=v in st.eligible))
    ranks = _rank({r["vendor"]: r["total"] for r in out})
    for r in out:
        r["rank"] = ranks[r["vendor"]]
    return sorted(out, key=lambda r: r["rank"])
