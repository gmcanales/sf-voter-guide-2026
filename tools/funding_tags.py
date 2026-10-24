"""Compute evidence-based funding tags for guides and local candidates.

    py tools/funding_tags.py                # all entities in data-src/funding_entities.json
    py tools/funding_tags.py --since 2025-01-01

Source: SF Ethics Commission campaign finance data on DataSF (dataset
pitq-e56w), queried live. Writes site/data/funding.json.

Method (published on the page, keep it in sync with docs/data-model.md):
  * Money in = itemized monetary contributions (Form 460 Schedule A) +
    unitemized contributions under $100 (Schedule A line 2) + late
    contributions (Form 497) dated after the committee's last 460 period.
  * Amended filings: for each committee and reporting period only the latest
    filed version is used, so amendments aren't double counted.
  * Donors are aggregated by name + ZIP within the window before sizing.
  * Small donors: donors whose total is at most SMALL_GUIDE ($250) for groups or
    SMALL_CAND ($100) for candidates (SF caps candidate gifts at $500).
    Unitemized money counts as small.
  * Big donors (groups only): donors totaling at least BIG ($10,000).
  * Tech: individual donors whose employer or occupation matches TECH_*,
    plus organization donors whose name matches TECH_EMPLOYERS.
  * Outside money (candidates): spending or giving by OTHER committees that names the
    candidate (Form 460 Schedule D + later Form 496 24-hour reports), split support/oppose.
    Tagged when support >= the candidate's own money (contributions + public funds
    approved, DataSF 5sxz-kk66) and >= OUTSIDE_MIN.
Tags fire only past the thresholds in TAG_RULES; every tag carries its number.
"""
import argparse
import json
import re
import sys
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://data.sf.gov/resource/pitq-e56w.json"

SMALL_GUIDE, SMALL_CAND, BIG = 250, 100, 10_000
TAG_RULES = {  # tag id: (metric, threshold share of money in)
    "small-donor": ("small_pct", 0.50),
    "big-donor": ("big_pct", 0.50),
    "tech-funded": ("tech_pct", 0.25),
}
OUTSIDE_RULE = 1.0   # "Outside-money backed": supporting outside spending >= 100% of the candidate's own money
OUTSIDE_MIN = 10_000 # ...and at least this much, so a stray $500 club contribution doesn't count

# Deliberately explicit and reviewable. Substring match, case-insensitive.
TECH_EMPLOYERS = [
    "GOOGLE", "ALPHABET", "META PLATFORMS", "FACEBOOK", "APPLE INC", "MICROSOFT", "AMAZON", "SALESFORCE", "UBER",
    "LYFT", "AIRBNB", "STRIPE", "OPENAI", "ANTHROPIC", "COINBASE", "RIPPLE", "TWITTER", "X CORP", "PALANTIR",
    "NVIDIA", "LINKEDIN", "DROPBOX", "PINTEREST", "DOORDASH", "INSTACART", "FIGMA", "DATABRICKS", "SNOWFLAKE",
    "Y COMBINATOR", "YCOMBINATOR", "ANDREESSEN", "A16Z", "SEQUOIA", "GENERAL CATALYST", "FOUNDERS FUND", "KHOSLA",
    "GREYLOCK", "KLEINER", "LIGHTSPEED", "INDEX VENTURES", "RIBBIT CAPITAL", "TWILIO", "ROBINHOOD", "PLAID",
    "BLOCK, INC", "SQUARE INC", "ADOBE", "ORACLE", "NETFLIX", "TESLA", "SPACEX", "SCALE AI", "WAYMO", "CRUISE LLC",
    "GITHUB", "ATLASSIAN", "ASANA", "GUSTO", "BREX", "VERCEL", "NOTION LABS", "INITIALIZED CAPITAL", "SV ANGEL",
]
TECH_OCCUPATIONS = [
    "SOFTWARE", "DEVELOPER", "PROGRAMMER", "PRODUCT MANAGER", "DATA SCIENTIST", "MACHINE LEARNING",
    "VENTURE CAPITAL", "VENTURE PARTNER", "TECH EXECUTIVE", "TECHNOLOGY EXECUTIVE",
]


def fetch(where: str, select: str | None = None) -> list[dict]:
    rows, offset = [], 0
    while True:
        q = {"$where": where, "$limit": 50000, "$offset": offset}
        if select:
            q["$select"] = select
        url = f"{API}?{urllib.parse.urlencode(q)}"
        req = urllib.request.Request(url, headers={"User-Agent": "sf_voter_guide/1.0"})
        with urllib.request.urlopen(req, timeout=120) as r:
            batch = json.load(r)
        rows += batch
        if len(batch) < 50000:
            return rows
        offset += 50000


def latest_versions(rows: list[dict]) -> list[dict]:
    """Keep only rows from the newest filing per (committee, period)."""
    best = {}
    for r in rows:
        key = (r.get("filer_nid"), r.get("start_date"), r.get("end_date"))
        rank = (r.get("filing_date", ""), float(r.get("filing_version") or 0), r.get("filing_id_number", ""))
        if key not in best or rank > best[key]:
            best[key] = rank
    return [r for r in rows if (r.get("filing_date", ""), float(r.get("filing_version") or 0),
                                r.get("filing_id_number", "")) == best[(r.get("filer_nid"), r.get("start_date"), r.get("end_date"))]]


