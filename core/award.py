"""Award engine and money-weighted uncertainty.

award(): lowest landed cost per line among eligible vendors (spec-compliant unless allowed),
with conditional volume discounts applied only if the awarded volume actually meets the threshold.

impact(): for every open issue, re-run the award under each possible resolution and measure how
much money and how many line winners it moves. That is what ranks the buyer's review queue.
"""
from __future__ import annotations
import copy
import json
from dataclasses import dataclass, field

from .normalize import NormQuote, load_fy26, load_freight, Flag
from .extract import load_rfx_lines
from .config import FREIGHT_LANE_HINTS


@dataclass
class Scenario:
    eligible: set[str]
    allow_spec_deviation: bool = False
    apply_conditional_discounts: bool = True
    lines: set[str] | None = None            # restrict to some lines
    max_vendors: int | None = None           # e.g. 2 = consolidate to at most two vendors
    overrides: dict[str, int] = field(default_factory=dict)   # group -> candidate index


def _price(n: NormQuote, overrides: dict[str, int]) -> float | None:
    if n.landed is None:
        return None
    if n.group and n.group in overrides and overrides[n.group] < len(n.candidates):
        return n.candidates[overrides[n.group]]["landed"]
    return n.landed


def _solve(norms, sc: Scenario, discount_on: dict[str, float]):
    lines = load_rfx_lines()
    by = {}
    for n in norms:
        by.setdefault(n.line_id, []).append(n)
    rows = []
    for l in lines:
        lid = l["line_id"]
        if sc.lines and lid not in sc.lines:
            continue
        opts = []
        for n in by.get(lid, []):
            if n.vendor not in sc.eligible or n.status == "missing":
                continue
            if not n.spec_compliant and not sc.allow_spec_deviation:
                continue
            p = _price(n, sc.overrides)
            if p is None:
                continue
            if n.vendor in discount_on:
                p = round((p - n.freight) * (1 - discount_on[n.vendor]) + n.freight, 2)
            opts.append((p, n))
        opts.sort(key=lambda x: x[0])
        qty = int(l["annual_qty"])
        if opts:
            p, n = opts[0]
            rows.append(dict(line_id=lid, description=l["description"], qty=qty, uom=l["uom"], vendor=n.vendor,
                             vendor_name=n.vendor_name, unit_price=p, line_total=round(p * qty, 2),
                             runner_up=opts[1][1].vendor_name if len(opts) > 1 else None,
                             runner_up_price=opts[1][0] if len(opts) > 1 else None,
                             options=len(opts), at_risk=bool(n.status == "review" and n.group not in sc.overrides)))
        else:
            rows.append(dict(line_id=lid, description=l["description"], qty=qty, uom=l["uom"], vendor=None, vendor_name="NO ELIGIBLE QUOTE",
                             unit_price=None, line_total=0.0, runner_up=None, runner_up_price=None, options=0, at_risk=True))
    return rows


def award(norms: list[NormQuote], sc: Scenario, discounts: dict[str, list[dict]] | None = None) -> dict:
    discounts = discounts or {}
    if sc.max_vendors:
        return _award_consolidated(norms, sc, discounts)
    on: dict[str, float] = {}
    rows = _solve(norms, sc, on)
    applied = []
    if sc.apply_conditional_discounts:
        for _ in range(3):  # fixed point: discount changes award, award changes whether threshold is met
            new_on = {}
            for v, ds in discounts.items():
                vol = sum(r["line_total"] for r in rows if r["vendor"] == v)
                if v in on:  # volume measured before discount
                    vol = vol / (1 - on[v])
                for d in ds:
                    thr = d.get("min_annual_value_inr")
                    if thr is not None and vol >= thr:
                        new_on[v] = d["percent"] / 100
            if new_on == on:
                break
            on = new_on
            rows = _solve(norms, sc, on)
        for v, pct in on.items():
            applied.append({"vendor": v, "percent": pct * 100})
    return _summarize(rows, applied, sc)


