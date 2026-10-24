"""Money-flow detail for the "Money" tabs: who funds each local measure's
committees, and which outside committees spend for/against each local candidate.

    py tools/money_flows.py [--since 2025-01-01]

Reads data-src/measure_committees.json and data-src/funding_entities.json,
queries SF Ethics data (DataSF pitq-e56w) with the same rules as
tools/funding_tags.py (latest filing versions only, late reports only after the
last 460 period), and writes site/data/money.json.
"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from funding_tags import fetch, latest_versions, money_in, name_matches, norm_name  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
TOP_N = 8


def committee_names(nids) -> dict:
    import urllib.parse, urllib.request
    ids = ",".join(f"'{n}'" for n in nids)
    q = urllib.parse.urlencode({"$where": f"filer_nid in ({ids})", "$limit": 500})
    req = urllib.request.Request(f"https://data.sf.gov/resource/4c8t-ngau.json?{q}", headers={"User-Agent": "sf_voter_guide/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return {int(x["filer_nid"]): x["filer_name"] for x in json.load(r)}


def donor_label(r: dict) -> str:
    if r.get("entity_code") == "IND":
        name = f"{(r.get('transaction_first_name') or '').title()} {(r.get('transaction_last_name') or '').title()}".strip()
        emp = (r.get("transaction_employer") or "").title()
        return f"{name} ({emp})" if emp and "Self" not in emp and "N/A" not in emp.upper() else name
    return (r.get("transaction_last_name") or "").strip()


def committee_profile(nid: int, since: str) -> dict:
    rows = money_in([nid], since)
    total = sum(float(r.get("calculated_amount") or 0) for r in rows)
    donors = defaultdict(float)
    for r in rows:
        if r["form_type"] != "F460ALine2":
            donors[donor_label(r)] += float(r.get("calculated_amount") or 0)
    top = sorted(donors.items(), key=lambda kv: -kv[1])[:TOP_N]
    return {"total": round(total), "donors": len(donors),
            "top": [{"name": n, "amount": round(a)} for n, a in top],
            "top_share": round(sum(a for _, a in top) / total, 3) if total else 0}


def outside_by_spender(since: str) -> dict:
    """{(normalized candidate name, district): {spender name: {support, oppose}}}"""
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
    out = defaultdict(lambda: defaultdict(lambda: {"support": 0.0, "oppose": 0.0}))
    for r in sched_d + list(f496.values()):
        name = norm_name(r.get("candidate_first_name"), r.get("candidate_last_name"))
        if not name:
            continue
        side = "oppose" if (r.get("support_oppose_code") or "").upper().startswith("O") else "support"
        out[(name, (r.get("district_number") or "").strip())][r.get("filer_name", "?")][side] += float(r.get("calculated_amount") or 0)
    return out


def main(since: str) -> None:
    mc = json.loads((ROOT / "data-src" / "measure_committees.json").read_text(encoding="utf-8"))
    mc.pop("_about", None)
    names = committee_names({c["nid"] for cs in mc.values() for c in cs})
    cache = {}
    measures = {}
    for mid, comms in mc.items():
        entries = []
        for c in comms:
            if c["nid"] not in cache:
                cache[c["nid"]] = committee_profile(c["nid"], since)
            entries.append({"name": names.get(c["nid"], str(c["nid"])), "nid": c["nid"], "side": c["side"], **cache[c["nid"]]})
        measures[mid] = entries
        for e in entries:
            print(f"{mid:7} {e['side']:3} ${e['total']:>12,}  {e['name'][:70]}")

    ent = json.loads((ROOT / "data-src" / "funding_entities.json").read_text(encoding="utf-8"))
    ob = outside_by_spender(since)
    cands = {}
    for cid, cs in ent["candidates"].items():
        for name in cs:
            spend = defaultdict(lambda: {"support": 0.0, "oppose": 0.0})
            for (n, dist), by in ob.items():
                if name_matches(n, dist, name, cid):
                    for spender, v in by.items():
                        spend[spender]["support"] += v["support"]; spend[spender]["oppose"] += v["oppose"]
            rows = sorted(({"committee": k, "support": round(v["support"]), "oppose": round(v["oppose"])}
                           for k, v in spend.items() if v["support"] + v["oppose"] >= 1000),
                          key=lambda x: -(x["support"] + x["oppose"]))
            cands.setdefault(cid, {})[name] = {"outside": rows}
    out = {"built": date.today().isoformat(), "since": since,
           "source": {"label": "SF Ethics Commission campaign finance data (DataSF)", "url": "https://data.sf.gov/d/pitq-e56w"},
           "measures": measures, "candidates": cands}
    dest = ROOT / "site" / "data" / "money.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--since", default="2025-01-01")
    sys.stdout.reconfigure(encoding="utf-8")
    main(ap.parse_args().since)
