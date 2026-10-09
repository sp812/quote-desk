# Quote desk: what I decided, and what I left out

**Quote desk** takes a buyer from a conversational RFQ to an award she can defend. Five vendors reply however they like (a styled Excel, a letterhead PDF, a Word letter, a tilted WhatsApp photo, a two-line email). The system reads them into one like-for-like comparison, ranks every uncertainty by the money it moves, and answers questions in plain language through to an award memo. Demo: a brewery's annual corrugated contract, 30 lines, about ₹3.7 crore. I chose packaging for its unit chaos (per box, per 100, per kg, per strip) and because beverage and packaging are categories Aerchain serves.

## Decisions

- **The AI reads; code does the arithmetic.** The model records prices exactly as written, with a source and a confidence. Code converts units, removes GST, applies FX, adds freight and writes every step out, so any rupee can be traced to the vendor's words.
- **Never guess an unreadable number.** Every plausible reading is kept and the vendor is evaluated at its least favourable one until the value is confirmed.
- **Rank uncertainty by money, not count.** Each open issue is re-run through the award under every possible answer. One blurred digit in the demo also tips a rival below its volume-discount threshold and moves other lines: a second-order effect no spreadsheet catches.
- **Landed cost, not sticker price**, with conditional discounts applied only when the awarded volume meets the threshold.
- **Code overrides the AI on facts.** Numeric questionnaire limits and certificate expiry are checked in code; a peer check catches unit errors.
- **Cheapest is not automatically defensible.** The board warns when one vendor would hold most of the spend and prices a split. L1 matching (the next vendor matches L1 for its share) usually removes the premium.
- **Measured accuracy.** A hidden answer key scores the live reading. The headline metric is *confidently wrong*: a wrong value shown without a warning. It is zero; the only misses were a blur the AI said it couldn't read.
- **A scorecard as a second lens, not the rule.** Price, quality, delivery, commercial terms and coverage are scored 0-100 by visible formulas with adjustable weights. The award still follows the RFQ rule; the scorecard shows approvers the trade-offs (in the demo, the only qualified vendor is 3% above the cheapest like-for-like price).
- **AI prepares, people validate.** Quality, Logistics, Finance and the VP each get a specific checklist built from the award; their sign-off is logged, and goes stale if the award changes afterwards. Including a vendor needs a written reason. Everything ships in the award pack.
- **Channel: email, WhatsApp and vendor portal** (simulated). Small Indian vendors answer on WhatsApp, and vendor participation decides whether a sourcing event works.
- **A price that can't be trusted never enters the award.** Unknown currency, a zero price, freight extra with no known lane, or a price more than 50% below every other vendor is shown but held out until the buyer accepts it with a written reason.
- **Guardrails.** Vendor documents are treated as data (instructions inside them are ignored and flagged); the analyst's SQL cannot read files or the network; vendor text is escaped before display.

## Deliberately left out

- **Negotiation and reverse auctions.** Aerchain has a Negotiation Agent; the award memo is where it would pick up.
- **Real email/WhatsApp/portal delivery, login, notifications to reviewers.** Plumbing, stubbed as allowed.
- **Silent auto-resolution.** The system drafts the vendor email instead of deciding for the buyer.
- **Payment terms inside landed cost.** Kept as an on-request cost-of-capital view, so the headline stays a price.
- **Re-mapping a line by hand, multi-RFQ history, other categories.** Next on the list; one RFQ done properly first.

## The better problem

Reading messy quotes is largely solved. The expensive failure is a fluent system that normalises the wrong thing and hands the buyer a clean table that is wrong. The product is **decision confidence**: knowing which uncertainties change the award and closing them with the vendor before money moves. Second, procurement has no **memory**: "rest same as last year" only works if the system remembers last year, and every buyer correction ("it's 68.50") should make the next read of that vendor better.

**What I'd measure:** quote-to-decision time, share of values needing review, confidently-wrong rate on audited samples, buyer overrides and why, vendor clarification turnaround.