def _award_consolidated(norms, sc: Scenario, discounts):
    from itertools import combinations
    best = None
    pool = sorted(sc.eligible)
    for k in range(1, (sc.max_vendors or 1) + 1):
        for combo in combinations(pool, k):
            sub = copy.copy(sc); sub.eligible = set(combo); sub.max_vendors = None
            res = award(norms, sub, discounts)
            if res["uncovered_lines"]:
                continue
            if best is None or res["total"] < best["total"]:
                best = res
    if best is None:
        sub = copy.copy(sc); sub.max_vendors = None
        best = award(norms, sub, discounts)
        best["note"] = f"No combination of {sc.max_vendors} vendors covers every line; showing unconstrained award."
    return best


def _summarize(rows, applied, sc):
    fy26 = load_fy26()
    fr = load_freight()
    baseline = 0.0
    for r in rows:
        rec = fy26.get(r["line_id"])
        if rec and rec.get("fy26_unit_price"):
            p = float(rec["fy26_unit_price"])
            if rec["currency"] == "USD":
                p = p * float(rec["fy26_fx_usd_inr"] or 0)
            if "freight extra" in (rec.get("notes") or "").lower():
                wt = next(float(l["target_weight_kg"]) for l in load_rfx_lines() if l["line_id"] == r["line_id"])
                p += fr.get("Bhiwandi -> Waluj", 0) * wt
            r["fy26_price"] = round(p, 2)
            baseline += p * r["qty"]
        else:
            r["fy26_price"] = None
    total = round(sum(r["line_total"] for r in rows), 2)
    # savings only on lines actually awarded and with a last-year price
    comparable = sum(r["line_total"] for r in rows if r["fy26_price"] and r["vendor"])
    comp_base = sum(r["fy26_price"] * r["qty"] for r in rows if r["fy26_price"] and r["vendor"])
    by_vendor = {}
    for r in rows:
        if r["vendor"]:
            b = by_vendor.setdefault(r["vendor_name"], {"lines": 0, "value": 0.0})
            b["lines"] += 1; b["value"] += r["line_total"]
    return dict(rows=rows, total=total, by_vendor=by_vendor, discounts_applied=applied,
                uncovered_lines=[r["line_id"] for r in rows if r["vendor"] is None],
                at_risk_lines=[r["line_id"] for r in rows if r["at_risk"]],
                at_risk_value=round(sum(r["line_total"] for r in rows if r["at_risk"]), 2),
                savings_vs_fy26=round(comp_base - comparable, 2), fy26_comparable_base=round(comp_base, 2),
                scenario=dict(eligible=sorted(sc.eligible), allow_spec_deviation=sc.allow_spec_deviation,
                              overrides=sc.overrides, max_vendors=sc.max_vendors))


def winners(res) -> dict[str, str | None]:
    return {r["line_id"]: r["vendor"] for r in res["rows"]}


