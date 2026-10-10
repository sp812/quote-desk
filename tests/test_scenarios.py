"""Buyer scenarios, run end to end on the five replies as the AI actually read them (cache/extractions).

No API key needed: these run the real normalisation, questionnaire rules, award engine, issue ranking,
analyst database and accuracy harness on the saved reading. Each test is one thing a buyer, a VP or
a reviewer would check. Run: python -m pytest -q tests/test_scenarios.py -v
"""
from __future__ import annotations
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import pipeline  # noqa: E402
from core.config import USD_INR, EXTRACT_CACHE  # noqa: E402
from core.extract import load_rfx_lines  # noqa: E402

A, B, C, D, E = ("vendor_A_indrayani", "vendor_B_seabreeze", "vendor_C_kaveri", "vendor_D_godavari", "vendor_E_nordvik")
pytestmark = pytest.mark.skipif(not (EXTRACT_CACHE / f"{A}.json").exists(), reason="saved reading not present")


@pytest.fixture()
def s(tmp_path, monkeypatch):
    """The app's state with a private decisions file, so a scenario never changes the live demo."""
    monkeypatch.setattr(pipeline, "STATE_FILE", tmp_path / "decisions.json")
    return pipeline.State()


def n(s, v, lid):
    return next(x for x in s.norms if x.vendor == v and x.line_id == lid)


QTY = {l["line_id"]: int(l["annual_qty"]) for l in load_rfx_lines()}


# 1 ---------------------------------------------------------------- reading
def test_01_every_reply_read_and_every_item_accounted_for(s):
    assert set(s.extractions) == {A, B, C, D, E}
    for v in s.extractions:
        lines = sorted(x.line_id for x in s.norms if x.vendor == v)
        assert lines == sorted(QTY), f"{v} does not account for all 30 items exactly once"


def test_02_vendor_who_quoted_27_of_30_is_never_imputed(s):
    priced = [x for x in s.norms if x.vendor == C and x.status != "missing"]
    missing = [x for x in s.norms if x.vendor == C and x.status == "missing"]
    assert len(priced) == 27 and len(missing) == 3
    assert all(x.landed is None for x in missing)


def test_03_per_100_rate_becomes_per_box(s):
    x = n(s, A, "L01")
    assert x.source_quote.strip().startswith("3893") and x.landed == pytest.approx(38.93)
    assert any("divided by 100" in st_ for st_ in x.steps)


def test_04_gst_inclusive_prices_are_brought_to_ex_gst(s):
    x = n(s, C, "L01")                         # 'Rs. 38.24 ... per box', GST included
    assert x.base == pytest.approx(38.24 / 1.18, abs=0.01)
    assert any("1.18" in st_ for st_ in x.steps)


def test_05_usd_quote_converted_at_the_stated_rate_and_flagged(s):
    x = n(s, E, "L01")                         # 'USD 0.40/pc'
    assert x.base == pytest.approx(0.40 * USD_INR, abs=0.01)
    assert any(f.type == "fx" for f in x.flags)


def test_06_same_as_last_year_uses_last_years_contract_or_refuses(s):
    used = n(s, E, "L03")
    assert any("FY26 contract price" in st_ for st_ in used.steps) and any(f.type == "history" for f in used.flags)
    unknown = n(s, E, "L12")                   # Nordvik did not supply L12 last year
    assert unknown.landed is None and any(f.type == "history" and f.severity == "critical" for f in unknown.flags)


def test_07_blurred_photo_value_is_not_guessed(s):
    x = n(s, D, "L30")
    assert len(x.candidates) >= 2 and x.status == "review"
    assert x.landed == max(c["landed"] for c in x.candidates)     # least favourable to the vendor


def test_08_freight_extra_is_estimated_from_the_rate_card_and_named(s):
    x = n(s, B, "L01")
    assert x.freight > 0 and x.landed == pytest.approx(x.base + x.freight, abs=0.01)
    assert any(f.type == "freight" for f in x.flags)


# 2 ---------------------------------------------------------------- qualification
def test_09_expired_certificate_fails_whatever_the_vendor_says(s):
    q1 = s.q_evals[B]["results"]["Q1"]
    assert q1["status"] == "fail" and s.verdicts[B] == "fail"
    assert s.blocker_kind(B) == "documents"            # a renewed certificate would fix it
    assert s.blocker_kind(D) == "capability"           # no in-house lab: no document fixes it


def test_10_lower_board_grade_never_wins_even_if_the_vendor_is_included(s):
    res = s.award(eligible={A, C})
    low_spec = {x.line_id for x in s.norms if x.vendor == C and not x.spec_compliant}
    assert low_spec and all(r["vendor"] != C for r in res["rows"] if r["line_id"] in low_spec)


