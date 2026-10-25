"""Build an early-preview ballot.json for a non-SF county.

    py tools/build_county_ballot.py alameda
    py tools/build_county_ballot.py sanmateo

Inputs:
  data-src/counties/alameda/{contests,measures}.json   (tools/county_alameda.py)
  data-src/counties/sanmateo/{roster,measures}.json    (tools/county_sanmateo_roster.py;
                                                        measures transcribed from smcacre.gov)
  site/data/ballot.json                                SF build: the statewide pieces
                                                        (offices, justices, props, RTM) are
                                                        identical on every ballot here and
                                                        are copied, not re-derived.
Output: site/data/counties/<county>/ballot.json, same schema as the SF ballot.

Shallow on purpose: contest lists come from the county's official lists, but
local candidate order, local measure details and district boundaries are not
verified. The page shows an "early preview" banner for any ballot with
election.preview set. Statewide offices get their Assembly-District rotation
recomputed for this county's ADs (Elections Code §13111); First District
Court of Appeal retention applies because both counties sit in the First
Appellate District (Gov. Code §69100).
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data-src" / "counties"
SF_BALLOT = ROOT / "site" / "data" / "ballot.json"

LOCAL_ORDER_NOTE = ("Listed in the order of the county's official candidate list, which may not be "
                    "the printed ballot order. Check your sample ballot.")
DISTRICT_ORDER_NOTE = ("Listed in the order of the county's official candidate list. Your printed ballot "
                       "uses a randomized-alphabet order. Check your sample ballot.")
DISTRICT_NOTE = "Only voters who live in this district see it."
PARA = "\n\n"   # paragraph break inside official text; the page renders it with white-space: pre-line

# Focus cities (deep-dive coverage) get one-tap selectors. `serves` lists patterns for the
# school and special districts that cover the city; picking the city hides other local
# district races (readers can show them again). Patterns match a contest's title or
# subtitle. Ward-based districts (AC Transit, EBMUD, park district) stay in, since the
# reader still has to find their ward on the sample ballot.
FOCUS = {
    "alameda": [
        {"city": "Oakland", "serves": ["Oakland", "Peralta", "AC Transit", "EBMUD", "East Bay Regional Park"]},
        {"city": "Fremont", "serves": ["Fremont", "Ohlone", "Washington Township", "Alameda County Water",
                                       "AC Transit", "East Bay Regional Park"]},
    ],
    "sanmateo": [
        {"city": "South San Francisco", "serves": ["South San Francisco", "San Mateo County Community College",
                                                   "County Board of Education"]},
        {"city": "San Mateo", "serves": ["San Mateo-Foster City", "San Mateo Union High",
                                         "San Mateo County Community College", "County Board of Education"]},
        {"city": "Redwood City", "serves": ["Redwood City", "Sequoia Union High", "Belmont-Redwood Shores",
                                            "San Mateo County Community College", "County Board of Education"]},
    ],
    "contracosta": [
        {"city": "Richmond", "label": "Richmond & Richmond Annex",
         "serves": ["West Contra Costa", "Contra Costa Community College", "Contra Costa County Board",
                    "East Bay M.U.D", "East Bay Reg"]},
    ],
}

COUNTIES = {
    "alameda": {
        "name": "Alameda County", "short": "Alameda", "prefix": "ala",
        "cities": ["Alameda", "Albany", "Berkeley", "Dublin", "Emeryville", "Fremont", "Hayward",
                   "Livermore", "Newark", "Oakland", "Piedmont", "Pleasanton", "San Leandro", "Union City"],
        "districts": {
            "cd": {"label": "U.S. House district", "options": [10, 12, 14, 17]},
            "ad": {"label": "State Assembly district", "options": [14, 16, 18, 20, 24]},
            "sd": {"label": "State Senate district", "options": [10, 0], "labels": {"0": "Another district"},
                   "note": "Only State Senate District 10 votes in Alameda County this year."},
            "bart": {"label": "BART district", "options": [4, 0], "labels": {"0": "Another district"},
                     "note": "Only BART District 4 has a contested race in Alameda County this year."},
        },
        "sources": [
            {"label": "Alameda County Registrar: Nov 3, 2026 election page", "url": "https://acvote.alamedacountyca.gov/election-information/elections?id=260"},
            {"label": "Alameda County Voter Information Guide (PDF)", "url": "https://acvote.alamedacountyca.gov/acvote-assets/02_election_information/PDFs/20261103/Voter%20Information%20Guide/vig_nov2026_eng.pdf"},
            {"label": "Alameda County official candidate list", "url": "https://alamedacountyca.gov/rov_app/candidatelist"},
            {"label": "CA Official Voter Information Guide", "url": "https://voterguide.sos.ca.gov/"},
        ],
    },
    "contracosta": {
        "name": "Contra Costa County", "short": "Contra Costa", "prefix": "cc",
        "cities": ["Antioch", "Brentwood", "Clayton", "Concord", "Danville", "El Cerrito", "Hercules",
                   "Lafayette", "Martinez", "Moraga", "Oakley", "Orinda", "Pinole", "Pittsburg",
                   "Pleasant Hill", "Richmond", "San Pablo", "San Ramon", "Walnut Creek"],
        # Richmond Annex is a neighborhood inside Richmond's city limits.
        "city_labels": {"Richmond": "Richmond (incl. Richmond Annex)"},
        "districts": {
            "cd": {"label": "U.S. House district", "options": [8, 9, 10]},
            "ad": {"label": "State Assembly district", "options": [11, 14, 15, 16]},
        },
        "sources": [
            {"label": "Contra Costa Elections: Nov 3, 2026 election page", "url": "https://www.contracostavote.gov/election/november-3-2026-general-election/"},
            {"label": "CA Official Voter Information Guide", "url": "https://voterguide.sos.ca.gov/"},
        ],
    },
    "sanmateo": {
        "name": "San Mateo County", "short": "San Mateo", "prefix": "smc",
        "cities": ["Atherton", "Belmont", "Brisbane", "Burlingame", "Colma", "Daly City", "East Palo Alto",
                   "Foster City", "Half Moon Bay", "Hillsborough", "Menlo Park", "Millbrae", "Pacifica",
                   "Portola Valley", "Redwood City", "San Bruno", "San Carlos", "San Mateo",
                   "South San Francisco", "Woodside"],
        "districts": {
            "cd": {"label": "U.S. House district", "options": [15, 16]},
            "ad": {"label": "State Assembly district", "options": [19, 21, 23]},
            "sup": {"label": "Supervisor district", "options": [1, 2, 3, 4, 5],
                    "note": "Only District 5 elects a supervisor this year (short term)."},
        },
        "sources": [
            {"label": "San Mateo County Elections: Nov 3, 2026 election page", "url": "https://smcacre.gov/elections/november-3-2026-statewide-general-election"},
            {"label": "San Mateo County Roster of Candidates (PDF)", "url": "https://smcacre.gov/media/8827"},
            {"label": "CA Official Voter Information Guide", "url": "https://voterguide.sos.ca.gov/"},
        ],
    },
}

# County-list title → shared statewide contest id in the SF build.
STATEWIDE = {
    "governor": "governor", "lieutenant governor": "lt-governor", "secretary of state": "secretary-of-state",
    "controller": "controller", "treasurer": "treasurer", "attorney general": "attorney-general",
    "insurance commissioner": "insurance-commissioner",
    "member, state board of equalization, 2nd district": "boe-2",
    "member, state board of equalization, district 2": "boe-2",
    "state superintendent of public instruction": "superintendent",
    "superintendent of public instruction": "superintendent",
}
# City offices elected by ranked-choice voting (Alameda County). Albany: the county voter guide's RCV
# insert (City Council, Board of Education; up to 5 rankings). Berkeley: council resolution of
# 2026-04-21 asking the Registrar to run Council and Auditor by RCV. Oakland and San Leandro: city
# offices by RCV under their charters (in use since 2010). Shown as a note, not an RCV grid, since the
# number of rankings per contest isn't verified here.
RCV = {
    "Albany": re.compile(r"city council|board of education", re.I),
    "Berkeley": re.compile(r"city council|auditor", re.I),
    "Oakland": re.compile(r"mayor|councilmember|auditor|school director", re.I),
    "San Leandro": re.compile(r"mayor|city council", re.I),
}
RCV_NOTE = "Ranked-choice contest: your ballot lets you rank candidates in order of preference. This preview shows them as a simple list."
# Spellings title-casing can't recover from all-caps county lists, each checked against the
# candidate's own statement or official record.
NAME_FIXES = {"Leana Powell": "LeAna Powell", "Mark Desaulnier": "Mark DeSaulnier",
              "Robert G. Newsom JR.": "Robert G. Newsom Jr."}
# Focus cities whose candidate statements exist only in voters' personal sample-ballot pamphlets.
PAMPHLET_NOTE = {"sanmateo": ("South San Francisco", "San Mateo", "Redwood City")}
PARTY_NAMES = {"DEM": "Democratic", "REP": "Republican", "NPP": "No Party Preference", "GRN": "Green",
               "LIB": "Libertarian", "PF": "Peace and Freedom", "AI": "American Independent"}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", t.strip().lower())


def candidates(raw: list, partisan: bool) -> list:
    out = []
    for c in raw:
        x = {"name": NAME_FIXES.get(c["name"], c["name"]), "designation": c.get("designation", "")}
        if partisan and c.get("party"):
            x["party"] = PARTY_NAMES.get(c["party"], c["party"])
        out.append(x)
    return out


def office(cfg, title, vote_for, raw, applies=None, district_level=False, partisan=False, cid=None):
    c = {"id": cid or f"{cfg['prefix']}-{slug(title)}", "kind": "office", "title": title,
         "candidates": candidates(raw, partisan),
         "order_note": DISTRICT_ORDER_NOTE if partisan else LOCAL_ORDER_NOTE}
    if vote_for > 1:
        c["vote_for"] = vote_for
    if applies:
        c["applies"] = applies
    if district_level:
        c["subtitle"] = DISTRICT_NOTE
    return c


def city_of(title: str, cities: list) -> str | None:
    # "For Mayor, Oakland" / "City of Belmont Mayor" / "Town of Atherton ..." / "..., Albany"
    m = re.match(r"(?:City|Town) of (.+?),? (?:Member|Mayor|City Clerk|City Treasurer|City Council|Town Council|Treasurer)", title)
    if m and m.group(1) in cities:
        return m.group(1)
    for c in sorted(cities, key=len, reverse=True):
        if re.search(rf",\s*{re.escape(c)}(?:\s*-.*)?$", title):
            return c
    return None


def shared_statewide(sf: dict, ads: list) -> dict:
    """Copy the SF build's statewide contests, re-rotating statewide offices for these ADs."""
    out = {}
    for s in sf["sections"]:
        for c in s["contests"]:
            if c.get("applies") or c.get("level") == "local":
                continue
            c = json.loads(json.dumps(c))
            if c.get("order") == "statewide" and len(c.get("candidates", [])) > 1:
                base = [x["name"] for x in c["candidates"]]
                # SF's verified sample ballot may have replaced the computed base order for its
                # own AD; rebuild the AD-1 base from SF's AD 17 entry when present.
                by_ad_sf = c.get("order_by_ad", {})
                if "17" in by_ad_sf:
                    n = len(base); shift = (17 - 1) % n
                    o = by_ad_sf["17"]
                    base = o[-shift:] + o[:-shift] if shift else o
                by_ad = {}
                for ad in ads:
                    shift = (ad - 1) % len(base)
                    by_ad[str(ad)] = base[shift:] + base[:shift]
                byname = {x["name"]: x for x in c["candidates"]}
                c["candidates"] = [byname[n] for n in base]
                c["order_by_ad"] = by_ad
                c["order_note"] = ("Order computed from the Secretary of State's randomized alphabet with "
                                   "statewide rotation by Assembly District. Pick your AD above to see yours.")
            out[c["id"]] = (s, c)
    return out