def impact(norms: list[NormQuote], sc: Scenario, discounts, vendor_status: dict[str, str], vendor_names: dict[str, str]) -> list[dict]:
    """Rank every open issue by how much it can move the award."""
    base = award(norms, sc, discounts)
    base_w = winners(base)
    issues = []
    qty = {l["line_id"]: int(l["annual_qty"]) for l in load_rfx_lines()}

    # 1) value ambiguities (illegible, unit) - re-run award under each reading
    groups: dict[str, list[NormQuote]] = {}
    for n in norms:
        if n.group and len(n.candidates) > 1 and not n.resolved_by_buyer:
            groups.setdefault(n.group, []).append(n)
    for g, ns in groups.items():
        k = max(len(n.candidates) for n in ns)
        outcomes = []
        for i in range(k):
            sc2 = copy.copy(sc); sc2.overrides = dict(sc.overrides); sc2.overrides[g] = i
            r = award(norms, sc2, discounts)
            w = winners(r)
            flips = [lid for lid in w if w[lid] != base_w[lid]]
            outcomes.append(dict(index=i, label=ns[0].candidates[min(i, len(ns[0].candidates) - 1)]["label"],
                                 total=r["total"], flips=flips, winners=w, discounts=r["discounts_applied"],
                                 vendor_lines=sum(1 for x in w.values() if x == ns[0].vendor)))
        flips_any = sorted({lid for o in outcomes for lid in o["flips"]} |
                           {lid for o in outcomes for o2 in outcomes for lid in o["winners"] if o["winners"][lid] != o2["winners"][lid]})
        quote_swing = sum(qty[n.line_id] * (max(c["landed"] for c in n.candidates) - min(c["landed"] for c in n.candidates)) for n in ns)
        award_swing = max(o["total"] for o in outcomes) - min(o["total"] for o in outcomes)
        kind = next((f.type for f in ns[0].flags if f.group == g), "ambiguity")
        issues.append(dict(id=g, kind=kind, vendor=ns[0].vendor, vendor_name=ns[0].vendor_name,
                           title=next((f.text for f in ns[0].flags if f.group == g), g),
                           lines=sorted(n.line_id for n in ns), quote_value_swing=round(quote_swing, 2),
                           award_swing=round(award_swing, 2), lines_flipping=flips_any, outcomes=outcomes,
                           cascade_lines=[x for x in flips_any if x not in {n.line_id for n in ns}],
                           discount_effect=len({json.dumps(o["discounts"], sort_keys=True) for o in outcomes}) > 1,
                           decision_relevant=bool(flips_any), resolvable=True))

    # 2) eligibility - what if a pending/failed vendor were cleared?
    for v, st in vendor_status.items():
        if st == "pass":
            continue
        sc2 = copy.copy(sc); sc2.eligible = set(sc.eligible) | {v}
        r = award(norms, sc2, discounts)
        w = winners(r)
        flips = [lid for lid in w if w[lid] != base_w[lid]]
        won = [lid for lid in w if w[lid] == v]
        newly_covered = [lid for lid in won if base_w.get(lid) is None]
        contested = [lid for lid in won if base_w.get(lid) is not None]
        # saving only where there was already an eligible winner to compare against
        base_by = {x["line_id"]: x for x in base["rows"]}
        new_by = {x["line_id"]: x for x in r["rows"]}
        saving = sum(base_by[l]["line_total"] - new_by[l]["line_total"] for l in contested)
        # discount cascades on other lines
        saving += sum(base_by[l]["line_total"] - new_by[l]["line_total"] for l in w if l not in won and base_w[l] is not None)
        issues.append(dict(id=f"{v}|eligibility", kind="eligibility", vendor=v, vendor_name=vendor_names.get(v, v),
                           title=f"Questionnaire status: {st.upper()}. If cleared, would win {len(won)} lines.",
                           lines=won, quote_value_swing=round(sum(x["line_total"] for x in r["rows"] if x["vendor"] == v), 2),
                           award_swing=round(saving, 2), lines_flipping=flips, newly_covered=newly_covered,
                           newly_covered_value=round(sum(new_by[l]["line_total"] for l in newly_covered), 2),
                           decision_relevant=bool(flips), resolvable=False, status=st))

    # 3) single-value assumptions (freight estimate, FX, history) - exposure in the current award
    seen = set()
    for n in norms:
        for f in n.flags:
            if f.group and f.type in ("freight", "fx", "history", "spec") and f.group not in seen:
                seen.add(f.group)
                affected = [m for m in norms if any(ff.group == f.group for ff in m.flags)]
                in_award = [m.line_id for m in affected if base_w.get(m.line_id) == m.vendor]
                exposure = sum(r["line_total"] for r in base["rows"] if r["line_id"] in in_award)
                issues.append(dict(id=f.group, kind=f.type, vendor=n.vendor, vendor_name=n.vendor_name, title=f.text,
                                   lines=sorted(m.line_id for m in affected), quote_value_swing=0.0,
                                   award_swing=0.0, exposure_in_award=round(exposure, 2), lines_flipping=[],
                                   decision_relevant=bool(in_award), resolvable=False))
    for i in issues:
        i.setdefault("exposure_in_award", 0.0)
        i["priority"] = (2 if i["decision_relevant"] and i["kind"] not in ("freight", "fx", "history", "spec") else
                         1 if i["decision_relevant"] else 0, i["award_swing"] + i["exposure_in_award"] + i.get("newly_covered_value", 0) + i["quote_value_swing"] * 0.01)
    issues.sort(key=lambda x: x["priority"], reverse=True)
    return issues
