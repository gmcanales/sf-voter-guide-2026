"""Law-enforcement union money for candidates: direct contributions from police, deputy
sheriff and other peace-officer associations (and their PACs) to the candidate's own
committee for this race.

    py tools/police_union_money.py [--since 2025-01-01]

SF: contributions come from the same DataSF rows as tools/funding_tags.py (money_in, with
its amendment and late-report rules) for each candidate's committees in
data-src/funding_entities.json. County ballots: each candidate committee already matched in
site/data/counties/<county>/candidate_money.json is re-read from NetFile
(local_measure_money.committee_rows). Independent spending and slate mailers aren't
counted: matching those to a candidate by name also catches gifts to the same person's
other committees (e.g. a party-committee race), so they need review case by case.

A donor counts only by its own name (UNION_RE): individual officers giving personally are
not unions and are never counted. Spelling variants of one donor are merged (canon).
Every match is printed for review.

Writes site/data/police_money.json: {candidates: {contest id: {name: {total, gifts:
[{donor, amount}]}}}}.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from funding_tags import money_in  # noqa: E402
from local_measure_money import agencies, committee_rows  # noqa: E402
from money_flows import donor_label  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
UNION_RE = re.compile(
    r"police (officers'?|officer'?s'?|managers'?)?\s*(association|assn|union|league)"
    r"|police association|peace officers?'?\s*(association|research)|deputy sheriffs?'?s?'?\s*(association|assn)"
    r"|sheriffs?'?s?'?\s*(association|assn|managers)|law enforcement (association|officers)"
    r"|correctional (officers|peace)|probation (officers|peace)|\bPORAC\b|\bCOPS\b", re.I)


def canon(name: str) -> str:
    """'SAN FRANCISCO DEPUTY SHERIFF'S ASSOCIATION PAC' and '... Sheriffs' Association Political
    Action Committee' are one donor."""
    n = re.sub(r"political action committee", "PAC", name, flags=re.I)
    return re.sub(r"[^a-z0-9 ]", "", n.lower()).replace("sheriffs", "sheriff").replace("officers", "officer")


def keep(rows: list[tuple[str, float]]) -> dict | None:
    by, label = defaultdict(float), {}
    for d, a in rows:
        k = canon(d)
        by[k] += a
        label.setdefault(k, d)
    gifts = sorted(({"donor": label[k], "amount": round(a)} for k, a in by.items()), key=lambda g: -g["amount"])
    return {"total": sum(g["amount"] for g in gifts), "gifts": gifts} if gifts else None


def sf(since: str) -> dict:
    ent = json.loads((ROOT / "data-src" / "funding_entities.json").read_text(encoding="utf-8"))
    out = {}
    for cid, cands in ent["candidates"].items():
        for name, nids in cands.items():
            rec = keep([(donor_label(r), float(r.get("calculated_amount") or 0))
                        for r in (money_in(nids, since) if nids else [])
                        if r["form_type"] != "F460ALine2" and r.get("entity_code") != "IND" and UNION_RE.search(donor_label(r))])
            if rec:
                out.setdefault(cid, {})[name] = rec
                print(f"  SF    {name[:26]:26} ${rec['total']:>7,}  {[g['donor'] for g in rec['gifts']]}")
    return out


def counties(since: str) -> dict:
    ags = {a["shortcut"]: a for a in agencies()}
    out = {}
    for county in ("alameda", "sanmateo", "contracosta"):
        cm = json.loads((ROOT / "site" / "data" / "counties" / county / "candidate_money.json").read_text(encoding="utf-8"))
        for cid, cands in cm["candidates"].items():
            for name, r in cands.items():
                if not r.get("itemized"):
                    continue
                rec = keep([(row["name"], row["amount"])
                            for row in committee_rows(ags[r["agency"]], r["fppc_id"], r["committee"], since) or []
                            if UNION_RE.search(row.get("name") or "")])
                if rec:
                    rec["portal"] = r.get("portal")
                    out.setdefault(cid, {})[name] = rec
                    print(f"  {r['agency']:5} {name[:26]:26} ${rec['total']:>7,}  {[g['donor'] for g in rec['gifts']]}")
    return out


def main(since: str) -> None:
    out = {**sf(since), **counties(since)}
    dest = ROOT / "site" / "data" / "police_money.json"
    dest.write_text(json.dumps({
        "built": date.today().isoformat(), "since": since,
        "source": {"sf": "SF Ethics Commission filings (DataSF)", "counties": "NetFile public API (local Form 460 / 497 filings)"},
        "candidates": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{sum(len(v) for v in out.values())} candidates with law-enforcement union money -> {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = argparse.ArgumentParser()
    p.add_argument("--since", default="2025-01-01")
    main(p.parse_args().since)