def check_statewide(shared: dict, cid: str, raw: list, title: str) -> None:
    want = {x["name"].lower().replace(".", "") for x in shared[cid][1]["candidates"]}
    got = {x["name"].lower().replace(".", "") for x in raw}
    if want != got:
        print(f"  WARNING {title}: county list {sorted(got)} != SF build {sorted(want)}")


def load_county(county: str, cfg: dict):
    d = SRC / county
    if county in ("alameda", "contracosta"):
        contests = json.loads((d / "contests.json").read_text(encoding="utf-8"))
    else:
        contests = [c for c in json.loads((d / "roster.json").read_text(encoding="utf-8")) if c["on_ballot"]]
    measures = json.loads((d / "measures.json").read_text(encoding="utf-8"))
    return contests, measures


def county_of(cfg) -> str:
    return next(k for k, v in COUNTIES.items() if v is cfg)


def classify(cfg, c):
    """Return (bucket, contest) for one county-list contest."""
    t = c["title"]
    n = norm_title(t)
    if n in STATEWIDE:
        return "statewide", STATEWIDE[n]
    if m := (re.match(r"(\d+)\w\w congressional district", n) or re.match(r"(?:u\.s\.|united states) representative, district (\d+)", n)):
        k = int(m.group(1))
        return "voter", office(cfg, f"United States Representative, District {k}", 1, c["candidates"],
                               {"cd": k}, partisan=True, cid=f"us-rep-{k}")
    if m := re.match(r"(\d+)\w\w state senate district", n):
        k = int(m.group(1))
        return "voter", office(cfg, f"State Senator, District {k}", 1, c["candidates"], {"sd": k},
                               partisan=True, cid=f"state-senate-{k}")
    if m := (re.match(r"(\d+)\w\w assembly district", n) or re.match(r"member of the state assembly, district (\d+)", n)):
        k = int(m.group(1))
        return "voter", office(cfg, f"Member of the State Assembly, District {k}", 1, c["candidates"],
                               {"ad": k}, partisan=True, cid=f"assembly-{k}")
    if m := re.match(r"member, board of supervisors, district (\d+)(.*)", n):
        k = int(m.group(1))
        return "county", office(cfg, t, c["vote_for"], c["candidates"], {"sup": k})
    if m := re.match(r"bart director, district (\d+)", n):
        k = int(m.group(1))
        return "district", office(cfg, f"BART Director, District {k}", 1, c["candidates"], {"bart": k})
    city = city_of(t, cfg["cities"])
    if city:
        title = re.sub(r"^For ", "", t)
        o = office(cfg, title, c["vote_for"], c["candidates"], {"city": cfg["cities"].index(city) + 1})
        if county_of(cfg) == "alameda" and city in RCV and RCV[city].search(title):
            o["subtitle"] = RCV_NOTE
        return "city", (city, o)
    school = re.search(r"school|college|education|unified|union high", n)
    return ("school" if school else "district"), office(cfg, t, c["vote_for"], c["candidates"], district_level=True)


