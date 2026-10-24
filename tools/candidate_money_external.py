"""Money for the state and federal candidates on SF's ballot.

    py tools/candidate_money_external.py path/to/dbwebexport.zip
    py tools/candidate_money_external.py --federal-only     # refresh FEC data only

State offices (governor ... superintendent, Assembly, BOE): the CA Secretary of
State's Cal-Access bulk export (https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip,
the SoS's published machine-readable data; the Cal-Access website itself is behind
a bot wall). For each controlled committee in data-src/state_committees.json:
  * contributions = sum of Form 460 Summary line 5 ("total contributions received",
    column A = the period) over every report period ending on/after 2025-01-01,
    using only the latest amendment of each filing and the latest filing per period;
  * small-donor share = Schedule A line 2 (unitemized, under $100) / line 3;
  * outside money = Form 496 independent expenditures (24-hour reports, filed in
    the 90 days before an election) whose cover names the candidate, by spender
    and support/oppose.
Federal (U.S. House 11 & 15): the FEC API, 2025-26 cycle: receipts, individual
itemized/unitemized, PAC money, and independent expenditures by candidate.

Writes site/data/external_money.json.
"""
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SINCE = datetime(2025, 1, 1)
FEC = "https://api.open.fec.gov/v1"
FEC_KEY = os.environ.get("FEC_API_KEY", "DEMO_KEY")   # free key: https://api.data.gov/signup/ (DEMO_KEY is heavily rate limited)
FEDERAL = {  # contest -> {ballot name: FEC candidate id}
    "us-rep-11": {"Connie Chan": "H6CA11268", "Scott Wiener": "H8CA11116"},
    "us-rep-15": {"Kevin Mullin": "H2CA14162", "Charles Hoelter": "H6CA15194"},
}


def tsv(z, table):
    with z.open(f"CalAccess/DATA/{table}.TSV") as f:
        r = io.TextIOWrapper(f, encoding="latin-1")
        head = r.readline().rstrip("\n").split("\t")
        for line in r:
            c = line.rstrip("\n").split("\t")
            if len(c) >= len(head) - 2:
                yield dict(zip(head, c))


def parse_dt(s):
    m = re.match(r"(\d+)/(\d+)/(\d{4})", s or "")
    return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def norm(s):
    return re.sub(r"[^A-Z ]", " ", (s or "").upper()).split()


def surname(ballot_name):
    toks = norm(re.sub(r"[“\"(].*?[”\")]", " ", ballot_name))
    while len(toks) > 1 and toks[-1] in ("JR", "SR", "II", "III"):
        toks.pop()
    return toks[-1], toks[0]


