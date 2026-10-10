"""Quote desk - from RFQ to a defensible award. Run: streamlit run app.py

Interface only. All logic lives in core/ (the AI reads, code does the arithmetic)."""
from __future__ import annotations
import json
import os
import re
from html import escape as E  # vendor- and AI-supplied text goes into HTML: always escape it

import pandas as pd
import plotly.express as px
import streamlit as st

from core import config, extract
from core.config import INBOX, api_key_present
from core.pipeline import State, run_extraction, vendor_dirs, load_decisions, log, reset_decisions

st.set_page_config(page_title="Quote desk", page_icon="📦", layout="wide", initial_sidebar_state="expanded")

# Streamlit Community Cloud keeps keys in st.secrets; other hosts use environment variables. Support both.
try:
    if not os.environ.get("ANTHROPIC_API_KEY") and "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass

# ------------------------------------------------------------------ design tokens
INK = "#16243A"        # text, structure
INK_2 = "#4B5869"      # secondary text
LINE = "#DDE3EA"       # borders
PAGE = "#F4F6F8"       # page background
CARD = "#FFFFFF"       # working surfaces
KRAFT = "#9A6A2F"      # corrugated kraft: used only to mark L1 (lowest qualified bid)
GOOD, GOOD_BG = "#1F7A55", "#E3F2EA"
CHECK, CHECK_BG = "#94600A", "#FFF3D9"
STOP, STOP_BG = "#A93A2E", "#FBE6E3"
MUTED, MUTED_BG = "#5F6B7A", "#EDF0F3"

st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Anek+Latin:wdth,wght@75..125,300..800&display=swap');
@font-face {{ font-family: 'Anek Latin'; src: url('/app/static/AnekLatin.ttf') format('truetype');
  font-weight: 100 800; font-stretch: 75% 125%; font-display: swap; }}
