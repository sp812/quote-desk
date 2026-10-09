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


# ---------------- scorecard, stakeholder validation, analyst sandbox
class FakeState:
    """Enough of core.pipeline.State for the scorecard, review and analyst modules, without the cache or the AI."""
    def __init__(self, ex, norms):
        from core.questionnaire import _rule_checks  # noqa: F401  (import check only)
        self.extractions, self.norms = ex, norms
        self.vendor_names = {k: v["vendor_name"] for k, v in ex.items()}
        self.status = dict(VERDICTS)
        self.verdicts = dict(VERDICTS)
        mand = ["Q1", "Q2", "Q3", "Q4", "Q5", "Q6"]
        self.q_evals = {v: {"results": {qq: {"status": ("pass" if s == "pass" or qq != "Q1" else "fail"), "reason": "test"}
                                        for qq in mand}} for v, s in VERDICTS.items()}
        self.discounts = conditional_discounts(ex)
        self.decisions = {"choices": {}, "eligibility": {}, "log": []}

    @property
    def eligible(self):
        return {v for v, s in self.status.items() if s in ("pass", "include")}

    def award(self, **kw):
        sc = Scenario(eligible=kw.pop("eligible", None) or set(self.eligible), **kw)
        return award(self.norms, sc, self.discounts)

    def issues(self):
        others = {v: s for v, s in self.status.items() if v not in self.eligible}
        return impact(self.norms, Scenario(eligible=set(self.eligible)), self.discounts, others, self.vendor_names)


def test_scorecard_scores_are_bounded_and_price_is_relative(norms, ex):
    from core.scorecard import build
    rows = build(FakeState(ex, norms))
    assert len(rows) == 5 and sorted(r["rank"] for r in rows) == [1, 2, 3, 4, 5]
    for r in rows:
        for k in ("price", "quality", "delivery", "commercial", "coverage", "total"):
            assert 0 <= r[k] <= 100, (r["vendor"], k, r[k])
    kaveri = next(r for r in rows if r["vendor"] == C)
    assert kaveri["items_priced"] == 27 and kaveri["coverage"] == 90.0
    # weights change the ranking input, not the per-dimension scores
    only_cov = build(FakeState(ex, norms), {"price": 0, "quality": 0, "delivery": 0, "commercial": 0, "coverage": 100})
    assert all(r["total"] == r["coverage"] for r in only_cov)


def test_review_asks_are_specific_and_responses_logged(norms, ex, tmp_path, monkeypatch):
    from core import review, pipeline
    monkeypatch.setattr(pipeline, "STATE_FILE", tmp_path / "decisions.json")
    s = FakeState(ex, norms)
    asks = review.asks(s)
    assert any("Seabreeze" in a for a in asks["quality"])          # a failed vendor is put to Quality
    assert any("crore" in a or "lakh" in a for a in asks["finance"])
    dec = {"log": []}
    review.request(dec, ["quality", "approver"], "by Friday", total=1.0)
    assert review.status(dec)["quality"]["status"] == "requested" and review.status(dec)["finance"]["status"] == "not_sent"
    review.respond(dec, "quality", "approved", "ok", total=1.0)
    assert dec["log"][-1]["actor"] == "Anil Deshmukh" and review.status(dec)["quality"]["status"] == "approved"


def test_analyst_sql_cannot_touch_files(norms, ex):
    from core.analyst import build_db
    con = build_db(FakeState(ex, norms))
    assert con.execute("select count(*) from quotes").fetchone()[0] > 0
    assert con.execute("select count(*) from vendor_scorecard").fetchone()[0] == 5
    with pytest.raises(Exception):
        con.execute("select * from read_csv('/etc/passwd')").fetchall()
    with pytest.raises(Exception):
        con.execute("SET enable_external_access = true")


def test_issued_rfq_matches_the_files_vendors_replied_to():
    from core.copilot import issued_draft
    from core.extract import load_rfx_lines, load_questionnaire
    d = issued_draft()
    assert [l["line_id"] for l in d["line_items"]] == [l["line_id"] for l in load_rfx_lines()]
    assert [q["q_id"] for q in d["questionnaire"]] == [q["q_id"] for q in load_questionnaire()]
    assert len(d["vendors"]) == 5


# ---------------- things that could put a wrong number in front of a buyer
def _one_quote(ex, vendor, line, **changes):
    import copy
    e2 = copy.deepcopy(ex)
    q = next(x for x in e2[vendor]["line_quotes"] if x["rfx_line_id"] == line)
    q.update(changes)
    return e2