def state(zip_path):
    cfg = json.loads((ROOT / "data-src" / "state_committees.json").read_text(encoding="utf-8"))
    cfg.pop("_about", None)
    want = {str(fid): (cid, name) for cid, cands in cfg.items() for name, ids in cands.items() for fid in ids}
    z = zipfile.ZipFile(zip_path)

    # 1. Cover pages: Form 460s of our committees + all Form 496s (for outside money).
    f460 = {}           # filing_id -> (filer, from, thru, amend)
    f496 = {}           # filing_id -> (spender name, cand name tokens, S/O, amend)
    for r in tsv(z, "CVR_CAMPAIGN_DISCLOSURE_CD"):
        form, fid, amend = r.get("FORM_TYPE"), r.get("FILING_ID"), int(r.get("AMEND_ID") or 0)
        thru = parse_dt(r.get("THRU_DATE")) or parse_dt(r.get("RPT_DATE"))
        if not thru or thru < SINCE:
            continue
        if form == "F460" and r.get("FILER_ID") in want:
            if fid not in f460 or amend > f460[fid][3]:
                f460[fid] = (r["FILER_ID"], parse_dt(r.get("FROM_DATE")), thru, amend)
        elif form == "F496" and (r.get("CAND_NAML") or "").strip():
            if fid not in f496 or amend > f496[fid][3]:
                f496[fid] = (r.get("FILER_NAML", "").strip(), norm(f"{r.get('CAND_NAMF','')} {r.get('CAND_NAML','')}"),
                             (r.get("SUP_OPP_CD") or "S").strip().upper()[:1], amend, r.get("FILER_ID"))
    # Latest filing per committee + period (a re-filed report gets a new filing id).
    best = {}
    for fid, (filer, frm, thru, amend) in f460.items():
        k = (filer, frm, thru)
        if k not in best or int(fid) > int(best[k]):
            best[k] = fid
    keep460 = {fid: f460[fid] for fid in best.values()}

    # 2. Summary totals for those filings (latest amendment only).
    sums = defaultdict(lambda: {"contrib": 0.0, "item": 0.0, "unitem": 0.0, "thru": None})
    for r in tsv(z, "SMRY_CD"):
        fid = r.get("FILING_ID")
        if fid not in keep460 or int(r.get("AMEND_ID") or 0) != keep460[fid][3]:
            continue
        filer, _, thru, _ = keep460[fid]
        amt = float(r.get("AMOUNT_A") or 0)
        s = sums[filer]
        if r.get("FORM_TYPE") == "F460" and r.get("LINE_ITEM") == "5":
            s["contrib"] += amt
            s["thru"] = max(filter(None, [s["thru"], thru]))
        elif r.get("FORM_TYPE") == "A" and r.get("LINE_ITEM") == "1":
            s["item"] += amt
        elif r.get("FORM_TYPE") == "A" and r.get("LINE_ITEM") == "2":
            s["unitem"] += amt

    # 3. Form 496 amounts (latest amendment), attributed to candidates by name and
    #    grouped by the spender's FILER ID (committees vary their names between reports).
    notes_cfg = json.loads((ROOT / "data-src" / "filing_notes.json").read_text(encoding="utf-8"))
    ie = defaultdict(lambda: defaultdict(lambda: {"support": 0.0, "oppose": 0.0, "notes": []}))
    spender_name = {}
    for r in tsv(z, "S496_CD"):
        fid = r.get("FILING_ID")
        if fid not in f496 or int(r.get("AMEND_ID") or 0) != f496[fid][3]:
            continue
        spender, cand, so, _, filer_id = f496[fid]
        # Shortest name variant reads best ("... Committee" vs "... Committee Supporting X ...").
        if filer_id not in spender_name or len(spender) < len(spender_name[filer_id]):
            spender_name[filer_id] = spender
        row = ie[" ".join(cand)][filer_id]
        row["oppose" if so == "O" else "support"] += float(r.get("AMOUNT") or 0)
        if fid in notes_cfg and notes_cfg[fid] not in row["notes"]:
            row["notes"].append(notes_cfg[fid])

    out = {}
    for cid, cands in cfg.items():
        for name, ids in cands.items():
            last, first = surname(name)
            total = sum(sums[str(i)]["contrib"] for i in ids)
            item = sum(sums[str(i)]["item"] for i in ids)
            unitem = sum(sums[str(i)]["unitem"] for i in ids)
            thru = max([sums[str(i)]["thru"] for i in ids if sums[str(i)]["thru"]], default=None)
            spend = defaultdict(lambda: {"support": 0.0, "oppose": 0.0})
            for cand_name, by in ie.items():
                toks = cand_name.split()
                if last in toks and (len(toks) == 1 or toks[0][:1] == first[:1] or last == toks[0]):
                    for sp, v in by.items():
                        spend[sp]["support"] += v["support"]; spend[sp]["oppose"] += v["oppose"]
                        spend[sp].setdefault("notes", []).extend(n for n in v["notes"] if n not in spend[sp].get("notes", []))
            rows = sorted(({"committee": spender_name.get(k, k), "support": round(v["support"]), "oppose": round(v["oppose"]),
                            **({"notes": v["notes"]} if v.get("notes") else {})}
                           for k, v in spend.items() if v["support"] + v["oppose"] >= 1000),
                          key=lambda x: -(x["support"] + x["oppose"]))
            rec = {"total": round(total), "outside": rows}
            if not ids:
                rec["no_committee"] = True
            if item + unitem > 0:
                rec["small_pct"] = round(unitem / (item + unitem), 3)
            if thru:
                rec["through"] = thru.date().isoformat()
            out.setdefault(cid, {})[name] = rec
            print(f"state {cid:22} {name:24} ${total:>13,.0f}  small {rec.get('small_pct', 0):.0%}  outside {len(rows)}")
    return out



JUSTICES = {  # contest id -> surname as it would appear in a committee name
    "scotus-groban": "GROBAN", "scotus-evans": "EVANS", "coa-1-1-wilson": "LANGHORNE", "coa-1-1-smiley": "SMILEY",
    "coa-1-1-banke": "BANKE", "coa-1-2-stewart": "STEWART", "coa-1-2-desautels": "DESAUTELS", "coa-1-3-petrou": "PETROU",
    "coa-1-3-rodriguez": "RODRIGUEZ", "coa-1-4-brown": "BROWN", "coa-1-5-chou": "CHOU", "coa-1-5-simons": "SIMONS",
    "coa-1-5-burns": "BURNS",
}


