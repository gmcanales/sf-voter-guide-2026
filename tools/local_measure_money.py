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


PORTALS = {"COAK": "City of Oakland", "COA": "Alameda County", "CCC": "Contra Costa County"}


def netfile(paths: list[str], name_to_id: dict) -> dict:
    """Full local totals from NetFile "All Transactions" exports (efile_<AID>_<year>.xlsx).

    Per committee: Form 460 line 5 (contributions received) summed over reporting periods,
    keeping the highest Report_Num (latest amendment) per period; itemized donors from
    Schedule A of those same reports; plus Form 497 late contributions received after the
    last 460 period. Committees are keyed by Filer_ID, or mapped by name when NetFile shows
    "Pending" (name_to_id).
    """
    import openpyxl
    out = {}
    for path in paths:
        aid = re.match(r"efile_([A-Z]+)_", Path(path).name).group(1)
        wb = openpyxl.load_workbook(path, read_only=True)

        def rows(sheet):
            it = wb[sheet].iter_rows(values_only=True)
            head = next(it)
            for r in it:
                yield dict(zip(head, r))

        def key(r):
            fid = str(r.get("Filer_ID") or "").strip()
            return fid if fid.isdigit() else name_to_id.get((r.get("Filer_NamL") or "").strip())

        latest = {}                                     # (fid, from, thru) -> report num
        for r in rows("Summary"):
            k = key(r)
            if k and r.get("Form_Type") == "F460":
                p = (k, r["From_Date"], r["Thru_Date"])
                latest[p] = max(latest.get(p, -1), int(r.get("Report_Num") or 0))
        totals, thru = defaultdict(float), {}
        for r in rows("Summary"):
            k = key(r)
            if k and r.get("Form_Type") == "F460" and str(r.get("Line_Item")) == "5" \
                    and int(r.get("Report_Num") or 0) == latest.get((k, r["From_Date"], r["Thru_Date"])):
                totals[k] += float(r.get("Amount_A") or 0)
                thru[k] = max(filter(None, [thru.get(k), r["Thru_Date"]]))
        donors = defaultdict(lambda: defaultdict(float))
        for r in rows("A-Contributions"):
            k = key(r)
            if k and int(r.get("Report_Num") or 0) == latest.get((k, r["From_Date"], r["Thru_Date"])):
                who = " ".join(x for x in (r.get("Tran_NamF"), r.get("Tran_NamL")) if x).strip()
                donors[k][who] += float(r.get("Tran_Amt1") or 0)
        late, seen = defaultdict(float), {}
        for r in rows("497"):
            k = key(r)
            if not k or r.get("Form_Type") != "F497P1":
                continue
            d = r.get("Ctrib_Date")
            if thru.get(k) and d and d <= thru[k]:
                continue                                # already inside a 460 period
            tid = (k, r.get("Tran_ID"))
            if int(r.get("Report_Num") or 0) < seen.get(tid, -1):
                continue
            seen[tid] = int(r.get("Report_Num") or 0)
            who = " ".join(x for x in (r.get("Enty_NamF"), r.get("Enty_NamL")) if x).strip()
            amt = float(r.get("Amount") or 0)
            late[k] += amt
            donors[k][who] += amt
        for k in set(totals) | set(late):
            top = sorted(donors[k].items(), key=lambda kv: -kv[1])
            out[k] = {"agency": aid, "agency_name": PORTALS.get(aid, aid),
                      "raised": round(totals[k]), "late_since": round(late[k]),
                      "through": thru[k].strftime("%Y-%m-%d") if k in thru else None,
                      "donor_count": len(top), "top": [{"name": n, "amount": round(a)} for n, a in top[:8]]}
    return out


API = "https://netfile.com/Connect2/api/public"
COUNTY_AGENCY = {"ala": "COA", "smc": "MAT", "cc": "CCC"}
A_TYPES = {0: "Schedule A", 1: "Schedule C (non-monetary)", 20: "Form 497 late contribution"}


def api_get(path: str, **params) -> dict:
    import time
    import urllib.parse
    import urllib.request
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "sf_voter_guide/1.0"})
    time.sleep(0.3)                                    # be polite to a free public API
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))


_FILERS: dict = {}


def agency_filers(shortcut: str) -> list[dict]:
    """Every committee registered with one NetFile agency: [{fppcId, name}, ...] (cached)."""
    if shortcut not in _FILERS:
        filers, page = [], 0
        while True:
            d = api_get("campaign/list/filer", AID=shortcut, PageSize=500, CurrentPageIndex=page)
            filers += d.get("filers", [])
            page += 1
            if page >= d.get("totalMatchingPages", 1):
                break
        _FILERS[shortcut] = filers
    return _FILERS[shortcut]


