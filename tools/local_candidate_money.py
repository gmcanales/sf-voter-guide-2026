"""Money for local candidates on the county ballots, from NetFile's public API.

    py tools/local_candidate_money.py [alameda sanmateo contracosta]

City and town races file with their city's NetFile agency; county offices and special
districts are looked up in the county's agency (many special-district candidates file
elsewhere or raise under $2,000 and form no committee, so absence is common and is
shown as "not found", never as $0 raised).

A candidate's committee is matched in the agency's filer list by surname (any part of a
hyphenated one) plus the first-name stem or a quoted nickname, among 2026-era committees
(the name says 2026, or the FPPC id was issued since 2025); independent-expenditure and
ballot-measure committees that mention the candidate are skipped. Every match is printed
for review. Totals are itemized contributions (see local_measure_money.committee_itemized).

Writes site/data/counties/<county>/candidate_money.json.
"""
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from local_measure_money import agencies, agency_filers, committee_itemized, COUNTY_AGENCY  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIRST_2025_ID = 1476000          # FPPC ids at or above this were issued from early 2025 on
SINCE = "2025-01-01"             # count this cycle only; some committees carry over from 2024
NOT_CANDIDATE = re.compile(r"support|oppos|independent|\bpac\b|yes on|no on|measure|recall|ballot", re.I)
SUFFIX = {"jr", "sr", "ii", "iii", "iv"}


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


OTHER_OFFICE = re.compile(r"assembly|state senate|\bsenate\b|governor|congress|attorney general", re.I)
NICK = {"mike": "michael", "bob": "robert", "bobby": "robert", "rob": "robert", "bill": "william",
        "will": "william", "jim": "james", "jimmy": "james", "tom": "thomas", "rick": "richard",
        "dick": "richard", "pam": "pamela", "becca": "rebecca", "becky": "rebecca", "dan": "daniel",
        "dave": "david", "steve": "steven", "chris": "christopher", "joe": "joseph", "tony": "anthony",
        "liz": "elizabeth", "beth": "elizabeth", "sue": "susan", "ed": "edward", "matt": "matthew",
        "nick": "nicholas", "ben": "benjamin", "greg": "gregory", "jeff": "jeffrey", "ken": "kenneth",
        "larry": "lawrence", "pat": "patrick", "ron": "ronald", "tim": "timothy", "andy": "andrew",
        "katie": "katherine", "kate": "katherine", "cathy": "catherine", "jen": "jennifer",
        "jenny": "jennifer", "zac": "zachary", "zach": "zachary", "sam": "samuel"}
# Words that say nothing about which contest a committee is for.
GENERIC = {"for", "the", "of", "to", "and", "city", "town", "council", "member", "board", "district",
           "director", "trustee", "area", "ward", "division", "governing", "committee", "elect", "re",
           "friends", "school", "unified", "union", "2026", "seat", "dr", "mr", "ms", "d", "a", "b", "c"}
NOT_FIRST = GENERIC | {"campaign", "fund", "political", "people", "neighbors"}


def stem(word: str) -> str:
    return NICK.get(word, word)[:3]


def name_keys(name: str) -> tuple[set, set]:
    """(surname parts, first-name stems incl. quoted nicknames) for a ballot name."""
    nick = re.findall(r"[\"“(]([^\"”)]+)[\"”)]", name)
    words = [w for w in re.sub(r"[\"“”().,]", " ", fold(re.sub(r"[\"“(][^\"”)]+[\"”)]", " ", name))).split()
             if w not in SUFFIX]
    if not words:
        return set(), set()
    sur = set(words[-1].split("-"))
    firsts = {stem(words[0])} | {stem(fold(n).split()[0]) for n in nick if n.strip()}
    return sur, firsts


def recent(f: dict) -> bool:
    fid = (f.get("fppcId") or "").rstrip(".")
    return "2026" in (f.get("name") or "") or (fid.isdigit() and FIRST_2025_ID <= int(fid) < 10_000_000)


def other_first_name(tokens: list[str], sur: set, firsts: set) -> bool:
    """A different first name right next to the surname ("Henderson, Jon"; "John Coleman")."""
    for i, t in enumerate(tokens):
        if t in sur:
            for j in (i - 1, i + 1):
                if 0 <= j < len(tokens):
                    w = tokens[j]
                    if w.isalpha() and len(w) > 1 and w not in NOT_FIRST and w not in sur and stem(w) not in firsts:
                        return True
    return False