def apply_digest(c: dict, dg: dict) -> None:
    """Merge a hand-checked deep-dive digest (data-src/counties/<county>/measure_digests.json)."""
    for k in ("question", "summary", "fiscal", "yes_means", "no_means", "threshold", "note"):
        if dg.get(k):
            c[k] = dg[k]
    c["summary_label"] = "What it does (our digest of the impartial analysis)"
    args = dg.get("args") or {}
    gist = lambda side: (args.get(side) or {}).get("gist")
    if gist("for") or gist("against"):
        c["official_args"] = {"for": gist("for"), "against": gist("against")}
        c["official_args_label"] = "digest"
    signers = lambda side: "; ".join((args.get(side) or {}).get("signers") or []) or None
    if signers("for"):
        c["listed_supporters"] = signers("for")
    if signers("against"):
        c["listed_opponents"] = signers("against")
    c["sources"] = dg.get("sources", [])
    c.pop("source", None)


def measure(cfg, m, city_index, digests=None):
    c = {"id": f"{cfg['prefix']}-measure-{m['letter'].lower()}", "kind": "measure", "level": "local",
         "letter": m["letter"], "title": m["title"], "subtitle": m["jurisdiction"]}
    city = re.match(r"(?:City|Town) of (.+)$", m["jurisdiction"])
    if city and city.group(1) in city_index:
        c["applies"] = {"city": city_index[city.group(1)]}
    elif m["jurisdiction"] != cfg["name"]:
        c["subtitle"] = f"{m['jurisdiction']} · {DISTRICT_NOTE}"
    # Counties whose measure pages were captured (Contra Costa) get the official text.
    if m.get("question"):
        c["question"] = m["question"]
    if m.get("analysis"):
        c["summary"] = PARA.join(m["analysis"])
        c["summary_label"] = "Impartial analysis"
    if m.get("arg_for") or m.get("arg_against"):
        c["official_args"] = {"for": PARA.join(m.get("arg_for") or []) or None,
                              "against": PARA.join(m.get("arg_against") or []) or None}
    if m.get("source"):
        c["source"] = {"label": "County measure page (official)", "url": m["source"]}
    if digests and m["letter"] in digests:
        apply_digest(c, digests[m["letter"]])
    return c


