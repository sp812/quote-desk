"""Stakeholder validation: the system prepares the evidence, people sign off.

Each reviewer gets a short, specific list of what to check, built by code from the award and the open issues
(nothing here is written by the model). Requests and responses go into the decision log."""
from __future__ import annotations
from datetime import datetime

from .normalize import num

# Fictional people at the fictional buyer.
REVIEWERS = {
    "quality": dict(role="Plant quality", person="Anil Deshmukh", why="Confirms who is qualified and that no lower-spec board slips in"),
    "logistics": dict(role="Logistics", person="Rohit Jadhav", why="Confirms freight assumptions and lead times into Waluj"),
    "finance": dict(role="Finance", person="Meera Iyer", why="Confirms the value, savings, payment terms and currency exposure"),
    "approver": dict(role="VP Procurement (approver)", person="Vikram Rao", why="Approves the award under the delegation of authority"),
}
STATUS = {"not_sent": "Not sent", "requested": "Waiting", "approved": "Approved", "changes": "Changes requested"}


def _lakh(x: float) -> str:
    return f"₹{x / 1e7:,.2f} crore" if abs(x) >= 1e7 else f"₹{x / 1e5:,.1f} lakh"


def asks(st) -> dict[str, list[str]]:
    res = st.award()
    awarded = {r["vendor"] for r in res["rows"] if r["vendor"]}
    by_v = {}
    for n in st.norms:
        by_v.setdefault(n.vendor, []).append(n)
    out = {k: [] for k in REVIEWERS}

    # quality: one line on who is out and why, one on the lower grade
    gap = {"Q1": "ISO certificate", "Q2": "test lab", "Q3": "inks", "Q4": "rejection rate", "Q5": "capacity", "Q6": "lead time"}
    out_list = []
    for v, s_ in st.status.items():
        if s_ in ("fail", "pending", "exclude"):
            ev = st.q_evals.get(v, {}).get("results", {})
            fails = [gap[q] for q, r in sorted(ev.items()) if r.get("status") == "fail" and q in gap]
            out_list.append(f"{st.vendor_names[v].split()[0]} ({', '.join(fails) or 'documents pending'})")
        elif s_ == "include":
            out["quality"].append(f"{st.vendor_names[v].split()[0]} was included by the buyer; see the reason in the log.")
    if out_list:
        out["quality"].insert(0, "Agree to leave out: " + "; ".join(out_list) + ".")
    low_spec = sorted({st.vendor_names[n.vendor].split()[0] for n in st.norms if n.status != "missing" and not n.spec_compliant})
    if low_spec:
        out["quality"].append(f"Lower board grade from {', '.join(low_spec)} stays out of the award.")

    # logistics
    for v in sorted(awarded):
        fr = [n for n in by_v.get(v, []) if any(f.type == "freight" for f in n.flags)]
        lt = num((st.extractions[v].get("terms") or {}).get("lead_time_days"))
        bits = [f"lead time {lt:g} days (limit 10)" if lt else "lead time not stated"]
        if fr:
            bits.append(f"freight estimated on {len(fr)} items")
        out["logistics"].append(f"{st.vendor_names[v].split()[0]}: " + "; ".join(bits) + ".")

    # finance
    out["finance"].append(f"Award value {_lakh(res['total'])} a year; "
                          f"{_lakh(res['savings_vs_fy26'])} {'below' if res['savings_vs_fy26'] >= 0 else 'above'} last year on comparable items.")
    for d in res["discounts_applied"]:
        out["finance"].append(f"{st.vendor_names.get(d['vendor'], d['vendor'])}'s {d['percent']:g}% volume discount is counted; "
                              f"it only holds if the annual threshold is met.")
    for v in sorted(awarded):
        t = st.extractions[v].get("terms") or {}
        if (t.get("currency") or "INR").upper() != "INR":
            out["finance"].append(f"{st.vendor_names[v]} is priced in {t.get('currency')}; the rupee value moves with the exchange rate.")
        pdays = num(t.get("payment_days"))
        if pdays is not None and pdays < 45:
            out["finance"].append(f"{st.vendor_names[v]} asks for {pdays:g}-day payment against 45 requested.")

    # approver
    hot = [i for i in st.issues() if i["decision_relevant"]]
    top = f", {res['top_vendor'].split()[0]} holds {res['top_share']:.0%}" if res.get("top_share", 0) > 0.7 else ""
    out["approver"].append(f"{_lakh(res['total'])} across {len(res['by_vendor'])} vendor{'s' if len(res['by_vendor']) != 1 else ''}{top}.")
    out["approver"].append(f"{len(hot)} open issue{'s' if len(hot) != 1 else ''} could still change it." if hot else "Nothing open changes it.")
    out["approver"].append("Above ₹1 crore: CFO/CPO sign-off.")
    return out


def status(dec: dict) -> dict[str, dict]:
    r = dec.get("reviews", {})
    return {k: r.get(k, {"status": "not_sent"}) for k in REVIEWERS}


def request(dec: dict, roles: list[str], note: str = "", total: float | None = None) -> None:
    from .pipeline import log
    for k in roles:
        dec.setdefault("reviews", {})[k] = {"status": "requested", "ts": datetime.now().isoformat(timespec="seconds"), "note": note,
                                            "total": total}
        log(dec, "review requested", f"{REVIEWERS[k]['person']} ({REVIEWERS[k]['role']}){': ' + note if note else ''}")


def respond(dec: dict, role: str, outcome: str, comment: str = "", total: float | None = None) -> None:
    """Record a reviewer's answer, with the award total they saw, so a later change to the award shows as stale."""
    from .pipeline import log
    assert outcome in ("approved", "changes")
    dec.setdefault("reviews", {})[role] = {"status": outcome, "ts": datetime.now().isoformat(timespec="seconds"), "note": comment,
                                           "total": total}
    log(dec, "review " + STATUS[outcome].lower(), comment or STATUS[outcome], actor=REVIEWERS[role]["person"])
