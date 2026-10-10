"""Deterministic normalization: vendor's words -> INR per RFx unit, ex-GST, landed at Waluj.

Every transformation appends a human-readable step, and every assumption raises a flag.
Unresolved ambiguities keep ALL candidate values; the default used for awarding is the
vendor's least favourable reading (we never award on a number we could not read).
"""
from __future__ import annotations
import csv
import re
import statistics
from dataclasses import dataclass, field, asdict

from .config import RECORDS, GST_RATE, USD_INR, USD_INR_SOURCE, FREIGHT_LANE_HINTS
from .extract import load_rfx_lines


def num(x) -> float | None:
    """Tolerant number parse: 38.93, '38.93', 'Rs. 3,893', '₹62.50' -> float."""
    if x is None or isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"-?\d[\d,]*\.?\d*", str(x))
    return float(m.group(0).replace(",", "")) if m else None


def inr(x: float | None) -> str:
    return "-" if x is None else f"₹{x:,.2f}"


@dataclass
class Flag:
    type: str            # illegible | unit | spec | history | missing | freight | fx | gst | outlier | mapping | low_conf | discount
    severity: str        # info | warn | critical
    text: str
    group: str | None = None   # shared id for issues that should be resolved together


@dataclass
class NormQuote:
    vendor: str
    vendor_name: str
    line_id: str
    status: str = "ok"                      # ok | review | missing
    candidates: list[dict] = field(default_factory=list)   # [{label, base, landed}]
    selected: int | None = None
    landed: float | None = None
    base: float | None = None
    freight: float = 0.0
    spec_compliant: bool = True
    steps: list[str] = field(default_factory=list)
    flags: list[Flag] = field(default_factory=list)
    source: str = ""
    source_quote: str = ""
    vendor_item_text: str = ""
    confidence: float | None = None
    group: str | None = None
    resolved_by_buyer: bool = False
    awardable: bool = True                  # False = shown, but kept out of the award until the buyer acts
    spec_accepted: bool = False             # lower spec, accepted by the buyer as a substitute (logged)
    block_group: str | None = None          # issue id that, when accepted by the buyer, makes it awardable

    def to_dict(self):
        d = asdict(self)
        return d


def load_fy26() -> dict:
    out = {}
    with open(RECORDS / "fy26_contract_prices.csv") as f:
        for r in csv.DictReader(f):
            out[r["line_id"]] = r
    return out


def load_freight() -> dict:
    with open(RECORDS / "freight_benchmarks.csv") as f:
        return {r["lane"]: float(r["inr_per_kg"]) for r in csv.DictReader(f)}


def canon_currency(c) -> str:
    """'Rs.', 'INR/-', '₹', 'rupees', '' -> INR; 'US$', '$', 'usd' -> USD; anything else upper-cased as given."""
    t = str(c or "").strip().upper()
    letters = "".join(ch for ch in t if ch.isalpha())
    if "$" in t and "₹" not in t:
        return "USD"
    if not letters and ("₹" in t or not t):
        return "INR"
    if letters in ("INR", "RS", "RUPEES", "RUPEE", "UNSTATED", "NONE", "NA", "") or "₹" in t or letters.startswith("INR"):
        return "INR"
    if letters in ("USD", "US", "USDOLLAR", "USDOLLARS", "DOLLAR", "DOLLARS") or t in ("$", "US$"):
        return "USD"
    return letters or t


def lane_for(location: str) -> str | None:
    loc = (location or "").lower()
    for k, lane in FREIGHT_LANE_HINTS.items():
        if k in loc:
            return lane
    return None


def strips_per_set(line: dict) -> int | None:
    m = re.search(r"set of (\d+)", line["dimensions_mm"]) or re.search(r"\((\d+) long \+ (\d+) short\)", line["description"])
    if not m:
        return None
    return int(m.group(1)) if len(m.groups()) == 1 else int(m.group(1)) + int(m.group(2))


def _vendor_matches(fy26_vendor: str, vendor_name: str) -> bool:
    a = fy26_vendor.lower().split()
    b = vendor_name.lower().split()
    return bool(a) and bool(b) and a[0] == b[0]