def committee_itemized(ag: dict, fid: str, nf_name: str, since: str | None = None) -> dict | None:
    """Itemized contributions to one committee, found by its exact NetFile name.

    Counts Schedule A, Schedule C and Form 497 part 1 (see committee_rows). Contributions
    under $100 aren't itemized, so this is "itemized", not the 460 total.
    """
    mine = committee_rows(ag, fid, nf_name, since)
    if not mine:
        return None
    donors, last = defaultdict(float), None
    for r in mine:
        donors[r.get("name") or "Unitemized"] += r["amount"]
        last = max(filter(None, [last, r["date"][:10]]))
    top = sorted(donors.items(), key=lambda kv: -kv[1])
    return {"agency": ag["shortcut"], "agency_name": ag["name"], "itemized": round(sum(donors.values())),
            "through": last, "donor_count": len(top),
            "top": [{"name": n, "amount": round(a)} for n, a in top[:8]]}


def committee_rows(ag: dict, fid: str, nf_name: str, since: str | None = None) -> list[dict] | None:
    """One committee's itemized contribution rows, found by its exact NetFile name.

    Transactions come from a name search with superseded amendments excluded, then are
    filtered to the committee's own FPPC id (or, while the id is still "Pending", its exact
    name). Keeps Schedule A, Schedule C and Form 497 part 1, deduping late contributions
    that reappear on the next Form 460 (same donor, date and amount). None if NetFile
    refuses every form of the search.
    """
    import urllib.error
    words = re.sub(r"[^\w\s&'-]", " ", nf_name).split()[:8]
    # The search rejects some queries as "ProfaneSearchException" (a word in a name trips its
    # filter). Retry with shorter prefixes; the FPPC-id filter below keeps results exact.
    for n in range(len(words), 1, -1):
        q, rows, page = " ".join(words[:n]), [], 0
        try:
            while True:
                d = api_get("campaign/search/transaction/query", Agency=ag["id"], QueryString=q,
                            PageSize=500, CurrentPageIndex=page, ShowSuperceded="false")
                rows += d.get("results", [])
                page += 1
                if page >= d.get("totalMatchingPages", 1):
                    break
            break
        except urllib.error.HTTPError as e:
            if e.code != 400:
                raise
    else:
        print(f"  ! NetFile search refused every form of {nf_name!r}; skipped")
        return None
    if fid.isdigit():
        mine = [r for r in rows if (r.get("filerFppcId") or "").rstrip(".") == fid]
    else:
        mine = [r for r in rows if (r.get("filerName") or "").strip().lower() == nf_name.strip().lower()]
    mine = [r for r in mine if r.get("transactionType") in A_TYPES and (not since or r["date"][:10] >= since)]
    seen, out = set(), []
    for r in sorted(mine, key=lambda r: r["transactionType"]):   # 460 rows before 497 rows
        k = ((r.get("name") or "").upper(), r["date"][:10], round(r["amount"], 2))
        if k not in seen:
            seen.add(k)
            out.append(r)
    return out


def agencies() -> list[dict]:
    a = api_get("campaign/agencies")
    return a.get("agencies", a) if isinstance(a, dict) else a


def netfile_api(wanted: dict) -> dict:
    """Itemized contributions per committee from NetFile's documented public API.

    wanted: filer id -> (committee name, measure jurisdiction, contest id). The committee is
    looked up in its city's NetFile agency (district and county measures: the county's), its
    transactions found by name search with superseded amendments excluded, then filtered to
    its own FPPC id. Counts Schedule A, Schedule C and Form 497 part 1, deduping late
    contributions that reappear on the next Form 460 (same donor, date and amount).
    Contributions under $100 aren't itemized, so this is "itemized", not the 460 total.
    """
    ags = agencies()
    out = {}
    for fid, (name, jur, cid) in wanted.items():
        place = re.sub(r"^(City|Town) of\s+", "", jur)
        ag = next((a for a in ags if jur.startswith(("City of", "Town of"))
                   and re.search(rf"\b{re.escape(place)}\b", a["name"]) and "County" not in a["name"]), None)
        if not ag:
            code = COUNTY_AGENCY[cid.split("-")[0]]
            ag = next(a for a in ags if a["shortcut"] == code) if not jur.startswith(("City of", "Town of")) else None
        if not ag:
            continue                                    # city not on NetFile (e.g. South San Francisco)
        # Search by the committee's exact NetFile name (looked up by FPPC id in the agency's filer
        # list); Cal-Access spellings differ and the search matches whole words.
        names = {(f.get("fppcId") or "").rstrip("."): f.get("name") or "" for f in agency_filers(ag["shortcut"])}
        nf_name = names.get(fid)
        if not nf_name:
            continue                                    # files elsewhere, or not yet on NetFile
        rec = committee_itemized(ag, fid, nf_name)
        if not rec:
            continue
        out[fid] = rec
        print(f"  api {ag['shortcut']:5} {fid} ${rec['itemized']:,} itemized, {rec['donor_count']} donors: {name[:60]}")
    return out