def apply_profiles(county: str, buckets: dict) -> None:
    """Merge data-src/counties/<county>/candidate_profiles.json (Who? lines from official statements)."""
    path = SRC / county / "candidate_profiles.json"
    data = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    profiles, designations, sources = data.get("profiles", {}), data.get("designations", {}), data.get("_sources", {})
    contests = [c for c in buckets["city"]] + buckets["school"] + buckets["district"] + buckets["county"]
    contests = [c[1] if isinstance(c, tuple) else c for c in contests]
    seen = set()
    for c in contests:
        prof, des = profiles.get(c["title"], {}), designations.get(c["title"], {})
        for x in c["candidates"]:
            if des.get(x["name"]) and not x.get("designation"):
                x["designation"] = des[x["name"]]
            if prof.get(x["name"]):
                x["who"] = prof[x["name"]]
                x["who_source"] = {"label": "Candidate's statement in the official county voter guide",
                                   "url": sources.get(prof.get("_source"), "")}
                seen.add(c["title"])
        cities = PAMPHLET_NOTE.get(county, ())
        if any(re.search(rf"(?:City|Town) of {re.escape(city)}", c["title"]) for city in cities):
            c["statement_note"] = ("Candidate statements for this race are printed in your Sample Ballot & Official Voter "
                                   "Information Pamphlet; the county doesn't post them publicly.")
    missing = set(profiles) - seen
    if missing:
        print("  WARNING profiles matched no contest:", sorted(missing))


