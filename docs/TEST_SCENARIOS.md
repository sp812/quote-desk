# Buyer test scenarios

Twenty end-to-end scenarios run on the five replies **as the AI actually read them** (`cache/extractions/`), through the real normalisation, questionnaire rules, award engine, issue ranking, analyst database and accuracy harness. No API key is needed. Run: `python -m pytest -q tests/test_scenarios.py -v`.

Each scenario was also checked to fail when the behaviour it protects is broken (e.g. picking the favourable reading of a blurred value, or forgetting to remove GST).

| # | Scenario | Expected | Result |
|---|---|---|---|
| 1 | Every reply read; every vendor accounts for all 30 items once | 5 vendors x 30 items | Pass |
| 2 | Vendor quoted 27 of 30 (Kaveri) | 27 priced, 3 not quoted, never imputed | Pass |
| 3 | Per-100 rate (Indrayani "3893 per 100") | ₹38.93 per box | Pass |
| 4 | GST-inclusive prose price (Kaveri ₹38.24) | ÷ 1.18 = ₹32.41 ex-GST | Pass |
| 5 | USD quote (Nordvik USD 0.40) | × 88.40 = ₹35.36, FX flagged | Pass |
| 6 | "Rest same as last year" | Last year's contract price, flagged; refused where they did not supply last year | Pass |
| 7 | Blurred photo rate (Godavari L30) | Both readings kept; least favourable used; marked to confirm | Pass |
| 8 | Freight extra (Seabreeze) | Estimated from the lane rate card; landed = price + freight; flagged | Pass |
| 9 | Expired ISO certificate (Seabreeze) | Q1 fails in code; classed as a document gap; Godavari's missing lab classed as capability | Pass |
| 10 | Lower board grade offered (Kaveri) | Never wins, even if Kaveri is included | Pass |
| 11 | VP: cheapest per line, qualified vendors only | Indrayani on all 30 items, ₹3,72,87,020 | Pass |
| 12 | Totals add up | Lines = vendors = total; line total = price × quantity | Pass |
| 13 | Savings vs last year | Only on comparable, awarded items: ₹5,30,950 | Pass |
| 14 | Footnote discount (4% above ₹50 lakh) | Applied only when awarded volume crosses ₹50 lakh | Pass |
| 15 | Seabreeze qualifies | ₹9,96,460 lower; Seabreeze wins 18 items; holds 83.2% of spend | Pass |
| 16 | 70% supply cap with one qualified vendor | Reported as not feasible | Pass |
| 17 | Buyer confirms a blurred value | That value is used; item no longer marked to confirm | Pass |
| 18 | Open-issue amounts | Equal to an actual re-run of the award; biggest first | Pass |
| 19 | Analyst database | SQL over its tables reproduces the award total; cannot read files | Pass |
| 20 | Reading accuracy vs hidden answer key | 133 of 136 correct, 0 confidently wrong, 17 of 17 traps, 5 of 5 verdicts; no miss reaches the award | Pass |