html, body, .stApp, .stMarkdown, button, input, textarea, select, label, p, li, td, th {{ font-family: 'Anek Latin', 'Segoe UI', sans-serif !important; font-stretch: 100%; }}
h1, h2, h3, .hero .big, .kpi-value, .issue .stake, .brand {{ font-family: 'Anek Latin', sans-serif !important; font-stretch: 82%; }}
.flute {{ height: 10px; background: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='18' height='10'><path d='M0 7 Q4.5 1 9 7 T18 7' fill='none' stroke='%239A6A2F' stroke-width='1.8'/></svg>") repeat-x; background-size: 18px 10px; opacity: .9; }}
.intro {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 16px 22px 14px 22px; margin: 2px 0 18px 0; }}
.intro .what {{ font-size: 1.12rem; line-height: 1.5; color: {INK}; max-width: 92ch; }}
.intro .what b {{ color: {INK}; }}
.intro .how {{ display: flex; flex-wrap: wrap; gap: 6px 26px; margin-top: 10px; color: {INK_2}; font-size: .92rem; }}
.intro .how span b {{ color: {KRAFT}; font-weight: 700; margin-right: 4px; }}
.brand {{ font-size: 1.5rem; font-weight: 750; letter-spacing: .01em; color: #FFFFFF !important; line-height: 1; }}
.stApp {{ background: {PAGE}; color: {INK}; }}
[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] li, [data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] h1, [data-testid="stAppViewContainer"] h2, [data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] summary, [data-testid="stAppViewContainer"] span:not(.pill):not(.l1) {{ color: {INK}; }}
[data-testid="stHeader"] {{ background: {PAGE}; }}
.block-container {{ padding-top: 3.6rem; max-width: 1320px; }}
p, li {{ font-size: 1rem; line-height: 1.55; }}
h1 {{ font-size: 2.15rem !important; font-weight: 750 !important; letter-spacing: 0; margin-bottom: .2rem !important; }}
h2 {{ font-size: 1.3rem !important; font-weight: 600 !important; margin-top: 1.6rem !important; }}
h3 {{ font-size: 1.08rem !important; font-weight: 600 !important; }}
.num, td, .kpi-value {{ font-variant-numeric: tabular-nums; }}

/* sidebar */
section[data-testid="stSidebar"] {{ background: {INK}; border-right: 1px solid #0E1828; }}
section[data-testid="stSidebar"] * {{ color: #E6EBF1 !important; }}
/* brand block above the navigation */
section[data-testid="stSidebar"] [data-testid="stSidebarContent"] {{ display: flex; flex-direction: column; }}
section[data-testid="stSidebar"] [data-testid="stSidebarUserContent"] {{ order: -1; padding: 0 1rem 14px 1rem; border-bottom: 1px solid rgba(255,255,255,.08); margin-bottom: 4px; }}
section[data-testid="stSidebar"] [data-testid="stSidebarHeader"] {{ order: -2; height: 2.4rem; min-height: 0; padding-bottom: 0; }}
section[data-testid="stSidebar"] [data-testid="stSidebarNav"] {{ padding-top: 0; }}
/* section labels */
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{ color: #8EA2B8 !important; font-size: .72rem !important;
  font-weight: 650; letter-spacing: .09em; text-transform: uppercase; margin: 14px 0 4px 0; }}
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] * {{ color: #8EA2B8 !important; }}
/* navigation items */
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] {{ border-radius: 7px; padding: 7px 12px; margin: 1px 0;
  border-left: 3px solid transparent; transition: background .12s; }}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] span {{ font-size: .98rem !important; color: #D3DCE6 !important; }}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"] [data-testid="stIconMaterial"] {{ color: #8EA2B8 !important; font-size: 1.15rem; }}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"]:hover {{ background: rgba(255,255,255,.06); }}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] {{ background: rgba(255,255,255,.10);
  border-left-color: {KRAFT}; }}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] span {{ color: #FFFFFF !important; font-weight: 650; }}
section[data-testid="stSidebar"] a[data-testid="stSidebarNavLink"][aria-current="page"] [data-testid="stIconMaterial"] {{ color: #D9A866 !important; }}
.sb-brand {{ display: flex; align-items: center; gap: 10px; margin: 0 0 2px 0; }}
.sb-mark {{ width: 34px; height: 34px; border-radius: 8px; background: {KRAFT}; display: flex; align-items: center; justify-content: center; flex: none; }}
.sb-sub {{ font-size: .82rem; color: #9FB0C3 !important; line-height: 1.35; margin: 2px 0 0 0; }}
.sb-rfq {{ margin: 12px 0 4px 0; padding: 10px 12px; border-radius: 8px; background: rgba(255,255,255,.05); border: 1px solid rgba(255,255,255,.08); }}
.sb-rfq .k {{ font-size: .7rem; letter-spacing: .08em; text-transform: uppercase; color: #8EA2B8 !important; }}
.sb-rfq .v {{ font-size: .9rem; color: #FFFFFF !important; font-weight: 600; margin-top: 2px; }}
.sb-rfq .m {{ font-size: .8rem; color: #B7C4D2 !important; margin-top: 2px; }}
.sb-note {{ font-size: .76rem; color: #8EA2B8 !important; margin-top: 8px; line-height: 1.4; }}
.sb-note.off {{ color: #E8B96B !important; }}

/* buttons: explicit so a dark-mode browser cannot invert them */
.stButton > button, .stDownloadButton > button {{ background: {CARD}; color: {INK} !important; border: 1px solid #C4CDD7; border-radius: 6px; font-weight: 500; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: {INK}; color: {INK} !important; }}
.stButton > button[kind="primary"] {{ background: {INK}; color: #FFFFFF !important; border-color: {INK}; }}
.stButton > button[kind="primary"] p {{ color: #FFFFFF !important; }}
.stButton > button p, .stDownloadButton > button p {{ color: inherit !important; }}
[data-testid="stMultiSelectTagsContainer"] > span > span, [data-baseweb="tag"] {{ background: {MUTED_BG} !important; border: 1px solid {LINE}; }}
[data-testid="stMultiSelectTagsContainer"] span, [data-testid="stMultiSelectTagsContainer"] svg {{ color: {INK} !important; fill: {INK} !important; }}
[data-testid="stExpander"] details {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; }}

/* components */
.purpose {{ color: {INK_2}; font-size: 1.02rem; margin: 0 0 1.2rem 0; max-width: 78ch; }}
.purpose b {{ color: {INK}; }}
.pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .8rem; font-weight: 600; white-space: nowrap; }}
.good {{ background: {GOOD_BG}; color: {GOOD}; }} .check {{ background: {CHECK_BG}; color: {CHECK}; }}
.stop {{ background: {STOP_BG}; color: {STOP}; }} .muted {{ background: {MUTED_BG}; color: {MUTED}; }}
.l1 {{ display: inline-block; background: {KRAFT}; color: #fff; font-weight: 700; font-size: .75rem; padding: 1px 7px; border-radius: 4px; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 6px 0 8px 0; }}
.kpi {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; padding: 14px 16px; }}
.kpi-label {{ color: {INK_2}; font-size: .86rem; }}
.kpi-value {{ font-size: 1.65rem; font-weight: 700; color: {INK}; line-height: 1.25; margin-top: 2px; }}
.kpi-note {{ color: {INK_2}; font-size: .82rem; margin-top: 2px; }}
.issue {{ background: {CARD}; border: 1px solid {LINE}; border-left: 6px solid {CHECK}; border-radius: 8px; padding: 14px 18px; margin: 12px 0 6px 0; }}
.issue.stopper {{ border-left-color: {STOP}; }} .issue.quiet {{ border-left-color: #C4CDD7; }}
.issue .head {{ font-weight: 600; font-size: 1.04rem; color: {INK}; }}
.issue .stake {{ font-size: 1.4rem; font-weight: 700; color: {INK}; font-variant-numeric: tabular-nums; }}
.issue .stake-l {{ color: {INK_2}; font-size: .88rem; }}
.issue .detail {{ color: {INK_2}; font-size: .9rem; margin-top: 4px; line-height: 1.45; }}
.legend {{ display: flex; gap: 14px; flex-wrap: wrap; align-items: center; font-size: .88rem; color: {INK_2}; margin: 2px 0 10px 0; }}
.sw {{ display: inline-block; width: 14px; height: 14px; border-radius: 3px; vertical-align: -2px; margin-right: 5px; border: 1px solid {LINE}; }}
.step {{ border-left: 2px solid {KRAFT}; padding: 3px 0 3px 12px; margin: 5px 0; font-size: .93rem; color: {INK}; }}
.terms td {{ padding: 4px 14px 4px 0; font-size: .93rem; }} .terms td:first-child {{ color: {INK_2}; }}
.small, p.small {{ color: {INK_2} !important; font-size: .88rem !important; line-height: 1.45; }}
.hero {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 20px 24px; height: 100%; }}
.hero .eyebrow {{ color: {INK_2}; font-size: .9rem; font-weight: 500; }}
.hero .big {{ font-size: 2.5rem; font-weight: 700; color: {INK}; line-height: 1.15; margin: 4px 0 14px 0; font-variant-numeric: tabular-nums; }}
.hero .big .per {{ font-size: 1rem; font-weight: 500; color: {INK_2}; }}
.hero .big .pill {{ font-size: .85rem; vertical-align: middle; margin-left: 6px; }}
.hero .bar {{ display: flex; height: 22px; border-radius: 6px; overflow: hidden; background: {MUTED_BG}; }}
.hero .bar div {{ height: 100%; border-right: 2px solid {CARD}; }}
.legend2 {{ display: flex; flex-wrap: wrap; gap: 6px 18px; margin: 10px 0 4px 0; font-size: .9rem; color: {INK}; }}
.legend2 b {{ color: {INK}; }}
.dot {{ display: inline-block; width: 10px; height: 10px; border-radius: 50%; margin-right: 6px; vertical-align: 0; }}
.hero .meta, .meta {{ color: {INK_2}; font-size: .86rem; margin-top: 8px; }}
.warn-line {{ margin-top: 10px; padding: 8px 12px; background: {CHECK_BG}; color: {CHECK}; border-radius: 6px; font-size: .9rem; }}
.hero.side {{ border-top: 4px solid {STOP}; }}
ol.todo {{ margin: 8px 0 0 0; padding-left: 1.2rem; }}
ol.todo li {{ margin: 0 0 12px 0; color: {INK}; }}
ol.todo .it {{ font-weight: 600; color: {INK}; line-height: 1.35; }}
ol.todo .iv {{ color: {INK_2}; font-size: .86rem; }}
table.vt {{ width: 100%; border-collapse: separate; border-spacing: 0; background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; overflow: hidden; }}
table.vt th {{ text-align: left; font-weight: 500; font-size: .84rem; color: {INK_2}; padding: 10px 14px; border-bottom: 1px solid {LINE}; background: #FAFBFC; }}
table.vt td {{ padding: 12px 14px; border-bottom: 1px solid {LINE}; vertical-align: top; color: {INK}; font-size: .93rem; }}
table.vt tr:last-child td {{ border-bottom: none; }}
table.vt td.n {{ font-variant-numeric: tabular-nums; white-space: nowrap; }}
table.vt .sub {{ color: {INK_2}; font-size: .8rem; margin-top: 2px; }}
table.vt td.why {{ color: {INK_2}; font-size: .86rem; max-width: 340px; }}
.statusrow {{ display: flex; flex-wrap: wrap; gap: 6px 18px; align-items: center; margin: -6px 0 14px 0; color: {INK_2}; font-size: .9rem; }}
.kpi .delta {{ display: inline-block; margin-top: 6px; font-size: .8rem; font-weight: 600; padding: 1px 8px; border-radius: 999px; }}
.kpi .delta.down {{ background: {GOOD_BG}; color: {GOOD}; }} .kpi .delta.up {{ background: {STOP_BG}; color: {STOP}; }}
.kpi {{ border-top: 3px solid {LINE}; }}
.nba {{ background: {CARD}; border: 1px solid {LINE}; border-left: 6px solid {KRAFT}; border-radius: 10px; padding: 14px 20px; margin: 14px 0 4px 0; }}
.nba.good {{ border-left-color: {GOOD}; }}
.nba-k {{ font-size: .75rem; letter-spacing: .08em; text-transform: uppercase; color: {KRAFT}; font-weight: 700; }}
.nba-t {{ font-size: 1.2rem; font-weight: 650; color: {INK}; margin-top: 2px; }}
.nba-s {{ color: {INK_2}; font-size: .93rem; margin-top: 4px; max-width: 95ch; }}
.panel {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 16px 20px; margin-top: 10px; height: 100%; }}
.panel-h {{ font-weight: 650; font-size: 1.05rem; color: {INK}; }}
.panel-s {{ color: {INK_2}; font-size: .85rem; margin: 2px 0 12px 0; }}
.srow {{ display: grid; grid-template-columns: 120px 1fr 92px; grid-template-rows: auto auto; column-gap: 12px; align-items: center; margin: 0 0 12px 0; }}
.sname {{ font-weight: 600; color: {INK}; font-size: .95rem; white-space: nowrap; }}
.sbar {{ height: 12px; background: {MUTED_BG}; border-radius: 6px; overflow: hidden; }} .sbar div {{ height: 100%; border-radius: 6px; }}
.sval {{ text-align: right; font-weight: 600; font-variant-numeric: tabular-nums; color: {INK}; }}
.verdict {{ border-radius: 8px; padding: 10px 14px; margin: 6px 0 14px 0; font-size: .95rem; }}
.verdict.good {{ background: {GOOD_BG}; color: {GOOD}; }} .verdict.check {{ background: {CHECK_BG}; color: {CHECK}; }}
.verdict.stop {{ background: {STOP_BG}; color: {STOP}; }} .verdict.muted {{ background: {MUTED_BG}; color: {MUTED}; }}
.verdict b {{ color: inherit; }}
.stack {{ display: flex; height: 12px; border-radius: 6px; overflow: hidden; margin-top: 8px; background: {MUTED_BG}; }}
.stack div {{ height: 100%; border-right: 2px solid {CARD}; }}
.spct {{ grid-column: 2 / 4; color: {INK_2}; font-size: .8rem; }}
.mini {{ width: 120px; height: 8px; background: {MUTED_BG}; border-radius: 4px; overflow: hidden; margin-top: 6px; }}
.mini div {{ height: 100%; }}
table.vt th abbr {{ text-decoration: underline dotted {INK_2}; cursor: help; }}
.sc {{ display: flex; align-items: center; gap: 8px; }}
.sc .track {{ flex: 1; height: 7px; background: {MUTED_BG}; border-radius: 4px; overflow: hidden; min-width: 40px; }}
table.vt td.watch {{ color: {INK_2}; font-size: .86rem; min-width: 150px; }}
.sc .track div {{ height: 100%; background: {INK}; }}
.sc .v {{ width: 2.2em; text-align: right; font-variant-numeric: tabular-nums; font-size: .9rem; }}
.total {{ font-size: 1.35rem; font-weight: 700; font-variant-numeric: tabular-nums; }}
.rev {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 10px; padding: 14px 18px; height: 100%; }}
.rev .who {{ font-weight: 600; color: {INK}; }} .rev .role {{ color: {INK_2}; font-size: .86rem; }}
.rev ul {{ margin: 8px 0 4px 1rem; padding: 0; }} .rev li {{ font-size: .9rem; margin-bottom: 4px; }}
@media (max-width: 900px) {{ .kpis {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
</style>""", unsafe_allow_html=True)

# ------------------------------------------------------------------ vocabulary
STATUS = {"pass": ("Qualified", "good"), "fail": ("Not qualified", "stop"), "pending": ("Documents pending", "check"),
          "include": ("Included by you", "good"), "exclude": ("Excluded by you", "muted")}
FREIGHT = {"included_delivered": "Included, delivered to Waluj", "free_local": "Free local delivery",
           "ex_works_buyer_pays": "Ex-works; we pay freight", "extra_unspecified": "Extra, amount not stated", "unclear": "Not stated"}
GST = {"included": "Included in price", "extra": "Extra (18%)", "unclear": "Not stated"}
TRAP_NAMES = {"unit": "Unit of price", "hidden_discount": "Discount in small print", "freight": "Freight not included",
              "compliance": "Questionnaire vs evidence", "gst": "GST inside price", "missing_lines": "Lines not quoted",
              "spec_deviation": "Lower spec offered", "illegible": "Unreadable value", "currency": "Quoted in USD",
              "reference": "'Same as last year'"}


def money(x):
    if x is None:
        return "-"
    return f"₹{x/1e7:,.2f} cr" if abs(x) >= 1e7 else f"₹{x/1e5:,.1f} lakh" if abs(x) >= 1e5 else f"₹{x:,.0f}"


_SHORT: dict[str, str] = {}


def _set_short_names(names):
    """First word of each vendor name; if two vendors share it, use the first two words."""
    _SHORT.clear()
    names = [n for n in names if n]
    first = [n.split()[0] for n in names]
    used: set[str] = set()
    for n in names:
        cand = n.split()[0] if first.count(n.split()[0]) == 1 else " ".join(n.split()[:2])
        k = 2
        while cand in used:          # still clashing (e.g. 'Acme Ltd' and 'Acme Ltd (2)'): number them
            cand = f"{' '.join(n.split()[:2])} #{k}"; k += 1
        used.add(cand)
        _SHORT[n] = cand


def short(name):
    return _SHORT.get(name) or (name or "").split()[0] if name else ""


def pill(text, cls):
    return f'<span class="pill {cls}">{text}</span>'


def header(title, purpose):
    st.title(title)
    st.markdown(f'<p class="purpose">{purpose}</p>', unsafe_allow_html=True)


def get_state(refresh=False) -> State:
    if refresh or "state" not in st.session_state:
        st.session_state.state = State()
        st.session_state.pop("analyst", None)
        st.session_state["_data_version"] = st.session_state.get("_data_version", 0) + 1
    _set_short_names(list(st.session_state.state.vendor_names.values()))
    return st.session_state.state


def refresh():
    get_state(refresh=True)


def key_notice():
    """No banner on every page: the sidebar says once if AI actions are off, and AI buttons are disabled."""
    return


def ai(fn, *args, **kw):
    """Run an AI step; on failure show the buyer a plain sentence (and keep everything already done), never a stack trace."""
    from core.llm import friendly_error
    try:
        return fn(*args, **kw)
    except Exception as e:
        st.error(friendly_error(e))
        return None


def need_replies():
    st.info("No vendor replies have been read yet. Start on the Decision board.")


def place(loc: str) -> str:
    loc = (loc or "").replace("(", ",").split(",")[0].strip()
    return loc[:28]


def vendor_reason(s, v) -> str:
    ev = s.q_evals.get(v, {}).get("results", {})
    bad = [f"{q}: {r.get('reason', '')}" for q, r in sorted(ev.items()) if r.get("status") != "pass"]
    if not bad:
        return ""
    txt = bad[0]
    return (txt[:110] + "…") if len(txt) > 110 else txt


def issue_headline(i) -> str:
    v = short(i["vendor_name"])
    k = i["kind"]
    if k == "eligibility":
        return {"fail": f"{v} is not qualified", "pending": f"{v}'s qualification documents are pending",
                "exclude": f"{v} was excluded by you"}.get(i.get("status"), f"{v}: {i.get('status')}")
    if k == "illegible":
        return f"{v}'s rate can't be read reliably on lines {', '.join(i['lines'][:3])}{'…' if len(i['lines']) > 3 else ''}"
    if k == "unit":
        return f"{v}'s unit of price is ambiguous on {', '.join(i['lines'])}"
    if k == "freight" and not i.get("held_out"):
        return f"{v}'s freight is estimated, not quoted"
    if k == "fx" and not i.get("held_out"):
        return f"{v} quoted in US dollars"
    if k == "history":
        return f"{v}'s 'same as last year' prices are unconfirmed"
    if k == "spec":
        return f"{v} offered a lower board grade than specified"
    if k == "outlier":
        return f"{v}'s price on {', '.join(i['lines'])} is far below every other vendor"
    if k == "freight" and i.get("held_out"):
        return f"{v}'s freight is extra and can't be estimated, so it is out of the award"
    if k == "fx" and i.get("held_out"):
        return f"{v} quoted in a currency with no reference rate"
    return f"{v}: {i['title'][:80]}"


# ================================================================== Decision board
def _link(key, label):
    page = st.session_state.get("_pages", {}).get(key)
    if page is not None:
        st.page_link(page, label=label, icon=":material/arrow_forward:")


VENDOR_COLORS = ["#16243A", "#4F7CAC", "#9A6A2F", "#6E9E80", "#B5655A", "#7A6FA8"]


Q_SHORT = {"Q1": "ISO certificate", "Q2": "In-house test lab", "Q3": "Food-safe inks", "Q4": "Rejection rate",
           "Q5": "Peak capacity", "Q6": "Lead time", "Q7": "FSC paper", "Q8": "Plant distance"}


def _blockers(s, v) -> tuple[str, str]:
    """Short label of what keeps a vendor out (for the table) and the full reasons (for the hover)."""
    ev = s.q_evals.get(v, {}).get("results", {})
    bad = [(q, r) for q, r in sorted(ev.items()) if r.get("status") != "pass" and q != "Q8"]
    fails = [Q_SHORT.get(q, q) for q, r in bad if r.get("status") == "fail"]
    unclear = [Q_SHORT.get(q, q) for q, r in bad if r.get("status") != "fail"]
    short_txt = " · ".join(fails[:3]) if fails else ("To confirm: " + ", ".join(unclear[:2]) if unclear else "")
    full = "\n".join(f"{q} {r.get('status')}: {r.get('reason', '')}" for q, r in bad)
    return short_txt, full


def page_board():
    s = get_state()
    header("Corrugated packaging, FY27 annual contract",
           f"Deccan Peak Breweries, Waluj · {config.RFX_ID} · 30 items · bids closed 7 Oct 2026")
    key_notice()
    missing = s.missing_extractions()
    if missing:
        st.markdown(f'<div class="nba"><div class="nba-k">Next step</div><div class="nba-t">{len(missing)} vendor replies are waiting to be read</div>'
                    f'<div class="nba-s">Any format: Excel, PDF, Word, photo, email. Usually 1 to 3 minutes.</div></div>', unsafe_allow_html=True)
        if st.button(f"Read {len(missing)} replies", type="primary", disabled=not api_key_present()):
            from core.pipeline import run_many
            box = st.status(f"Reading {len(missing)} replies", expanded=True)
            msgs = []
            res = run_many(missing, progress=msgs.append)
            for m in msgs:
                box.write(m.replace("vendor_", "").replace("_", " "))
            ok = all(v is None for v in res.values())
            box.update(label="All replies read" if ok else "Some replies could not be read - details above", state="complete" if ok else "error")
            refresh(); st.rerun()
    if not s.ready():
        _saved_results()
        return

    from core.review import status as review_status
    res = s.award()
    issues = s.issues()
    hot = [i for i in issues if i["decision_relevant"]]
    color = {v: VENDOR_COLORS[k % len(VENDOR_COLORS)] for k, v in enumerate(s.extractions)}
    name_to_key = {s.vendor_names[v]: v for v in s.extractions}
    qual = sum(1 for v in s.status.values() if v in ("pass", "include"))
    rs = review_status(load_decisions())
    signed = sum(1 for r in rs.values() if r["status"] == "approved")
    out = [v for v, st_ in s.status.items() if st_ not in ("pass", "include")]
    fixable = [v for v in out if s.blocker_kind(v) == "documents"]
    capability = [v for v in out if v not in fixable]
    unlocked = s.award(eligible=s.eligible | set(fixable)) if fixable else None
    gain = (res["total"] - unlocked["total"]) if (unlocked and res["total"] and len(unlocked["uncovered_lines"]) <= len(res["uncovered_lines"])) else 0
    stake = max((_stake(i)[0] for i in hot), default=0)   # issues overlap, so they are never summed

    # ---------------- status line
    if not res["total"]:
        state_txt, state_cls = "No vendor qualified yet", "stop"
    elif hot:
        state_txt, state_cls = f"Not ready: {len(hot)} open item{'s' if len(hot) != 1 else ''} can change the award", "check"
    elif signed < len(rs):
        state_txt, state_cls = "Ready for sign-off", "good"
    else:
        state_txt, state_cls = "Approved by all reviewers", "good"
    st.markdown(f'<div class="statusrow">{pill(state_txt, state_cls)}<span>{len(s.extractions)} of {len(vendor_dirs())} replies read</span></div>',
                unsafe_allow_html=True)

    # ---------------- four numbers
    sav = res["savings_vs_fy26"] if res["fy26_comparable_base"] else None
    tiles = [
        ("Recommended award", money(res["total"]) if res["total"] else "–", "a year, landed, ex-GST" if res["total"] else "no qualified vendor yet",
         (f'<span class="delta {"up" if sav < 0 else "down"}">{"↑" if sav < 0 else "↓"} {money(abs(sav))} vs last year</span>' if sav else "")),
        ("Qualified vendors", f"{qual} of {len(s.extractions)}", "passed quality checks", ""),
        ("Open items", str(len(hot)), f"largest worth {money(stake)}" if hot else "none change the award", ""),
        ("Sign-off", f"{signed} of {len(rs)}", "Quality, Logistics, Finance, VP", ""),
    ]
    st.markdown('<div class="kpis">' + "".join(
        f'<div class="kpi"><div class="kpi-label">{a}</div><div class="kpi-value">{b}</div><div class="kpi-note">{n}</div>{d}</div>'
        for a, b, n, d in tiles) + "</div>", unsafe_allow_html=True)

    # ---------------- the one thing to do next
    if gain > 0:
        names = [short(s.vendor_names[v]) for v in fixable]
        who = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
        n_sup = len(unlocked["by_vendor"])
        cap_txt = (f" {', '.join(short(s.vendor_names[v]) for v in capability)} fail on capability, which no document fixes." if capability else "")
        st.markdown(f"""<div class="nba"><div class="nba-k">Biggest opportunity</div>
            <div class="nba-t">Get {E(who)}'s missing documents: {money(gain)} lower award{' and a second supplier' if n_sup > len(res['by_vendor']) else ''}</div>
            <div class="nba-s">Same quotes, {money(unlocked['total'])} across {n_sup} vendor{'s' if n_sup != 1 else ''}.{E(cap_txt)}</div></div>""",
                    unsafe_allow_html=True)
        _link("issues", "Ask for the documents in Open issues")
    elif hot:
        top = hot[0]
        st.markdown(f'<div class="nba"><div class="nba-k">Next step</div><div class="nba-t">{E(issue_headline(top))}</div>'
                    f'<div class="nba-s">{money(_stake(top)[0])} {E(_stake(top)[1])}.</div></div>', unsafe_allow_html=True)
        _link("issues", "Resolve it in Open issues")
    elif res["total"]:
        st.markdown('<div class="nba good"><div class="nba-k">Next step</div><div class="nba-t">Nothing open changes the award</div>'
                    '<div class="nba-s">Write the memo and send it to the reviewers.</div></div>', unsafe_allow_html=True)
        _link("memo", "Write the memo and get sign-off")

    # ---------------- award split + what blocks approval
    left, right = st.columns([6, 5], gap="medium")
    with left:
        rows = sorted(res["by_vendor"].items(), key=lambda kv: -kv[1]["value"])
        body = "".join(f"""<div class="srow"><div class="sname"><span class="dot" style="background:{color[name_to_key[n]]}"></span>{E(short(n))}</div>
            <div class="sbar"><div style="width:{d['value'] / res['total'] * 100:.1f}%;background:{color[name_to_key[n]]}"></div></div>
            <div class="sval">{money(d['value'])}</div><div class="spct">{d['value'] / res['total']:.0%} · {d['lines']} items</div></div>"""
                       for n, d in rows) if res["total"] else '<div class="small">No qualified vendor yet.</div>'
        warn = ""
        if res.get("top_share", 0) > 0.7:
            warn = f'<div class="warn-line">{E(short(res["top_vendor"]))} holds {res["top_share"]:.0%} of spend: a single-supplier risk.</div>'
        alt = ""
        if gain > 0:
            seg = "".join(f'<div title="{E(n)}: {money(d["value"])}" style="width:{d["value"] / unlocked["total"] * 100:.1f}%;background:{color[name_to_key[n]]}"></div>'
                          for n, d in sorted(unlocked["by_vendor"].items(), key=lambda kv: -kv[1]["value"]))
            lg = "".join(f'<span style="margin-right:14px;white-space:nowrap"><span class="dot" style="background:{color[name_to_key[n]]}"></span>'
                         f'{E(short(n))} {d["lines"]} items · {money(d["value"])}</span>'
                         for n, d in sorted(unlocked["by_vendor"].items(), key=lambda kv: -kv[1]["value"]))
            alt = (f'<div class="panel-h" style="margin-top:16px;font-size:.95rem">With the missing documents: {money(unlocked["total"])}</div>'
                   f'<div class="stack">{seg}</div><div class="spct" style="margin-top:8px">{lg}</div>')
        st.markdown(f'<div class="panel"><div class="panel-h">Award split</div>'
                    f'{body}{warn}{alt}</div>', unsafe_allow_html=True)
    with right:
        items = "".join(f'<li><div class="it">{E(issue_headline(i))}</div><div class="iv">{money(_stake(i)[0])} · '
                        f'{str(len(i["lines_flipping"])) + (" item" if len(i["lines_flipping"]) == 1 else " items") if i["lines_flipping"] else "to confirm"}</div></li>'
                        for i in hot[:4]) or '<li><div class="it">Nothing open changes the award</div></li>'
        more = f'<div class="meta">+{len(hot) - 4} more in Open issues</div>' if len(hot) > 4 else ""
        st.markdown(f'<div class="panel"><div class="panel-h">Before you approve</div>'
                    f'<ol class="todo">{items}</ol>{more}</div>', unsafe_allow_html=True)

    # ---------------- vendors
    st.subheader("Vendors")
    vrows = []
    for v, ex in s.extractions.items():
        lbl, cls = STATUS.get(s.status[v], ("Unknown", "muted"))
        ns = [n for n in s.norms if n.vendor == v]
        quoted = sum(1 for n in ns if n.status != "missing")
        conf = sum(1 for n in ns if n.status == "review")
        won = res["by_vendor"].get(s.vendor_names[v], {"lines": 0, "value": 0})
        fmt = ", ".join(sorted({FORMAT.get("." + f.split(".")[-1].lower(), "Email") for f in ex.get("_meta", {}).get("files", [])}))
        short_b, full_b = _blockers(s, v) if s.status[v] not in ("pass", "include") else ("", "")
        sub = " · ".join(x for x in [f"{30 - quoted} not quoted" if quoted < 30 else "", f"{conf} to confirm" if conf else ""] if x)
        vrows.append(f"""<tr><td><span class="dot" style="background:{color[v]}"></span><b>{E(s.vendor_names[v])}</b>
            <div class="sub">{E(place(ex.get('vendor_location')))}{' · ' + fmt if fmt else ''}</div></td>
            <td>{pill(lbl, cls)}</td>
            <td class="n"><b>{quoted}</b> of 30{f'<div class="sub">{sub}</div>' if sub else ''}</td>
            <td class="n">{won['lines'] or '–'}</td>
            <td class="n">{money(won['value']) if won['lines'] else '–'}</td>
            <td class="why" title="{E(full_b)}">{E(short_b) or '–'}</td></tr>""")
    st.markdown('<table class="vt"><thead><tr><th>Vendor</th><th>Qualification</th>'
                '<th><abbr title="How many of the 30 RFQ items this vendor gave a price for">Items priced</abbr></th>'
                '<th><abbr title="Items where this vendor is the cheapest qualified landed price">Wins</abbr></th>'
                '<th>Value</th><th><abbr title="Hover a row for the full reasons">Missing to qualify</abbr></th></tr></thead><tbody>'
                + "".join(vrows) + "</tbody></table>", unsafe_allow_html=True)
    st.write("")


def _review_line():
    from core.review import status as review_status
    rs = review_status(load_decisions())
    done = sum(1 for r in rs.values() if r["status"] == "approved")
    sent = sum(1 for r in rs.values() if r["status"] != "not_sent")
    st.markdown(f'<p class="small">Stakeholder validation: {done} of {len(rs)} signed off'
                f'{"" if sent else " · not sent yet"}</p>', unsafe_allow_html=True)


def _saved_results():
    import io
    import zipfile
    from core.config import EXTRACT_CACHE
    with st.expander("Saved results: backup and restore"):
        files = sorted(EXTRACT_CACHE.glob("*.json"))
        st.caption("Download a backup, or commit these files to `cache/extractions/` so the live app always starts with them.")
        if files:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w") as z:
                for f in files:
                    z.write(f, f.name)
            st.download_button(f"Download saved results ({len(files)} files)", buf.getvalue(), file_name="saved_results.zip")
        up = st.file_uploader("Restore from a backup (.zip)", type=["zip"], key="restore_zip")
        if up is not None and st.button("Restore"):
            with zipfile.ZipFile(io.BytesIO(up.getvalue())) as z:
                n = 0
                for name in z.namelist():
                    base = name.split("/")[-1]
                    if base.endswith(".json") and base.startswith("vendor_"):
                        (EXTRACT_CACHE / base).write_bytes(z.read(name)); n += 1
            log(load_decisions(), "restore", f"Restored {n} saved result files", actor="buyer")
            refresh(); st.rerun()


# ================================================================== Draft RFQ
def page_draft():
    from core import copilot
    header("Draft the RFQ", "Say what you need; the co-pilot drafts items, questionnaire and terms.")
    key_notice()
    if "draft" not in st.session_state:
        st.session_state.draft, st.session_state.draft_hist, st.session_state.draft_chat = copilot.new_draft(), [], []
    left, right = st.columns([5, 6], gap="large")
    with left:
        st.subheader("Conversation")
        for role, text in st.session_state.draft_chat:
            st.chat_message(role).write(text)
        if not st.session_state.draft_chat:
            st.markdown('<p class="small">For example: "Annual rate contract for all corrugated packaging at Waluj from November, same items as '
                        'last year plus the new 7-ply export shippers and the cold-chain carton. Quality matters, we had rejection problems last year."</p>',
                        unsafe_allow_html=True)
        if not st.session_state.draft_chat and not st.session_state.draft["line_items"]:
            if st.button(f"Or open the RFQ already issued ({config.RFX_ID})", key="load_issued"):
                st.session_state.draft = copilot.issued_draft()
                st.rerun()
        msg = st.chat_input("What do you need to buy?", disabled=not api_key_present())
        if msg:
            st.session_state.draft_chat.append(("user", msg))
            with st.spinner("Drafting the RFQ"):
                out = ai(copilot.chat, st.session_state.draft, st.session_state.draft_hist, msg)
            if out is None:
                st.session_state.draft_chat.pop()
            else:
                st.session_state.draft_hist = out[1]
                st.session_state.draft_chat.append(("assistant", out[0] or "Done. The draft is updated on the right."))
                st.rerun()
    with right:
        d = st.session_state.draft
        st.subheader(d["header"].get("title") or "Your RFQ draft")
        if not (d["header"] or d["line_items"]):
            st.caption("Builds here as you talk.")
        if d["header"]:
            st.markdown('<table class="terms">' + "".join(f"<tr><td>{E(k.replace('_', ' ').capitalize())}</td><td>{E(str(v))}</td></tr>"
                                                         for k, v in d["header"].items() if k != "title") + "</table>", unsafe_allow_html=True)
        if d["line_items"]:
            st.markdown(f"**Line items ({len(d['line_items'])})**")
            st.dataframe(pd.DataFrame(d["line_items"]).rename(columns=lambda c: c.replace("_", " ").capitalize()), hide_index=True, width="stretch", height=280)
        if d["questionnaire"]:
            st.markdown("**Supplier questionnaire**")
            st.dataframe(pd.DataFrame(d["questionnaire"]).rename(columns=lambda c: c.replace("_", " ").capitalize()), hide_index=True, width="stretch")
        if d["terms"]:
            st.markdown("**Terms**\n" + "\n".join(f"- {t}" for t in d["terms"]))
        if d["line_items"]:
            st.markdown("**Send to:** " + ", ".join(d["vendors"]))
            chosen = st.pills("Send by", ["Email", "WhatsApp Business", "Vendor portal"], selection_mode="multi",
                              default=["Email", "WhatsApp Business"],
                              help="Vendors answer wherever suits them. Small vendors often reply on WhatsApp; larger ones may prefer a portal. "
                                   "Replies from every channel land in Vendor replies, and nobody is forced into a template.") or []
            channel = " + ".join(chosen)
            if st.button("Send RFQ to vendors", type="primary", disabled=not chosen):
                st.session_state.sent = channel
                log(load_decisions(), "rfq sent", f"Sent to {len(d['vendors'])} vendors by {channel} (simulated)")
            if st.session_state.get("sent"):
                st.success(f"Sent to {len(d['vendors'])} vendors by {st.session_state.sent} (simulated). Replies are tracked below.")
    if st.session_state.get("sent"):
        st.subheader("Replies")
        _reply_tracker(get_state(), key="draft")
    _next("replies", "Next: see the replies as they arrive")

FORMAT = {".xlsx": "Excel", ".xlsm": "Excel", ".pdf": "PDF", ".docx": "Word", ".jpg": "Photo", ".jpeg": "Photo", ".png": "Photo"}


def _reply_meta(vdir):
    """Who replied, when, on which channel and in what format, taken from what actually arrived."""
    from email.utils import parsedate_to_datetime
    sender, when = vdir.name.split("_")[-1].title(), None
    mail = vdir / "email.txt"
    if mail.exists():
        for ln in mail.read_text(errors="ignore").splitlines()[:12]:
            if ln.lower().startswith("from:"):
                sender = ln[5:].split("<")[0].strip() or sender
            if ln.lower().startswith("date:"):
                try:
                    when = parsedate_to_datetime(ln[5:].strip())
                except Exception:
                    pass
    files = [f for f in vdir.iterdir() if f.is_file()]
    kinds = []
    for f in files:
        k = FORMAT.get(f.suffix.lower())
        if k and k not in kinds:
            kinds.append(k)
    photo = "Photo" in kinds
    return dict(sender=sender, when=when, channel="WhatsApp" if photo else "Email",
                formats=kinds or ["Email text"], attachments=sum(1 for f in files if f.name != "email.txt"))


def _reply_tracker(s, key="tracker"):
    """The handoff between sending the RFQ and reading the replies: one row per vendor, as they came in."""
    from core.config import EXTRACT_CACHE
    dirs = vendor_dirs()
    rows, unread = [], []
    for d in sorted(dirs, key=lambda d: (_reply_meta(d)["when"] is None, _reply_meta(d)["when"] or 0)):
        m = _reply_meta(d)
        name = s.vendor_names.get(d.name) or m["sender"]
        read = (EXTRACT_CACHE / f"{d.name}.json").exists() and d.name in s.extractions
        if read:
            ns = [n for n in s.norms if n.vendor == d.name]
            priced = sum(1 for n in ns if n.status != "missing")
            status = pill("Read", "good") + f'<div class="sub">{priced} of 30 priced</div>'
        else:
            unread.append(d)
            status = pill("Not read yet", "check")
        when = m["when"].strftime("%a %d %b, %H:%M") if m["when"] else "–"
        rows.append(f"""<tr><td><b>{E(name)}</b></td><td class="n">{when}</td><td>{m['channel']}</td>
            <td>{E(' + '.join(m['formats']))}{f'<div class="sub">{m["attachments"]} file{"s" if m["attachments"] != 1 else ""}</div>' if m['attachments'] else ''}</td>
            <td>{status}</td></tr>""")
    st.markdown('<table class="vt"><thead><tr><th>Vendor</th><th>Received</th><th>Channel</th><th>Format</th><th>Status</th></tr></thead>'
                f'<tbody>{"".join(rows)}</tbody></table>', unsafe_allow_html=True)
    st.write("")
    c1, c2 = st.columns([2, 3])
    if unread and c1.button(f"Read {len(unread)} repl{'ies' if len(unread) != 1 else 'y'}", type="primary",
                            disabled=not api_key_present(), key=f"read_{key}"):
        from core.pipeline import run_many
        with st.spinner(f"Reading {len(unread)} replies, usually 1-3 minutes"):
            run_many(unread)
        refresh(); st.rerun()
    if not unread:
        with c1:
            _link("compare", "Open the comparison")


# ================================================================== Vendor replies
@st.cache_data(show_spinner=False, max_entries=64)
def _pdf_pages(path: str, resolution: int, mtime: float) -> list[bytes]:
    from pathlib import Path
    from core import readers
    return readers.pdf_page_images(Path(path), resolution)


def page_replies():
    from core import readers
    s = get_state()
    header("Vendor replies", "What each vendor sent, next to what was read from it.")
    key_notice()
    with st.expander(f"Inbox: {len(vendor_dirs())} replies to {config.RFX_ID}", expanded=not s.ready()):
        _reply_tracker(s, key="replies")
    dirs = vendor_dirs()
    names = {d.name: s.vendor_names.get(d.name, d.name.split("_")[-1].title()) for d in dirs}
    pick = st.segmented_control("Vendor", [d.name for d in dirs], format_func=lambda k: short(names[k]),
                                default=dirs[0].name if dirs else None, label_visibility="collapsed") or (dirs[0].name if dirs else None)
    if not pick:
        return
    vdir = INBOX / pick
    ex = s.extractions.get(pick)
    left, right = st.columns([4, 8], gap="large")
    with left:
        st.subheader("What they sent")
        old = sorted((vdir / "_superseded").glob("*")) if (vdir / "_superseded").exists() else []
        if old:
            st.caption(f"Revised quote: {len(old)} earlier version{'s' if len(old) != 1 else ''} kept for the audit trail and no longer counted.")
        for f in sorted((p for p in vdir.iterdir() if p.is_file() and not p.name.startswith("_")), key=lambda p: (p.name != "email.txt", p.name)):
            label = "Email" if f.name == "email.txt" else f.name
            with st.expander(label, expanded=f.suffix.lower() in (".jpg", ".jpeg", ".png")):
                suf = f.suffix.lower()
                if suf in (".jpg", ".jpeg", ".png"):
                    st.image(str(f), width="stretch")
                elif suf in (".txt", ".eml"):
                    st.text(f.read_text(errors="ignore"))
                elif suf == ".pdf":
                    for img in _pdf_pages(str(f), 70, f.stat().st_mtime):
                        st.image(img, width="stretch")
                elif suf in (".xlsx", ".xlsm"):
                    import openpyxl
                    wb = openpyxl.load_workbook(f, data_only=True)
                    for ws in wb.worksheets:
                        st.caption(f"Sheet: {ws.title}")
                        st.dataframe(pd.DataFrame(ws.values).fillna("").astype(str), hide_index=True, width="stretch")
                elif suf == ".docx":
                    st.text(readers.read_docx(f))
        if ex and st.button("Read this reply again", disabled=not api_key_present()):
            with st.spinner("Reading, usually under a minute"):
                ok = ai(run_extraction, vdir)
            if ok is not None:
                refresh(); st.rerun()
    with right:
        st.subheader("What was read")
        if not ex:
            st.info("This reply hasn't been read yet.")
            if st.button("Read this reply", type="primary", disabled=not api_key_present()):
                with st.spinner("Reading, usually under a minute"):
                    ok = ai(run_extraction, vdir)
                if ok is not None:
                    refresh(); st.rerun()
            return
        t = ex.get("terms", {})
        disc = "; ".join(f"{d.get('percent')}% if {d.get('condition')}" for d in ex.get("discounts", [])) or "None found"
        rows = [("Currency", t.get("currency") or "-"), ("GST", GST.get(t.get("gst"), t.get("gst") or "-")),
                ("Freight", FREIGHT.get(t.get("freight"), t.get("freight") or "-")),
                ("Payment", f"{t.get('payment_days')} days" if t.get("payment_days") else "Not stated"),
                ("Lead time", f"{t.get('lead_time_days')} days" if t.get("lead_time_days") else "Not stated"),
                ("Discounts", disc)]
        st.markdown('<table class="terms">' + "".join(f"<tr><td>{a}</td><td><b>{E(str(b))}</b></td></tr>" for a, b in rows) + "</table>", unsafe_allow_html=True)
        unsure = [str(u) for u in ex.get("unreadable_or_uncertain", [])]
        for u in [u for u in unsure if u.startswith("Possible instruction")]:   # security warnings are never hidden
            st.markdown(f"{pill('Security', 'stop')} {E(u)}", unsafe_allow_html=True)
        notes = [u for u in unsure if not u.startswith("Possible instruction")]
        if notes or ex.get("response_summary"):
            with st.expander(f"Reader's notes ({len(notes)})" if notes else "Reader's summary"):
                if ex.get("response_summary"):
                    st.write(ex["response_summary"])
                for u in notes[:10]:
                    st.markdown(f"- {E(u)}")
        prices, not_quoted = [], []
        for n in [n for n in s.norms if n.vendor == pick]:
            if n.status == "missing":
                not_quoted.append(n.line_id)
                continue
            worst = max((f.severity for f in n.flags), key=lambda x: ["info", "warn", "critical"].index(x), default="")
            prices.append({"Line": n.line_id, "Their item": n.vendor_item_text, "As they wrote it": n.source_quote,
                           "Landed ₹ per unit": f"{n.landed:,.2f}" if n.landed is not None else "unusable",
                           "Possible readings": " or ".join(f"{c['landed']:.2f}" for c in n.candidates) if len(n.candidates) > 1 else "",
                           "Status": ("Lower spec" if not n.spec_compliant else "Held out" if not n.awardable
                                      else "Confirm" if n.status == "review" else "Read")})
        st.markdown(f"**Prices, converted to landed cost** · {len(prices)} of 30 items priced")
        if prices:
            pdf = pd.DataFrame(prices)
            if not pdf["Possible readings"].astype(bool).any():
                pdf = pdf.drop(columns=["Possible readings"])
            st.dataframe(pdf, hide_index=True, width="stretch", height=min(38 * (len(prices) + 1) + 3, 420),
                         column_config={"Line": st.column_config.TextColumn(width=48),
                                        "Landed ₹ per unit": st.column_config.TextColumn(width="small"),
                                        "Possible readings": st.column_config.TextColumn(width="small"),
                                        "Status": st.column_config.TextColumn(width="small"),
                                        "Attention": st.column_config.TextColumn(width="small")})
        if not_quoted:
            st.caption(f"Not quoted ({len(not_quoted)}): {', '.join(not_quoted)}")
        ev = s.q_evals.get(pick)
        if ev:
            lbl, cls = STATUS[s.verdicts[pick]]
            st.markdown(f"**Quality questionnaire** {pill(lbl, cls)}", unsafe_allow_html=True)
            qmeta = {q["q_id"]: q for q in extract.load_questionnaire()}
            ans = {a.get("q_id"): a.get("answer") for a in ex.get("questionnaire", [])}
            short_q = {q: Q_SHORT.get(q, q) for q in qmeta}
            bad = [(k, r) for k, r in sorted(ev["results"].items()) if r.get("status") != "pass" and qmeta.get(k, {}).get("type") != "Info"]
            for k, r in bad:
                tag = pill("Fail", "stop") if r.get("status") == "fail" else pill("Unclear", "check")
                st.markdown(f"{tag} <b>{E(short_q.get(k, k))}</b>: {E(r.get('reason', ''))}", unsafe_allow_html=True)
            if not bad:
                st.caption("Every mandatory answer passes.")
            res_lbl = {"pass": "Pass", "fail": "Fail", "unclear": "Unclear"}
            with st.expander("All answers"):
                st.dataframe(pd.DataFrame([{"Question": qmeta.get(k, {}).get("question", k), "Their answer": ans.get(k) or "No answer",
                                            "Result": res_lbl.get(r.get("status"), r.get("status")),
                                            "Why": r.get("reason", "") + (f" ({r['rule_note']})" if r.get("rule_note") else "")}
                                           for k, r in sorted(ev["results"].items())]), hide_index=True, width="stretch")

    with st.expander("Add a vendor reply (any format)"):
        existing = {d.name: s.vendor_names.get(d.name, d.name) for d in vendor_dirs()}
        kind = st.radio("This is", ["A new vendor", "A revised quote from a vendor already here"], horizontal=True, key="add_kind")
        revise = None
        if kind.startswith("A revised"):
            revise = st.selectbox("Which vendor revised their quote?", list(existing), format_func=lambda k: existing[k], key="revise_of")
            name = existing.get(revise, "")
            st.caption("Only the new version counts. Earlier files are archived.")
        else:
            name = st.text_input("Vendor name", max_chars=80)
        files = st.file_uploader("Files: Excel, PDF, Word, photo, CSV or a saved email", accept_multiple_files=True,
                                 type=["xlsx", "xlsm", "pdf", "docx", "jpg", "jpeg", "png", "webp", "csv", "txt", "eml"])
        body = st.text_area("Or paste the email / WhatsApp text")
        st.caption("Old .xls or .doc files and iPhone .heic photos: save as .xlsx, .docx or .jpg first.")
        if st.button("Add and read", disabled=not (name.strip() and (files or body.strip()) and api_key_present())):
            import hashlib
            seen = {hashlib.sha256(f.read_bytes()).hexdigest(): d.name for d in vendor_dirs() for f in d.iterdir() if f.is_file()}
            dup = [(f.name, seen[h]) for f in (files or []) if (h := hashlib.sha256(f.getvalue()).hexdigest()) in seen]
            if dup:
                st.error("Already received: " + "; ".join(f"{a} is the same file as {s.vendor_names.get(b, b)}'s reply" for a, b in dup)
                         + ". Nothing was added, so nothing is counted twice.")
                st.stop()
            if revise:
                from datetime import datetime as _dt
                nd = INBOX / revise
                arch = nd / "_superseded" / _dt.now().strftime("%Y%m%d-%H%M%S")
                arch.mkdir(parents=True)
                for f in [p for p in nd.iterdir() if p.is_file()]:
                    f.rename(arch / f.name)
                log(load_decisions(), "revised quote", f"{name}: earlier files archived ({arch.name}); reading the revision")
            else:
                base = "vendor_X_" + ("".join(c for c in name.lower() if c.isalnum())[:20] or "new")
                slug, k = base, 2
                while (INBOX / slug).exists():
                    slug, k = f"{base}{k}", k + 1
                nd = INBOX / slug
                nd.mkdir()
            if body.strip():
                (nd / "email.txt").write_text(f"From: {name}\nSubject: Quote for {config.RFX_ID}\n\n{body}")
            for f in files or []:
                safe = "".join(c for c in f.name if c.isalnum() or c in "._- ")[:80] or "file"
                if safe == "email.txt":
                    safe = "attachment_email.txt"
                (nd / safe).write_bytes(f.getvalue())
            with st.spinner("Reading, usually under a minute"):
                ok = ai(run_extraction, nd)
            if ok is not None:
                refresh(); st.rerun()
            else:
                st.caption("The files are saved; try Read this reply again in a minute.")
    added = [d for d in vendor_dirs() if d.name.startswith("vendor_X_")]
    if added:
        with st.expander("Remove a vendor you added"):
            rm = st.selectbox("Vendor", [d.name for d in added], format_func=lambda k: s.vendor_names.get(k, k))
            if st.button("Remove this vendor and its results"):
                import shutil
                from core.config import EXTRACT_CACHE
                shutil.rmtree(INBOX / rm, ignore_errors=True)
                for f in EXTRACT_CACHE.glob(f"{rm}.*json"):
                    f.unlink()
                log(load_decisions(), "vendor removed", s.vendor_names.get(rm, rm))
                refresh(); st.rerun()
    _next("compare", "Next: compare all vendors like for like")

# ================================================================== Comparison
def page_compare():
    s = get_state()
    header("Comparison", "Every price in ₹ per unit, without GST, delivered to Waluj. Click any price to see where it came from.")
    if not s.ready():
        need_replies(); return
    lines = extract.load_rfx_lines()
    vendors = list(s.extractions)
    by = {(n.vendor, n.line_id): n for n in s.norms}
    tab_p, tab_s, tab_q = st.tabs(["Prices", "Vendor scorecard", "Questionnaire, terms and documents"])
    with tab_p:
        data, picked = _price_table(s, lines, vendors, by)
        if data:
            v, lid = picked
            st.markdown(f'<div class="panel-h" style="margin-top:14px">Where this price came from</div>', unsafe_allow_html=True)
            _evidence(s, by.get((v, lid)))
            with st.expander("Or pick an item and vendor"):
                c1, c2 = st.columns(2)
                lid2 = c1.selectbox("Item", [l["line_id"] for l in lines], index=[l["line_id"] for l in lines].index(lid),
                                    format_func=lambda x: f"{x} · {next(l['description'] for l in lines if l['line_id'] == x)}", key="ev_line")
                v2 = c2.selectbox("Vendor", vendors, index=vendors.index(v), format_func=lambda k: s.vendor_names[k], key="ev_vendor")
                if (v2, lid2) != (v, lid):
                    st.session_state["_picked"] = (v2, lid2); st.rerun()
    with tab_s:
        _scorecard(s)
    with tab_q:
        _vendor_summary(s, vendors)
    if data:
        st.download_button("Download Excel", _comparison_xlsx(s, pd.DataFrame(data)), file_name="comparison.xlsx",
                           help="Prices with their status, scorecard, questionnaire and terms in one workbook")
    _next("issues", "Next: resolve what could change the award")


def _price_table(s, lines, vendors, by):
    """The comparison grid. Returns the rows and the (vendor, item) whose evidence to show: the clicked cell,
    or the awarded price on the first item."""
    res = s.award()
    won = {r["line_id"]: r for r in res["rows"]}
    disc = {d["vendor"]: d["percent"] for d in res["discounts_applied"]}
    c1, c2 = st.columns([3, 2])
    view = c1.segmented_control("Show", ["All items", "Items to check", "Items with no qualified price"], default="All items",
                                label_visibility="collapsed") or "All items"
    only_q = c2.toggle("Only qualified vendors", value=False)
    disc_note = (f'<span>† after {", ".join(f"{short(s.vendor_names.get(v, v))} {p:g}%" for v, p in disc.items())} volume discount</span>'
                 if disc else "")
    st.markdown(f"""<div class="legend"><span><span class="sw" style="background:#DCEFE4"></span>Awarded</span>
        <span><span class="sw" style="background:{CHECK_BG}"></span>Needs your check</span>
        <span><span class="sw" style="background:{STOP_BG}"></span>Lower spec than asked</span>
        <span>– Not quoted</span><span>* Vendor not qualified</span>{disc_note}</div>""", unsafe_allow_html=True)
    shown = [v for v in vendors if (not only_q or v in s.eligible)]
    colname = {v: short(s.vendor_names[v]) + ("" if v in s.eligible else " *") for v in shown}
    data, style = [], []
    for l in lines:
        lid = l["line_id"]
        w = won.get(lid) or {}
        best_v = w.get("vendor")
        needs_check = any(by.get((v, lid)) and (by[(v, lid)].status == "review" or not by[(v, lid)].awardable) for v in vendors)
        if view == "Items to check" and not needs_check:
            continue
        if view == "Items with no qualified price" and best_v is not None:
            continue
        row = {"Item": lid, "Description": l["description"], "Qty / year": f"{int(l['annual_qty']):,}",
               "Awarded to": (f"{short(w['vendor_name'])} ₹{w['unit_price']:,.2f}{' †' if best_v in disc else ''}" if best_v
                              else "No qualified price")}
        srow = {"Awarded to": f"color:{KRAFT}; font-weight:600" if best_v else f"color:{STOP}"}
        for v in shown:
            n = by.get((v, lid))
            priced = n is not None and n.status != "missing" and n.landed is not None
            row[colname[v]] = f"{n.landed:,.2f}" if priced else ("check" if (n and n.status == "review") else "–")
            css = ""
            if n is None or n.status == "missing":
                css = f"color:{MUTED}"
            elif n.landed is None or not n.awardable or n.status == "review":
                css = f"background-color:{CHECK_BG}; color:{CHECK}"
            elif not n.spec_compliant and not n.spec_accepted:
                css = f"background-color:{STOP_BG}; color:{STOP}"
            if v == best_v:
                css = "background-color:#DCEFE4; font-weight:700"
            srow[colname[v]] = css
        data.append(row); style.append(srow)
    default = (won.get(lines[0]["line_id"], {}).get("vendor") or vendors[0], lines[0]["line_id"])
    if not data:
        st.success("No items match this filter.")
        return data, st.session_state.get("_picked", default)
    df = pd.DataFrame(data)
    sty = df.style.apply(lambda _: pd.DataFrame([{**{c: "" for c in df.columns}, **r} for r in style], columns=df.columns), axis=None) \
        .set_properties(subset=[colname[v] for v in shown] + ["Qty / year"], **{"text-align": "right"})
    ev = st.dataframe(sty, hide_index=True, width="stretch", height=min(35 * (len(df) + 1) + 3, 528), key="cmp_grid",
                      on_select="rerun", selection_mode="single-cell",
                      column_config={colname[v]: st.column_config.Column(width="small") for v in shown} |
                      {"Item": st.column_config.Column(width=52), "Description": st.column_config.Column(width="medium"),
                       "Qty / year": st.column_config.Column(width="small"), "Awarded to": st.column_config.Column(width="medium")})
    cells = (ev.selection.get("cells") if ev and getattr(ev, "selection", None) else None) or []
    if cells:
        r_i, col = cells[0][0], cells[0][1]
        if 0 <= r_i < len(data):
            lid = data[r_i]["Item"]
            inv = {c: v for v, c in colname.items()}
            v = inv.get(col) or (won.get(lid, {}).get("vendor")) or st.session_state.get("_picked", default)[0]
            st.session_state["_picked"] = (v, lid)
    return data, st.session_state.get("_picked", default)


def _next(page_key, label):
    """One obvious way forward at the end of every page."""
    st.write("")
    page = st.session_state.get("_pages", {}).get(page_key)
    if page is not None:
        st.page_link(page, label=label, icon=":material/arrow_forward:")


def _scorecard(s):
    from core.scorecard import DIMENSIONS, DEFAULT_WEIGHTS, build
    st.caption("A cross-check for approvers. The award still follows the RFQ rule: cheapest qualified price per item.")
    with st.expander("Change weights · how scores work"):
        cols = st.columns(5)
        w = {k: cols[i].number_input(k.title(), 0, 100, DEFAULT_WEIGHTS[k], 5, key=f"w_{k}") for i, k in enumerate(DEFAULT_WEIGHTS)}
        for k, txt in DIMENSIONS.items():
            st.markdown(f"- {txt}")
    rows = build(s, w)
    tot_w = sum(w.values()) or 1

    def bar(x):
        return f'<div class="sc"><div class="track"><div style="width:{x:.0f}%"></div></div><span class="v">{x:.0f}</span></div>'
    body = []
    for r in rows:
        lbl, cls = STATUS.get(r["status"], ("Unknown", "muted"))
        notes = []
        if r["price_premium"] is not None:
            notes.append("cheapest on its items" if r["price_premium"] < 0.005 else f"{r['price_premium']:+.0%} vs cheapest")
        if r["failed_mandatory"]:
            notes.append("fails " + ", ".join(r["failed_mandatory"]))
        if r["lower_spec_items"]:
            notes.append(f"{r['lower_spec_items']} items at lower spec")
        body.append(f"""<tr><td class="n"><b>{r['rank']}</b></td><td><b>{E(r['vendor_name'])}</b><div class="sub">{pill(lbl, cls)}</div></td>
            <td><span class="total">{r['total']:.0f}</span></td>
            {''.join(f'<td>{bar(r[k])}</td>' for k in DEFAULT_WEIGHTS)}
            <td class="watch">{E('; '.join(notes)) or '–'}</td></tr>""")
    heads = "".join(f'<th><abbr title="{DIMENSIONS[k]}">{k.title()}</abbr> <span class="sub">{w[k] / tot_w:.0%}</span></th>' for k in DEFAULT_WEIGHTS)
    st.markdown(f'<table class="vt"><thead><tr><th>#</th><th>Vendor</th><th>Overall</th>{heads}<th>Watch</th></tr></thead>'
                f'<tbody>{"".join(body)}</tbody></table>', unsafe_allow_html=True)
    top = rows[0] if rows else None
    if top and not top["eligible"]:
        st.markdown(f'<div class="warn-line">⚠ {E(top["vendor_name"])} ranks first overall but is not qualified, so it cannot win under the RFQ '
                    f'rule. Its open questionnaire items are in Open issues.</div>', unsafe_allow_html=True)
    st.session_state["_scorecard_weights"] = w


def _vendor_rows(s, vendors):
    """Questionnaire answers, commercial terms and attached documents, one column per vendor."""
    qs = extract.load_questionnaire()
    mark = {"pass": "✓", "fail": "✗", "unclear": "?"}
    rows, kinds = [], []

    def add(label, vals, kind="text"):
        rows.append({"": label, **vals}); kinds.append(kind)

    add("Qualification", {short(s.vendor_names[v]): STATUS.get(s.status[v], ("-",))[0] for v in vendors}, "status")
    for q in qs:
        vals = {}
        for v in vendors:
            ans = {a_.get("q_id"): a_.get("answer") for a_ in s.extractions[v].get("questionnaire", [])}.get(q["q_id"]) or "No answer"
            res = s.q_evals.get(v, {}).get("results", {}).get(q["q_id"], {})
            vals[short(s.vendor_names[v])] = f"{mark.get(res.get('status'), '·')} {ans}"
        add(f"{q['q_id']} {q['question'].split('?')[0][:58]}? ({q['type']})", vals, "q")
    for label, fn in [("Payment terms", lambda t: f"{t.get('payment_days')} days" if t.get("payment_days") else "Not stated"),
                      ("Lead time", lambda t: f"{t.get('lead_time_days')} days" if t.get("lead_time_days") else "Not stated"),
                      ("Freight", lambda t: FREIGHT.get(t.get("freight"), t.get("freight") or "-")),
                      ("GST", lambda t: GST.get(t.get("gst"), t.get("gst") or "-")),
                      ("Currency", lambda t: t.get("currency") or "-"),
                      ("Price validity", lambda t: t.get("validity") or "Not stated"),
                      ("Price variation clause", lambda t: t.get("price_variation_clause") or "None stated"),
                      ("Minimum order", lambda t: t.get("moq_or_min_order") or "None stated")]:
        add(label, {short(s.vendor_names[v]): fn(s.extractions[v].get("terms", {})) for v in vendors})
    add("Discounts", {short(s.vendor_names[v]): "; ".join(f"{d.get('percent')}% if {d.get('condition')}" for d in s.extractions[v].get("discounts", []))
                      or "None" for v in vendors})
    add("Documents attached", {short(s.vendor_names[v]): ", ".join(f for f in s.extractions[v].get("_meta", {}).get("files", []) if f != "email.txt") or "None"
                               for v in vendors})
    add("What the documents show", {short(s.vendor_names[v]): "; ".join(f"{d.get('fact_type', '').replace('_', ' ')}: {d.get('value')}"
                                                                         for d in s.extractions[v].get("document_facts", []) if isinstance(d, dict)) or "-"
                                    for v in vendors})
    return rows, kinds


def _vendor_summary(s, vendors):
    st.caption("✓ pass · ✗ fail · ? unclear")
    rows, kinds = _vendor_rows(s, vendors)
    df = pd.DataFrame(rows)

    def color(val, kind):
        if kind == "status":
            return {"Qualified": f"background-color:{GOOD_BG}; color:{GOOD}", "Not qualified": f"background-color:{STOP_BG}; color:{STOP}",
                    "Documents pending": f"background-color:{CHECK_BG}; color:{CHECK}",
                    "Included by you": f"background-color:{GOOD_BG}; color:{GOOD}"}.get(val, "")
        if kind == "q" and isinstance(val, str):
            return {"✓": f"color:{GOOD}", "✗": f"background-color:{STOP_BG}; color:{STOP}", "?": f"background-color:{CHECK_BG}; color:{CHECK}"}.get(val[:1], "")
        return ""
    sty = df.style.apply(lambda d: pd.DataFrame([[("" if c == "" else color(d.iloc[i][c], kinds[i])) for c in d.columns] for i in range(len(d))],
                                                columns=d.columns, index=d.index), axis=None)
    st.dataframe(sty, hide_index=True, width="stretch", height=35 * (len(df) + 1) + 3,
                 column_config={"": st.column_config.Column(width="medium")})


def _comparison_xlsx(s, prices: pd.DataFrame) -> bytes:
    import io
    rows, _ = _vendor_rows(s, list(s.extractions))
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as xw:
        prices.to_excel(xw, sheet_name="Landed prices", index=False)
        from core.scorecard import build
        sc = pd.DataFrame(build(s, st.session_state.get("_scorecard_weights")))
        if not sc.empty:
            sc["failed_mandatory"] = sc["failed_mandatory"].apply(", ".join)
            sc.to_excel(xw, sheet_name="Vendor scorecard", index=False)
        pd.DataFrame(rows).to_excel(xw, sheet_name="Questionnaire & terms", index=False)
        # every price with its status, so missing and uncertain values survive outside the app
        pd.DataFrame([{"Item": x.line_id, "Vendor": x.vendor_name,
                       "Landed ₹ per unit": x.landed,
                       "Status": ("Not quoted" if x.status == "missing" else "Price unusable" if x.landed is None
                                  else "Held out until confirmed" if not x.awardable else "To confirm" if x.status == "review"
                                  else "Lower spec" if not x.spec_compliant else "Read"),
                       "Possible readings": " / ".join(f"{c['landed']:.2f}" for c in x.candidates) if len(x.candidates) > 1 else "",
                       "Vendor wrote": x.source_quote, "Where": x.source,
                       "Warnings": " | ".join(f.text for f in x.flags if f.severity != "info")}
                      for x in s.norms]).to_excel(xw, sheet_name="Price details", index=False)
    return buf.getvalue()


def _verdict(s, n) -> str:
    """One plain sentence a buyer can act on: can this price be used as it is, and if not, what to do."""
    def box(cls, head, body):
        return f'<div class="verdict {cls}"><b>{head}</b> {E(body)}</div>'
    crit = [f for f in n.flags if f.severity == "critical"]
    if n.status == "missing":
        return box("muted", "Not quoted.", "Never filled in or guessed; this item goes to another vendor.")
    if n.landed is None:
        return box("stop", "Can't be used.", (crit[0].text if crit else "No usable price.") + " Ask the vendor; Open issues drafts the email.")
    if not n.awardable:
        return box("check", "Kept out of the award until you confirm it.", crit[0].text if crit else "")
    if len(n.candidates) > 1 and not n.resolved_by_buyer:
        opts = " or ".join(f"₹{c['landed']:,.2f}" for c in n.candidates)
        return box("check", "Needs your check.", f"The vendor's figure could mean {opts} landed. The higher one is used until the vendor "
                   f"confirms, so a doubt never makes them look cheaper. Confirm it in Open issues.")
    if not n.spec_compliant and not n.spec_accepted:
        return box("stop", "Lower spec than asked, so it can't win.", next((f.text for f in crit if f.type == "spec"), ""))
    if n.vendor not in s.eligible:
        return box("muted", "Read clearly, but this vendor isn't qualified yet,", "so this price can't win until they pass the questionnaire.")
    warns = [f.text for f in n.flags if f.severity == "warn"]
    if warns:
        return box("check", "Usable, with an assumption to know:", warns[0])
    return box("good", "Read clearly and used as is.", "")


def _evidence(s, n):
    if not n:
        return
    val = "not quoted" if n.landed is None or n.status == "missing" else f"₹{n.landed:,.2f} landed per unit"
    st.markdown(f"**{E(n.vendor_name)}, {n.line_id}:** {val}")
    st.markdown(_verdict(s, n), unsafe_allow_html=True)
    left, right = st.columns([6, 5], gap="large")
    with left:
        st.markdown("**Steps**")
        for stp in n.steps:
            st.markdown(f'<div class="step">{E(stp)}</div>', unsafe_allow_html=True)
        if n.flags:
            st.markdown("**Things to know**")
        for f in n.flags:
            cls = {"critical": "stop", "warn": "check", "info": "muted"}[f.severity]
            lbl = {"critical": "Blocks", "warn": "Check", "info": "Note"}[f.severity]
            st.markdown(f"{pill(lbl, cls)} {E(f.text)}", unsafe_allow_html=True)
        if len(n.candidates) > 1:
            st.table(pd.DataFrame([{"If the value is": c["label"], "Landed ₹": f"{c['landed']:,.2f}"} for c in n.candidates]))
    with right:
        _show_source(n)


def _show_source(n):
    import re
    from core import readers
    vdir = INBOX / n.vendor
    if not vdir.exists():
        return
    st.markdown("**In the vendor's own document**")
    ev = readers.load_vendor(vdir)
    lines = [ln for _, body in ev.texts for ln in body.splitlines()]
    loc = (n.source or "").strip()
    hit = readers.locate(lines, n.source, n.source_quote)
    if hit is not None:
        def pretty(ln):
            m_x = re.match(r"(.+?\.xls[xm]?)!([^!]+)!R(\d+):\s*(.*)", ln)
            if m_x:   # Excel: show the row and its cells, without the file name on every line
                return f"Row {m_x.group(3)}  " + re.sub(r"\b[A-Z]{1,3}\d+=", "", m_x.group(4)).replace("'", "")
            if " | " in ln:   # email, PDF, Word: show the line number and the words
                head, body = ln.split(" | ", 1)
                return f"{head.split(':')[-1]:<6}{body}"
            return ln
        parts = loc.split("!")
        if ".xls" in loc and len(parts) >= 3:
            st.caption(f"From {E(parts[0])}, sheet {E(parts[1])}, cell {E(parts[-1])}")
        elif loc:
            st.caption(f"From {E(loc)}")
        st.code("\n".join(("▶ " if i == hit else "  ") + pretty(lines[i]) for i in range(max(0, hit - 2), min(len(lines), hit + 3))),
                language=None, wrap_lines=True)
    m = re.search(r"([\w\-. ]+\.pdf):p(\d+)", loc)
    if m and (vdir / m.group(1).strip()).exists():
        pf = vdir / m.group(1).strip()
        pages = _pdf_pages(str(pf), 90, pf.stat().st_mtime)
        k = int(m.group(2)) - 1
        if 0 <= k < len(pages):
            st.image(pages[k], caption=f"{m.group(1).strip()}, page {k + 1}", width="stretch")
    imgs = [f for f in vdir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    if imgs and (any(f.name in loc for f in imgs) or any(k in loc.lower() for k in ("jpg", "png", "jpeg", "image", "photo")) or hit is None):
        st.image(str(imgs[0]), width="stretch", caption=imgs[0].name)
    if hit is None and not m and not imgs:
        st.caption("The exact spot wasn't found; open the original in Vendor replies.")


# ================================================================== Open issues
def _stake(i):
    if i.get("held_out"):
        return 0, "kept out of the award until the vendor gives a usable price"
    if i["kind"] == "outlier":
        return abs(i["award_swing"]), "lower award cost if you accept this price (kept out until you do)"
    if i["kind"] == "eligibility" and i.get("newly_covered"):
        return i["newly_covered_value"], f"of spend on {len(i['newly_covered'])} lines with no qualified quote today"
    if i["kind"] == "eligibility":
        if i["award_swing"] > 0:
            return i["award_swing"], "lower award if they qualify"
        if i["award_swing"] < 0:
            return -i["award_swing"], "higher award cost if this vendor qualifies (volume-discount effect)"
        return 0, "no change in award cost if this vendor qualifies"
    if i["kind"] == "spec":
        return abs(i["award_swing"]), "lower award cost if you accept the lower spec as a substitute (kept out until you do)"
    if i["award_swing"]:
        return i["award_swing"], "difference in award cost between the possible readings"
    if i.get("exposure_in_award"):
        return i["exposure_in_award"], "of the current award depends on this assumption"
    return i["quote_value_swing"], "of quoted value affected; this vendor isn't in the current award"


def _issue_card(s, i, compact=False):
    stopper = i["decision_relevant"] and i["kind"] not in ("freight", "fx", "history")
    cls = "stopper" if stopper else ("" if i["decision_relevant"] else "quiet")
    stake, stake_lbl = _stake(i)
    flips = i["lines_flipping"]
    if i["kind"] == "eligibility":
        short_b, full = _blockers(s, i["vendor"])
        detail = (f"Missing: {short_b}. " if short_b else "") + (f"Would win {len(i['lines'])} item{'s' if len(i['lines']) != 1 else ''}." if i["lines"] else "")
    else:
        full = i["title"]
        first = re.split(r"(?<=[.;])\s", i["title"], maxsplit=1)[0]
        detail = first + (f" Changes the winner on {len(flips)} item{'s' if len(flips) != 1 else ''}." if flips else "")
    st.markdown(f"""<div class="issue {cls}"><div class="head">{E(issue_headline(i))}</div>
        <div><span class="stake">{money(stake)}</span> <span class="stake-l">{stake_lbl}</span></div>
        <div class="detail">{E(detail)}</div></div>""", unsafe_allow_html=True)
    if compact:
        return
    if full and full.strip() != detail.strip():
        with st.expander("Why"):
            st.markdown("\n".join(f"- {E(x.strip())}" for x in re.split(r"\n|;\s(?=Q\d)", full) if x.strip()), unsafe_allow_html=True)
    if i.get("cascade_lines") and i.get("discount_effect"):
        st.markdown(f"Knock-on effect: under one reading a vendor's volume discount switches on or off, which moves "
                    f"{len(i['cascade_lines'])} other lines ({', '.join(i['cascade_lines'])}).")
    if i.get("outcomes"):
        st.table(pd.DataFrame([{"If the value is": o["label"], "Award total": money(o["total"]),
                                f"{short(i['vendor_name'])} is L1 on": f"{o['vendor_lines']} lines",
                                "Volume discounts": ", ".join(f"{short(s.vendor_names.get(d['vendor'], d['vendor']))} {d['percent']:g}%"
                                                              for d in o["discounts"]) or "none"} for o in i["outcomes"]]))
    dec = load_decisions()
    c1, c2, c3 = st.columns([5, 2, 2], vertical_alignment="bottom")
    key = i["id"]
    if i.get("resolvable") and i.get("outcomes"):
        opts = {o["label"]: o["index"] for o in i["outcomes"]}
        choice = c1.selectbox("Vendor confirmed it as", ["Not confirmed yet"] + list(opts), key=f"ch_{key}")
        if c2.button("Use this value", key=f"ap_{key}", type="primary", disabled=choice == "Not confirmed yet"):
            dec.setdefault("choices", {})[key] = opts[choice]
            log(dec, "value confirmed", f"{i['vendor_name']}: {issue_headline(i)} -> {choice}")
            refresh(); st.rerun()
    elif i["kind"] == "fx" and not i.get("held_out"):
        cur = float(dec.get("usd_inr") or config.USD_INR)
        rate = c1.number_input("USD rate (₹ per USD)", min_value=1.0, max_value=500.0, value=cur, step=0.1, key=f"fx_{key}",
                               help=f"Reference {config.USD_INR} ({config.USD_INR_SOURCE}). Every USD price and the award follow.")
        if c2.button("Use this rate", key=f"fxb_{key}", disabled=rate == cur):
            dec["usd_inr"] = rate
            log(dec, "FX rate set", f"USD prices now converted at {rate:g} (reference {config.USD_INR})")
            refresh(); st.rerun()
        if dec.get("usd_inr") and c3.button("Reset rate", key=f"fxr_{key}"):
            dec.pop("usd_inr")
            log(dec, "FX rate reset", f"Back to the reference rate {config.USD_INR}")
            refresh(); st.rerun()
    elif i.get("acceptable") or i["kind"] == "eligibility":
        spec, elig = i["kind"] == "spec", i["kind"] == "eligibility"
        why = c1.text_input("Reason (saved to the log)", key=f"rs_{key}", label_visibility="collapsed",
                            placeholder=("Reason to include, e.g. renewed ISO certificate received" if elig else
                                         "Reason, e.g. Quality approved 120 GSM after a BCT test" if spec else
                                         "Reason, e.g. vendor confirmed in writing on 9 Oct"))
        label = "Include" if elig else "Accept spec" if spec else "Accept price"
        if c2.button(label, key=f"in_{key}", disabled=not why, help="Saved to the decision log with your reason"):
            if elig:
                dec.setdefault("eligibility", {})[i["vendor"]] = "include"
                log(dec, "vendor included", f"{i['vendor_name']}: {why}")
            else:
                dec.setdefault("accepted", {})[key] = why
                log(dec, "price accepted" if not spec else "substitute accepted", f"{i['vendor_name']}: {issue_headline(i)} ({why})")
            refresh(); st.rerun()
    if not (i["kind"] == "fx" and dec.get("usd_inr")):
        if c3.button("Email vendor", key=f"cl_{key}", disabled=not api_key_present(), help="Drafts a clarification email for you to send"):
            from core.memo import draft_clarification
            with st.spinner("Drafting"):
                mail = ai(draft_clarification, i, s)
            if mail:
                st.session_state[f"mail_{key}"] = mail
                log(dec, "clarification drafted", f"{i['vendor_name']}: {issue_headline(i)}")
    if st.session_state.get(f"mail_{i['id']}"):
        st.text_area("Email draft: copy, edit and send", st.session_state[f"mail_{i['id']}"], height=230, key=f"ta_{i['id']}")
    st.write("")


def page_issues():
    s = get_state()
    header("Open issues", "Every uncertainty, ranked by how much money it can move.")
    if not s.ready():
        need_replies(); return
    issues = s.issues()
    hot = [i for i in issues if i["decision_relevant"]]
    cold = [i for i in issues if not i["decision_relevant"]]
    st.subheader(f"These change the award ({len(hot)})")
    if not hot:
        st.success("Nothing open changes the award.")
    for i in hot:
        _issue_card(s, i)
    with st.expander(f"Noted, but they don't change the award ({len(cold)})"):
        for i in cold:
            _issue_card(s, i, compact=not (i.get("acceptable") or (i["kind"] == "fx" and not i.get("held_out"))))
    dec = load_decisions()
    with st.expander(f"Decision log ({len(dec.get('log', []))} entries)"):
        if dec.get("log"):
            st.dataframe(pd.DataFrame(dec["log"]).rename(columns={"ts": "When", "actor": "Who", "action": "What", "detail": "Detail"}),
                         hide_index=True, width="stretch")
        if st.button("Reset all my decisions"):
            reset_decisions(); refresh(); st.rerun()
    _next("ask", "Next: ask a question about the award")

# ================================================================== Ask a question
SUGGESTED = [
    ("The VP's question", "Split it cheapest per line, but only among vendors who cleared the quality questionnaire?"),
    ("Supply risk", "No vendor above 70% of spend: what does that cost, and what would L1 matching save?"),
    ("A blurred price", "If Godavari's blurred 5-ply rate is 62.50, not 68.50, what changes?"),
    ("Cheap but risky", "Nordvik is cheapest on the Classic 650 shipper. What would it take to award them?"),
    ("Payment terms", "At 10% cost of capital, do 90 vs 30 days' payment change who is cheapest?"),
    ("Ranking", "Rank the vendors on price, quality, delivery and terms, as a chart, and export it."),
]


def page_ask():
    from core.analyst import Analyst
    s = get_state()
    header("Ask a question", "Answers come from the data, with every step shown.")
    key_notice()
    if not s.ready():
        need_replies(); return
    if "analyst" not in st.session_state:
        st.session_state.analyst = Analyst(s)
        if st.session_state.get("an_view") and st.session_state.get("_an_version") != st.session_state.get("_data_version"):
            # the data changed after these answers: keep them on screen, but never let the model reuse their numbers
            st.session_state.an_hist = []
            st.session_state.an_view.append({"q": None, "a": None, "outputs": [], "notice": True})
        st.session_state.setdefault("an_hist", []); st.session_state.setdefault("an_view", [])
        st.session_state["_an_version"] = st.session_state.get("_data_version")
    a = st.session_state.analyst
    for turn in st.session_state.an_view:
        if turn.get("notice"):
            st.info("The data changed since these answers. Ask again for updated numbers.")
            continue
        st.chat_message("user").write(turn["q"])
        with st.chat_message("assistant"):
            _render_outputs(turn["outputs"])
            st.markdown(turn["a"])
    q = None
    if not st.session_state.an_view:
        st.caption("Try one, or type your own below.")
        cols = st.columns(3)
        for k, (lbl, sq) in enumerate(SUGGESTED):
            with cols[k % 3]:
                with st.container(border=True):
                    st.markdown(f"**{lbl}**")
                    st.markdown(f'<p class="small" style="min-height:4.6em">{sq}</p>', unsafe_allow_html=True)
                    if st.button("Ask this", key=f"sq{k}"):
                        q = sq
    typed = st.chat_input("Ask about prices, vendors, scenarios or risks", disabled=not api_key_present())
    q = typed or q
    if q:
        st.chat_message("user").write(q)
        with st.chat_message("assistant"):
            box = st.status("Working on it", expanded=False)
            names = {"sql": "Querying the comparison", "award_scenario": "Running the award engine", "chart": "Drawing a chart",
                     "export": "Preparing a download", "evidence": "Checking the source"}
            out = ai(a.ask, st.session_state.an_hist, q, on_step=lambda stp: box.write(names.get(stp["tool"], stp["tool"])))
            if out is None:
                box.update(label="Couldn't answer this time", state="error")
                return
            text, hist, outs = out
            box.update(label=f"Done · {len(outs)} step{'s' if len(outs) != 1 else ''}", state="complete")
        st.session_state.an_hist = hist
        st.session_state.an_view.append({"q": q, "a": text, "outputs": outs})
        st.rerun()
    if st.session_state.an_view and st.button("Start a new conversation"):
        st.session_state.an_hist, st.session_state.an_view = [], []
        st.rerun()
    _next("memo", "Next: write the memo and get sign-off")

def _render_outputs(outs):
    for k, o in enumerate(outs):
        if o["type"] in ("table", "award"):
            if o["type"] == "award":
                r = o["res"]
                st.markdown(f"**{o['title']}:** total {money(r['total'])} · " +
                            " · ".join(f"{short(v)} {d['lines']} lines, {money(d['value'])}" for v, d in r["by_vendor"].items()))
            else:
                st.markdown(f"**{o['title']}**")
            st.dataframe(o["df"], hide_index=True, width="stretch", height=min(38 * (len(o["df"]) + 1), 360))
        elif o["type"] == "chart":
            df, kind = o["df"], o["kind"]
            try:
                if kind in ("bar", "grouped_bar"):
                    fig = px.bar(df, x=o["x"], y=o["y"], color=o.get("color"), barmode="group", title=o["title"])
                elif kind == "line":
                    fig = px.line(df, x=o["x"], y=o["y"], color=o.get("color"), title=o["title"])
                elif kind == "scatter":
                    fig = px.scatter(df, x=o["x"], y=o["y"], color=o.get("color"), title=o["title"])
                else:
                    fig = px.density_heatmap(df, x=o["x"], y=o["y"], z=o.get("color"), title=o["title"])
                fig.update_layout(font_family="Anek Latin, sans-serif", font_color=INK, plot_bgcolor="white", paper_bgcolor="white",
                                  colorway=[INK, KRAFT, "#4F7CAC", "#6E9E80", "#B5655A"], margin=dict(l=10, r=10, t=50, b=10))
                fig.update_xaxes(gridcolor=LINE); fig.update_yaxes(gridcolor=LINE)
                st.plotly_chart(fig, width="stretch", key=f"ch{id(o)}{k}")
            except Exception as e:
                st.caption(f"The chart couldn't be drawn: {e}")
        elif o["type"] == "download":
            st.download_button(f"Download {o['title']}", o["data"], file_name=o["title"], key=f"dl{id(o)}{k}")
        elif o["type"] == "evidence":
            with st.expander(o["title"]):
                st.json(o["data"])
        if o.get("sql"):
            with st.expander("How this was worked out"):
                st.code(o["sql"], language="sql")


# ================================================================== Award memo
def page_memo():
    from core.memo import write_memo, memo_workbook
    s = get_state()
    header("Award and approvals", "Write the memo, get sign-off, download the audit trail.")
    key_notice()
    if not s.ready():
        need_replies(); return
    res = s.award()
    hot = [i for i in s.issues() if i["decision_relevant"]]
    if hot:
        st.warning(f"{len(hot)} open issue{'s' if len(hot) != 1 else ''} could still change this award. The memo will list them as risks.")
    st.subheader("1. Award memo")
    if st.button("Write the memo", type="primary", disabled=not api_key_present()):
        with st.spinner("Writing the memo"):
            out = ai(write_memo, s)
        if out:
            md, facts, res_w = out
            st.session_state.memo = (md, res_w)
            log(load_decisions(), "memo written", f"Award {money(res_w['total'])}")
    if st.session_state.get("memo"):
        md, res_m = st.session_state.memo
        if abs(res_m["total"] - res["total"]) > 1:
            st.info(f"The award changed ({money(res_m['total'])} → {money(res['total'])}). Write the memo again.")
        with st.container(border=True):
            st.markdown(md)
        c1, c2 = st.columns(2)
        c1.download_button("Download memo", md, file_name="award_memo.md")
        c2.download_button("Download award pack (Excel)", memo_workbook(s, res_m, s.issues()), file_name="award_pack.xlsx")
    _validation(s, res)


def _validation(s, res):
    from core import review
    st.subheader("2. Stakeholder validation")
    st.caption("Sending is simulated; answers are logged.")
    dec = load_decisions()
    rs = review.status(dec)
    asks = review.asks(s)
    cols = st.columns(2, gap="medium")
    for k, (role, meta) in enumerate(review.REVIEWERS.items()):
        r = rs[role]
        cls = {"not_sent": "muted", "requested": "check", "approved": "good", "changes": "stop"}[r["status"]]
        stale = r["status"] == "approved" and r.get("total") is not None and abs(r["total"] - res["total"]) > 1
        with cols[k % 2]:
            items = "".join(f"<li>{E(x)}</li>" for x in asks.get(role, [])) or "<li>Nothing specific to check.</li>"
            said = f'<div class="small">“{E(r["note"])}”</div>' if r.get("note") and r["status"] in ("approved", "changes") else ""
            st.markdown(f'<div class="rev"><div class="who">{meta["person"]} {pill(review.STATUS[r["status"]], cls)}'
                        f'{" " + pill("award changed since", "check") if stale else ""}</div>'
                        f'<div class="role">{meta["role"]}</div><ul>{items}</ul>'
                        f'{said}'
                        f'</div>', unsafe_allow_html=True)
            if r["status"] in ("requested", "changes") or stale:
                c1, c2 = st.columns([3, 2])
                note = c1.text_input("Their comment", key=f"rv_n_{role}", label_visibility="collapsed", placeholder="Their comment (optional)")
                outcome = c2.selectbox("Outcome", ["Approved", "Changes requested"], key=f"rv_o_{role}", label_visibility="collapsed")
                if st.button("Record response", key=f"rv_b_{role}"):
                    review.respond(dec, role, "approved" if outcome == "Approved" else "changes", note, total=res["total"])
                    refresh(); st.rerun()
            st.write("")
    unsent = [k for k, r in rs.items() if r["status"] == "not_sent"]
    if unsent:
        c1, c2 = st.columns([3, 1])
        note = c1.text_input("Note to reviewers", label_visibility="collapsed", placeholder="Note to reviewers (optional)")
        if c2.button(f"Send to {'all ' if len(unsent) == len(rs) else ''}{len(unsent)} reviewer{'s' if len(unsent) != 1 else ''}",
                     type="primary", width="stretch"):
            review.request(dec, unsent, note, total=res["total"])
            refresh(); st.rerun()
    done = sum(1 for r in rs.values() if r["status"] == "approved")
    if done == len(rs):
        st.success("All reviewers have signed off.")


# ================================================================== Reading accuracy
def page_accuracy():
    from core.evaluate import score
    s = get_state()
    header("Reading accuracy", "The AI's reading, scored against a hidden answer key.")
    if not s.ready():
        need_replies(); return
    r = score(s.norms, s.extractions, s.verdicts)
    c = r["counts"]
    tiles = [("Read correctly", f"{c['correct']} of {r['total_values']}", "prices that match the answer key"),
             ("Flagged, not guessed", str(c["flagged_not_guessed"]), "unreadable values kept as options"),
             ("Wrong but flagged", str(c["wrong_but_flagged"]), "you were warned before using them"),
             ("Confidently wrong", str(c["confidently_wrong"]), "wrong with no warning: the one that matters")]
    st.markdown('<div class="kpis">' + "".join(f'<div class="kpi"><div class="kpi-label">{a}</div><div class="kpi-value">{b}</div>'
                                               f'<div class="kpi-note">{n}</div></div>' for a, b, n in tiles) + "</div>", unsafe_allow_html=True)
    st.markdown(f'<p class="small">Lines missed: {c["missed_line"]} · lines invented: {c["invented_line"]} · '
                f'lines correctly recognised as not quoted: {c["correctly_missing"]}</p>', unsafe_allow_html=True)
    letter = {k.split("_")[1]: v for k, v in s.vendor_names.items() if k.count("_") >= 2}
    st.subheader(f"Traps planted in the vendor files: {sum(t['caught'] for t in r['traps'])} of {len(r['traps'])} caught")
    st.dataframe(pd.DataFrame([{"Vendor": short(letter.get(t["vendor"], t["vendor"])), "Trap": TRAP_NAMES.get(t["type"], t["type"]),
                                "What was planted": t["detail"], "Caught": "Yes" if t["caught"] else "No"} for t in r["traps"]]),
                 hide_index=True, width="stretch")
    st.subheader("Questionnaire verdicts")
    st.dataframe(pd.DataFrame([{"Vendor": short(letter.get(q["vendor"], q["vendor"])), "Answer key": q["truth"].title(),
                                "System": q["system"].title(), "Agrees": "Yes" if q["ok"] else "No"} for q in r["questionnaire"]]),
                 hide_index=True, width="stretch")
    bad = [x for x in r["rows"] if x["result"] not in ("correct", "correctly_missing")]
    if bad:
        st.subheader("Every price that wasn't simply right")
        lbl = {"flagged_not_guessed": "Unreadable, options kept", "wrong_but_flagged": "Wrong, but flagged",
               "confidently_wrong": "Wrong, no warning", "missed_line": "Missed", "invented_line": "Invented"}
        st.dataframe(pd.DataFrame([{"Vendor": short(letter.get(x["vendor"], x["vendor"])), "Line": x["line_id"], "Answer key ₹": x["truth"],
                                    "System ₹": x["system"], "Options considered": ", ".join(f"{v:.2f}" for v in x["candidates"]),
                                    "Result": lbl.get(x["result"], x["result"])} for x in bad]), hide_index=True, width="stretch")
    models = {ex.get("_meta", {}).get("model") for ex in s.extractions.values()}
    st.caption(f"Read by: {', '.join(m for m in models if m)}")
    _saved_results()
    _next("board", "Back to the decision board")

# ================================================================== navigation
pages = {
    "Overview": [st.Page(page_board, title="Decision board", icon=":material/space_dashboard:", default=True)],
    "Collect": [st.Page(page_draft, title="Draft RFQ", icon=":material/edit_note:", url_path="draft"),
                st.Page(page_replies, title="Vendor replies", icon=":material/inbox:", url_path="replies")],
    "Evaluate": [st.Page(page_compare, title="Comparison", icon=":material/table_chart:", url_path="compare"),
                 st.Page(page_issues, title="Open issues", icon=":material/priority_high:", url_path="issues"),
                 st.Page(page_ask, title="Ask a question", icon=":material/forum:", url_path="ask")],
    "Decide": [st.Page(page_memo, title="Award and approvals", icon=":material/verified:", url_path="memo")],
    "Trust": [st.Page(page_accuracy, title="Reading accuracy", icon=":material/fact_check:", url_path="accuracy")],
}
st.session_state["_pages"] = {"issues": pages["Evaluate"][1], "memo": pages["Decide"][0], "compare": pages["Evaluate"][0],
                               "replies": pages["Collect"][1], "ask": pages["Evaluate"][2], "board": pages["Overview"][0]}
nav = st.navigation(pages)
with st.sidebar:
    BOX = ("<svg width='20' height='20' viewBox='0 0 24 24' fill='none' stroke='#FFFFFF' stroke-width='1.8' stroke-linejoin='round'>"
           "<path d='M3 7.5 12 3l9 4.5v9L12 21l-9-4.5z'/><path d='M3 7.5 12 12l9-4.5M12 12v9'/></svg>")
    _n = len(vendor_dirs())
    st.markdown(f"""<div class="sb-brand"><div class="sb-mark">{BOX}</div><div class="brand">Quote desk</div></div>
        <div class="flute" style="margin:10px 0 0 0"></div>
        <div class="sb-sub" style="margin-top:8px">{config.RFX_ID} · {_n} vendors</div>
        {'' if api_key_present() else '<div class="sb-note off">AI is off (no API key). Everything already read still works.</div>'}""",
                unsafe_allow_html=True)
nav.run()