# 3 ---------------------------------------------------------------- the award
def test_11_vp_question_cheapest_per_line_among_qualified_only(s):
    res = s.award()
    assert s.eligible == {A}
    assert {r["vendor"] for r in res["rows"]} == {A} and not res["uncovered_lines"]
    assert res["total"] == pytest.approx(37287020, abs=1)              # ₹3.73 crore


def test_12_totals_add_up(s):
    res = s.award()
    assert res["total"] == pytest.approx(sum(r["line_total"] for r in res["rows"]), abs=1)
    assert res["total"] == pytest.approx(sum(d["value"] for d in res["by_vendor"].values()), abs=1)
    for r in res["rows"]:
        assert r["line_total"] == pytest.approx(r["unit_price"] * r["qty"], abs=0.01)
        assert r["qty"] == QTY[r["line_id"]]


def test_13_savings_vs_last_year_only_on_comparable_items(s):
    res = s.award()
    comp = sum(r["fy26_price"] * r["qty"] for r in res["rows"] if r["fy26_price"] and r["vendor"])
    paid = sum(r["line_total"] for r in res["rows"] if r["fy26_price"] and r["vendor"])
    assert res["savings_vs_fy26"] == pytest.approx(comp - paid, abs=1)
    assert res["savings_vs_fy26"] == pytest.approx(530950, abs=1)       # ₹5.3 lakh


def test_14_footnote_discount_counts_only_when_its_threshold_is_met(s):
    base = s.award(eligible={A, B})
    applied = {d["vendor"] for d in base["discounts_applied"]}
    vol = sum(r["line_total"] for r in base["rows"] if r["vendor"] == B) / (0.96 if B in applied else 1)
    assert (B in applied) == (vol >= 5_000_000)
    small = s.award(eligible={A, B}, lines={"L13", "L14"})
    assert not small["discounts_applied"]                                # far below ₹50 lakh


def test_15_seabreeze_certificate_is_worth_10_lakh_and_a_second_supplier(s):
    base, alt = s.award(), s.award(eligible={A, B})
    assert base["total"] - alt["total"] == pytest.approx(996460, abs=1)  # ₹10.0 lakh
    assert alt["by_vendor"]["Seabreeze Packaging Industries"]["lines"] == 18
    assert alt["top_share"] == pytest.approx(0.832, abs=0.001)           # still above the 70% cap


def test_16_supply_cap_says_so_when_no_second_vendor_is_qualified(s):
    res = s.award(max_share=0.7)
    assert res["split"] is not None and not res["split"]["feasible"]


def test_17_confirming_a_blurred_value_changes_the_price_used(s, tmp_path, monkeypatch):
    x = n(s, D, "L30")
    low = min(range(len(x.candidates)), key=lambda i: x.candidates[i]["landed"])
    d = pipeline.load_decisions(); d["choices"][x.group] = low; pipeline.save_decisions(d)
    s2 = pipeline.State()
    y = n(s2, D, "L30")
    assert y.resolved_by_buyer and y.landed == x.candidates[low]["landed"] and y.status != "review"


# 4 ---------------------------------------------------------------- issues, analyst, accuracy
def test_18_open_issue_amounts_match_a_real_rerun(s):
    issues = {i["id"]: i for i in s.issues()}
    sea = issues[f"{B}|eligibility"]
    assert sea["award_swing"] == pytest.approx(s.award()["total"] - s.award(eligible={A, B})["total"], abs=1)
    hot = [i for i in s.issues() if i["decision_relevant"]]
    assert hot and hot[0]["vendor"] == B                                   # the biggest one comes first


def test_19_analyst_database_reproduces_the_award(s):
    from core.analyst import build_db
    con = build_db(s)
    total = con.execute(
        "SELECT SUM(q.landed_inr * l.annual_qty) FROM quotes q JOIN lines l USING(line_id) "
        "WHERE q.vendor_key = 'vendor_A_indrayani' AND q.status <> 'missing'").fetchone()[0]
    assert total == pytest.approx(s.award()["total"], abs=1)
    with pytest.raises(Exception):
        con.execute("SELECT * FROM read_csv('/etc/hosts')").fetchall()


def test_20_reading_accuracy_against_the_hidden_answer_key(s):
    from core.evaluate import score
    r = score(s.norms, s.extractions, s.verdicts)
    c = r["counts"]
    assert r["total_values"] == 136 and c["correct"] == 133 and c["confidently_wrong"] == 0
    assert sum(t["caught"] for t in r["traps"]) == len(r["traps"]) == 17
    assert all(q["ok"] for q in r["questionnaire"])
    misses = [x for x in r["rows"] if x["result"] == "wrong_but_flagged"]
    award_lines = {(row["vendor"], row["line_id"]) for row in s.award()["rows"]}
    assert all((D, m["line_id"]) not in award_lines for m in misses)     # no miss reaches the award
