"""Deterministic tests: everything except the live model calls.

Run from the repo root:  python -m pytest -q
The AI steps are replaced by (a) an 'ideal extraction' fixture built from the dataset generator's ground truth,
and (b) a fake API client that checks request payloads. The app itself never uses either.
"""
import json
import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from ideal_extraction import build  # noqa: E402
from core.normalize import normalize_all, conditional_discounts, num  # noqa: E402
from core.award import award, impact, Scenario  # noqa: E402
from core.evaluate import score  # noqa: E402
from core.extract import coerce, _repair  # noqa: E402

A, B, C, D, E = ("vendor_A_indrayani", "vendor_B_seabreeze", "vendor_C_kaveri", "vendor_D_godavari", "vendor_E_nordvik")
VERDICTS = {A: "pass", B: "fail", C: "fail", D: "pending", E: "fail"}


@pytest.fixture(scope="module")
def ex():
    return build()


@pytest.fixture(scope="module")
def norms(ex):
    return normalize_all(ex, {})


def q(norms, v, lid):
    return next(n for n in norms if n.vendor == v and n.line_id == lid)


# ---------------- normalization
def test_per_100_converted(norms):
    n = q(norms, A, "L01")
    assert n.landed == pytest.approx(38.93, abs=0.01)
    assert any("divided by 100" in s for s in n.steps)


def test_gst_inclusive_removed_and_spec_deviation_blocks(norms):
    n = q(norms, C, "L01")
    assert any(f.type == "gst" for f in n.flags)
    assert not n.spec_compliant


def test_per_strip_partition_keeps_both_readings_and_peer_check_explains(norms):
    n = q(norms, C, "L18")
    assert len(n.candidates) == 2 and n.status == "review"
    assert any("Peer check" in s for s in n.steps)
    assert n.landed == max(c["landed"] for c in n.candidates)  # least favourable until confirmed


def test_illegible_photo_value_not_guessed(norms):
    n = q(norms, D, "L01")
    assert [round(c["landed"], 2) for c in n.candidates] == [36.25, 39.73]
    assert n.status == "review" and any(f.type == "illegible" for f in n.flags)


def test_same_as_last_year_resolved_or_unknowable(norms):
    assert any(f.type == "history" and f.severity == "warn" for f in q(norms, E, "L03").flags)
    unknown = q(norms, E, "L12")
    assert unknown.status == "missing" and any(f.severity == "critical" for f in unknown.flags)


def test_usd_and_freight_flagged(norms):
    n = q(norms, E, "L01")
    assert {"fx", "freight"} <= {f.type for f in n.flags}


def test_tolerant_number_parsing():
    assert num("Rs. 3,893") == 3893 and num("₹62.50") == 62.5 and num("n/a") is None


# ---------------- award
def test_strict_award_only_cleared_vendor(norms, ex):
    r = award(norms, Scenario(eligible={A}), conditional_discounts(ex))
    assert set(r["by_vendor"]) == {"Indrayani Corrupack Pvt. Ltd."} and not r["uncovered_lines"]


def test_conditional_discount_applies_only_above_threshold(norms, ex):
    disc = conditional_discounts(ex)
    big = award(norms, Scenario(eligible={A, B, D}), disc)
    assert any(d["vendor"] == B for d in big["discounts_applied"])
    small = award(norms, Scenario(eligible={A, B}, lines={"L13", "L14"}), disc)
    assert not small["discounts_applied"]


def test_no_eligible_vendor_gives_no_fake_savings(norms, ex):
    r = award(norms, Scenario(eligible=set()), conditional_discounts(ex))
    assert r["total"] == 0 and r["savings_vs_fy26"] == 0 and len(r["uncovered_lines"]) == 30


def test_ambiguity_impact_finds_discount_cascade(norms, ex):
    issues = impact(norms, Scenario(eligible={A, B, D}), conditional_discounts(ex), {}, {})
    blur = next(i for i in issues if i["kind"] == "illegible" and "L01" in i["lines"])
    assert blur["decision_relevant"] and blur["discount_effect"] and blur["cascade_lines"]


# ---------------- accuracy harness
def test_ideal_extraction_scores_clean(norms, ex):
    s = score(norms, ex, VERDICTS)
    assert s["counts"]["confidently_wrong"] == 0
    assert all(t["caught"] for t in s["traps"])


# ---------------- guards against malformed model output
def test_malformed_model_output_is_coerced(ex):
    bad = json.loads(json.dumps(ex[D]))
    bad["terms"] = json.dumps(bad["terms"])
    bad["line_quotes"] = json.dumps(bad["line_quotes"])
    fixed = _repair(bad)
    assert isinstance(fixed["terms"], dict) and isinstance(fixed["line_quotes"], list) and len(fixed["line_quotes"]) == 29
    assert coerce("not json")["line_quotes"] == []


def test_questionnaire_rule_checks():
    from core.questionnaire import _rule_checks
    from core.extract import load_questionnaire
    res = {"Q4": {"q_id": "Q4", "status": "pass"}, "Q6": {"q_id": "Q6", "status": "pass"}}
    _rule_checks({"questionnaire": [{"q_id": "Q4", "answer": "3.8%"}, {"q_id": "Q6", "answer": "about 12 days"}]}, res, load_questionnaire())
    assert res["Q4"]["status"] == "fail" and res["Q6"]["status"] == "fail"


# ---------------- API payloads (fake client, no network)
def test_request_payloads_respect_model_rules(monkeypatch):
    import core.llm as llm
    seen = []

    def fake_create(**kw):
        seen.append(kw)
        return types.SimpleNamespace(content=[types.SimpleNamespace(type="tool_use", name="t", id="1", input={"ok": True})])
    monkeypatch.setattr(llm, "client", lambda: types.SimpleNamespace(messages=types.SimpleNamespace(create=fake_create)))
    out = llm.structured_call("s", "c", "t", "d", {"type": "object"}, effort="medium")
    assert out == {"ok": True}
    kw = seen[0]
    assert "temperature" not in kw and "tool_choice" not in kw
    assert kw["extra_body"]["output_config"]["effort"] == "medium"


# ---------------- supply security
def test_share_cap_moves_lines_and_reports_premium(norms, ex):
    disc = conditional_discounts(ex)
    base = award(norms, Scenario(eligible={A, B, D}), disc)
    assert base["top_share"] > 0.7
    capped = award(norms, Scenario(eligible={A, B, D}, max_share=0.6), disc)
    sp = capped["split"]
    assert sp["feasible"] and sp["moved"] and all(v <= 0.6 + 1e-9 for v in capped["shares"].values())
    assert sp["premium"] == pytest.approx(capped["total"] - base["total"], abs=1)


def test_share_cap_reports_when_no_second_vendor(norms, ex):
    sp = award(norms, Scenario(eligible={A}, max_share=0.7), conditional_discounts(ex))["split"]
    assert not sp["feasible"] and "qualifying" in sp["note"] or "No other qualified vendor" in sp["note"]
