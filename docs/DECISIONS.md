# What I built, what I decided, what I left out

**Quote desk** takes a buyer from a conversational RFQ to a defensible award decision. Five vendors reply however they like (a styled Excel, a letterhead PDF, a Word letter, a tilted phone photo, a two-line email); the system reads all of them into one like-for-like comparison, ranks every uncertainty by how much money it can move, and lets the buyer interrogate the result in plain language, all the way to an award memo with an audit trail.

Demo scenario: a mid-size brewery's annual corrugated packaging contract (30 lines, about ₹3.7 crore). I chose packaging because it has the worst unit chaos in indirect spend (per box, per 100, per kg, per strip) and because beverage and packaging are categories Aerchain already serves.

## The core decision: the AI reads, code does the arithmetic

The model extracts prices *exactly as written*, with a source locator and a confidence. It never converts units, removes GST, applies FX or adds freight. Deterministic code does that and writes every step out ("₹68.50/kg × 0.58 kg = ₹39.73"). A buyer with ₹4 crore on the line can trace any number back to the vendor's own words, and a reviewer can test the arithmetic without trusting a model.

## Decisions that earn trust

- **Never guess an unreadable number.** If a photo digit could be 62.50 or 68.50, the system keeps both, evaluates the vendor at its least favourable reading until confirmed, and says so.
- **Rank uncertainty by money, not by count.** Every open issue is re-run through the award under each possible reading. The buyer sees "this blurred rate changes the winner on these lines and moves the award by this much", not a page of yellow cells. In the demo data, one blurred digit also pushes a competitor below its volume-discount threshold, moving eight *other* lines. Nobody catches that second-order effect in a spreadsheet.
- **Compare landed cost, not sticker price.** Freight (estimated from the buyer's own rate card when a vendor quotes ex-works), GST treatment, FX, and conditional discounts applied only when the awarded volume actually meets the threshold.
- **Independent cross-checks.** A peer check compares every price with the other vendors to catch unit errors. Questionnaire limits (rejection ≤ 2%, lead time ≤ 10 days) are checked in code, and certificate expiry is checked against contract start. When code and AI disagree, code wins and the override is shown.
- **Measured, not claimed, accuracy.** The fabricated dataset has a hidden answer key the AI never sees. The app scores itself against it, and the headline metric is *confidently wrong*: a wrong value shown without a warning.
- **The buyer stays in charge.** Eligibility overrides need a written reason; every decision lands in a log that ships with the award pack.

## What I deliberately left out

- **Negotiation.** Aerchain already has a Negotiation Agent; the award memo is where it would pick up.
- **Real email, vendor portal, login, multi-buyer workflow.** That's plumbing; the brief asked to stub it.
- **Automatic resolution of ambiguity.** The system drafts a clarification email to the vendor instead of resolving it silently.
- **Payment terms inside landed cost.** They're shown and available as a cost-of-capital view on request, but kept out of the headline number so it stays a price, not a model.
- **Multi-category, multi-RFQ, history across years.** One RFQ done properly beats ten done shallowly.

## The better problem

Extraction is largely solved; models read messy documents well. The expensive failure is a *fluent* system that quietly normalises the wrong thing (a per-strip price read as per-set, a blurred digit read confidently) and hands the buyer a clean table that is wrong. The real product is **decision confidence**: knowing which uncertainties actually change the award, and closing them with the vendor before money moves.

A second problem hides in "rest same as last year": procurement has no memory. A system that remembers past prices, specs and vendor behaviour turns vague references into verifiable claims and stops vendors hiding behind them.

## What I'd measure in production

Quote-to-decision time; share of values needing human review; confidently-wrong rate on audited samples; how often buyers override the recommendation and why; vendor clarification turnaround.
