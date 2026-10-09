# Quote desk: from RFQ to a defensible award

Prototype for the Aerchain product take-home "Kill the Quote Spreadsheet".

A buyer drafts an RFQ with an AI co-pilot. Five vendors reply in five messy formats. The system reads every reply into one like-for-like comparison (same lines, same units, same currency, landed at the plant), ranks every uncertainty by how much money it can move, and lets the buyer interrogate the result in plain language, all the way to an award memo with a full audit trail.

The demo data is fabricated (see `datagen/`); all companies are fictional. Design decisions and scope are in [`docs/DECISIONS.md`](docs/DECISIONS.md).

## The eight screens

| Screen | What it does |
|---|---|
| Overview | Award, savings vs last year, vendor status, the issues worth your attention first |
| Draft RFQ | Chat with the co-pilot; it pulls approved specs and volumes, proposes questionnaire and terms. Sending is simulated. |
| Vendor replies | Each vendor's original files next to what was read from them, with sources |
| Comparison | 30 lines × 5 vendors in ₹ per unit, delivered, ex-GST. Click any cell to see every conversion step and the vendor's own words |
| Review queue | Every uncertainty ranked by money at stake; confirm values, include vendors (reason logged), draft clarification emails |
| Ask the data | Plain-language questions answered by real SQL and award-engine runs, shown under each answer; charts and Excel exports |
| Award memo | One-page recommendation written only from computed numbers, plus an Excel pack with the audit trail |
| Accuracy check | Scores the live reading against a hidden answer key; the headline number is "confidently wrong" |

## How it works

| Stage | Who does it | Where |
|---|---|---|
| Read replies (Excel, PDF incl. small print, Word, photo, email) | AI | `core/readers.py`, `core/extract.py` |
| Units, GST, FX, freight, discounts, last-year lookups | Code, every step written out | `core/normalize.py` |
| Questionnaire | AI judgement + code checks for numeric limits and certificate dates | `core/questionnaire.py` |
| Award and money-weighted review queue | Code | `core/award.py` |
| Ask the data | AI agent with tools (SQL, award scenarios, charts, exports, evidence) | `core/analyst.py` |
| RFQ drafting, memo, clarification emails | AI | `core/copilot.py`, `core/memo.py` |
| Accuracy scoring | Code | `core/evaluate.py` |

**Design rule:** the AI reads and reasons; code does the arithmetic. Unreadable values are never guessed; they're kept as alternatives and evaluated at the vendor's least favourable reading until the buyer confirms.

## Run it on Streamlit Community Cloud (free, about 10 minutes)

1. Create a **public** GitHub repo and upload **everything in this folder**, keeping the folder structure. In Chrome, drag the folders onto GitHub's *Add file → Upload files* page; the hidden `.streamlit` folder is optional.
2. Go to **share.streamlit.io**, then **Create app → Deploy a public app from GitHub**, and pick the repo, branch `main`, file `app.py`.
3. Under **Advanced settings**, choose **Python 3.12** and add this secret:
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
4. Deploy. On **Overview**, click **Read 5 replies** (1-3 minutes).

### Keep results across restarts (recommended before sharing the link)

Streamlit Cloud can restart an app and clear files it wrote. After the first good run:

1. Open **Overview → Saved results** and click **Download saved results**.
2. Unzip, and upload the `.json` files to `cache/extractions/` in the GitHub repo.

The live app then always opens with results loaded. Anyone can still click **Re-read this reply** on Vendor replies to watch the AI read a document live. If the app restarts during a demo, you can also use **Restore from a backup** on the same panel.

## Run locally

```bash
pip install -r requirements.txt
export ANTHROPIC_API_KEY=sk-ant-...
streamlit run app.py
```

Tests (no API key needed): `pip install pytest && python -m pytest -q`

## Configuration

`core/config.py` sets the models (`CLAUDE_MODEL`, default `claude-sonnet-5-5`), the USD/INR reference rate, contract start date and cost of capital. Every assumption used in a number is shown to the buyer where it is used.

## Repository layout

```
app.py            Streamlit app (8 screens)
core/             extraction, normalization, questionnaire, award engine, analyst, co-pilot, memo, accuracy
data/rfx/         the RFQ, line items, questionnaire
data/inbox/       what the five vendors sent (the AI's input)
data/buyer_records/  last year's contract prices, freight rate card
data/answer_key/  ground truth for scoring; never shown to the AI
datagen/          script that fabricated the dataset (python datagen/render.py)
tests/            deterministic tests; the AI is replaced by a fixture and a fake client
docs/DECISIONS.md what was decided, what was left out, and why
```