def normalize_vendor(vkey: str, ex: dict, decisions: dict) -> list[NormQuote]:
    lines = {l["line_id"]: l for l in load_rfx_lines()}
    fy26 = load_fy26()
    freight_rates = load_freight()
    terms = ex.get("terms") if isinstance(ex.get("terms"), dict) else {}
    vname = ex.get("vendor_name", vkey)
    out: list[NormQuote] = []

    # vendor-level freight
    fr_mode = terms.get("freight", "unclear")
    lane = lane_for(ex.get("vendor_location", ""))
    unconditional = [dict(d, percent=num(d.get("percent")) or 0) for d in (ex.get("discounts") or [])
                     if "unconditional" in str(d.get("condition", "")).lower()]

    quoted = {q["rfx_line_id"]: q for q in ex.get("line_quotes", [])}
    for lid, line in lines.items():
        nq = NormQuote(vendor=vkey, vendor_name=vname, line_id=lid)
        q = quoted.get(lid)
        if not q:
            miss = next((m for m in ex.get("lines_not_quoted", []) if m["rfx_line_id"] == lid), None)
            nq.status = "missing"
            nq.flags.append(Flag("missing", "warn", f"Not quoted: {miss['reason'] if miss else 'not mentioned'}"))
            nq.source = (miss or {}).get("source", "")
            out.append(nq)
            continue
        nq.source, nq.source_quote = q.get("source", ""), q.get("source_quote", "")
        nq.vendor_item_text, nq.confidence = q.get("vendor_item_text", ""), q.get("confidence")
        raw = [v for v in (num(c) for c in (q.get("price_candidates") or [])) if v is not None]
        cands = [v for v in raw if v > 0]
        if raw and not cands:
            nq.flags.append(Flag("missing", "critical", f"Price read as {raw[0]:g}: a zero or negative price is not a price. Ask the vendor."))
        cur = canon_currency(q.get("currency") or terms.get("currency"))
        unit = q.get("price_unit", "per_piece")
        wt = float(line["target_weight_kg"])
        nq.steps.append(f"Vendor wrote: '{q.get('source_quote','')}' ({q.get('unit_as_written','')}) at {q.get('source','')}")

        # ---- price by reference to last year
        if q.get("references_history") and not cands:
            rec = fy26.get(lid)
            if rec and rec.get("fy26_unit_price") and _vendor_matches(rec.get("fy26_vendor", ""), vname):
                cands = [float(rec["fy26_unit_price"])]
                cur = canon_currency(rec["currency"])
                unit = "per_set" if line["uom"] == "set" else "per_piece"
                nq.steps.append(f"'Same as last year' -> FY26 contract price {rec['currency']} {rec['fy26_unit_price']} from buyer records")
                nq.flags.append(Flag("history", "warn", "Price taken from FY26 contract because vendor wrote 'same as last year'. Not confirmed by vendor for FY27.",
                                     group=f"{vkey}|history"))
            else:
                nq.status = "missing"
                nq.flags.append(Flag("history", "critical", "Vendor wrote 'same as last year' but they did not supply this line last year. Price is unknowable - ask the vendor.",
                                     group=f"{vkey}|history-unknown"))
                out.append(nq)
                continue

        if not cands:
            nq.status = "review"
            nq.flags.append(Flag("missing", "critical", "Line mentioned but no readable price."))
            out.append(nq)
            continue

        # ---- unit conversion -> list of (label, value in vendor currency per RFx uom)
        variants: list[tuple[str, float]] = []
        sps = strips_per_set(line) if line["uom"] == "set" else None
        for c in cands:
            if unit in ("per_piece", "per_set", "per_metre"):
                if line["uom"] == "set" and unit == "per_piece" and sps:
                    variants.append((f"{c:g} if 'per pc' means a full set", c))
                    variants.append((f"{c:g} x {sps} strips if 'per pc' means one strip", c * sps))
                    nq.flags.append(Flag("unit", "critical", f"Vendor priced 'per pc' but the RFx buys a set of {sps} strips. Reading differs {sps}x.",
                                         group=f"{vkey}|unit|{lid}"))
                else:
                    variants.append((f"{c:g} per {line['uom']}", c))
                    if unit == "per_metre":
                        nq.steps.append("Per-metre price; RFx piece is 1000 mm, so 1 metre = 1 piece")
            elif unit == "per_strip" and sps:
                variants.append((f"{c:g} x {sps} strips", c * sps))
                nq.steps.append(f"Per strip x {sps} strips per set")
            elif unit == "per_pack":
                pk = num(q.get("pack_size"))
                if pk and pk > 0:
                    variants.append((f"{c:g} / pack of {pk:g}", c / pk))
                    nq.steps.append(f"Price per pack of {pk:g} -> divided by {pk:g}")
                else:
                    nq.flags.append(Flag("unit", "critical", f"Priced per pack ('{q.get('unit_as_written')}') but the pack size is not stated. Ask the vendor."))
            elif unit == "per_100":
                variants.append((f"{c:g} / 100", c / 100))
            elif unit == "per_1000":
                variants.append((f"{c:g} / 1000", c / 1000))
            elif unit == "per_kg":
                v = c * wt
                label = f"{c:g}/kg x {wt} kg"
                for a in q.get("adders") or []:
                    v += num(a.get("amount")) or 0; label += f" + {a.get('amount')} ({a.get('reason','adder')})"
                variants.append((label, v))
            else:
                nq.flags.append(Flag("unit", "critical", f"Unit '{q.get('unit_as_written')}' cannot be converted automatically."))
        if unit == "per_kg":
            nq.steps.append(f"Per-kg rate converted with buyer-spec box weight {wt} kg (vendor: 'box wt as per spec')")
            nq.flags.append(Flag("unit", "info", f"Per-kg price depends on box weight; used RFx target weight {wt} kg.", group=f"{vkey}|weight"))
        if unit == "per_100":
            nq.steps.append("Rate per 100 nos -> divided by 100")
        if q.get("unit_ambiguous") and not any(f.type == "unit" and f.severity == "critical" for f in nq.flags):
            nq.flags.append(Flag("unit", "warn", f"Unit wording may be ambiguous: {q.get('notes') or q.get('unit_as_written')}"))
        if not variants:
            nq.status = "review"
            out.append(nq)
            continue

        # ---- GST
        gst_inc = q.get("gst_included")
        if gst_inc is None:
            gst_inc = {"included": True, "extra": False}.get(terms.get("gst"), None)
        if gst_inc:
            variants = [(lbl + f" / {1+GST_RATE:.2f} (GST incl.)", v / (1 + GST_RATE)) for lbl, v in variants]
            nq.steps.append(f"Price stated inclusive of GST -> divided by {1+GST_RATE:.2f}")
            nq.flags.append(Flag("gst", "info", "Quoted GST-inclusive; GST removed for like-for-like comparison."))
        elif gst_inc is None:
            nq.flags.append(Flag("gst", "warn", "GST treatment not stated; assumed exclusive."))

        # ---- FX
        if cur == "USD":
            rate = num(decisions.get("usd_inr")) or USD_INR
            basis = "rate set by the buyer" if rate != USD_INR else USD_INR_SOURCE
            variants = [(lbl + f" x {rate:g} INR/USD", v * rate) for lbl, v in variants]
            nq.steps.append(f"USD converted at {rate:g} INR/USD ({basis})")
            nq.flags.append(Flag("fx", "warn", f"Quoted in USD; converted at {rate:g} ({basis}). A 3% rupee move shifts this price ~3%.", group=f"{vkey}|fx"))
        elif cur != "INR":
            nq.flags.append(Flag("fx", "critical", f"Quoted in {cur}, which has no reference rate here. Not converted and kept out of "
                                                   f"the award; ask the vendor for an INR price.", group=f"{vkey}|currency"))
            nq.steps.append(f"Quoted {' or '.join(f'{v:g}' for _, v in variants)} {cur} per {line['uom']}: no INR reference rate, not converted")
            nq.status, nq.awardable = "review", False
            out.append(nq)
            continue

        # ---- unconditional discounts
        for d in unconditional:
            variants = [(lbl + f" less {d['percent']}%", v * (1 - d["percent"] / 100)) for lbl, v in variants]
            nq.steps.append(f"Unconditional discount {d['percent']}% applied ({d.get('source','')})")

        # ---- freight
        if fr_mode in ("included_delivered", "free_local"):
            nq.freight = 0.0
            nq.steps.append("Freight included / free delivery to Waluj")
        elif lane and lane in freight_rates:
            nq.freight = round(freight_rates[lane] * wt, 2)
            nq.steps.append(f"Freight not included -> estimated {lane} @ ₹{freight_rates[lane]}/kg x {wt} kg = {inr(nq.freight)}")
            nq.flags.append(Flag("freight", "warn", f"Freight estimated from buyer benchmark ({lane}); vendor said '{fr_mode.replace('_',' ')}'.",
                                 group=f"{vkey}|freight"))
        else:
            nq.flags.append(Flag("freight", "critical", f"Freight is extra but there is no rate-card lane from "
                                                        f"'{ex.get('vendor_location') or 'unknown origin'}'. Landed cost unknown, so kept out of the award; "
                                                        f"ask the vendor for a delivered price.", group=f"{vkey}|freight-unknown"))
            nq.awardable = False
            nq.status = "review"

        nq.candidates = [{"label": lbl, "base": round(v, 2), "landed": round(v + nq.freight, 2)} for lbl, v in variants]

        # ---- uncertainty
        if len(cands) > 1:
            gid = f"{vkey}|{q.get('ambiguity_id') or 'illegible-' + lid}"
            nq.group = gid
            nq.flags.append(Flag("illegible", "critical",
                                 f"Value could be read as {' or '.join(f'{c:g}' for c in cands)} ({q.get('source','')}). Not guessed.", group=gid))
        elif any(f.type == "unit" and f.severity == "critical" for f in nq.flags):
            nq.group = next(f.group for f in nq.flags if f.type == "unit" and f.severity == "critical")
        if (num(q.get("confidence")) or 1) < 0.8 and len(cands) == 1:
            nq.flags.append(Flag("low_conf", "warn", f"Extraction confidence {q.get('confidence')}: verify against source."))
        if (num(q.get("mapping_confidence")) or 1) < 0.7:
            nq.flags.append(Flag("mapping", "warn", f"Mapped '{q.get('vendor_item_text')}' to {lid} with confidence {q.get('mapping_confidence')}."))
        if q.get("spec_deviation"):
            nq.spec_compliant = False
            nq.flags.append(Flag("spec", "critical", f"Spec deviation: {q['spec_deviation']}", group=f"{vkey}|spec"))
            why = decisions.get("accepted", {}).get(f"{vkey}|spec")
            if why:
                nq.spec_accepted = True
                nq.steps.append(f"Buyer accepted the lower spec as a substitute: {why}")

        # ---- selection: buyer choice, else least favourable
        choice = decisions.get("choices", {}).get(nq.group) if nq.group else None
        if choice is not None and choice < len(nq.candidates):
            nq.selected, nq.resolved_by_buyer = choice, True
            nq.steps.append(f"Buyer resolved: using '{nq.candidates[choice]['label']}'")
        else:
            nq.selected = max(range(len(nq.candidates)), key=lambda i: nq.candidates[i]["landed"])
            if len(nq.candidates) > 1:
                nq.steps.append("Unresolved: evaluated at vendor's least favourable reading until confirmed")
        nq.base = nq.candidates[nq.selected]["base"]
        nq.landed = nq.candidates[nq.selected]["landed"]
        nq.steps.append(f"Landed at Waluj, ex-GST: {inr(nq.landed)} per {line['uom']}")
        if len(nq.candidates) > 1 and not nq.resolved_by_buyer:
            nq.status = "review"
        out.append(nq)
    return out