def test_unknown_currency_is_never_priced_or_awarded(ex):
    e2 = _one_quote(ex, A, "L01", currency="EUR")
    n = q(normalize_all(e2, {}), A, "L01")
    assert n.landed is None and not n.awardable and n.status == "review"
    r = award(normalize_all(e2, {}), Scenario(eligible={A}), conditional_discounts(e2))
    assert "L01" in r["uncovered_lines"]


def test_currency_spellings():
    from core.normalize import canon_currency as c
    assert [c(x) for x in ["Rs.", "INR/-", "₹", "", None, "$", "US$", "usd", "EUR"]] == ["INR"] * 5 + ["USD"] * 3 + ["EUR"]


def test_zero_price_is_not_a_price(ex):
    n = q(normalize_all(_one_quote(ex, A, "L01", price_candidates=[0]), {}), A, "L01")
    assert n.landed is None and any(f.severity == "critical" for f in n.flags)


def test_too_good_to_be_true_price_is_held_until_accepted(ex):
    e2 = _one_quote(ex, A, "L01", price_candidates=[500])   # 5.00 per box after /100: a unit slip
    ns = normalize_all(e2, {})
    n = q(ns, A, "L01")
    assert not n.awardable and n.block_group
    r = award(ns, Scenario(eligible={A, B}), conditional_discounts(e2))
    assert next(x for x in r["rows"] if x["line_id"] == "L01")["vendor"] != A
    issues = impact(ns, Scenario(eligible={A, B}), conditional_discounts(e2), {}, {})
    assert any(i["kind"] == "outlier" and i.get("acceptable") for i in issues)
    ns2 = normalize_all(e2, {"accepted": {n.block_group: "confirmed in writing"}})
    assert q(ns2, A, "L01").awardable


def test_freight_extra_from_unknown_city_is_held_out(ex):
    import copy
    e2 = copy.deepcopy(ex)
    e2[A]["terms"]["freight"] = "ex_works_buyer_pays"
    e2[A]["vendor_location"] = "Coimbatore"
    n = q(normalize_all(e2, {}), A, "L01")
    assert not n.awardable and any(f.type == "freight" and f.severity == "critical" for f in n.flags)


def test_line_ids_in_other_spellings_are_mapped():
    from core.extract import canon_line_id
    ids = {f"L{i:02d}" for i in range(1, 31)}
    assert [canon_line_id(x, ids) for x in ["L01", "l1", "Line 7", "07", 12, "L31", "abc", None]] == \
        ["L01", "L01", "L07", "L07", "L12", None, None, None]


def test_same_vendor_name_twice_stays_separate():
    from core.pipeline import _unique_names
    assert _unique_names({"a": "Acme", "b": "Acme", "c": "Zen"}) == {"a": "Acme", "b": "Acme (2)", "c": "Zen"}


def test_damaged_decisions_file_does_not_break_the_app(tmp_path, monkeypatch):
    from core import pipeline
    f = tmp_path / "d.json"; f.write_text("{not json")
    monkeypatch.setattr(pipeline, "STATE_FILE", f)
    d = pipeline.load_decisions()
    assert d["choices"] == {} and list(tmp_path.glob("d.damaged-*.json"))


def test_long_conversations_are_trimmed_at_question_boundaries():
    from core.llm import trim_history
    msgs = []
    for k in range(10):
        msgs += [{"role": "user", "content": f"q{k}"}, {"role": "assistant", "content": [{"type": "tool_use"}]},
                 {"role": "user", "content": [{"type": "tool_result"}]}, {"role": "assistant", "content": "a"}]
    t = trim_history(msgs, keep_turns=3)
    assert t[0] == {"role": "user", "content": "q7"} and len(t) == 12


def test_big_phone_photo_is_shrunk_for_the_api():
    import io
    from PIL import Image
    from core.readers import _fit_image
    buf = io.BytesIO(); Image.effect_noise((4000, 3000), 90).convert("RGB").save(buf, format="PNG")
    data, mt = _fit_image(buf.getvalue(), ".png")
    im = Image.open(io.BytesIO(data))
    assert len(data) <= 3_500_000 and max(im.size) <= 2400 and mt == "image/jpeg"


def test_copilot_survives_malformed_draft_updates(monkeypatch):
    from core import copilot
    calls = iter([("update_draft", {"line_items": '[{"line_id": "L01"}]', "terms": "Net 45", "header": {"title": ["x"]}})])

    def fake_loop(system, msgs, tools, run_tool, **kw):
        for name, inp in calls:
            run_tool(name, inp)
        return "ok", msgs
    monkeypatch.setattr(copilot, "agent_loop", fake_loop)
    d = copilot.new_draft()
    copilot.chat(d, [], "hi")
    assert d["line_items"] == [{"line_id": "L01"}] and d["terms"] == ["Net 45"] and isinstance(d["header"]["title"], str)
