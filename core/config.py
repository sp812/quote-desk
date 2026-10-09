"""Paths and tunable assumptions. Every assumption here is shown to the buyer wherever it is used."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
INBOX = DATA / "inbox"
RFX_DIR = DATA / "rfx"
RECORDS = DATA / "buyer_records"
ANSWER_KEY = DATA / "answer_key" / "ground_truth.json"
CACHE = ROOT / "cache"
EXTRACT_CACHE = CACHE / "extractions"
STATE_FILE = CACHE / "buyer_decisions.json"
for p in (CACHE, EXTRACT_CACHE):
    p.mkdir(parents=True, exist_ok=True)

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5-5")
FAST_MODEL = os.environ.get("CLAUDE_FAST_MODEL", "claude-haiku-5-5")

RFX_ID = "RFQ-DPB-PKG-2026-014"
CONTRACT_START = "2026-11-01"
GST_RATE = 0.18
USD_INR = 88.40           # reference rate; flagged wherever used
USD_INR_SOURCE = "Reference rate 07-Oct-2026 (configurable)"
COST_OF_CAPITAL = 0.10    # used only when the buyer asks for payment-terms-adjusted cost

# Where each vendor ships from, used to pick a freight benchmark lane when freight is not included.
FREIGHT_LANE_HINTS = {
    "daman": "Daman -> Waluj", "bhiwandi": "Bhiwandi -> Waluj", "thane": "Bhiwandi -> Waluj",
    "hosur": "Hosur -> Waluj", "chakan": "Chakan -> Waluj", "pune": "Chakan -> Waluj",
    "waluj": "Waluj -> Waluj (local)", "aurangabad": "Waluj -> Waluj (local)",
}


def api_key_present() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))