TOO_LOW = -0.5   # a price more than 50% below the other vendors' median is held out of the award until the buyer accepts it


def peer_check(all_norm: list[NormQuote], decisions: dict | None = None) -> None:
    """Independent sanity check: compare every candidate with the other vendors' prices for the line."""
    by_line: dict[str, list[NormQuote]] = {}
    for n in all_norm:
        by_line.setdefault(n.line_id, []).append(n)
    for lid, ns in by_line.items():
        for n in ns:
            peers = [p.landed for p in ns if p is not n and p.landed is not None and p.spec_compliant]
            if len(peers) < 2 or n.landed is None:
                continue
            med = statistics.median(peers)
            notes = []
            for c in n.candidates:
                dev = (c["landed"] - med) / med
                notes.append((c, dev))
            sel_dev = (n.landed - med) / med
            if sel_dev < TOO_LOW and n.awardable:
                g = f"{n.vendor}|outlier|{n.line_id}"
                if g in (decisions or {}).get("accepted", {}):
                    n.steps.append(f"Buyer accepted this price although it is {sel_dev:+.0%} vs other vendors: "
                                   f"{(decisions or {})['accepted'][g]}")
                else:
                    n.flags.append(Flag("outlier", "critical", f"{sel_dev:+.0%} vs the other vendors' median {inr(med)}: too good to be "
                                                               f"true until confirmed (often a unit or reading error). Kept out of the award.", group=g))
                    n.awardable, n.block_group = False, g
            elif abs(sel_dev) > 0.30:
                n.flags.append(Flag("outlier", "warn", f"{sel_dev:+.0%} vs peer median {inr(med)}. Check unit/reading."))
            if len(n.candidates) > 1:
                desc = "; ".join(f"'{c['label']}' -> {inr(c['landed'])} ({d:+.0%} vs peers)" for c, d in notes)
                n.steps.append(f"Peer check (median of other vendors {inr(med)}): {desc}")


def normalize_all(extractions: dict[str, dict], decisions: dict) -> list[NormQuote]:
    out = []
    for vkey, ex in extractions.items():
        out += normalize_vendor(vkey, ex, decisions)
    peer_check(out, decisions)
    return out


def conditional_discounts(extractions: dict[str, dict]) -> dict[str, list[dict]]:
    out = {}
    for v, ex in extractions.items():
        ds = []
        for d in ex.get("discounts", []) or []:
            if "unconditional" in str(d.get("condition", "")).lower():
                continue
            pct = num(d.get("percent"))
            if pct is None:
                continue
            ds.append(dict(d, percent=pct, min_annual_value_inr=num(d.get("min_annual_value_inr"))))
        out[v] = ds
    return out
