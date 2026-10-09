"""Quote desk - from RFQ to a defensible award. Run: streamlit run app.py

Interface only. All logic lives in core/ (the AI reads, code does the arithmetic)."""
from __future__ import annotations
import json
import os

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
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
html, body, .stApp, .stMarkdown, button, input, textarea, select, label {{ font-family: 'IBM Plex Sans', sans-serif !important; }}
.stApp {{ background: {PAGE}; color: {INK}; }}
[data-testid="stAppViewContainer"] p, [data-testid="stAppViewContainer"] li, [data-testid="stAppViewContainer"] label,
[data-testid="stAppViewContainer"] h1, [data-testid="stAppViewContainer"] h2, [data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] summary, [data-testid="stAppViewContainer"] span:not(.pill):not(.l1) {{ color: {INK}; }}
[data-testid="stHeader"] {{ background: {PAGE}; }}
.block-container {{ padding-top: 2.2rem; max-width: 1320px; }}
p, li {{ font-size: 1rem; line-height: 1.55; }}
h1 {{ font-size: 1.9rem !important; font-weight: 700 !important; letter-spacing: -0.015em; margin-bottom: .2rem !important; }}
h2 {{ font-size: 1.3rem !important; font-weight: 600 !important; margin-top: 1.6rem !important; }}
h3 {{ font-size: 1.08rem !important; font-weight: 600 !important; }}
.num, td, .kpi-value {{ font-variant-numeric: tabular-nums; }}