def judicial(zip_path):
    """Committees (Form 460/496, 2025+) whose name pairs a justice's surname with a
    judicial word. Common surnames make a bare-name match meaningless, so the
    judicial word is required."""
    z = zipfile.ZipFile(zip_path)
    found = {cid: {} for cid in JUSTICES}
    for r in tsv(z, "CVR_CAMPAIGN_DISCLOSURE_CD"):
        if r.get("FORM_TYPE") not in ("F460", "F496", "F465"):
            continue
        thru = parse_dt(r.get("THRU_DATE")) or parse_dt(r.get("RPT_DATE"))
        if not thru or thru < SINCE:
            continue
        name = (r.get("FILER_NAML") or "").upper()
        if not re.search(r"\b(JUSTICE|COURT|RETAIN|RETENTION)\b", name):
            continue
        for cid, sur in JUSTICES.items():
            if re.search(rf"\b{sur}\b", name):
                found[cid][r.get("FILER_ID")] = r.get("FILER_NAML").strip()
    out = {cid: {"committees": [{"committee": n, "support": 0, "oppose": 0} for n in v.values()]} for cid, v in found.items()}
    for cid, v in out.items():
        print(f"judicial {cid:20} {len(v['committees'])} committee(s) {[c['committee'][:60] for c in v['committees']]}")
    return out


def fec_get(path, **params):
    params["api_key"] = FEC_KEY
    url = f"{FEC}{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "sf_voter_guide/1.0"}), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 7:   # DEMO_KEY is rate limited; wait it out
                print("  FEC rate limit, waiting 90s...", flush=True)
                time.sleep(90)
                continue
            raise


def federal():
    out = {}
    for cid, cands in FEDERAL.items():
        for name, fec_id in cands.items():
            t = (fec_get(f"/candidate/{fec_id}/totals/", cycle=2026, election_full="false").get("results") or [None])[0]
            ies = fec_get("/schedules/schedule_e/by_candidate/", candidate_id=fec_id, cycle=2026, per_page=50).get("results", [])
            spend = defaultdict(lambda: {"support": 0.0, "oppose": 0.0})
            for r in ies:
                spend[r["committee_name"]]["oppose" if r.get("support_oppose_indicator") == "O" else "support"] += r["total"]
            rows = sorted(({"committee": k.title(), "support": round(v["support"]), "oppose": round(v["oppose"])}
                           for k, v in spend.items() if v["support"] + v["oppose"] >= 1000),
                          key=lambda x: -(x["support"] + x["oppose"]))
            if not t:
                out.setdefault(cid, {})[name] = {"total": 0, "no_committee": True, "outside": rows,
                                                 "note": "No FEC filings this cycle (candidates who raise under $5,000 don’t have to register)."}
                print(f"fed   {cid:22} {name:24} no filings"); continue
            indiv = (t.get("individual_itemized_contributions") or 0) + (t.get("individual_unitemized_contributions") or 0)
            rec = {"total": round(t.get("receipts") or 0),
                   "pac": round(t.get("other_political_committee_contributions") or 0),
                   "small_pct": round((t.get("individual_unitemized_contributions") or 0) / indiv, 3) if indiv else None,
                   "through": (t.get("coverage_end_date") or "")[:10], "outside": rows,
                   "fec_url": f"https://www.fec.gov/data/candidate/{fec_id}/?cycle=2026"}
            out.setdefault(cid, {})[name] = rec
            print(f"fed   {cid:22} {name:24} ${rec['total']:>13,}  small {rec['small_pct'] or 0:.0%}  outside {len(rows)}")
    return out


def main(zip_path, federal_only=False):
    dest = ROOT / "site" / "data" / "external_money.json"
    prev = json.loads(dest.read_text(encoding="utf-8")) if dest.exists() else {}
    if federal_only:
        state_part = {k: v for k, v in prev.get("candidates", {}).items() if k not in FEDERAL}
        judicial_part = prev.get("judicial", {})
    else:
        state_part = state(zip_path)
        judicial_part = judicial(zip_path)
        # Save right away so a federal-API hiccup doesn't cost another 1.6 GB scan.
        dest.write_text(json.dumps({**prev, "candidates": {**prev.get("candidates", {}), **state_part}, "judicial": judicial_part},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    data = {"built": date.today().isoformat(),
            "sources": {
                "state": {"label": "CA Secretary of State, Cal-Access bulk export", "url": "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"},
                "federal": {"label": "Federal Election Commission (FEC) API", "url": "https://www.fec.gov/data/"}},
            "rules": {"small_state": "Unitemized contributions (under $100) as a share of all contributions",
                      "small_federal": "Unitemized individual contributions (under $200) as a share of individual contributions"},
            "candidates": {**state_part, **federal()},
            "judicial": judicial_part}
    dest.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    federal_only = "--federal-only" in sys.argv
    if not args and not federal_only:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    main(args[0] if args else None, federal_only)
