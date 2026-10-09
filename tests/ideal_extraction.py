"""TEST FIXTURE ONLY - never imported by the app. Builds what a perfect extraction agent should return,
so the deterministic pipeline (normalize -> award -> impact -> accuracy) can be tested without an API key.
Never imported by the app."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "datagen"))
import spec, vendors as V

def build():
    L = {l[0]: l for l in spec.LINES}
    out = {}
    # A
    qa = V.vendor_a()
    out["vendor_A_indrayani"] = dict(vendor_name=V.VENDORS["A"]["name"], vendor_location="Chakan, Pune", response_summary="",
        terms=dict(currency="INR", gst="extra", freight="included_delivered", payment_days=45, lead_time_days=7, source="xlsx terms"),
        discounts=[], lines_not_quoted=[], unreadable_or_uncertain=[],
        line_quotes=[dict(rfx_line_id=k, vendor_item_text=k, mapping_confidence=0.95, price_candidates=[v["raw_value"]], price_unit="per_100",
                          unit_as_written="Rate / 100 Nos", unit_ambiguous=False, currency="INR", gst_included=False, references_history=False,
                          source=f"xlsx!Quotation!G{k}", source_quote=str(v["raw_value"]), confidence=0.97) for k, v in qa.items()],
        questionnaire=[dict(q_id=q, answer=a) for q, a in V.QA["A"].items() if q.startswith("Q")], document_facts=[])
    qb = V.vendor_b()
    out["vendor_B_seabreeze"] = dict(vendor_name=V.VENDORS["B"]["name"], vendor_location="Nani Daman", response_summary="",
        terms=dict(currency="INR", gst="extra", freight="ex_works_buyer_pays", payment_days=30, lead_time_days=9, source="pdf p2"),
        discounts=[dict(percent=4, condition="annual order value exceeds Rs 50 lakh", min_annual_value_inr=5000000, source="pdf p2 footnote")],
        lines_not_quoted=[], unreadable_or_uncertain=[],
        line_quotes=[dict(rfx_line_id=k, vendor_item_text=k, mapping_confidence=0.95, price_candidates=[v["raw_value"]], price_unit="per_set" if L[k][11]=="set" else "per_piece",
                          unit_as_written="Rs/pc", unit_ambiguous=False, currency="INR", gst_included=False, references_history=False,
                          source="pdf", source_quote=str(v["raw_value"]), confidence=0.97) for k, v in qb.items()],
        questionnaire=[dict(q_id=q, answer=a) for q, a in V.QA["B"].items() if q.startswith("Q")],
        document_facts=[dict(document="Seabreeze_ISO9001_Certificate.pdf", fact_type="ISO 9001 certificate_valid_until", value="31-Aug-2026", source="cert")])
    qc = V.vendor_c()
    lq = []
    for k, v in qc.items():
        per_strip = k in V.C_PER_STRIP
        lq.append(dict(rfx_line_id=k, vendor_item_text=k, mapping_confidence=0.9, price_candidates=[v["raw_value"]],
                       price_unit="per_piece", unit_as_written="per pc" if per_strip else "per box", unit_ambiguous=per_strip,
                       currency="INR", gst_included=True, references_history=False, spec_deviation=v.get("spec_deviation"),
                       source="docx", source_quote=str(v["raw_value"]), confidence=0.95))
    out["vendor_C_kaveri"] = dict(vendor_name=V.VENDORS["C"]["name"], vendor_location="Hosur", response_summary="",
        terms=dict(currency="INR", gst="included", freight="included_delivered", payment_days=60, lead_time_days=12, source="docx"),
        discounts=[], unreadable_or_uncertain=[], line_quotes=lq,
        lines_not_quoted=[dict(rfx_line_id=x, reason="unable to quote 7-ply/WR") for x in V.C_MISSING],
        questionnaire=[dict(q_id=q, answer=a) for q, a in V.QA["C"].items() if q.startswith("Q")], document_facts=[])
    lq = []
    for l in spec.LINES:
        k, cat = l[0], l[10]
        if k in V.D_NOT_SUPPLIED: continue
        cands = list(V.D_BLUR[cat]) if cat in V.D_BLUR else [V.D_RATE[cat]]
        adders = []
        if "4-col" in l[7]: adders.append(dict(amount=V.D_FOUR_COL, per="box", reason="4 colour print"))
        if "WR" in l[6]: adders.append(dict(amount=V.D_WR_COAT, per="box", reason="WR coating"))
        lq.append(dict(rfx_line_id=k, vendor_item_text=cat, mapping_confidence=0.85, price_candidates=cands, price_unit="per_kg",
                       unit_as_written="Rs. per Kg", unit_ambiguous=False, currency="INR", gst_included=False, references_history=False,
                       rate_category=cat, adders=adders, source="jpg", source_quote="/".join(map(str, cands)),
                       confidence=0.5 if len(cands) > 1 else 0.9, ambiguity_id=f"D-{cat}-blurred" if len(cands) > 1 else None))
    out["vendor_D_godavari"] = dict(vendor_name=V.VENDORS["D"]["name"], vendor_location="MIDC Waluj, Aurangabad", response_summary="",
        terms=dict(currency="INR", gst="extra", freight="free_local", payment_days=30, lead_time_days=4, source="jpg"),
        discounts=[], unreadable_or_uncertain=[], line_quotes=lq, lines_not_quoted=[dict(rfx_line_id="L23", reason="edge board not available")],
        questionnaire=[dict(q_id=q, answer=a) for q, a in V.QA["D"].items() if q.startswith("Q")], document_facts=[])
    qe = V.vendor_e()
    lq = []
    for l in spec.LINES:
        k = l[0]
        if k in ("L28", "L29"): continue
        if k in V.E_EXPLICIT:
            lq.append(dict(rfx_line_id=k, vendor_item_text=k, mapping_confidence=0.9, price_candidates=[qe[k]["raw_value"]], price_unit="per_piece",
                           unit_as_written="/pc", unit_ambiguous=False, currency="USD", gst_included=None, references_history=False,
                           source="email:L08", source_quote=str(qe[k]["raw_value"]), confidence=0.95))
        else:
            lq.append(dict(rfx_line_id=k, vendor_item_text="rest", mapping_confidence=0.6, price_candidates=[], price_unit="per_piece",
                           unit_as_written="same as last year", unit_ambiguous=False, currency="USD", gst_included=None, references_history=True,
                           source="email:L08", source_quote="Rest same as last year", confidence=0.5))
    out["vendor_E_nordvik"] = dict(vendor_name=V.VENDORS["E"]["name"], vendor_location="Bhiwandi, Thane", response_summary="",
        terms=dict(currency="USD", gst="unclear", freight="extra_unspecified", payment_days=90, lead_time_days=10, source="email"),
        discounts=[], unreadable_or_uncertain=[], line_quotes=lq,
        lines_not_quoted=[dict(rfx_line_id=x, reason="can't do export 7-ply") for x in ("L28", "L29")],
        questionnaire=[dict(q_id=q, answer=a) for q, a in V.QA["E"].items() if q.startswith("Q")], document_facts=[])
    return out

if __name__ == "__main__":
    print(json.dumps({k: len(v["line_quotes"]) for k, v in build().items()}))
