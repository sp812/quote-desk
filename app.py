"""Quote desk - RFx to award, for Deccan Peak Breweries (demo). Run: streamlit run app.py"""
from __future__ import annotations
import json
import shutil

import pandas as pd
import plotly.express as px
import streamlit as st

from core import config, extract
from core.config import INBOX, api_key_present
from core.pipeline import State, run_extraction, vendor_dirs, load_decisions, save_decisions, log, reset_decisions

st.set_page_config(page_title="Quote desk", page_icon="📦", layout="wide")

# Streamlit Community Cloud keeps keys in st.secrets; Replit puts Secrets in the environment. Support both.
import os
try:
    if not os.environ.get("ANTHROPIC_API_KEY") and "ANTHROPIC_API_KEY" in st.secrets:
        os.environ["ANTHROPIC_API_KEY"] = st.secrets["ANTHROPIC_API_KEY"]
except Exception:
    pass

INK, PAPER, KRAFT = "#1D2B3A", "#FBFBF9", "#A8743A"
OK, WARN, BAD, MUTE = "#2E7D5B", "#B7791F", "#B4423A", "#8A9099"
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"], .stMarkdown, .stDataFrame, button, input, textarea {{ font-family: 'IBM Plex Sans', sans-serif; }}
.stApp {{ background: {PAPER}; }}
section[data-testid="stSidebar"] {{ background: {INK}; }}
section[data-testid="stSidebar"] * {{ color: #E8ECF1 !important; }}
h1 {{ font-weight: 700; letter-spacing: -0.02em; color: {INK}; font-size: 2.0rem; }}
h2, h3 {{ color: {INK}; letter-spacing: -0.01em; }}
.num {{ font-variant-numeric: tabular-nums; }}
.pill {{ display:inline-block; padding:2px 10px; border-radius: 999px; font-size: 0.8rem; font-weight:600; }}
.ok {{ background:#E4F1EA; color:{OK}; }} .warn {{ background:#FBF0DC; color:{WARN}; }} .bad {{ background:#F6E1DF; color:{BAD}; }} .mute {{ background:#ECEEF1; color:#5D6470; }}
.issue {{ border-left: 6px solid {WARN}; background: white; padding: 14px 18px; margin: 10px 0; border-radius: 4px; }}
.issue.crit {{ border-left-color: {BAD}; }} .issue.low {{ border-left-color: #C9CDD3; }}
.stake {{ font-size: 1.5rem; font-weight: 700; color: {INK}; font-variant-numeric: tabular-nums; }}
.small {{ color:#5D6470; font-size:0.85rem; }}
.vcard {{ background: white; border: 1px solid #E3E6EA; border-radius: 6px; padding: 12px 14px; height: 100%; }}
.vcard b {{ color: {INK}; }}
.step {{ border-left: 2px solid {KRAFT}; padding: 2px 0 2px 12px; margin: 4px 0; font-size: 0.9rem; }}
</style>""", unsafe_allow_html=True)

STATUS_LABEL = {"pass": ("Cleared", "ok"), "fail": ("Failed questionnaire", "bad"), "pending": ("Pending evidence", "warn"),
                "include": ("Included by buyer", "ok"), "exclude": ("Excluded by buyer", "mute")}


def money(x):
    if x is None:
        return "-"
    return f"₹{x/1e7:,.2f} cr" if abs(x) >= 1e7 else f"₹{x/1e5:,.1f} lakh" if abs(x) >= 1e5 else f"₹{x:,.0f}"


def short(name):
    return name.split()[0]


def colname(s, v):
    return short(s.vendor_names[v]) + ("" if v in s.eligible else " (not eligible)")


def pill(text, cls):
    return f'<span class="pill {cls}">{text}</span>'


def get_state(refresh=False) -> State:
    if refresh or "state" not in st.session_state:
        st.session_state.state = State()
        st.session_state.pop("analyst", None)
    return st.session_state.state


def refresh():
    get_state(refresh=True)


def need_key_banner():
    if not api_key_present():
        st.warning("Add your Anthropic API key as a secret named ANTHROPIC_API_KEY to run the AI steps. "
                   "Everything already extracted still works without it.")


# =============================================================== pages
def page_overview():
    s = get_state()
    st.title("Corrugated packaging FY27 - Waluj brewery")
    st.markdown(f'<span class="small">{config.RFX_ID} · annual rate contract · 30 lines · bids closed 07-Oct-2026</span>', unsafe_allow_html=True)
    need_key_banner()
    missing = s.missing_extractions()
    if missing:
        st.subheader(f"{len(missing)} vendor replies not read yet")
        st.write("Each reply is read by the extraction agent (Excel, PDF, Word, photo or plain email), mapped to the 30 RFQ lines, "
                 "then checked against the questionnaire.")
        if st.button(f"Read {len(missing)} replies", type="primary", disabled=not api_key_present()):
            from core.pipeline import run_many
            prog = st.status(f"Reading {len(missing)} replies in parallel (usually 1-3 minutes)", expanded=True)
            msgs = []
            res = run_many(missing, progress=msgs.append)
            for m_ in msgs:
                prog.write(m_)
            prog.update(label="Done" if all(v is None for v in res.values()) else "Finished with errors - see above",
                        state="complete" if all(v is None for v in res.values()) else "error")
            refresh(); st.rerun()
    _saved_results()
    if not s.ready():
        return

    res = s.award()
    issues = s.issues()
    hot = [i for i in issues if i["decision_relevant"]]
    if res["uncovered_lines"]:
        st.warning(f"{len(res['uncovered_lines'])} of 30 lines have no eligible quote yet. Under the RFQ rule only vendors that pass every "
                   "mandatory questionnaire item can be awarded. Review queue shows what each blocked vendor is missing and what clearing it is worth.")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Recommended award (eligible vendors)", money(res["total"]) if res["total"] else "No eligible award yet",
              f"{30 - len(res['uncovered_lines'])} of 30 lines covered" if res["uncovered_lines"] else None, delta_color="off")
    c2.metric("Savings vs FY26 contract", money(res["savings_vs_fy26"]) if res["fy26_comparable_base"] else "-",
              f"{res['savings_vs_fy26']/res['fy26_comparable_base']:.1%}" if res["fy26_comparable_base"] else None)
    c3.metric("Vendors eligible", f"{len(s.eligible)} of {len(s.extractions)}")
    c4.metric("Open issues that could change the award", len(hot))

    st.subheader("Vendors")
    cols = st.columns(len(s.extractions))
    for col, (v, ex) in zip(cols, s.extractions.items()):
        lbl, cls = STATUS_LABEL.get(s.status[v], ("?", "mute"))
        ns = [n for n in s.norms if n.vendor == v]
        quoted = sum(1 for n in ns if n.status != "missing")
        rev = sum(1 for n in ns if n.status == "review")
        won = res["by_vendor"].get(s.vendor_names[v], {"lines": 0, "value": 0})
        col.markdown(f"""<div class="vcard"><b>{s.vendor_names[v]}</b><br><span class="small">{(ex.get('vendor_location','') or '')[:42]}{'…' if len(ex.get('vendor_location','') or '')>42 else ''} · sent {', '.join(f.split('.')[-1] for f in ex['_meta']['files'])}</span><br><br>
        {pill(lbl, cls)}<br><br><span class="num">{quoted}/30 lines quoted · {rev} need review</span><br>
        <span class="num">Wins {won['lines']} lines · {money(won['value'])}</span></div>""", unsafe_allow_html=True)

    st.subheader("What needs your attention first")
    if not hot:
        st.success("No open issue can change the current award.")
    for i in hot[:3]:
        _issue_card(s, i, compact=True)
    st.caption("Full list with actions in Review queue.")


def _saved_results():
    """Results of the AI reading are saved on the server. Download them so a restart never costs a re-read."""
    import io, zipfile
    from core.config import EXTRACT_CACHE
    with st.expander("Saved results (backup and restore)"):
        files = sorted(EXTRACT_CACHE.glob("*.json"))
        st.write("The AI's reading of each reply is saved so pages load instantly. Download a backup, or commit these files to "
                 "`cache/extractions/` in the repo so the live app always starts with them. Re-read any reply at any time to see it run live.")
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


def page_draft():
    from core import copilot
    st.title("Draft the RFQ")
    st.write("Describe what you need. The co-pilot pulls approved specs and last year's volumes, proposes a questionnaire and terms, and asks about gaps.")
    need_key_banner()
    if "draft" not in st.session_state:
        st.session_state.draft, st.session_state.draft_hist, st.session_state.draft_chat = copilot.new_draft(), [], []
    left, right = st.columns([5, 6])
    with left:
        for role, text in st.session_state.draft_chat:
            st.chat_message(role).write(text)
        if not st.session_state.draft_chat:
            st.caption('Try: "Annual rate contract for all corrugated packaging at Waluj from November, same items as last year plus the new 7-ply export shippers and the cold-chain carton. Quality matters - we had rejection problems last year."')
        msg = st.chat_input("Tell the co-pilot what you need", disabled=not api_key_present())
        if msg:
            st.session_state.draft_chat.append(("user", msg))
            with st.spinner("Drafting"):
                text, hist = copilot.chat(st.session_state.draft, st.session_state.draft_hist, msg)
            st.session_state.draft_hist = hist
            st.session_state.draft_chat.append(("assistant", text))
            st.rerun()
    with right:
        d = st.session_state.draft
        st.subheader(d["header"].get("title", "Draft (empty)"))
        if d["header"]:
            st.table(pd.DataFrame([d["header"]]).T.rename(columns={0: ""}))
        if d["line_items"]:
            st.markdown(f"**Line items ({len(d['line_items'])})**")
            st.dataframe(pd.DataFrame(d["line_items"]), hide_index=True, width="stretch", height=260)
        if d["questionnaire"]:
            st.markdown("**Supplier questionnaire**")
            st.dataframe(pd.DataFrame(d["questionnaire"]), hide_index=True, width="stretch")
        if d["terms"]:
            st.markdown("**Terms**\n" + "\n".join(f"- {t}" for t in d["terms"]))
        if d["line_items"]:
            st.markdown("**Send to**: " + ", ".join(d["vendors"]))
            if st.button("Send RFQ to vendors", type="primary"):
                st.session_state.sent = True
            if st.session_state.get("sent"):
                st.success(f"Sent to {len(d['vendors'])} vendors by email (simulated channel). Replies arrive in Vendor replies. "
                           f"For this demo the five replies to {config.RFX_ID} are already in the inbox.")


def page_responses():
    from core import readers
    s = get_state()
    st.title("Vendor replies")
    st.write("What each vendor actually sent, next to what the system read from it. Every number cites where it came from.")
    need_key_banner()
    dirs = vendor_dirs()
    names = {d.name: s.vendor_names.get(d.name, d.name) for d in dirs}
    pick = st.selectbox("Vendor", [d.name for d in dirs], format_func=lambda k: names[k])
    vdir = INBOX / pick
    ex = s.extractions.get(pick)
    left, right = st.columns([5, 7])
    with left:
        st.markdown("**Original**")
        for f in sorted(vdir.iterdir()):
            with st.expander(f.name, expanded=f.suffix.lower() in (".jpg", ".png") or f.name == "email.txt"):
                suf = f.suffix.lower()
                if suf in (".jpg", ".jpeg", ".png"):
                    st.image(str(f), width="stretch")
                elif f.name.endswith(".txt"):
                    st.text(f.read_text())
                elif suf == ".pdf":
                    for img in readers.pdf_page_images(f, 70):
                        st.image(img, width="stretch")
                elif suf == ".xlsx":
                    import openpyxl
                    wb = openpyxl.load_workbook(f, data_only=True)
                    for ws in wb.worksheets:
                        st.caption(f"Sheet: {ws.title}")
                        st.dataframe(pd.DataFrame(ws.values).fillna("").astype(str), hide_index=True, width="stretch")
                elif suf == ".docx":
                    st.text(readers.read_docx(f))
        if ex and st.button("Re-read this reply", disabled=not api_key_present()):
            with st.spinner("Reading"):
                run_extraction(vdir)
            refresh(); st.rerun()
    with right:
        if not ex:
            st.info("Not read yet.")
            if st.button("Read this reply", type="primary", disabled=not api_key_present()):
                with st.spinner("Reading"):
                    run_extraction(vdir)
                refresh(); st.rerun()
        else:
            st.markdown(f"**What the system read** · {ex.get('response_summary','')}")
            t = ex.get("terms", {})
            st.markdown(f"Currency **{t.get('currency')}** · GST **{t.get('gst')}** · Freight **{t.get('freight','').replace('_',' ')}** · "
                        f"Payment **{t.get('payment_days')} days** · Lead time **{t.get('lead_time_days')} days**")
            for d_ in ex.get("discounts", []):
                st.markdown(f"Discount found: **{d_['percent']}%** - {d_['condition']} <span class='small'>({d_.get('source','')})</span>", unsafe_allow_html=True)
            for u in ex.get("unreadable_or_uncertain", []):
                st.markdown(f"{pill('Unsure', 'warn')} {u}", unsafe_allow_html=True)
            rows = []
            for n in [n for n in s.norms if n.vendor == pick]:
                worst = max((f.severity for f in n.flags), key=lambda x: ["info", "warn", "critical"].index(x), default="")
                rows.append({"Line": n.line_id, "Vendor's item": n.vendor_item_text, "As written": n.source_quote,
                             "Landed ₹/unit": n.landed, "Readings": " or ".join(f"{c['landed']:.2f}" for c in n.candidates) if len(n.candidates) > 1 else "",
                             "Status": {"ok": "OK", "review": "Needs review", "missing": "Not quoted"}[n.status] + ("" if n.spec_compliant else " · off-spec"),
                             "Flag": {"critical": "Blocking", "warn": "Check", "info": "Note", "": ""}[worst],
                             "Source": n.source})
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", height=430,
                         column_config={"Landed ₹/unit": st.column_config.NumberColumn(format="%.2f")})
            ev = s.q_evals.get(pick)
            if ev:
                st.markdown(f"**Questionnaire** · {pill(*STATUS_LABEL[s.verdicts[pick]])}", unsafe_allow_html=True)
                qmeta = {q["q_id"]: q for q in extract.load_questionnaire()}
                ans = {a.get("q_id"): a.get("answer") for a in ex.get("questionnaire", [])}
                st.dataframe(pd.DataFrame([{"Q": k, "Type": qmeta.get(k, {}).get("type"), "Answer": ans.get(k), "Result": r["status"],
                                            "Why": r.get("reason", "") + (f" [{r['rule_note']}]" if r.get("rule_note") else "") + (" [certificate date check]" if r.get("check") == "deterministic" else "")}
                                           for k, r in sorted(ev["results"].items())]), hide_index=True, width="stretch")

    with st.expander("Add a vendor reply (any format)"):
        name = st.text_input("Vendor name")
        files = st.file_uploader("Files", accept_multiple_files=True)
        body = st.text_area("Email body (optional)")
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


def page_compare():
    s = get_state()
    st.title("Side-by-side comparison")
    st.write("INR per RFQ unit, ex-GST, delivered to Waluj. Same lines, same units, same currency. "
             "Green is the lowest eligible, on-spec price. Amber has more than one possible reading (shown at the vendor's least favourable). "
             "Red is off-spec. Blank is not quoted.")
    if not s.ready():
        st.info("Read the vendor replies first (Overview)."); return
    lines = extract.load_rfx_lines()
    vendors = list(s.extractions)
    by = {(n.vendor, n.line_id): n for n in s.norms}
    data, style = [], []
    for l in lines:
        row, srow = {"Line": l["line_id"], "Item": l["description"], "Qty": int(l["annual_qty"])}, {}
        elig = [by[(v, l["line_id"])] for v in vendors if v in s.eligible and by.get((v, l["line_id"])) and by[(v, l["line_id"])].landed
                and by[(v, l["line_id"])].spec_compliant]
        best = min(elig, key=lambda n: n.landed) if elig else None
        for v in vendors:
            n = by.get((v, l["line_id"]))
            col = colname(s, v)
            row[col] = n.landed if (n and n.landed is not None and n.status != "missing") else float("nan")
            css = ""
            if n is None or n.status == "missing":
                css = "color:#9AA0A6"
            elif not n.spec_compliant:
                css = f"color:{BAD}; text-decoration: line-through"
            elif n.status == "review":
                css = f"background-color:#FBF0DC"
            if best is n and n is not None:
                css += f"; background-color:#DCEFE4; font-weight:600"
            srow[col] = css
        data.append(row); style.append(srow)
    df = pd.DataFrame(data)
    sty = df.style.apply(lambda _: pd.DataFrame([{**{c: "" for c in df.columns}, **r} for r in style], columns=df.columns), axis=None) \
        .format({colname(s, v): lambda x: "" if pd.isna(x) else f"{x:,.2f}" for v in vendors}).format({"Qty": "{:,}"})
    st.dataframe(sty, hide_index=True, width="stretch", height=1100,
                 column_config={colname(s, v): st.column_config.NumberColumn(format="%.2f") for v in vendors} |
                 {"Item": st.column_config.TextColumn(width="large")})
    st.caption("Vendors marked not eligible have failed or not yet cleared the questionnaire. Change eligibility in Review queue.")

    st.subheader("Why is this number what it is?")
    c1, c2 = st.columns(2)
    lid = c1.selectbox("Line", [l["line_id"] for l in lines], format_func=lambda x: f"{x} - {next(l['description'] for l in lines if l['line_id']==x)}")
    v = c2.selectbox("Vendor", vendors, format_func=lambda k: s.vendor_names[k])
    _evidence(s, by.get((v, lid)))


def _evidence(s, n):
    if not n:
        return
    st.markdown(f"**{n.vendor_name} · {n.line_id}** · landed **{'-' if n.landed is None else f'₹{n.landed:,.2f}'}** · source `{n.source}`")
    for stp in n.steps:
        st.markdown(f'<div class="step">{stp}</div>', unsafe_allow_html=True)
    for f in n.flags:
        cls = {"critical": "bad", "warn": "warn", "info": "mute"}[f.severity]
        st.markdown(f"{pill(f.type, cls)} {f.text}", unsafe_allow_html=True)
    if len(n.candidates) > 1:
        st.table(pd.DataFrame([{"Reading": c["label"], "Landed ₹": f"{c['landed']:,.2f}"} for c in n.candidates]))
    _show_source(n)


def _show_source(n):
    """Put the vendor's own words next to the number: the cited line, page or photo."""
    import re
    from core import readers
    vdir = INBOX / n.vendor
    if not vdir.exists():
        return
    st.markdown("**In the vendor's document**")
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
            st.image(pages[k], caption=f"{m.group(1).strip()}, page {k + 1}", width=560)
    imgs = [f for f in vdir.iterdir() if f.suffix.lower() in (".jpg", ".jpeg", ".png")]
    if imgs and (any(f.name in loc for f in imgs) or any(k in loc.lower() for k in ("jpg", "png", "jpeg", "image", "photo")) or hit is None):
        st.image(str(imgs[0]), width=480, caption=imgs[0].name)
    if hit is None and not m and not imgs:
        st.caption("Exact location not found in the text; check the original in Vendor replies.")


def _issue_card(s, i, compact=False):
    crit = i["decision_relevant"] and i["kind"] not in ("freight", "fx", "history")
    cls = "crit" if crit else ("" if i["decision_relevant"] else "low")
    if i["kind"] == "eligibility" and i.get("newly_covered"):
        stake = i["newly_covered_value"]
        stake_lbl = f"of spend on {len(i['newly_covered'])} lines that have no eligible quote today"
    elif i["kind"] == "eligibility":
        stake = abs(i["award_swing"])
        stake_lbl = ("lower award cost if this vendor is cleared" if i["award_swing"] > 0 else
                     "higher award cost if cleared (volume discount effects)" if i["award_swing"] < 0 else "no cost change if cleared")
    elif i["award_swing"]:
        stake, stake_lbl = i["award_swing"], "difference in award cost between the possible readings"
    elif i.get("exposure_in_award"):
        stake, stake_lbl = i["exposure_in_award"], "of the current award rests on this assumption"
    else:
        stake, stake_lbl = i["quote_value_swing"], "of quoted value affected (vendor not in current award)"
    flips = i["lines_flipping"]
    flip_txt = f"Changes the winner on {len(flips)} line{'s' if len(flips)!=1 else ''}" if flips else "Does not change any winner"
    st.markdown(f"""<div class="issue {cls}"><span class="stake">{money(stake)}</span> <span class="small">{stake_lbl}</span><br>
    <b>{i['vendor_name']}</b> · {i['title']}<br><span class="small">{(i.get('detail') + '. ') if i.get('detail') else ''}{flip_txt}. Lines: {', '.join(i['lines'][:12])}{' ...' if len(i['lines'])>12 else ''}</span></div>""",
                unsafe_allow_html=True)
    if compact:
        return
    if i.get("cascade_lines") and i.get("discount_effect"):
        st.markdown(f"Second-order effect: under one reading, a conditional volume discount stops (or starts) applying, which moves "
                    f"{len(i['cascade_lines'])} other lines ({', '.join(i['cascade_lines'])}).")
    if i.get("outcomes"):
        st.table(pd.DataFrame([{"If the value is": o["label"], "Award total": money(o["total"]),
                                f"{i['vendor_name']} wins": f"{o['vendor_lines']} lines",
                                "Volume discounts applied": ", ".join(f"{s.vendor_names.get(d['vendor'], d['vendor'])} {d['percent']:g}%" for d in o["discounts"]) or "none"}
                               for o in i["outcomes"]]))
    dec = load_decisions()
    c1, c2, c3 = st.columns(3)
    if i.get("resolvable") and i.get("outcomes"):
        opts = {o["label"]: o["index"] for o in i["outcomes"]}
        choice = c1.selectbox("Confirmed value", ["(not confirmed)"] + list(opts), key=f"ch_{i['id']}")
        if choice != "(not confirmed)" and c1.button("Apply", key=f"ap_{i['id']}"):
            dec.setdefault("choices", {})[i["id"]] = opts[choice]
            log(dec, "resolved", f"{i['vendor_name']}: {i['title']} -> {choice}")
            refresh(); st.rerun()
    if i["kind"] == "eligibility":
        reason = c1.text_input("Reason (logged)", key=f"rs_{i['id']}", placeholder="e.g. renewed ISO certificate received")
        if c1.button("Include in award", key=f"in_{i['id']}", disabled=not reason):
            dec.setdefault("eligibility", {})[i["vendor"]] = "include"
            log(dec, "eligibility override", f"Included {i['vendor_name']}: {reason}")
            refresh(); st.rerun()
    if c2.button("Draft clarification to vendor", key=f"cl_{i['id']}", disabled=not api_key_present()):
        from core.memo import draft_clarification
        with st.spinner("Drafting"):
            st.session_state[f"mail_{i['id']}"] = draft_clarification(i, s)
        log(dec, "clarification drafted", f"{i['vendor_name']}: {i['title']}")
    if st.session_state.get(f"mail_{i['id']}"):
        st.text_area("Email draft (copy and send)", st.session_state[f"mail_{i['id']}"], height=220, key=f"ta_{i['id']}")


def page_review():
    s = get_state()
    st.title("Review queue")
    st.write("Every uncertainty, ranked by how much money it can move. The system re-runs the award under each possible reading, "
             "so you only spend time on what changes the decision.")
    if not s.ready():
        st.info("Read the vendor replies first."); return
    issues = s.issues()
    hot = [i for i in issues if i["decision_relevant"]]
    cold = [i for i in issues if not i["decision_relevant"]]
    st.subheader(f"Could change the award ({len(hot)})")
    for i in hot:
        _issue_card(s, i)
    with st.expander(f"Noted, no effect on the current award ({len(cold)})"):
        for i in cold:
            _issue_card(s, i, compact=True)
    dec = load_decisions()
    with st.expander(f"Decision log ({len(dec.get('log', []))})"):
        st.dataframe(pd.DataFrame(dec.get("log", [])), hide_index=True, width="stretch")
        if st.button("Reset all buyer decisions"):
            reset_decisions(); refresh(); st.rerun()


SUGGESTED = [
    "What if we split it, cheapest per line, but only among vendors who cleared the quality questionnaire?",
    "Who is cheapest on our five biggest lines by annual value, and how confident are we in those prices?",
    "If Godavari's blurred 5-ply rate is 62.50 instead of 68.50, what changes in the award?",
    "Consolidate to two vendors at most. What does it cost us versus the best split?",
    "Nordvik is cheapest on the Classic 650 shipper. What would it take to award them, and what's the risk?",
    "Chart landed cost by vendor for the 650 ml shippers and export the full comparison to Excel.",
]


def page_analyst():
    from core.analyst import Analyst
    s = get_state()
    st.title("Ask the data")
    st.write("Plain-language questions over the full comparison. Answers come from real queries and award runs, shown under each answer.")
    need_key_banner()
    if not s.ready():
        st.info("Read the vendor replies first."); return
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
        st.caption("Questions worth asking")
        for i, sq in enumerate(SUGGESTED):
            if st.button(sq, key=f"sq{i}"):
                q = sq
    typed = st.chat_input("Ask about prices, vendors, scenarios, risks", disabled=not api_key_present())
    q = typed or q
    if q:
        st.chat_message("user").write(q)
        with st.chat_message("assistant"):
            box = st.status("Working", expanded=False)
            text, hist, outs = a.ask(st.session_state.an_hist, q,
                                     on_step=lambda stp: box.write(f"{stp['tool']}: {json.dumps(stp['input'])[:160]}"))
            box.update(label=f"Done · {len(outs)} steps", state="complete")
        st.session_state.an_hist = hist
        st.session_state.an_view.append({"q": q, "a": text, "outputs": outs})
        st.rerun()
    if st.session_state.an_view and st.button("Clear conversation"):
        st.session_state.an_hist, st.session_state.an_view = [], []
        st.rerun()


def _render_outputs(outs):
    for k, o in enumerate(outs):
        if o["type"] in ("table", "award"):
            if o["type"] == "award":
                r = o["res"]
                st.markdown(f"**{o['title']}** · total {money(r['total'])} · " +
                            " · ".join(f"{v}: {d['lines']} lines {money(d['value'])}" for v, d in r["by_vendor"].items()))
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
                fig.update_layout(font_family="IBM Plex Sans", plot_bgcolor="white", paper_bgcolor="white",
                                  colorway=[INK, KRAFT, "#5B8DB8", "#7A9E7E", "#C46B5A"])
                st.plotly_chart(fig, width="stretch", key=f"ch{id(o)}{k}")
            except Exception as e:
                st.caption(f"Chart could not be drawn: {e}")
        elif o["type"] == "download":
            st.download_button(f"Download {o['title']}", o["data"], file_name=o["title"], key=f"dl{id(o)}{k}")
        elif o["type"] == "evidence":
            with st.expander(o["title"]):
                st.json(o["data"])
        if o.get("sql"):
            with st.expander("How this was computed"):
                st.code(o["sql"], language="sql")


def page_memo():
    from core.memo import write_memo, memo_workbook
    s = get_state()
    st.title("Award recommendation")
    st.write("A one-page memo for approval, written only from computed numbers, plus an Excel pack with the full audit trail.")
    need_key_banner()
    if not s.ready():
        st.info("Read the vendor replies first."); return
    if st.button("Write the memo", type="primary", disabled=not api_key_present()):
        with st.spinner("Writing"):
            md, facts, res = write_memo(s)
        st.session_state.memo = (md, res)
        log(load_decisions(), "memo generated", f"Award {money(res['total'])}")
    if st.session_state.get("memo"):
        md, res = st.session_state.memo
        st.markdown(md)
        c1, c2 = st.columns(2)
        c1.download_button("Download memo (Markdown)", md, file_name="award_memo.md")
        c2.download_button("Download award pack (Excel)", memo_workbook(s, res, s.issues()), file_name="award_pack.xlsx")


def page_accuracy():
    from core.evaluate import score
    s = get_state()
    st.title("How accurate was the reading?")
    st.write("The demo dataset has a hidden answer key that the AI never sees. This scores the live extraction against it. "
             "The number that matters most is 'confidently wrong': a wrong price shown without any warning.")
    if not s.ready():
        st.info("Read the vendor replies first."); return
    r = score(s.norms, s.extractions, s.verdicts)
    c = r["counts"]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Prices read correctly", f"{c['correct']} / {r['total_values']}")
    c2.metric("Ambiguous, flagged not guessed", c["flagged_not_guessed"])
    c3.metric("Wrong but flagged", c["wrong_but_flagged"])
    c4.metric("Confidently wrong", c["confidently_wrong"])
    st.markdown(f"Missed lines: **{c['missed_line']}** · invented lines: **{c['invented_line']}** · correctly identified as not quoted: **{c['correctly_missing']}**")
    st.subheader("Planted traps")
    st.dataframe(pd.DataFrame([{"Vendor": t["vendor"], "Trap": t["type"], "Detail": t["detail"], "Caught": "Yes" if t["caught"] else "No"} for t in r["traps"]]),
                 hide_index=True, width="stretch")
    st.subheader("Questionnaire verdicts")
    st.dataframe(pd.DataFrame(r["questionnaire"]), hide_index=True, width="stretch")
    bad = [x for x in r["rows"] if x["result"] not in ("correct", "correctly_missing")]
    if bad:
        st.subheader("Every value that was not simply correct")
        st.dataframe(pd.DataFrame(bad), hide_index=True, width="stretch")
    models = {ex["_meta"].get("model") for ex in s.extractions.values()}
    st.caption(f"Extraction model: {', '.join(m for m in models if m)}")


pages = [st.Page(page_overview, title="Overview", default=True),
         st.Page(page_draft, title="Draft RFQ", url_path="draft"),
         st.Page(page_responses, title="Vendor replies", url_path="replies"),
         st.Page(page_compare, title="Comparison", url_path="compare"),
         st.Page(page_review, title="Review queue", url_path="review"),
         st.Page(page_analyst, title="Ask the data", url_path="ask"),
         st.Page(page_memo, title="Award memo", url_path="memo"),
         st.Page(page_accuracy, title="Accuracy check", url_path="accuracy")]
nav = st.navigation(pages)
with st.sidebar:
    st.markdown("**Quote desk**")
    st.caption("Deccan Peak Breweries, packaging category. Demo data; all companies are fictional.")
nav.run()