def main(zip_path: str, netfile_paths: list[str] | None = None) -> None:
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
    for fid, p in pin.items():         # pinned committees can predate the cycle cutoff or be missing a name
        names.setdefault(fid, p.get("name", fid))
    for fid, nm in names.items():
        if fid in exclude:
            continue
        if fid in pin:
            p = pin[fid]
            # A pinned name wins: committees reused across campaigns keep old names in Cal-Access.
            committees[p["contest"]][fid] = {"name": p.get("name", nm), "side": p.get("side", side_of(nm))}
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
    # One gift can appear three times: on the giver's Form 497 (late contribution made), then
    # on its next Form 460 as Schedule D (contribution to a committee) AND Schedule E (payment).
    # Count Schedule D and 497 part 2 only, and keep one row per (giver, recipient, date, amount).
    gifts = defaultdict(lambda: defaultdict(float))     # committee -> giver -> $
    last = {}
    unique = set()
    for table, date_col in (("EXPN_CD", "EXPN_DATE"), ("S497_CD", "CTRIB_DATE")):
        for r in tsv(z, table):
            cid = r.get("CMTE_ID", "")
            if cid not in want:
                continue
            if table == "S497_CD" and r.get("FORM_TYPE") != "F497P2":   # part 2 = contributions made
                continue
            if table == "EXPN_CD" and r.get("FORM_TYPE") != "D":         # Schedule D = contributions made
                continue
            fid = r.get("FILING_ID")
            if int(r.get("AMEND_ID") or 0) != best_amend.get(fid, 0):
                continue
            d = parse_dt(r.get(date_col))
            if not d or d < SINCE:
                continue
            giver = filer_of.get(fid) or "Unnamed committee"
            amt = round(float(r.get("AMOUNT") or 0), 2)
            key = (giver.upper(), cid, d, amt)
            if key in unique:
                continue
            unique.add(key)
            gifts[cid][giver] += amt
            last[cid] = max(filter(None, [last.get(cid), d]))

    local = netfile(netfile_paths or [], pins.get("netfile_names", {}))
    jur_of = {m["id"]: m["jurisdiction"] for m in ms}
    need = {fid: (names[fid], jur_of[cid], cid) for cid, cs in committees.items() for fid in cs if fid not in local}
    api = netfile_api(need) if "--no-api" not in sys.argv else {}
    out = {"built": date.today().isoformat(),
           "source": {"label": "CA Secretary of State, Cal-Access bulk export",
                      "url": "https://campaignfinance.cdn.sos.ca.gov/dbwebexport.zip"},
           "netfile_source": {"label": "NetFile public portal exports (local Form 460 / 497 filings)",
                              "url": "https://public.netfile.com/pub2/",
                              "agencies": sorted({v["agency"] for v in local.values()})},
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
                         "through": last[fid].strftime("%Y-%m-%d") if fid in last else None,
                         **({"local": local[fid]} if fid in local else {}),
                         **({"local_api": api[fid]} if fid in api else {})})
        out["measures"][m["id"]] = rows
    dest = ROOT / "site" / "data" / "county_measure_money.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}: {len(out['measures'])} of {len(ms)} local measures have registered committees")
    for mid, rows in out["measures"].items():
        for r in rows:
            loc = r.get("local")
            full = f" | local: ${loc['raised']:,} thru {loc['through']} + ${loc['late_since']:,} late ({loc['agency']})" if loc else ""
            print(f"  {mid:16} {r['side']:3} ${r['from_state_committees']:>9,} {r['name'][:70]}{full}")
    missing = [m["id"] for m in ms if m["id"] not in out["measures"]]
    print("no committee found:", ", ".join(missing))


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1], [a for a in sys.argv[2:] if not a.startswith("--")])