def is_tech(r: dict) -> bool:
    emp = (r.get("transaction_employer") or "").upper()
    occ = (r.get("transaction_occupation") or "").upper()
    name = (r.get("transaction_last_name") or "").upper()
    if r.get("entity_code") == "IND":
        return any(t in emp for t in TECH_EMPLOYERS) or any(t in occ for t in TECH_OCCUPATIONS)
    return any(t in name for t in TECH_EMPLOYERS)


def money_in(nids: list[int], since: str) -> list[dict]:
    if not nids:
        return []
    ids = ",".join(f"'{n}'" for n in nids)
    base = f"filer_nid in ({ids})"
    s460 = latest_versions(fetch(f"{base} AND form_type in ('A','F460ALine2') AND end_date >= '{since}'"))
    last_end = defaultdict(str)
    for r in s460:
        last_end[r["filer_nid"]] = max(last_end[r["filer_nid"]], r.get("end_date", ""))
    late = [r for r in fetch(f"{base} AND form_type='F497P1' AND transaction_date >= '{since}'")
            if r.get("transaction_date", "") > last_end[r["filer_nid"]]]
    # 497s can be amended too; dedupe by transaction id, keeping the latest filing.
    by_tx = {}
    for r in late:
        k = (r["filer_nid"], r.get("transaction_id"))
        if k not in by_tx or r.get("filing_date", "") > by_tx[k].get("filing_date", ""):
            by_tx[k] = r
    out = []
    for r in s460:
        if r["form_type"] == "A" and r.get("transaction_date", r.get("end_date", "")) < since:
            continue
        out.append(r)
    return out + list(by_tx.values())


def summarize(rows: list[dict], small_cap: float, with_big: bool) -> dict:
    unitemized = sum(float(r.get("calculated_amount") or 0) for r in rows if r["form_type"] == "F460ALine2")
    donors = defaultdict(lambda: {"amt": 0.0, "tech": False})
    for r in rows:
        if r["form_type"] == "F460ALine2":
            continue
        key = ((r.get("transaction_first_name") or "").strip().upper(),
               (r.get("transaction_last_name") or "").strip().upper(),
               (r.get("transaction_zip") or "")[:5])
        donors[key]["amt"] += float(r.get("calculated_amount") or 0)
        donors[key]["tech"] |= is_tech(r)
    total = unitemized + sum(d["amt"] for d in donors.values())
    if total <= 0:
        return {"total": 0}
    small = unitemized + sum(d["amt"] for d in donors.values() if d["amt"] <= small_cap)
    out = {
        "total": round(total),
        "donors": len(donors),
        "small_pct": round(small / total, 3),
        "tech_pct": round(sum(d["amt"] for d in donors.values() if d["tech"]) / total, 3),
    }
    if with_big:
        out["big_pct"] = round(sum(d["amt"] for d in donors.values() if d["amt"] >= BIG) / total, 3)
    return out


def norm_name(first: str, last: str) -> str:
    """'Alan' + 'Wong' or '' + 'Alan Wong' -> 'ALAN WONG' (filers fill these fields inconsistently)."""
    full = f"{first or ''} {last or ''}".upper()
    full = re.sub(r"[“”\"(].*?[”\")]", " ", full).replace(".", " ")
    return " ".join(w for w in full.split() if w not in ("II", "III", "JR", "SR"))


def outside_money(since: str) -> dict:
    """Spending by OTHER committees naming a candidate, split support/oppose.
    Schedule D (Form 460, latest version per period) plus 24-hour Form 496
    reports dated after the spender's last 460 period, so nothing is counted twice."""
    sched_d = latest_versions(fetch(f"form_type='D' AND end_date >= '{since}' AND support_oppose_code IS NOT NULL"))
    last_end = defaultdict(str)
    for r in sched_d:
        last_end[r["filer_nid"]] = max(last_end[r["filer_nid"]], r.get("end_date", ""))
    f496 = {}
    for r in fetch(f"form_type='F496' AND calculated_date >= '{since}'"):
        if r.get("calculated_date", "") <= last_end[r["filer_nid"]]:
            continue
        k = (r["filer_nid"], r.get("transaction_id"))
        if k not in f496 or r.get("filing_date", "") > f496[k].get("filing_date", ""):
            f496[k] = r
    agg = defaultdict(lambda: {"support": 0.0, "oppose": 0.0})
    for r in sched_d + list(f496.values()):
        name = norm_name(r.get("candidate_first_name"), r.get("candidate_last_name"))
        if not name:
            continue
        side = "oppose" if (r.get("support_oppose_code") or "").upper().startswith("O") else "support"
        agg[(name, (r.get("district_number") or "").strip())][side] += float(r.get("calculated_amount") or 0)
    return agg


def tags_for(m: dict) -> list[dict]:
    tags = []
    for tag, (metric, cut) in TAG_RULES.items():
        if m.get(metric) is not None and m["total"] and m[metric] >= cut:
            tags.append({"tag": tag, "pct": m[metric]})
    return tags


