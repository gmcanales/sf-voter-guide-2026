"""Fetch Alameda County's official contest + measure lists for Nov 3 2026.

    py tools/county_alameda.py

Sources (Alameda County Registrar of Voters, both public, no bot wall):
  - Candidate List search  https://alamedacountyca.gov/rov_app/candidatelist
    (election 260, race status "On Ballot", candidate status "Filing Completed")
  - Election page          https://acvote.alamedacountyca.gov/election-information/elections?id=260
    ("List of Measure Questions": letter, jurisdiction, title)

Writes data-src/counties/alameda/{contests,measures}.json. Contest order is the
order the Registrar's list returns, which follows its ballot contest order.
"""
import html
import json
import re
import sys
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data-src" / "counties" / "alameda"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) sf_voter_guide/1.0"
CAND_URL = "https://alamedacountyca.gov/rov_app/candidatelist/"
ELEC_URL = "https://acvote.alamedacountyca.gov/election-information/elections?id=260"
PARTIES = {"Democratic Party": "DEM", "Republican Party": "REP", "No Party Preference": "NPP",
           "Green Party": "GRN", "Libertarian Party": "LIB", "Peace and Freedom Party": "PF",
           "American Independent Party": "AI"}


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def titlecase_name(n: str) -> str:
    out = []
    for w in n.split():
        if re.fullmatch(r"(?:[A-Z]\.?){1,3}", w) and (len(w) == 1 or "." in w) or w in ("II", "III", "IV"):
            out.append(w)
        elif w.startswith("("):
            out.append("(" + w[1:].capitalize())
        elif "-" in w:
            out.append("-".join(p.capitalize() for p in w.split("-")))
        elif w.startswith("MC") and len(w) > 2:
            out.append("Mc" + w[2:].capitalize())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def fetch_candidates() -> list:
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(CookieJar()))
    opener.addheaders = [("User-Agent", UA)]
    opener.open(CAND_URL.rstrip("/")).read()  # session cookie
    form = urllib.parse.urlencode({"electionId": 260, "categoryId": "", "raceId": "", "lastName": "",
                                   "raceStatus": "onballot", "candidateStatus": "COMPLETED"}).encode()
    page = opener.open(CAND_URL, data=form).read().decode("utf-8")
    contests = []
    # The page renders every contest twice (a "big data" desktop table and a "small data"
    # mobile one). Read only the FIRST LOOP sections; within one, the first candidate block
    # carries the contest header and each further candidate is its own block.
    for section in re.findall(r"FIRST LOOP BEGIN.*?-->(.*?)<!-- FIRST LOOP END", page, re.S):
        head = re.search(r'candidate-list-table-header">(.*?)</span>\s*<span class="candidate-list-text_vote_for">Vote For:\s*(\d+)', section, re.S)
        if not head:
            continue
        title = re.sub(r"\s*-\s*On Ballot\s*$", "", text(head.group(1)))
        cands = []
        for row in re.findall(r"<tr>(.*?)</tr>", section, re.S):
            cells = re.findall(r"<td[^>]*>(.*?)</td>", row, re.S)
            if len(cells) < 2 or "candidateName" not in cells[0]:
                continue
            name = text(re.search(r"<span class='candidateName'>(.*?)</span>", cells[0], re.S).group(1))
            party = text(cells[0].split("<br", 1)[1]) if "<br" in cells[0] else ""
            inc = re.search(r'Incumbent:</div>\s*<div class="candidate-detail-data">\s*([YN])', row)
            cands.append({"name": titlecase_name(name), "party": PARTIES.get(party, party),
                          "designation": text(cells[1]), "incumbent": bool(inc and inc.group(1) == "Y")})
        contests.append({"title": title, "vote_for": int(head.group(2)), "candidates": cands})
    return contests


def fetch_measures() -> list:
    req = urllib.request.Request(ELEC_URL, headers={"User-Agent": UA})
    page = text(urllib.request.urlopen(req).read().decode("utf-8"))
    out = []
    for m in re.finditer(r"Measure (RTM|[A-Z]{1,2}) - (.+?)(?= Measure (?:RTM|[A-Z]{1,2}) - | Randomized Alphabet)", page):
        letter, rest = m.group(1), m.group(2).strip()
        parts = [p.strip() for p in rest.split(" - ")]
        if letter == "RTM":
            out.append({"letter": "RTM", "jurisdiction": "Regional (BART district counties)", "title": rest})
        else:
            out.append({"letter": letter, "jurisdiction": parts[0], "title": " - ".join(parts[1:]) or parts[0]})
    # The list appears more than once on the page (nav + body); keep first occurrence of each letter.
    seen, uniq = set(), []
    for x in out:
        if x["letter"] not in seen:
            seen.add(x["letter"]); uniq.append(x)
    return uniq


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    contests = fetch_candidates()
    measures = fetch_measures()
    (OUT / "contests.json").write_text(json.dumps(contests, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "measures.json").write_text(json.dumps(measures, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"alameda: {len(contests)} contests, {sum(len(c['candidates']) for c in contests)} candidates, {len(measures)} measures")
    for c in contests:
        print(f"  {c['title'][:62]:62} v{c['vote_for']} {', '.join(x['name'] for x in c['candidates'][:3])}")
    for m in measures:
        print(f"  Measure {m['letter']:3} {m['jurisdiction'][:28]:28} {m['title'][:60]}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
