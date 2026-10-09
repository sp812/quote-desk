"""Orchestration + buyer decisions + audit trail."""
from __future__ import annotations
import json
from datetime import datetime

from .config import INBOX, STATE_FILE, EXTRACT_CACHE
from . import extract, questionnaire
from .normalize import normalize_all, conditional_discounts
from .award import award, Scenario, impact


# ---------------- buyer decisions & audit log ----------------
def load_decisions() -> dict:
    """Never let a damaged decisions file take the app down: keep a copy of it and start clean."""
    blank = {"choices": {}, "eligibility": {}, "log": []}
    if not STATE_FILE.exists():
        return blank
    try:
        d = json.loads(STATE_FILE.read_text())
        if not isinstance(d, dict):
            raise ValueError("not an object")
    except Exception:
        STATE_FILE.rename(STATE_FILE.with_suffix(f".damaged-{datetime.now():%Y%m%d%H%M%S}.json"))
        return blank
    for k, v in blank.items():
        if not isinstance(d.get(k), type(v)):
            d[k] = type(v)()
    return d


def save_decisions(d: dict) -> None:
    STATE_FILE.write_text(json.dumps(d, indent=2))


def log(d: dict, action: str, detail: str, actor: str = "buyer") -> None:
    d.setdefault("log", []).append({"ts": datetime.now().isoformat(timespec="seconds"), "actor": actor,
                                    "action": action, "detail": detail})
    save_decisions(d)


def reset_decisions():
    if STATE_FILE.exists():
        STATE_FILE.unlink()


# ---------------- pipeline ----------------
def vendor_dirs():
    return sorted([p for p in INBOX.iterdir() if p.is_dir()])


def run_many(dirs, progress=None, workers=3):
    """Read several vendor replies in parallel. Returns {vendor: error or None}."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    out = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futs = {pool.submit(_extract_only, d): d for d in dirs}
        for f in as_completed(futs):
            d = futs[f]
            try:
                f.result(); out[d.name] = None
                if progress: progress(f"Read {d.name}")
            except Exception as e:
                from .llm import friendly_error
                out[d.name] = friendly_error(e)
                if progress: progress(f"Could not read {d.name}: {friendly_error(e)}")
    dec = load_decisions()
    log(dec, "extraction", f"Read {sum(1 for v in out.values() if v is None)} of {len(out)} replies", actor="system")
    return out


def _extract_only(vdir):
    ex = extract.extract_vendor(vdir)
    questionnaire.evaluate_vendor(vdir.name, ex)
    return ex


def run_extraction(vdir, progress=None):
    ex = extract.extract_vendor(vdir)
    if progress: progress(f"Read {vdir.name}: {len(ex['line_quotes'])} lines quoted")
    q = questionnaire.evaluate_vendor(vdir.name, ex)
    d = load_decisions()
    log(d, "extraction", f"{vdir.name}: {len(ex['line_quotes'])} quotes, {len(ex['lines_not_quoted'])} not quoted, "
        f"{len(ex.get('unreadable_or_uncertain', []))} uncertainties", actor="system")
    return ex, q


def _unique_names(names: dict[str, str]) -> dict[str, str]:
    """Two replies from vendors with the same name would merge in every total; keep them apart."""
    out, seen = {}, {}
    for k, n in names.items():
        n = n.strip() or k
        seen[n] = seen.get(n, 0) + 1
        out[k] = n if seen[n] == 1 else f"{n} ({seen[n]})"
    return out


class State:
    """Everything the UI and the analyst need, rebuilt from cached extractions + buyer decisions."""

    def __init__(self):
        self.decisions = load_decisions()
        self.extractions = extract.load_cached()
        self.q_evals = questionnaire.load_cached()
        self.norms = normalize_all(self.extractions, self.decisions) if self.extractions else []
        self.discounts = conditional_discounts(self.extractions)
        self.vendor_names = _unique_names({k: (v.get("vendor_name") or k) for k, v in self.extractions.items()})
        for n in self.norms:
            n.vendor_name = self.vendor_names[n.vendor]
        self.verdicts = {}
        for v in self.extractions:
            if v in self.q_evals:
                self.verdicts[v] = questionnaire.verdict(self.q_evals[v])
            else:
                self.verdicts[v] = "pending"
        # buyer overrides on eligibility ("include pending docs" etc.)
        self.status = {v: self.decisions.get("eligibility", {}).get(v, self.verdicts[v]) for v in self.extractions}

    @property
    def eligible(self) -> set[str]:
        return {v for v, s in self.status.items() if s in ("pass", "include")}

    def scenario(self, **kw) -> Scenario:
        sc = Scenario(eligible=kw.pop("eligible", None) or set(self.eligible), **kw)
        sc.overrides = dict(self.decisions.get("choices", {}), **sc.overrides)
        return sc

    def award(self, **kw):
        return award(self.norms, self.scenario(**kw), self.discounts)

    def issues(self):
        sc = self.scenario()
        others = {v: s for v, s in self.status.items() if v not in sc.eligible}
        issues = impact(self.norms, sc, self.discounts, others, self.vendor_names)
        for i in issues:
            if i["kind"] == "eligibility":
                ev = self.q_evals.get(i["vendor"], {}).get("results", {})
                why = "; ".join(f"{q} {r['status']}: {r['reason']}" for q, r in sorted(ev.items()) if r["status"] != "pass") or "no questionnaire evaluation"
                st_txt = {"fail": "Failed questionnaire", "pending": "Questionnaire evidence pending", "exclude": "Excluded by buyer"}.get(i.get("status"), i.get("status"))
                i["title"] = f"{st_txt}. {why}"
                i["detail"] = f"If cleared, wins {len(i['lines'])} lines"
        return issues

    def ready(self) -> bool:
        return bool(self.extractions)

    def missing_extractions(self):
        return [d for d in vendor_dirs() if not (EXTRACT_CACHE / f"{d.name}.json").exists()]