def first_variants(name: str) -> set[str]:
    """Ways a filer might write the first name: legal name, nickname in quotes or
    parentheses, and letters-only initials ("J.R." -> "JR")."""
    vs = set()
    nick = re.findall(r"[“\"(]([^”\")]+)[”\")]", name)
    legal = re.sub(r"[“\"(].*?[”\")]", " ", name).split()
    if legal:
        vs.add(re.sub(r"[^A-Z]", "", legal[0].upper()))
    for n in nick:
        vs.add(re.sub(r"[^A-Z]", "", n.split()[0].upper()))
    return {v for v in vs if v}


def name_matches(record_name: str, record_district: str, cand_name: str, contest_id: str) -> bool:
    rec = record_name.split()
    if not rec:
        return False
    last, _ = surname_key(cand_name)
    if rec[-1] != last:
        return False
    if contest_id.startswith("sup-") and record_district and record_district.strip() not in ("", contest_id[4:]):
        return False
    rec_first = re.sub(r"[^A-Z]", "", rec[0])
    # "J R EPPLER" (dots normalized away): rejoin leading single-letter initials -> "JR".
    initials = "".join(t for t in rec[:-1] if len(t) == 1)
    if len(initials) > 1:
        rec_first = initials
    return any(rec_first[:2] == v[:2] or rec_first == v for v in first_variants(cand_name))


def surname_key(name: str) -> tuple[str, str]:
    clean = re.sub(r"[“”\"(].*?[”\")]", " ", name)
    parts = [p for p in re.split(r"\s+", re.sub(r"[.,]", " ", clean.upper())) if p]
    # Drop generational suffixes from the END only, so "J.R. Eppler" keeps its initials.
    while len(parts) > 1 and parts[-1] in ("II", "III", "JR", "SR"):
        parts.pop()
    return parts[-1], parts[0][:3]


PUBLIC_FUNDS_URL = "https://data.sf.gov/resource/5sxz-kk66.json?$limit=500"   # Nov 2026 public funds approved


def public_funds() -> list[tuple[str, str, float]]:
    """[(normalized 'FIRST LAST', district, amount)] from SF Ethics' public-financing dataset.
    The dataset writes names 'Last, First'."""
    req = urllib.request.Request(PUBLIC_FUNDS_URL, headers={"User-Agent": "sf_voter_guide/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        rows = json.load(r)
    out = []
    for x in rows:
        last, _, first = (x.get("candidate") or "").partition(",")
        out.append((norm_name(first.replace('"', "“", 1).replace('"', "”", 1), last), (x.get("district") or "").strip(),
                    float(x.get("sum_funds_approved") or 0)))
    return out


def main(since: str) -> None:
    ent = json.loads((ROOT / "data-src" / "funding_entities.json").read_text(encoding="utf-8"))
    out = {"built": date.today().isoformat(), "since": since,
           "source": {"label": "SF Ethics Commission campaign finance data (DataSF)", "url": "https://data.sf.gov/d/pitq-e56w"},
           "rules": {"small_guide": SMALL_GUIDE, "small_candidate": SMALL_CAND, "big": BIG,
                     "thresholds": {k: v[1] for k, v in TAG_RULES.items()}, "outside_ratio": OUTSIDE_RULE, "outside_min": OUTSIDE_MIN},
           "public_funds_source": {"label": "SF Ethics: Total Public Funds Approved, Nov 3 2026", "url": "https://data.sf.gov/d/5sxz-kk66"},
           "guides": {}, "candidates": {}}
    for gid, nids in ent["guides"].items():
        m = summarize(money_in(nids, since), SMALL_GUIDE, with_big=True)
        m["tags"] = tags_for(m)
        out["guides"][gid] = m
        print(f"guide {gid:10} {m}")
    ie = outside_money(since)
    pf = public_funds()
    for cid, cands in ent["candidates"].items():
        for name, nids in cands.items():
            m = summarize(money_in(nids, since), SMALL_CAND, with_big=False) if nids else {"total": 0, "no_committee": True}
            hits = [v for (n, dist), v in ie.items() if name_matches(n, dist, name, cid)]
            sup = sum(h["support"] for h in hits); opp = sum(h["oppose"] for h in hits)
            if sup or opp:
                m["outside_support"], m["outside_oppose"] = round(sup), round(opp)
            pub = sum(a for n, dist, a in pf if name_matches(n, dist, name, cid))
            if pub:
                m["public_funds"] = round(pub)
            m["tags"] = tags_for(m) if m.get("total") else []
            # Compare outside support with everything the campaign itself has: contributions + public funds.
            own = m.get("total", 0) + pub
            if sup >= OUTSIDE_MIN and sup >= OUTSIDE_RULE * own:
                m["tags"].append({"tag": "outside-backed", "amount": round(sup)})
            out["candidates"].setdefault(cid, {})[name] = m
            print(f"cand {cid:18} {name:28} {m}")
    dest = ROOT / "site" / "data" / "funding.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2025-01-01")
    sys.stdout.reconfigure(encoding="utf-8")
    main(ap.parse_args().since)
