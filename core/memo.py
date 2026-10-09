"""Award memo (narrative written by the model strictly from computed facts) and vendor clarification drafts."""
from __future__ import annotations
import io
import json
from datetime import date

import pandas as pd

from .llm import simple_text
from .config import RFX_ID


def lakh(x):
    return f"₹{x/1e5:,.1f} lakh" if abs(x) < 1e7 else f"₹{x/1e7:,.2f} crore"


def facts(st) -> dict:
    res = st.award()
    issues = st.issues()
    split = st.award(max_share=0.7).get("split") if res.get("top_share", 0) > 0.7 else None
    return dict(
        rfx=RFX_ID, date=str(date.today()),
        eligible_vendors=[st.vendor_names[v] for v in sorted(st.eligible)],
        vendor_status={st.vendor_names[v]: s for v, s in st.status.items()},
        questionnaire_fail_reasons={st.vendor_names[v]: [f"{q}: {r['reason']}" for q, r in ev["results"].items() if r["status"] != "pass"]
                                    for v, ev in st.q_evals.items()},
        award_total=res["total"], award_total_text=lakh(res["total"]),
        by_vendor={k: dict(lines=v["lines"], value=lakh(v["value"])) for k, v in res["by_vendor"].items()},
        discounts_applied=res["discounts_applied"], uncovered_lines=res["uncovered_lines"],
        savings_vs_fy26=lakh(res["savings_vs_fy26"]), fy26_comparable_base=lakh(res["fy26_comparable_base"]),
        lines_at_risk=res["at_risk_lines"], value_at_risk=lakh(res["at_risk_value"]),
        open_issues=[dict(vendor=i["vendor_name"], kind=i["kind"], issue=i["title"], decision_relevant=i["decision_relevant"],
                          award_swing=lakh(i["award_swing"]), exposure=lakh(i.get("exposure_in_award", 0)),
                          lines_flipping=i["lines_flipping"]) for i in issues[:10]],
        supply_concentration=dict(top_vendor=res.get("top_vendor"), top_share=f"{res.get('top_share', 0):.0%}",
                                  split_at_70pct=(dict(feasible=split["feasible"], lines_moved=len(split["moved"]),
                                                       premium=lakh(split["premium"]), note=split["note"]) if split else None)),
        approval=("Award value above ₹1 crore: per a typical approval matrix this needs CFO/CPO sign-off "
                  "(adjust to Deccan Peak's actual delegation of authority)."),
        buyer_decisions=st.decisions.get("log", [])[-15:],
    ), res, issues


MEMO_SYSTEM = """Write a one-page award recommendation memo from a category buyer to the VP Procurement.
Use ONLY the facts provided in JSON. Do not introduce any number that is not in the facts. Indian money units as given.
Structure (markdown):
# Award recommendation - <rfx>
**Recommendation** (2-3 sentences: who gets what, total, savings)
**Award split** (short table: vendor, lines, annual value)
**Who was excluded and why**
**Open risks before PO** (only decision-relevant items, each with the money at stake and the action - e.g. clarification sent to vendor)
**Assumptions** (freight estimates, FX, last-year prices)
**Approval requested**
Tone: crisp, factual, no hype."""


def write_memo(st) -> tuple[str, dict, dict]:
    f, res, issues = facts(st)
    md = simple_text(MEMO_SYSTEM, json.dumps(f, default=str, indent=1), max_tokens=6000)
    return md, f, res


def memo_workbook(st, res, issues) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        pd.DataFrame(res["rows"]).to_excel(xw, sheet_name="Award", index=False)
        comp = pd.DataFrame([dict(line_id=n.line_id, vendor=n.vendor_name, landed_inr=n.landed, status=n.status,
                                  readings=" / ".join(f"{c['landed']:.2f}" for c in n.candidates),
                                  spec_ok=n.spec_compliant, source=n.source, quoted_as=n.source_quote,
                                  steps=" -> ".join(n.steps), flags=" | ".join(f.text for f in n.flags)) for n in st.norms])
        comp.to_excel(xw, sheet_name="Comparison (audit)", index=False)
        pd.DataFrame([{k: v for k, v in i.items() if k not in ("outcomes",)} for i in issues]).to_excel(xw, sheet_name="Open issues", index=False)
        pd.DataFrame(st.decisions.get("log", [])).to_excel(xw, sheet_name="Decision log", index=False)
    return buf.getvalue()


CLARIFY_SYSTEM = """Draft a short, polite, specific clarification email from a buyer (Priya Kulkarni, Deccan Peak Breweries) to a vendor
about their quotation for RFQ-DPB-PKG-2026-014. Quote exactly what is unclear, list the specific line items affected, and ask
for a written confirmation by a date 2 working days out. Do not reveal competitor prices or how the award would change.
Return: first line 'Subject: ...', then the body."""


def draft_clarification(issue: dict, st) -> str:
    ns = [n for n in st.norms if n.line_id in issue["lines"] and n.vendor == issue["vendor"]]
    detail = dict(vendor=issue["vendor_name"], issue=issue["title"], kind=issue["kind"],
                  lines=[dict(line=n.line_id, item=n.vendor_item_text, vendor_wrote=n.source_quote, source=n.source,
                              readings=[c["label"] for c in n.candidates]) for n in ns][:15])
    return simple_text(CLARIFY_SYSTEM, json.dumps(detail, indent=1), max_tokens=2000)
