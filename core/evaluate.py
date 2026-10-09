"""Accuracy harness: score the live pipeline against the dataset's hidden answer key.

The key question for trust is not 'how many did we get right' but
'how many did we get wrong WITHOUT telling the buyer' (confidently wrong).
"""
from __future__ import annotations
import json

from .config import ANSWER_KEY
from .normalize import NormQuote

TOL = 0.01


def _close(a, b):
    return a is not None and b is not None and abs(a - b) <= max(0.02, TOL * abs(b))


def score(norms: list[NormQuote], extractions: dict, verdicts: dict[str, str]) -> dict:
    key = json.loads(ANSWER_KEY.read_text())
    letter = {k: k.split("_")[1] for k in extractions}  # vendor_A_indrayani -> A
    by = {(letter[n.vendor], n.line_id): n for n in norms if n.vendor in letter}
    rows, counts = [], {"correct": 0, "flagged_not_guessed": 0, "wrong_but_flagged": 0, "confidently_wrong": 0,
                        "correctly_missing": 0, "missed_line": 0, "invented_line": 0}
    for v, vd in key["vendors"].items():
        truth_lines = vd["lines"]
        for lid in [f"L{i:02d}" for i in range(1, 31)]:
            n = by.get((v, lid))
            t = truth_lines.get(lid, {}).get("per_unit_exgst")
            sys_val = n.base if n else None
            flagged = bool(n and any(f.severity in ("warn", "critical") for f in n.flags))
            if t is None:
                cls = "correctly_missing" if (n is None or n.status == "missing") else "invented_line"
            elif n is None or n.status == "missing" or sys_val is None:
                cls = "missed_line"
            elif _close(sys_val, t):
                cls = "correct"
            elif any(_close(c["base"], t) for c in n.candidates) and len(n.candidates) > 1:
                cls = "flagged_not_guessed"
            elif flagged:
                cls = "wrong_but_flagged"
            else:
                cls = "confidently_wrong"
            counts[cls] += 1
            rows.append(dict(vendor=v, line_id=lid, truth=t, system=sys_val,
                             candidates=[c["base"] for c in n.candidates] if n else [], result=cls))
    traps = [dict(t, caught=_trap_caught(t, by, extractions, letter, verdicts)) for t in key["traps"]]
    q_truth = {v: vd["questionnaire"]["verdict"] for v, vd in key["vendors"].items()}
    q_rows = []
    inv = {l: k for k, l in letter.items()}
    for v, tv in q_truth.items():
        sv = verdicts.get(inv.get(v, ""), "not evaluated")
        ok = (tv == "PASS" and sv == "pass") or (tv == "FAIL" and sv == "fail") or (tv == "FLAG" and sv in ("pending", "fail"))
        q_rows.append(dict(vendor=v, truth=tv, system=sv, ok=ok))
    total_values = sum(counts[k] for k in ("correct", "flagged_not_guessed", "wrong_but_flagged", "confidently_wrong", "missed_line"))
    return dict(counts=counts, rows=rows, traps=traps, questionnaire=q_rows, total_values=total_values)


def _trap_caught(t, by, ex, letter, verdicts) -> bool:
    v, typ, d = t["vendor"], t["type"], t["detail"]
    vk = next((k for k, l in letter.items() if l == v), None)
    if vk is None:
        return False
    ns = [n for (vv, _), n in by.items() if vv == v]
    has = lambda ftype, sev=("warn", "critical", "info"): any(f.type == ftype and f.severity in sev for n in ns for f in n.flags)
    if typ == "hidden_discount":
        return any(abs(x.get("percent", 0) - 4) < 0.01 for x in ex[vk].get("discounts", []))
    if typ == "freight":
        return has("freight")
    if typ == "gst":
        return has("gst")
    if typ == "currency":
        return has("fx")
    if typ == "reference":
        return has("history")
    if typ == "spec_deviation":
        return sum(1 for n in ns if not n.spec_compliant) >= 4
    if typ == "missing_lines":
        want = [x for x in ("L23", "L28", "L29", "L30") if x in d]
        return all(by.get((v, x)) is not None and by[(v, x)].status == "missing" for x in want)
    if typ == "compliance":
        return verdicts.get(vk) in ("fail", "pending")
    if typ == "illegible":
        lid = "L01" if "5-ply" in d else "L28"
        n = by.get((v, lid))
        return bool(n and len(n.candidates) > 1)
    if typ == "unit":
        if v == "A":
            return all(by.get((v, f"L{i:02d}")) and abs((by[(v, f"L{i:02d}")].base or 0) - 0) > 0 and
                       by[(v, f"L{i:02d}")].base < 100 for i in range(1, 31))
        if v == "C":
            return all(by.get((v, x)) and any(f.type == "unit" for f in by[(v, x)].flags) for x in ("L18", "L19"))
        if v == "D":
            return any("per-kg" in s.lower() or "/kg" in s for n in ns for s in n.steps)
    return False
