"""RFx drafting co-pilot: the buyer describes what they need; the agent assembles scope, line items
(from the plant's packaging spec master), questionnaire and terms, asking about gaps instead of inventing."""
from __future__ import annotations
import csv
import json

from .config import RFX_DIR, RECORDS
from .llm import agent_loop

SYSTEM = """You are an RFx drafting co-pilot for a category buyer at Deccan Peak Breweries (Waluj brewery, Aurangabad).
Help the buyer turn a conversational request into a complete, sendable RFQ.
- Use get_spec_master to pull approved item specifications and last year's volumes; never invent specs or dimensions.
- Use update_draft to write into the draft (header, line items, questionnaire, terms). The buyer sees the draft update live.
- Be proactive like a senior buyer: propose a supplier questionnaire with pass/fail criteria (quality certification, testing capability, rejection rate, capacity, lead time), a clear price basis (per piece/set, FOR destination, ex-GST) and payment terms. Ask before adding anything costly or unusual.
- Keep replies short: what you changed, then at most 2 questions about genuine gaps.
- Ask about anything you cannot know (new items not in the spec master, volume changes, deadlines)."""

TOOLS = [
    {"name": "get_spec_master", "description": "Approved packaging specifications for the Waluj plant with FY26 annual volumes, filterable by keyword.",
     "input_schema": {"type": "object", "properties": {"keyword": {"type": "string"}}}},
    {"name": "update_draft", "description": "Write parts of the RFx draft. Any field given replaces that section.",
     "input_schema": {"type": "object", "properties": {
         "header": {"type": "object", "description": "title, category, contract_period, bid_due, price_basis, payment_terms, delivery, award_basis"},
         "line_items": {"type": "array", "items": {"type": "object", "properties": {
             "line_id": {"type": "string"}, "description": {"type": "string"}, "dimensions_mm": {"type": "string"}, "ply": {"type": "string"},
             "board_spec": {"type": "string"}, "print": {"type": "string"}, "annual_qty": {"type": "integer"}, "uom": {"type": "string"}}}},
         "questionnaire": {"type": "array", "items": {"type": "object", "properties": {
             "q_id": {"type": "string"}, "question": {"type": "string"}, "type": {"type": "string", "enum": ["Mandatory", "Preferred", "Info"]},
             "pass_criterion": {"type": "string"}}}},
         "terms": {"type": "array", "items": {"type": "string"}},
         "vendors": {"type": "array", "items": {"type": "string"}}}}},
]


def spec_master(keyword: str | None = None) -> list[dict]:
    with open(RFX_DIR / "line_items.csv") as f:
        rows = list(csv.DictReader(f))
    fy = {}
    with open(RECORDS / "fy26_contract_prices.csv") as f:
        for r in csv.DictReader(f):
            fy[r["line_id"]] = r
    out = []
    for r in rows:
        r = dict(r)
        r["fy26_supplier"] = fy.get(r["line_id"], {}).get("fy26_vendor") or "new item"
        if not keyword or keyword.lower() in json.dumps(r).lower():
            out.append(r)
    return out


DEFAULT_VENDORS = ["Indrayani Corrupack (Chakan)", "Seabreeze Packaging (Daman)", "Kaveri Kraftline (Hosur)",
                   "Godavari Box Works (Waluj)", "Nordvik Packaging India (Bhiwandi)"]


def new_draft() -> dict:
    return {"header": {}, "line_items": [], "questionnaire": [], "terms": [], "vendors": list(DEFAULT_VENDORS)}


def issued_draft() -> dict:
    """The RFQ as actually issued for this sourcing event (no AI involved): lets the buyer reopen it and follow the replies."""
    from .config import RFX_ID
    with open(RFX_DIR / "line_items.csv") as f:
        lines = [{k: r[k] for k in ("line_id", "description", "ply", "dimensions_mm", "board_spec", "print", "annual_qty", "uom")}
                 for r in csv.DictReader(f)]
    with open(RFX_DIR / "questionnaire.csv") as f:
        qs = list(csv.DictReader(f))
    header = {"title": f"{RFX_ID}: Annual rate contract, corrugated packaging FY2026-27 (Waluj)",
              "contract_period": "01-Nov-2026 to 31-Oct-2027", "issued": "28-Sep-2026", "bid_due": "07-Oct-2026",
              "price_basis": "Per piece (per set for partitions), FOR Waluj plant, ex-GST",
              "payment_terms": "45 days from GRN", "award_basis": "Lowest landed cost per line among vendors who pass the mandatory questionnaire"}
    header["freight"] = "Included (FOR destination)"
    header["delivery"] = "Waluj Brewery, MIDC Waluj, Chhatrapati Sambhajinagar"
    terms = ["Scope: corrugated shippers, trays, partitions and pads under an annual rate contract; weekly call-offs, peak March-May",
             "Quantities are annual estimates; award may be split by line",
             "Boxes must meet the specified board grade and pass BCT testing per DPB standard PS-04",
             "Only suppliers passing all mandatory questionnaire items are eligible",
             "Award on lowest landed cost per line: price + freight to Waluj, net of discounts, ex-GST",
             "Quote in the attached template; other formats are accepted"]
    return {"header": header, "line_items": lines, "questionnaire": qs, "terms": terms, "vendors": list(DEFAULT_VENDORS)}


def chat(draft: dict, history: list[dict], user_msg: str, on_step=None):
    def run_tool(name, inp):
        if name == "get_spec_master":
            rows = spec_master(inp.get("keyword"))
            return {"count": len(rows), "items": rows}
        if name == "update_draft":
            for k in ("header", "line_items", "questionnaire", "terms", "vendors"):
                if k in inp and inp[k] is not None:
                    if k == "header":
                        draft["header"].update(inp[k])
                    else:
                        draft[k] = inp[k]
            return {"ok": True, "lines": len(draft["line_items"]), "questions": len(draft["questionnaire"])}
        raise ValueError(name)
    sys = SYSTEM + "\n\nCURRENT DRAFT:\n" + json.dumps(draft)[:12000]
    msgs = history + [{"role": "user", "content": user_msg}]
    text, msgs = agent_loop(sys, msgs, TOOLS, run_tool, on_step=on_step, max_steps=8, max_tokens=16000)
    return text, msgs
