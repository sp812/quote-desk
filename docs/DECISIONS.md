# Quote desk: what I decided, and what I left out

**In one line:** Quote desk takes a buyer from five messy vendor replies to an award she can defend, and shows her exactly what still stands in the way.

**The demo:** Deccan Peak Breweries (fictional) buys 30 corrugated packaging items for about ₹3.7 crore a year. Five vendors reply five ways: an Excel in their own layout, a letterhead PDF with a discount in tiny print, a Word letter with GST inside the prices, a tilted WhatsApp photo, and a two-line email in US dollars saying "rest same as last year, freight extra".

## What the buyer experiences

1. **Decision board.** One screen answers: what should I award, is it ready, and what is the single most useful next step. Today: ₹3.73 crore, all to one vendor, not ready; the biggest opportunity is one missing certificate.
2. **Vendor replies.** Each original file next to what was read from it. Nothing is retyped.
3. **Comparison.** Every price on the same basis: rupees per unit, without GST, delivered to the plant. Click any price to see the vendor's own words and every conversion step.
4. **Open issues.** Every doubt, ranked by how many rupees it can move. One click drafts the email to the vendor.
5. **Ask a question.** Plain-language questions, answered from the data, with the working shown. The VP's question ("cheapest per line, only vendors who cleared the questionnaire") is answered in seconds.
6. **Award and approvals.** A memo written only from computed numbers, a checklist for each approver, and an Excel pack with the full audit trail.

## The decisions that matter

- **The AI reads; code does the maths; people decide.** The AI copies prices exactly as written and says where it found them. Code converts units, removes GST, converts currency and adds freight, writing each step down. Approvers sign off.
- **Never guess.** If a price can be read two ways, both are kept and the vendor is judged at the less favourable one until they confirm.
- **A suspicious price never wins silently.** Unknown currency, zero, freight with no known rate, or a price far below everyone else is shown but kept out of the award until the buyer accepts it with a reason.
- **Rank doubts by money, not by count.** Each open issue is tested by re-running the award under every answer, so the buyer works on what changes the decision.
- **Rules beat the AI on facts.** Certificate dates and numeric limits (rejection rate, lead time) are checked in code.
- **The award follows the RFQ rule.** A scorecard (price, quality, delivery, terms, coverage) is a cross-check for approvers, not a way around the rule.
- **Every action is logged.** Including a vendor or accepting a price needs a written reason.

## What I left out, on purpose

- **Real email, WhatsApp and portal sending, logins, notifications:** plumbing, simulated as the brief allows.
- **Negotiation:** the memo's open issues are where Aerchain's negotiation step would pick up.
- **Separate workspaces per user:** everyone on the demo link shares one set of decisions.
- **Field accuracy:** the data and its traps are mine; a blind test on a real buyer's files comes next.

## The interesting problem was somewhere else

Reading the quotes took minutes. The award was still stuck, and not because of price. Four of five vendors failed the quality questionnaire, leaving ₹3.73 crore with one supplier.

- **One gap is paperwork.** Seabreeze failed only because its ISO certificate expires before the contract starts. A renewed certificate would cut the award by **₹10.0 lakh** and add a second supplier (Seabreeze would hold 83% of spend).
- **Three gaps are capability.** Kaveri, Godavari and Nordvik fail on a missing test lab, a high rejection rate or a long lead time. No document fixes those.

So the real job is **closure**: knowing which gaps a document can close, what each is worth, and chasing it. Over time that becomes a verified supplier record (certificates, lab, rejection rate, price history) that each buyer reuses, then, with consent, buyers share: verify once, qualify everywhere.

## How I would measure it

- **North star:** time from bids closing to an approved award.
- **Guardrail:** zero prices shown wrong without a warning.

On the demo: 133 of 136 prices read correctly; the 3 misses were flagged and none reached the award; 17 of 17 planted traps caught. 87 automated tests run, including 20 buyer scenarios on the real reading ([list](TEST_SCENARIOS.md)) and one test per edge case on the review panel's list ([list](EDGE_CASES.md)). In a pilot I would add how many values buyers still re-check by hand, and how fast open issues get closed.
