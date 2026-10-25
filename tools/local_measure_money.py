"""Money for local measures outside SF, from the Cal-Access bulk export.

    py tools/local_measure_money.py path/to/dbwebexport.zip

Local measure committees file their spending reports with the city clerk or
county registrar (mostly NetFile, which has no open API and sits behind a bot
challenge), but every committee registers with the Secretary of State, and
statewide committees report what they give to local committees. So for each
measure on the Alameda, San Mateo and Contra Costa previews this finds:

  1. the committees registered for it (Cal-Access FILERNAME): name, sponsor
     and side, matched by measure letter + a place keyword from the measure's
     jurisdiction (see KEYWORDS); data-src/local_measure_committees.json can
     pin or exclude committees by filer id;
  2. contributions to those committees reported by state-filing committees:
     Schedule D "contributions made" (EXPN_CD) and Form 497 late contributions
     made (S497_CD), 2025 onward, latest amendment of each filing only.

The total is a FLOOR, not the committee's full fundraising: local individual
donors and money reported only to the local clerk aren't in Cal-Access. The
page says so. Writes site/data/county_measure_money.json keyed by contest id.
"""
import io
import json
import re
import sys
import zipfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SINCE = datetime(2025, 1, 1)
MIN_FILER_ID = 1480000          # committees registered for the 2026 cycle onward
PREFIX = {"alameda": "ala", "sanmateo": "smc", "contracosta": "cc"}
# Extra place words for district measures whose committee names don't repeat the jurisdiction.
KEYWORDS = {
    "San Mateo County Community College District": ["SAN MATEO COUNTY", "COLLEGE", "HIGHER EDUCATION"],
    "San Mateo-Foster City School District": ["SAN MATEO", "FOSTER CITY"],
    "West Contra Costa Unified School District": ["WEST CONTRA COSTA", "WCCUSD"],
    "Jefferson Union High School District": ["JEFFERSON"],
    "Cabrillo Unified School District": ["CABRILLO", "HALF MOON BAY", "COASTSIDE"],
    "Acalanes Union High School District": ["ACALANES"],
    "Liberty Union High School District": ["LIBERTY"],
    "Dublin USD": ["DUBLIN"], "San Lorenzo USD": ["SAN LORENZO"], "Sunol Glen": ["SUNOL"],
}


def tsv(z, table):
    with z.open(f"CalAccess/DATA/{table}.TSV") as f:
        r = io.TextIOWrapper(f, encoding="latin-1")
        head = r.readline().rstrip("\n").split("\t")
        for line in r:
            yield dict(zip(head, line.rstrip("\n").split("\t")))


def parse_dt(s):
    m = re.match(r"(\d+)/(\d+)/(\d{4})", s or "")
    return datetime(int(m.group(3)), int(m.group(1)), int(m.group(2))) if m else None


def place_words(jur: str) -> list[str]:
    if jur in KEYWORDS:
        return KEYWORDS[jur]
    core = re.sub(r"^(City|Town) of\s+|\s+(School District|Unified School District|USD|Elementary School District)$", "", jur)
    return [core.upper()]


def measures():
    out = []
    for county, prefix in PREFIX.items():
        for m in json.loads((ROOT / "data-src" / "counties" / county / "measures.json").read_text(encoding="utf-8")):
            if m["letter"] == "RTM":
                continue
            out.append({"id": f"{prefix}-measure-{m['letter'].lower()}", "letter": m["letter"],
                        "jurisdiction": m["jurisdiction"], "words": place_words(m["jurisdiction"])})
    return out


def side_of(name: str) -> str:
    n = name.upper()
    if re.search(r"\bNO ON\b|\bOPPOS|\bAGAINST\b|\bSTOP\b", n):
        return "no"
    return "yes"


