# Brief coverage: every line of the assignment, and where it is answered

Source: "Kill the Quote Spreadsheet" (Aerchain product take-home, 2 pages) and the cover email from the recruiter.

## Page 1: the problem and the flow

| The brief says | Where it is answered | How to see it |
|---|---|---|
| Build the system that drafts an RFx | RFQ co-pilot (`core/copilot.py`) | Draft RFQ |
| …reads whatever vendors send back | Readers for Excel, PDF (incl. small print), Word, images, email + AI extraction (`core/readers.py`, `core/extract.py`) | Vendor replies |
| …lets a buyer interrogate the result in plain language | Analyst agent with tools (`core/analyst.py`) | Ask a question |
| 30 line items of corrugated packaging; you pick the category | Corrugated packaging for a brewery: 30 lines, about ₹3.7 crore a year. Chosen for its unit chaos and because beverage and packaging are Aerchain categories | `data/rfx/` |
| They email five vendors | Five vendors, five formats | Vendor replies |
| A beautiful Excel that ignores the template | Indrayani: own layout, own item codes and order, rates per 100 | Vendor replies → Indrayani |
| A PDF on letterhead with the discount buried in a footnote | Seabreeze: 4% discount in 6-pt small print, conditional on ₹50 lakh annual volume; the reader flags small print explicitly | Vendor replies → Seabreeze |
| A Word doc where the commercials are in a paragraph | Kaveri: every price in prose, GST-inclusive | Vendor replies → Kaveri |
| A photo of a printed rate card, taken at an angle, on a phone | Godavari: tilted WhatsApp photo, ₹/kg rate card, two blurred rates | Vendor replies → Godavari |
| One email: "₹42/kg… rest same as last year, freight extra" | Nordvik: two-line email, "rest same as last year, freight extra", in USD. Per-kg pricing is covered by Godavari | Vendor replies → Nordvik |
| The buyer retypes all of it. Three days gone | Nothing is retyped; all five replies are read in 1-3 minutes | Decision board → Read replies |
| VP: "split it, cheapest per line, but only among vendors who cleared the quality questionnaire" | Award engine with questionnaire eligibility (`core/award.py`); first suggested question | Ask a question → The VP's question |
| A buyer *talks* an RFx into existence: scope, line items, questionnaire, terms | Co-pilot fills header/scope, line items from the approved spec master, a pass/fail questionnaire and terms | Draft RFQ |
| It goes out to vendors over a channel you choose | Email, WhatsApp Business and vendor portal (simulated), pick any combination. WhatsApp because small Indian vendors answer there; Godavari's reply is a WhatsApp photo | Draft RFQ → Send |
| Vendors reply however they like; nobody is forced into your template | A quote template exists (`data/rfx/RFQ_quote_template.xlsx`); no vendor used it, and nothing depends on it | Vendor replies |
| Your system reads every response, whatever shape it arrives in | Five formats in the demo; any new file or pasted email can be added live | Vendor replies → Add a vendor reply |
| A single side-by-side comparison: same lines, same units, same currency | ₹ per RFQ unit, ex-GST, landed at Waluj; unit, GST, FX, freight conversions written out per cell | Comparison |
| …with questionnaire answers and attached docs sitting alongside the numbers | "Questionnaire, terms and documents" panel under the price table: each answer with pass/fail, terms, price-variation clauses, attached documents and what they show | Comparison |
| The buyer stops clicking and starts asking. Natural language, over the whole comparison | Analyst agent over five tables (lines, vendors, quotes, questionnaire, last year's contract) | Ask a question |
| Text answers, tables, charts, exports | Answers + tables + Plotly charts + Excel/CSV exports from the analyst; Excel export on Comparison; Excel award pack | Ask a question, Comparison, Award memo |
| Real analysis on real extracted data | Every answer is a SQL query or award-engine run on the extracted data; the query is shown | "How this was worked out" under each answer |
| …all the way to a defensible award decision | Vendor scorecard (price, quality, delivery, terms, coverage) as a cross-check; stakeholder validation by Quality, Logistics, Finance and the VP, logged; award memo written only from computed facts, with exclusions, open risks, supply security, approval and L1 justification; Excel pack with audit trail and decision log | Award memo |
| Five vendors, thirty line items, a questionnaire, attached documents | 5 vendors, 30 lines, 8-question questionnaire (6 mandatory), attachments: 2 ISO certificates, a BCT test report | Vendor replies |
| Fabricate a dataset a procurement person would nod at | Board grades (GSM/BF), flutes, partitions per set, IPL promo shipper, MIDC Waluj vendor, kraft-index price clauses, last year's contract, a freight rate card | `datagen/`, `data/` |

## Page 2: rules, what is judged, deliverables

| The brief says | Where it is answered | How to see it |
|---|---|---|
| You pick everything: framework, models, email path, storage, UI, personas, industry, data, exports, guardrails | No agent framework (plain tool-use loops); Claude Sonnet 5.5; simulated email/WhatsApp; JSON cache + DuckDB; Streamlit; persona Priya, category manager; brewery packaging; Excel + Markdown exports; guardrails listed in DECISIONS.md | `docs/DECISIONS.md` |
| Stub the plumbing, but the AI loops must be real | Stubbed: sending email/WhatsApp. Real: drafting, extraction, questionnaire judgement, analyst, memo, vendor emails | Any AI page |
| Don't fake the extraction | Live extraction; "Read this reply again" re-runs it; scored against a hidden answer key | Vendor replies, Reading accuracy |
| Don't fake the reasoning | Every analyst step (query, award run, chart) is shown | Ask a question |
| Don't hardcode the answers to your demo questions | Nothing is pre-written; ask anything | Ask a question |
| The angled photo | Godavari; blurred values kept as options, never guessed | Comparison (amber), Open issues |
| The vendor who quoted 27 of 30 lines | Kaveri; missing lines shown as not quoted, never imputed | Comparison |
| The one who quoted in USD | Nordvik; converted at a stated reference rate and flagged | Comparison → evidence |
| "per box" vs "per 100 pieces" | Indrayani per 100; Kaveri "per pc" for a partition bought as a set of 5 strips (both readings kept, peer check explains); Godavari per kg | Comparison → evidence |
| What does it do, and what does it show, when it isn't sure? | Keeps every reading, evaluates at the least favourable, colours it amber, ranks it by money moved, drafts the vendor email | Open issues |
| Trust: would a buyer with ₹4 crore act on your screen? | AI reads, code computes; every number traces to the vendor's words; rule checks override the AI on numbers and dates; measured accuracy (0 confidently wrong); decision log | Comparison, Reading accuracy |
| Judgment and taste: how you made decisions, and why | Decisions and trade-offs written up | `docs/DECISIONS.md` |
| A working prototype, ready for a live demo we'll drive | Public link; results persist; any file or question can be tried live | Live app |
| A recorded walkthrough of the analyst conversation; you choose the questions | Video centred on the analyst conversation, with questions chosen to show buyer judgement | Video |
| A one-page note on what you decided and what you left out | One page | `docs/DECISIONS.md` |
| "The interesting problem was actually somewhere else": tell us | Decision confidence and procurement memory | `docs/DECISIONS.md` |

## The recruiter's email

| Asked for | Delivered as |
|---|---|
| A recorded video (Loom or Google Drive) walking through the build | Loom link |
| Live link to the build | Streamlit Community Cloud URL |
| Document / PPT detailing what you built | Slide deck + `docs/DECISIONS.md` |
| Link where the build is hosted | GitHub repository |
| Within 48 hours | Due 10 Oct 2026, 16:55 IST |