def main(county: str) -> None:
    cfg = COUNTIES[county]
    sf = json.loads(SF_BALLOT.read_text(encoding="utf-8"))
    shared = shared_statewide(sf, cfg["districts"]["ad"]["options"])
    contests, measures = load_county(county, cfg)
    dpath = SRC / county / "measure_digests.json"
    digests = json.loads(dpath.read_text(encoding="utf-8")) if dpath.exists() else {}
    buckets = {"statewide": [], "voter": [], "school": [], "county": [], "city": [], "district": []}
    for c in contests:
        kind, val = classify(cfg, c)
        if kind == "statewide":
            check_statewide(shared, val, c["candidates"], c["title"])
        buckets[kind].append(val)

    apply_profiles(county, buckets)
    sf_secs = {s["id"]: s for s in sf["sections"]}
    def sec(sid, heading, group, contests, **extra):
        base = {k: v for k, v in sf_secs.get(sid, {}).items() if k not in ("contests",)}
        return {**base, "id": sid, "heading": heading, "group": group, **extra, "contests": contests}

    state_offices = [shared[i][1] for i in ["governor", "lt-governor", "secretary-of-state", "controller",
                     "treasurer", "attorney-general", "insurance-commissioner", "boe-2"]]
    city_index = {name: i + 1 for i, name in enumerate(cfg["cities"])}
    city_contests = [c for _, c in sorted(buckets["city"], key=lambda x: cfg["cities"].index(x[0]))]
    county_measures = [measure(cfg, m, city_index, digests) for m in measures if m["jurisdiction"] == cfg["name"]]
    school_measures = [measure(cfg, m, city_index, digests) for m in measures
                       if m["letter"] != "RTM" and m["jurisdiction"] != cfg["name"] and not m["jurisdiction"].startswith(("City of", "Town of"))]
    city_measures = [measure(cfg, m, city_index, digests) for m in measures if m["jurisdiction"].startswith(("City of", "Town of"))]

    sections = [
        sec("voter-nominated", "Voter-Nominated Offices", "offices", state_offices + buckets["voter"]),
        sec("judicial", "Judicial", "offices", [c for s, c in shared.values() if c["kind"] == "retention"]),
        sec("school", "School", "offices", [shared["superintendent"][1]] + buckets["school"],
            note="Local school seats appear only on ballots inside that school or college district."),
        sec("county-offices", "County", "offices", buckets["county"]) if buckets["county"] else None,
        sec("city-offices", "City", "offices", city_contests,
            note="Pick your city above to see only its races. Unincorporated areas have no city races."),
        sec("district-offices", "Special Districts", "offices", buckets["district"],
            note="Transit, water, park, sanitary, fire and healthcare districts. Each appears only on ballots inside that district."),
        sec("state-props", "State Propositions", "measures", [c for s, c in shared.values() if c.get("level") == "state"]),
        sec("regional", "Regional", "measures", [shared["rtm"][1]]),
        sec("county-measures", "County Measures", "measures", county_measures) if county_measures else None,
        sec("school-measures", "School & District Measures", "measures", school_measures,
            note="Each appears only on ballots inside that district. Titles are from the county's official list; full text is in the county voter guide."),
        sec("city-measures", "City Measures", "measures", city_measures,
            note="Titles are from the county's official list; full text and arguments are in the county voter guide."),
    ]
    sections = [s for s in sections if s and s["contests"]]
    districts = dict(cfg["districts"])
    districts["city"] = {"label": "City", "options": list(range(1, len(cfg["cities"]) + 1)) + [0],
                         "labels": {**{str(i + 1): cfg.get("city_labels", {}).get(n, n) for i, n in enumerate(cfg["cities"])}, "0": "Unincorporated area"}}
    out = {
        "election": {"name": "Statewide General Election", "jurisdiction": cfg["name"], "county": county,
                     "short": cfg["short"], "date": sf["election"]["date"], "preview": True,
                     "focus": [{"city": cfg["cities"].index(f["city"]) + 1, "label": f.get("label", f["city"]),
                                "serves": f["serves"]} for f in FOCUS.get(county, [])],
                     "official_sources": cfg["sources"]},
        "built": date.today().isoformat(),
        "randomized_alphabet": sf["randomized_alphabet"],
        "districts": districts,
        "sections": sections,
    }
    dest = ROOT / "site" / "data" / "counties" / county / "ballot.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(s["contests"]) for s in sections)
    print(f"wrote {dest.relative_to(ROOT)}: {n} contests in {len(sections)} sections")
    for s in sections:
        print(f"  {s['heading']:28} {len(s['contests'])}")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in COUNTIES:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