def main(zip_path: str) -> None:
    z = zipfile.ZipFile(zip_path)
    ms = measures()
    pins = json.loads((ROOT / "data-src" / "local_measure_committees.json").read_text(encoding="utf-8"))
    pin, exclude = pins.get("pin", {}), set(pins.get("exclude", []))

    # 1. Committees per measure.
    # A committee can carry several registered names over time ("Committee for Strong Burlingame
    # Schools" vs "Yes on R for Strong Burlingame Schools"); match on any, display the longest.
    names, variants = {}, defaultdict(set)
    for r in tsv(z, "FILERNAME_CD"):
        fid = r.get("FILER_ID", "")
        if not fid.isdigit():
            continue
        nm = " ".join(x for x in (r.get("NAMT", ""), r.get("NAML", ""), r.get("NAMF", "")) if x).strip()
        variants[fid].add(nm.upper())
        if len(nm) > len(names.get(fid, "")):
            names[fid] = nm
    committees = defaultdict(dict)     # contest id -> filer id -> info
    for fid, nm in names.items():
        if fid in exclude:
            continue
        if fid in pin:
            p = pin[fid]
            committees[p["contest"]][fid] = {"name": nm, "side": p.get("side", side_of(nm))}
            continue
        if int(fid) < MIN_FILER_ID:
            continue
        up = " | ".join(sorted(variants[fid]))
        # "YES ON MEASURE Z", "MEASURES O, P, Q, R, S AND T", "YES ON U AND V"
        letters = set()
        for seg in re.findall(r"\b(?:MEASURES?|YES ON|NO ON|SUPPORTING|OPPOSING)\s+((?:MEASURES?\s+)?[A-Z]{1,2}\b(?:\s*(?:,|&|AND)\s*[A-Z]{1,2}\b)*)", up):
            letters |= set(re.findall(r"\b([A-Z]{1,2})\b", re.sub(r"^MEASURES?\s+|\bAND\b", " ", seg)))
        if not letters:
            continue
        hits = [m for m in ms if m["letter"] in letters and any(w in up for w in m["words"])]
        # One committee may back several measures in the same place; all must share a jurisdiction.
        if hits and len({h["jurisdiction"] for h in hits}) == 1:
            for h in hits:
                committees[h["id"]][fid] = {"name": nm, "side": side_of(nm),
                                            "shared": sorted(x["letter"] for x in hits if x is not h)}

    # 2. Contributions to them reported by state filers (latest amendment per filing).
    want = {fid for cs in committees.values() for fid in cs}
    filer_of, best_amend = {}, {}
    for r in tsv(z, "CVR_CAMPAIGN_DISCLOSURE_CD"):
        fid, amend = r.get("FILING_ID"), int(r.get("AMEND_ID") or 0)
        if amend >= best_amend.get(fid, -1):
            best_amend[fid] = amend
            filer_of[fid] = r.get("FILER_NAML", "").strip()
    gifts = defaultdict(lambda: defaultdict(float))     # committee -> giver -> $
    last = {}
    for table, date_col in (("EXPN_CD", "EXPN_DATE"), ("S497_CD", "CTRIB_DATE")):
        seen = set()
        for r in tsv(z, table):
            cid = r.get("CMTE_ID", "")
            if cid not in want:
                continue
            if table == "S497_CD" and r.get("FORM_TYPE") != "F497P2":   # part 2 = contributions made
                continue
            fid = r.get("FILING_ID")
            if int(r.get("AMEND_ID") or 0) != best_amend.get(fid, 0):
                continue
            d = parse_dt(r.get(date_col))
            if not d or d < SINCE:
                continue
            key = (fid, r.get("TRAN_ID") or r.get("LINE_ITEM"))
            if key in seen:
                continue
            seen.add(key)
            gifts[cid][filer_of.get(fid) or "Unnamed committee"] += float(r.get("AMOUNT") or 0)
            last[cid] = max(filter(None, [last.get(cid), d]))

    out = {"built": date.today().isoformat(),
           "source": {"label": "CA Secretary of State, Cal-Access bulk export",
                      "url": "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"},
           "note": ("Totals count only money given by committees that report to the state. The measure committees' "
                    "own reports, including local individual donors, are filed with the local elections office."),
           "measures": {}}
    for m in ms:
        cs = committees.get(m["id"])
        if not cs:
            continue
        rows = []
        for fid, info in sorted(cs.items(), key=lambda kv: -sum(gifts[kv[0]].values())):
            top = sorted(gifts[fid].items(), key=lambda kv: -kv[1])
            rows.append({"filer_id": fid, "name": info["name"], "side": info["side"], "shared": info.get("shared", []),
                         "from_state_committees": round(sum(v for _, v in top)),
                         "top": [{"name": n, "amount": round(a)} for n, a in top[:6]],
                         "through": last[fid].strftime("%Y-%m-%d") if fid in last else None})
        out["measures"][m["id"]] = rows
    dest = ROOT / "site" / "data" / "county_measure_money.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}: {len(out['measures'])} of {len(ms)} local measures have registered committees")
    for mid, rows in out["measures"].items():
        for r in rows:
            print(f"  {mid:16} {r['side']:3} ${r['from_state_committees']:>9,} {r['name'][:90]}")
    missing = [m["id"] for m in ms if m["id"] not in out["measures"]]
    print("no committee found:", ", ".join(missing))


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