def find_committee(cand: str, contest: dict, filers: list[dict]) -> dict | None:
    sur, firsts = name_keys(cand)
    contest_words = set(re.split(r"[^a-z]+", fold(contest["title"]))) - GENERIC - {""}
    strong, weak = [], []
    for f in filers:
        fn = f.get("name") or ""
        if not recent(f) or NOT_CANDIDATE.search(fn) or OTHER_OFFICE.search(fn):
            continue
        tokens = [t for t in re.split(r"[^a-z]+", fold(fn).replace("-", " ")) if t]
        words = set(tokens)
        if not sur & words:
            continue
        if any(stem(w) in firsts for w in words if len(w) >= 2):
            strong.append(f)
        elif not other_first_name(tokens, sur, firsts) and words & contest_words:
            weak.append(f)          # "Kimberlin for Fremont City Council D3 2026"
    if len(strong) == 1:
        return strong[0]
    if not strong and len(weak) == 1:
        return weak[0]
    return None                     # none, or ambiguous: leave for a human


def agency_for(contest: dict, city_labels: dict, ags: list[dict]) -> dict | None:
    """The city's NetFile agency for a city race (its `applies.city` label), else the county's.
    City committees appear in the county agency's filer list too, but their transactions are
    only searchable in the city's own agency."""
    n = (contest.get("applies") or {}).get("city")
    if n:
        place = re.sub(r"\s*\(.*?\)", "", city_labels.get(str(n), "")).strip()   # "Richmond (incl. Richmond Annex)"
        return next((a for a in ags if place and re.search(r"\b" + re.escape(place) + r"\b", a["name"])
                     and "County" not in a["name"]), None)
    code = COUNTY_AGENCY.get(contest["id"].split("-")[0])
    return next((a for a in ags if a["shortcut"] == code), None)


def agency_label(name: str) -> str:
    """NetFile's "Fremont, City" / "Berkeley, City of" / "Alameda, County of" -> readable."""
    m = re.match(r"(.+?),\s*(City|Town)(?: of)?$", name)
    if m:
        return f"{m.group(2)} of {m.group(1)}"
    m = re.match(r"(.+?),\s*County(?: of)?$", name)
    return f"{m.group(1)} County" if m else name


def main(counties: list[str]) -> None:
    ags = agencies()
    for county in counties:
        ballot = json.loads((ROOT / "site" / "data" / "counties" / county / "ballot.json").read_text(encoding="utf-8"))
        city_labels = ballot.get("districts", {}).get("city", {}).get("labels", {})
        out, n_found, n_cands = {}, 0, 0
        for sec in ballot["sections"]:
            for c in sec["contests"]:
                if c.get("kind") != "office" or not re.match(r"(ala|smc|cc)-", c["id"]) or not c.get("candidates"):
                    continue
                ag = agency_for(c, city_labels, ags)
                if not ag:
                    continue                    # city not on NetFile
                filers = agency_filers(ag["shortcut"])
                for x in c["candidates"]:
                    n_cands += 1
                    f = find_committee(x["name"], c, filers)
                    if not f:
                        continue
                    fid = (f.get("fppcId") or "").rstrip(".")
                    rec = committee_itemized(ag, fid, f["name"], since=SINCE) or {
                        "agency": ag["shortcut"], "agency_name": ag["name"], "itemized": 0, "donor_count": 0, "top": []}
                    rec.update({"committee": f["name"], "fppc_id": fid, "agency_name": agency_label(ag["name"]),
                                "portal": f"https://public.netfile.com/pub2/?AID={ag['shortcut']}"})
                    out.setdefault(c["id"], {})[x["name"]] = rec
                    n_found += 1
                    print(f"  {ag['shortcut']:5} {x['name'][:26]:26} -> {f['name'][:58]:58} ${rec['itemized']:>9,}")
        dest = ROOT / "site" / "data" / "counties" / county / "candidate_money.json"
        dest.write_text(json.dumps({
            "built": date.today().isoformat(),
            "source": {"label": "NetFile public API (local Form 460 / 497 filings)",
                       "url": "https://netfile.com/Connect2/api/swagger-ui/"},
            "candidates": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{county}: committees found for {n_found} of {n_cands} local candidates on NetFile agencies")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1:] or ["alameda", "sanmateo", "contracosta"])