/* sidebar */
section[data-testid="stSidebar"] {{ background: {INK}; }}
section[data-testid="stSidebar"] * {{ color: #E6EBF1 !important; }}
section[data-testid="stSidebar"] [data-testid="stNavSectionHeader"] {{ color: #9FB0C3 !important; font-size: .78rem; letter-spacing: .02em; }}

/* buttons: explicit so a dark-mode browser cannot invert them */
.stButton > button, .stDownloadButton > button {{ background: {CARD}; color: {INK} !important; border: 1px solid #C4CDD7; border-radius: 6px; font-weight: 500; }}
.stButton > button:hover, .stDownloadButton > button:hover {{ border-color: {INK}; color: {INK} !important; }}
.stButton > button[kind="primary"] {{ background: {INK}; color: #FFFFFF !important; border-color: {INK}; }}
.stButton > button[kind="primary"] p {{ color: #FFFFFF !important; }}
.stButton > button p, .stDownloadButton > button p {{ color: inherit !important; }}
[data-testid="stExpander"] details {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; }}

/* components */
.purpose {{ color: {INK_2}; font-size: 1.02rem; margin: 0 0 1.2rem 0; max-width: 78ch; }}
.purpose b {{ color: {INK}; }}
.pill {{ display: inline-block; padding: 2px 10px; border-radius: 999px; font-size: .8rem; font-weight: 600; white-space: nowrap; }}
.good {{ background: {GOOD_BG}; color: {GOOD}; }} .check {{ background: {CHECK_BG}; color: {CHECK}; }}
.stop {{ background: {STOP_BG}; color: {STOP}; }} .muted {{ background: {MUTED_BG}; color: {MUTED}; }}
.l1 {{ display: inline-block; background: {KRAFT}; color: #fff; font-weight: 700; font-size: .75rem; padding: 1px 7px; border-radius: 4px; }}
.reco {{ background: {CARD}; border: 1px solid {LINE}; border-left: 6px solid {KRAFT}; border-radius: 8px; padding: 18px 22px; margin: 4px 0 18px 0; }}
.reco .lead {{ font-size: 1.22rem; font-weight: 600; line-height: 1.45; color: {INK}; }}
.reco .sub {{ color: {INK_2}; margin-top: 6px; }}
.kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin: 6px 0 8px 0; }}
.kpi {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; padding: 14px 16px; }}
.kpi-label {{ color: {INK_2}; font-size: .86rem; }}
.kpi-value {{ font-size: 1.65rem; font-weight: 700; color: {INK}; line-height: 1.25; margin-top: 2px; }}
.kpi-note {{ color: {INK_2}; font-size: .82rem; margin-top: 2px; }}
.steps {{ display: flex; gap: 0; margin: 4px 0 6px 0; flex-wrap: wrap; }}
.stp {{ flex: 1 1 0; min-width: 150px; padding: 10px 14px; background: {CARD}; border: 1px solid {LINE}; margin-right: -1px; }}
.stp:first-child {{ border-radius: 8px 0 0 8px; }} .stp:last-child {{ border-radius: 0 8px 8px 0; }}
.stp .t {{ font-size: .8rem; color: {INK_2}; }} .stp .v {{ font-weight: 600; color: {INK}; }}
.stp.done {{ box-shadow: inset 0 3px 0 {GOOD}; }} .stp.wait {{ box-shadow: inset 0 3px 0 {CHECK}; }} .stp.block {{ box-shadow: inset 0 3px 0 {STOP}; }}
.vcard {{ background: {CARD}; border: 1px solid {LINE}; border-radius: 8px; padding: 14px 16px; height: 100%; }}
.vcard .name {{ font-weight: 600; font-size: 1.02rem; color: {INK}; }}
.vcard .meta {{ color: {INK_2}; font-size: .84rem; margin: 2px 0 10px 0; }}
.vcard .row {{ font-size: .9rem; color: {INK}; margin-top: 6px; }}
.vcard .why {{ font-size: .84rem; color: {INK_2}; margin-top: 8px; line-height: 1.4; }}
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
.small {{ color: {INK_2}; font-size: .86rem; }}
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


def short(name):
    return (name or "").split()[0]


def pill(text, cls):
    return f'<span class="pill {cls}">{text}</span>'


def header(title, purpose):
    st.title(title)
    st.markdown(f'<p class="purpose">{purpose}</p>', unsafe_allow_html=True)


def get_state(refresh=False) -> State:
    if refresh or "state" not in st.session_state:
        st.session_state.state = State()
        st.session_state.pop("analyst", None)
    return st.session_state.state


def refresh():
    get_state(refresh=True)


def key_notice():
    if not api_key_present():
        st.info("AI actions are off because no Anthropic API key is configured. Everything already read still works.")


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
        lbl = STATUS.get(i.get("status"), (i.get("status", ""),))[0].lower()
        return f"{v} is {lbl}"
    if k == "illegible":
        return f"{v}'s rate can't be read reliably on lines {', '.join(i['lines'][:3])}{'…' if len(i['lines']) > 3 else ''}"
    if k == "unit":
        return f"{v}'s unit of price is ambiguous on {', '.join(i['lines'])}"
    if k == "freight":
        return f"{v}'s freight is estimated, not quoted"
    if k == "fx":
        return f"{v} quoted in US dollars"
    if k == "history":
        return f"{v}'s 'same as last year' prices are unconfirmed"
    if k == "spec":
        return f"{v} offered a lower board grade than specified"
    return f"{v}: {i['title'][:80]}"


# ================================================================== Decision board
def page_board():
    s = get_state()
    header("Corrugated packaging, FY27 annual contract",
           f"Waluj brewery · {config.RFX_ID} · 30 lines · bids closed 7 Oct 2026. "
           "<b>Start here:</b> the recommendation, what could change it, and where each vendor stands.")
    key_notice()
    missing = s.missing_extractions()
    if missing:
        st.subheader(f"{len(missing)} vendor replies are waiting to be read")
        st.write("Each reply is read whatever its format (Excel, PDF, Word, a phone photo or a plain email), mapped to the 30 RFQ lines, "
                 "converted to landed cost and checked against the quality questionnaire. Usually 1-3 minutes.")
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

    res = s.award()
    issues = s.issues()
    hot = [i for i in issues if i["decision_relevant"]]
    covered = 30 - len(res["uncovered_lines"])

    # the recommendation, in one sentence
    split = sorted(res["by_vendor"].items(), key=lambda kv: -kv[1]["value"])
    if not split:
        lead = "No vendor is qualified yet, so nothing can be awarded under the RFQ rule."
    else:
        if len(split) == 1:
            who = short(split[0][0])
        else:
            parts = [f"{short(n)} ({d['lines']} lines)" for n, d in split]
            who = ", ".join(parts[:-1]) + " and " + parts[-1]
        scope = "all 30 lines" if covered == 30 else f"{covered} of 30 lines"
        lead = f"Award {scope} to {who} for {money(res['total'])} a year"
        if res["fy26_comparable_base"]:
            lead += f", {money(res['savings_vs_fy26'])} below last year's contract" if res["savings_vs_fy26"] >= 0 else \
                    f", {money(-res['savings_vs_fy26'])} above last year's contract"
        lead += "."
    if hot:
        top = hot[0]
        sub = (f"{len(hot)} open issue{'s' if len(hot) != 1 else ''} could change this. The largest: {issue_headline(top)} "
               f"({money(_stake(top)[0])} at stake).")
    else:
        sub = "No open issue can change this recommendation."
    if res["uncovered_lines"]:
        sub += f" {len(res['uncovered_lines'])} lines have no qualified quote yet."
    st.markdown(f'<div class="reco"><div class="lead">{lead}</div><div class="sub">{sub}</div></div>', unsafe_allow_html=True)

    # progress through the sourcing event
    n_prices = sum(1 for n in s.norms if n.status != "missing")
    n_review = sum(1 for n in s.norms if n.status == "review")
    steps = [("done", "RFQ issued", "28 Sep 2026"), ("done", "Replies read", f"{len(s.extractions)} of {len(vendor_dirs())}"),
             ("done" if not n_review else "wait", "Prices normalised", f"{n_prices} prices · {n_review} to confirm"),
             ("done" if not hot else "wait", "Open issues", f"{len(hot)} could change the award"),
             ("done" if (not hot and not res["uncovered_lines"]) else ("block" if res["uncovered_lines"] else "wait"), "Award",
              "Ready to approve" if (not hot and not res["uncovered_lines"]) else "Needs your decisions")]
    st.markdown('<div class="steps">' + "".join(f'<div class="stp {c}"><div class="t">{t}</div><div class="v">{v}</div></div>' for c, t, v in steps)
                + "</div>", unsafe_allow_html=True)

    pct = (f"{res['savings_vs_fy26']/res['fy26_comparable_base']:.1%} on comparable lines" if res["fy26_comparable_base"] else "no comparable lines")
    tiles = [("Recommended award", money(res["total"]) if res["total"] else "None yet", f"{covered} of 30 lines covered"),
             ("Savings vs last year", money(res["savings_vs_fy26"]) if res["fy26_comparable_base"] else "-", pct),
             ("Qualified vendors", f"{sum(1 for v in s.status.values() if v == 'pass')} of {len(s.extractions)}",
              f"{sum(1 for v in s.status.values() if v == 'include')} more included by you"),
             ("Decisions waiting on you", str(len(hot)), "open issues that change the award")]
    st.markdown('<div class="kpis">' + "".join(f'<div class="kpi"><div class="kpi-label">{a}</div><div class="kpi-value">{b}</div>'
                                               f'<div class="kpi-note">{c}</div></div>' for a, b, c in tiles) + "</div>", unsafe_allow_html=True)

    st.subheader("Where each vendor stands")
    cols = st.columns(len(s.extractions))
    for col, (v, ex) in zip(cols, s.extractions.items()):
        lbl, cls = STATUS.get(s.status[v], ("Unknown", "muted"))
        ns = [n for n in s.norms if n.vendor == v]
        quoted = sum(1 for n in ns if n.status != "missing")
        rev = sum(1 for n in ns if n.status == "review")
        won = res["by_vendor"].get(s.vendor_names[v], {"lines": 0, "value": 0})
        fmt = ", ".join(sorted({f.split(".")[-1].upper().replace("TXT", "email") for f in ex.get("_meta", {}).get("files", [])}))
        why = vendor_reason(s, v)
        col.markdown(f"""<div class="vcard"><div class="name">{s.vendor_names[v]}</div>
            <div class="meta">{place(ex.get('vendor_location'))} · sent {fmt}</div>{pill(lbl, cls)}
            <div class="row">{quoted} of 30 lines quoted{f' · {rev} to confirm' if rev else ''}</div>
            <div class="row"><b>{'L1 on ' + str(won['lines']) + ' lines · ' + money(won['value']) if won['lines'] else 'Not L1 on any line'}</b></div>
            {f'<div class="why">{why}</div>' if why and s.status[v] != 'pass' else ''}</div>""", unsafe_allow_html=True)

    st.subheader("Decide these first")
    if not hot:
        st.success("Nothing open can change the award. Go to Award memo when you are ready.")
    for i in hot[:3]:
        _issue_card(s, i, compact=True)
    if len(hot) > 3:
        st.caption(f"{len(hot) - 3} more in Open issues.")
    _saved_results()


def _saved_results():
    import io
    import zipfile
    from core.config import EXTRACT_CACHE
    with st.expander("Saved results: backup and restore"):
        files = sorted(EXTRACT_CACHE.glob("*.json"))
        st.write("What the AI read from each reply is saved, so pages open instantly. Download a backup, or commit these files to "
                 "`cache/extractions/` in the repository so the live app always starts with them. Re-read any reply to watch it run live.")
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
    header("Draft the RFQ", "Describe what you need in your own words. The co-pilot pulls approved specs and last year's volumes, "
           "proposes a supplier questionnaire with pass/fail rules, and asks about anything it can't know.")
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
        msg = st.chat_input("What do you need to buy?", disabled=not api_key_present())
        if msg:
            st.session_state.draft_chat.append(("user", msg))
            with st.spinner("Drafting the RFQ"):
                text, hist = copilot.chat(st.session_state.draft, st.session_state.draft_hist, msg)
            st.session_state.draft_hist = hist
            st.session_state.draft_chat.append(("assistant", text))
            st.rerun()
    with right:
        d = st.session_state.draft
        st.subheader(d["header"].get("title") or "Your RFQ draft")
        if not (d["header"] or d["line_items"]):
            st.markdown('<p class="small">The draft builds here as you talk: scope, line items, questionnaire and terms.</p>', unsafe_allow_html=True)
        if d["header"]:
            st.markdown('<table class="terms">' + "".join(f"<tr><td>{k.replace('_', ' ').capitalize()}</td><td>{v}</td></tr>"
                                                         for k, v in d["header"].items()) + "</table>", unsafe_allow_html=True)
        if d["line_items"]:
            st.markdown(f"**Line items ({len(d['line_items'])})**")
            st.dataframe(pd.DataFrame(d["line_items"]), hide_index=True, width="stretch", height=280)
        if d["questionnaire"]:
            st.markdown("**Supplier questionnaire**")
            st.dataframe(pd.DataFrame(d["questionnaire"]), hide_index=True, width="stretch")
        if d["terms"]:
            st.markdown("**Terms**\n" + "\n".join(f"- {t}" for t in d["terms"]))
        if d["line_items"]:
            st.markdown("**Send to:** " + ", ".join(d["vendors"]))
            if st.button("Send RFQ to vendors", type="primary"):
                st.session_state.sent = True
                log(load_decisions(), "rfq sent", f"Sent to {len(d['vendors'])} vendors (simulated email)")
            if st.session_state.get("sent"):
                st.success(f"Sent to {len(d['vendors'])} vendors. Email is simulated in this demo; the five replies to {config.RFX_ID} "
                           "are already in Vendor replies.")


# ================================================================== Vendor replies
def page_replies():
    from core import readers
    s = get_state()
    header("Vendor replies", "What each vendor actually sent, side by side with what was read from it. "
           "Every price shows the vendor's own words and where they appear.")
    key_notice()
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
        for f in sorted(vdir.iterdir(), key=lambda p: (p.name != "email.txt", p.name)):
            label = "Email" if f.name == "email.txt" else f.name
            with st.expander(label, expanded=f.suffix.lower() in (".jpg", ".jpeg", ".png") or f.name == "email.txt"):
                suf = f.suffix.lower()
                if suf in (".jpg", ".jpeg", ".png"):
                    st.image(str(f), width="stretch")
                elif suf in (".txt", ".eml"):
                    st.text(f.read_text(errors="ignore"))
                elif suf == ".pdf":
                    for img in readers.pdf_page_images(f, 70):
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
            with st.spinner("Reading"):
                run_extraction(vdir)
            refresh(); st.rerun()
    with right:
        st.subheader("What was read")
        if not ex:
            st.info("This reply hasn't been read yet.")
            if st.button("Read this reply", type="primary", disabled=not api_key_present()):
                with st.spinner("Reading"):
                    run_extraction(vdir)
                refresh(); st.rerun()
            return
        if ex.get("response_summary"):
            st.write(ex["response_summary"])
        t = ex.get("terms", {})
        disc = "; ".join(f"{d.get('percent')}% if {d.get('condition')}" for d in ex.get("discounts", [])) or "None found"
        rows = [("Currency", t.get("currency") or "-"), ("GST", GST.get(t.get("gst"), t.get("gst") or "-")),
                ("Freight", FREIGHT.get(t.get("freight"), t.get("freight") or "-")),
                ("Payment", f"{t.get('payment_days')} days" if t.get("payment_days") else "Not stated"),
                ("Lead time", f"{t.get('lead_time_days')} days" if t.get("lead_time_days") else "Not stated"),
                ("Discounts", disc)]
        st.markdown('<table class="terms">' + "".join(f"<tr><td>{a}</td><td><b>{b}</b></td></tr>" for a, b in rows) + "</table>", unsafe_allow_html=True)
        unsure = ex.get("unreadable_or_uncertain", [])
        if unsure:
            st.markdown("**The reader flagged**")
            for u in unsure[:8]:
                st.markdown(f"{pill('Check', 'check')} {u}", unsafe_allow_html=True)
        prices = []
        for n in [n for n in s.norms if n.vendor == pick]:
            worst = max((f.severity for f in n.flags), key=lambda x: ["info", "warn", "critical"].index(x), default="")
            prices.append({"Line": n.line_id, "Their item": n.vendor_item_text, "As they wrote it": n.source_quote,
                           "Landed ₹ per unit": n.landed,
                           "Possible readings": " or ".join(f"{c['landed']:.2f}" for c in n.candidates) if len(n.candidates) > 1 else "",
                           "Status": {"ok": "Read", "review": "Confirm", "missing": "Not quoted"}[n.status] + ("" if n.spec_compliant else ", lower spec"),
                           "Attention": {"critical": "Blocks award", "warn": "Check", "info": "Note", "": ""}[worst]})
        st.markdown("**Prices, converted to landed cost**")
        st.dataframe(pd.DataFrame(prices), hide_index=True, width="stretch", height=420,
                     column_config={"Line": st.column_config.TextColumn(width=48),
                                    "Landed ₹ per unit": st.column_config.NumberColumn(format="%.2f", width="small"),
                                    "Possible readings": st.column_config.TextColumn(width="small"),
                                    "Status": st.column_config.TextColumn(width="small"),
                                    "Attention": st.column_config.TextColumn(width="small")})
        ev = s.q_evals.get(pick)
        if ev:
            lbl, cls = STATUS[s.verdicts[pick]]
            st.markdown(f"**Quality questionnaire** {pill(lbl, cls)}", unsafe_allow_html=True)
            qmeta = {q["q_id"]: q for q in extract.load_questionnaire()}
            ans = {a.get("q_id"): a.get("answer") for a in ex.get("questionnaire", [])}
            res_lbl = {"pass": "Pass", "fail": "Fail", "unclear": "Unclear"}
            st.dataframe(pd.DataFrame([{"Question": qmeta.get(k, {}).get("question", k), "Rule": qmeta.get(k, {}).get("type"),
                                        "Their answer": ans.get(k), "Result": res_lbl.get(r.get("status"), r.get("status")),
                                        "Why": r.get("reason", "") + (f" ({r['rule_note']})" if r.get("rule_note") else "")
                                        + (" (checked against the certificate date)" if r.get("check") == "deterministic" else "")}
                                       for k, r in sorted(ev["results"].items())]), hide_index=True, width="stretch")

    with st.expander("Add a vendor reply (any format)"):
        name = st.text_input("Vendor name")
        files = st.file_uploader("Files", accept_multiple_files=True)
        body = st.text_area("Email text (optional)")
        if st.button("Add and read", disabled=not (name and (files or body) and api_key_present())):
            slug = "vendor_X_" + "".join(c for c in name.lower() if c.isalnum())[:20]
            nd = INBOX / slug
            nd.mkdir(exist_ok=True)
            if body:
                (nd / "email.txt").write_text(f"From: {name}\nSubject: Quote for {config.RFX_ID}\n\n{body}")
            for f in files or []:
                (nd / f.name).write_bytes(f.getvalue())
            with st.spinner("Reading"):
                run_extraction(nd)
            refresh(); st.rerun()


# ================================================================== Comparison
def page_compare():
    s = get_state()
    header("Comparison", "Every vendor on the same basis: rupees per RFQ unit, excluding GST, delivered to Waluj. "
           "Click any line and vendor below to see exactly how a number was worked out.")
    if not s.ready():
        need_replies(); return
    lines = extract.load_rfx_lines()
    vendors = list(s.extractions)
    by = {(n.vendor, n.line_id): n for n in s.norms}
    c1, c2 = st.columns([3, 2])
    view = c1.segmented_control("Show", ["All lines", "Lines to confirm", "Lines without a qualified quote"], default="All lines",
                                label_visibility="collapsed") or "All lines"
    only_q = c2.toggle("Only qualified vendors", value=False)
    st.markdown(f"""<div class="legend"><span><span class="l1">L1</span> lowest qualified, on-spec price</span>
        <span><span class="sw" style="background:#DCEFE4"></span>L1 cell</span>
        <span><span class="sw" style="background:{CHECK_BG}"></span>more than one possible reading (shown at the higher one)</span>
        <span><span class="sw" style="background:{STOP_BG}"></span>lower spec than asked</span>
        <span>– = not quoted</span><span>* = not qualified yet</span></div>""", unsafe_allow_html=True)
    shown = [v for v in vendors if (not only_q or v in s.eligible)]
    colname = {v: short(s.vendor_names[v]) + ("" if v in s.eligible else " *") for v in shown}
    data, style = [], []
    for l in lines:
        lid = l["line_id"]
        elig = [by[(v, lid)] for v in vendors if v in s.eligible and by.get((v, lid)) and by[(v, lid)].landed is not None
                and by[(v, lid)].status != "missing" and by[(v, lid)].spec_compliant]
        best = min(elig, key=lambda n: n.landed) if elig else None
        any_review = any(by.get((v, lid)) and by[(v, lid)].status == "review" for v in vendors)
        if view == "Lines to confirm" and not any_review:
            continue
        if view == "Lines without a qualified quote" and best is not None:
            continue
        row = {"Line": lid, "Item": l["description"], "Annual qty": f"{int(l['annual_qty']):,}",
               "L1": f"{short(best.vendor_name)} ₹{best.landed:,.2f}" if best else "No qualified quote"}
        srow = {"L1": f"color:{KRAFT}; font-weight:600" if best else f"color:{STOP}"}
        for v in shown:
            n = by.get((v, lid))
            row[colname[v]] = f"{n.landed:,.2f}" if (n and n.landed is not None and n.status != "missing") else "–"
            css = ""
            if n is None or n.status == "missing":
                css = f"color:{MUTED}"
            elif not n.spec_compliant:
                css = f"background-color:{STOP_BG}; color:{STOP}"
            elif n.status == "review":
                css = f"background-color:{CHECK_BG}"
            if best is n and n is not None:
                css = "background-color:#DCEFE4; font-weight:700"
            srow[colname[v]] = css
        data.append(row); style.append(srow)
    if not data:
        st.success("No lines match this filter.")
    else:
        df = pd.DataFrame(data)
        sty = df.style.apply(lambda _: pd.DataFrame([{**{c: "" for c in df.columns}, **r} for r in style], columns=df.columns), axis=None) \
            .set_properties(subset=[colname[v] for v in shown] + ["Annual qty"], **{"text-align": "right"})
        st.dataframe(sty, hide_index=True, width="stretch", height=min(38 * (len(df) + 1) + 4, 1150),
                     column_config={colname[v]: st.column_config.Column(width="small") for v in shown} |
                     {"Line": st.column_config.Column(width=48), "Item": st.column_config.Column(width="medium"),
                      "Annual qty": st.column_config.Column(width="small"), "L1": st.column_config.Column(width="medium")})
    st.subheader("How was this number worked out?")
    c1, c2 = st.columns(2)
    lid = c1.selectbox("Line", [l["line_id"] for l in lines], format_func=lambda x: f"{x} · {next(l['description'] for l in lines if l['line_id'] == x)}")
    v = c2.selectbox("Vendor", vendors, format_func=lambda k: s.vendor_names[k])
    _evidence(s, by.get((v, lid)))


def _evidence(s, n):
    if not n:
        return
    val = "not quoted" if n.landed is None or n.status == "missing" else f"₹{n.landed:,.2f} landed per unit"
    st.markdown(f"**{n.vendor_name}, {n.line_id}:** {val}")
    left, right = st.columns([6, 5], gap="large")
    with left:
        st.markdown("**Steps**")
        for stp in n.steps:
            st.markdown(f'<div class="step">{stp}</div>', unsafe_allow_html=True)
        if n.flags:
            st.markdown("**Things to know**")
        for f in n.flags:
            cls = {"critical": "stop", "warn": "check", "info": "muted"}[f.severity]
            lbl = {"critical": "Blocks", "warn": "Check", "info": "Note"}[f.severity]
            st.markdown(f"{pill(lbl, cls)} {f.text}", unsafe_allow_html=True)
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
    loc, quote = (n.source or "").strip(), (n.source_quote or "").strip()
    hit = None
    if loc:
        key = loc.split(",")[0].strip()
        hit = next((i for i, ln in enumerate(lines) if ln.startswith(key + " ") or ln.startswith(key + ":") or ln.startswith(key + " |")), None)
    if hit is None and quote and len(quote) >= 3:
        hit = next((i for i, ln in enumerate(lines) if quote[:40] in ln), None)
    if hit is not None:
        st.code("\n".join(lines[max(0, hit - 2): hit + 3]), language=None)
    m = re.search(r"([\w\-. ]+\.pdf):p(\d+)", loc)
    if m and (vdir / m.group(1).strip()).exists():
        pages = readers.pdf_page_images(vdir / m.group(1).strip(), 90)
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
    if i["kind"] == "eligibility" and i.get("newly_covered"):
        return i["newly_covered_value"], f"of spend on {len(i['newly_covered'])} lines with no qualified quote today"
    if i["kind"] == "eligibility":
        if i["award_swing"] > 0:
            return i["award_swing"], "lower award cost if this vendor qualifies"
        if i["award_swing"] < 0:
            return -i["award_swing"], "higher award cost if this vendor qualifies (volume-discount effect)"
        return 0, "no change in award cost if this vendor qualifies"
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
    flip_txt = (f"Changes L1 on {len(flips)} line{'s' if len(flips) != 1 else ''}" if flips else "Doesn't change L1 on any line")
    detail = i["title"] if i["kind"] != "eligibility" else i["title"].split(". ", 1)[-1]
    st.markdown(f"""<div class="issue {cls}"><div class="head">{issue_headline(i)}</div>
        <div><span class="stake">{money(stake)}</span> <span class="stake-l">{stake_lbl}</span></div>
        <div class="detail">{detail}</div>
        <div class="detail">{flip_txt}{'. ' + i['detail'] if i.get('detail') else ''}.</div></div>""", unsafe_allow_html=True)
    if compact:
        return
    if i.get("cascade_lines") and i.get("discount_effect"):
        st.markdown(f"Knock-on effect: under one reading a vendor's volume discount switches on or off, which moves "
                    f"{len(i['cascade_lines'])} other lines ({', '.join(i['cascade_lines'])}).")
    if i.get("outcomes"):
        st.table(pd.DataFrame([{"If the value is": o["label"], "Award total": money(o["total"]),
                                f"{short(i['vendor_name'])} is L1 on": f"{o['vendor_lines']} lines",
                                "Volume discounts": ", ".join(f"{short(s.vendor_names.get(d['vendor'], d['vendor']))} {d['percent']:g}%"
                                                              for d in o["discounts"]) or "none"} for o in i["outcomes"]]))
    dec = load_decisions()
    c1, c2 = st.columns(2)
    with c1:
        if i.get("resolvable") and i.get("outcomes"):
            opts = {o["label"]: o["index"] for o in i["outcomes"]}
            choice = st.selectbox("Vendor confirmed the value as", ["Not confirmed yet"] + list(opts), key=f"ch_{i['id']}")
            if choice != "Not confirmed yet" and st.button("Use this value", key=f"ap_{i['id']}", type="primary"):
                dec.setdefault("choices", {})[i["id"]] = opts[choice]
                log(dec, "value confirmed", f"{i['vendor_name']}: {issue_headline(i)} -> {choice}")
                refresh(); st.rerun()
        if i["kind"] == "eligibility":
            reason = st.text_input("Reason for including (saved to the decision log)", key=f"rs_{i['id']}",
                                   placeholder="e.g. renewed ISO certificate received")
            if st.button("Include in the award", key=f"in_{i['id']}", disabled=not reason):
                dec.setdefault("eligibility", {})[i["vendor"]] = "include"
                log(dec, "vendor included", f"{i['vendor_name']}: {reason}")
                refresh(); st.rerun()
    with c2:
        if st.button("Draft an email to the vendor", key=f"cl_{i['id']}", disabled=not api_key_present()):
            from core.memo import draft_clarification
            with st.spinner("Drafting"):
                st.session_state[f"mail_{i['id']}"] = draft_clarification(i, s)
            log(dec, "clarification drafted", f"{i['vendor_name']}: {issue_headline(i)}")
    if st.session_state.get(f"mail_{i['id']}"):
        st.text_area("Email draft: copy, edit and send", st.session_state[f"mail_{i['id']}"], height=230, key=f"ta_{i['id']}")


def page_issues():
    s = get_state()
    header("Open issues", "Every uncertainty, ranked by the money it can move. Each one has been tested by re-running the award under "
           "every possible answer, so you only spend time on what changes the decision.")
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
            _issue_card(s, i, compact=True)
    dec = load_decisions()
    with st.expander(f"Decision log ({len(dec.get('log', []))} entries)"):
        st.write("Everything you and the system decided, in order. It ships with the award pack.")
        if dec.get("log"):
            st.dataframe(pd.DataFrame(dec["log"]).rename(columns={"ts": "When", "actor": "Who", "action": "What", "detail": "Detail"}),
                         hide_index=True, width="stretch")
        if st.button("Reset all my decisions"):
            reset_decisions(); refresh(); st.rerun()


# ================================================================== Ask a question
SUGGESTED = [
    ("The VP's question", "What if we split it, cheapest per line, but only among vendors who cleared the quality questionnaire?"),
    ("Biggest lines", "Who is cheapest on our five biggest lines by annual value, and how confident are we in those prices?"),
    ("Test an unreadable value", "If Godavari's blurred 5-ply rate is 62.50 instead of 68.50, what changes in the award?"),
    ("Fewer vendors", "Consolidate to two vendors at most. What does it cost us versus the best split?"),
    ("Cheap but risky", "Nordvik is cheapest on the Classic 650 shipper. What would it take to award them, and what's the risk?"),
    ("Chart and export", "Chart landed cost by vendor for the 650 ml shippers and export the full comparison to Excel."),
]


def page_ask():
    from core.analyst import Analyst
    s = get_state()
    header("Ask a question", "Ask in plain language. Answers come from real queries and award runs over the comparison, "
           "and every answer shows how it was worked out.")
    key_notice()
    if not s.ready():
        need_replies(); return
    if "analyst" not in st.session_state:
        st.session_state.analyst = Analyst(s)
        st.session_state.an_hist, st.session_state.an_view = [], []
    a = st.session_state.analyst
    for turn in st.session_state.an_view:
        st.chat_message("user").write(turn["q"])
        with st.chat_message("assistant"):
            _render_outputs(turn["outputs"])
            st.markdown(turn["a"])
    q = None
    if not st.session_state.an_view:
        st.markdown('<p class="small">Questions buyers ask most. Click one, or type your own below.</p>', unsafe_allow_html=True)
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
            text, hist, outs = a.ask(st.session_state.an_hist, q, on_step=lambda stp: box.write(names.get(stp["tool"], stp["tool"])))
            box.update(label=f"Done · {len(outs)} step{'s' if len(outs) != 1 else ''}", state="complete")
        st.session_state.an_hist = hist
        st.session_state.an_view.append({"q": q, "a": text, "outputs": outs})
        st.rerun()
    if st.session_state.an_view and st.button("Start a new conversation"):
        st.session_state.an_hist, st.session_state.an_view = [], []
        st.rerun()


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
                fig.update_layout(font_family="IBM Plex Sans", font_color=INK, plot_bgcolor="white", paper_bgcolor="white",
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
    header("Award memo", "A one-page recommendation for approval, written only from the computed numbers, "
           "plus an Excel pack with the full comparison, open issues and your decision log.")
    key_notice()
    if not s.ready():
        need_replies(); return
    res = s.award()
    hot = [i for i in s.issues() if i["decision_relevant"]]
    if hot:
        st.warning(f"{len(hot)} open issue{'s' if len(hot) != 1 else ''} could still change this award. The memo will list them as risks.")
    if st.button("Write the memo", type="primary", disabled=not api_key_present()):
        with st.spinner("Writing the memo"):
            md, facts, res = write_memo(s)
        st.session_state.memo = (md, res)
        log(load_decisions(), "memo written", f"Award {money(res['total'])}")
    if st.session_state.get("memo"):
        md, res_m = st.session_state.memo
        with st.container(border=True):
            st.markdown(md)
        c1, c2 = st.columns(2)
        c1.download_button("Download memo", md, file_name="award_memo.md")
        c2.download_button("Download award pack (Excel)", memo_workbook(s, res_m, s.issues()), file_name="award_pack.xlsx")


# ================================================================== Reading accuracy
def page_accuracy():
    from core.evaluate import score
    s = get_state()
    header("Reading accuracy", "This demo's vendor files have a hidden answer key the AI never sees. Here the live reading is scored against it. "
           "The number that matters most is <b>confidently wrong</b>: a wrong price shown without any warning.")
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


# ================================================================== navigation
pages = {
    "": [st.Page(page_board, title="Decision board", default=True)],
    "Collect": [st.Page(page_draft, title="Draft RFQ", url_path="draft"),
                st.Page(page_replies, title="Vendor replies", url_path="replies")],
    "Evaluate": [st.Page(page_compare, title="Comparison", url_path="compare"),
                 st.Page(page_issues, title="Open issues", url_path="issues"),
                 st.Page(page_ask, title="Ask a question", url_path="ask")],
    "Decide": [st.Page(page_memo, title="Award memo", url_path="memo")],
    "Trust": [st.Page(page_accuracy, title="Reading accuracy", url_path="accuracy")],
}
nav = st.navigation(pages)
with st.sidebar:
    st.markdown("**Quote desk**")
    st.caption("Deccan Peak Breweries · Packaging. Demo data; all companies are fictional.")
nav.run()
