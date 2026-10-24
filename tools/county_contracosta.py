"""Fetch Contra Costa County's official contest + measure lists for Nov 3 2026.

    py tools/county_contracosta.py

Source: the Elections Division's own election widget API (the data behind
"List of candidates and measures" on
https://www.contracostavote.gov/election/november-3-2026-general-election/):
  /ce/mobile/seam/resource/rest/election/getElection?eid=66          offices + measures
  /ce/mobile/seam/resource/rest/election/getOfficeCandidates?eoid=N  candidates per office
Each measure links to a county page carrying the ballot question, the impartial
analysis and the official arguments; those are captured too.

Writes data-src/counties/contracosta/{contests,measures}.json. The API carries no
ballot designations, so candidates have names and party preference only.
"""
import html
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data-src" / "counties" / "contracosta"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) sf_voter_guide/1.0"
API = "https://www.contracostavote.gov/ce/mobile/seam/resource/rest/election/"
EID = 66
PARTIES = {"Democratic": "DEM", "Republican": "REP", "No Party Preference": "NPP", "Green": "GRN",
           "Libertarian": "LIB", "Peace and Freedom": "PF", "American Independent": "AI"}


def get(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=60).read().decode("utf-8")


def jsonp(url: str) -> dict:
    body = get(url)
    return json.loads(re.match(r"\s*cb\((.*)\)\s*;?\s*$", body, re.S).group(1))


def text(s: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s))).strip()


def fetch_contests(e: dict) -> list:
    out = []
    for level, groups in e["offices"].items():
        for group, offices in groups.items():
            for o in offices:
                if not o["hasCand"]:          # judicial retention: no candidate list
                    continue
                d = jsonp(f"{API}getOfficeCandidates?eoid={o['id']}&lang=en-US&callback=cb")
                cands = []
                for c in d["candidates"]:
                    party = (c.get("party") or {}).get("name", "").replace("Party Preference:", "").strip()
                    cands.append({"name": c["candidateDisplayName"].strip(), "party": PARTIES.get(party, ""),
                                  "designation": ""})
                out.append({"level": level, "group": text(group), "title": text(o["name"]),
                            "vote_for": d.get("votefor") or 1, "candidates": cands})
                time.sleep(0.2)
    return out


# Short titles where the page has no title line and the question doesn't name the type.
# Each paraphrases the measure's own ballot question / impartial analysis.
TITLES = {
    "Q": "Fire station and firefighter facility bonds ($120M)",   # question: $120,000,000 in bonds
    "O": "Business license tax update",          # analysis: "Business License Tax Simplification"
    "S": "Rent stabilization ordinance",          # question: caps rent increases at 60% of CPI or 3%
    "T": "Appointed city treasurer",              # question: "Shall the office of the City Treasurer be appointive?"
    "U": "Senior mixed-use rezoning (N. California Blvd at Ygnacio Valley Rd)",
    "W": "Parcel tax increase",                   # analysis: +$168/yr for eight years
}

STOP = ("The above statement", "/s/", "TAX RATE STATEMENT", "ARGUMENT IN", "ARGUMENT AGAINST",
        "REBUTTAL TO", "FULL TEXT", "TEXT OF", "BOND MEASURE", "EXHIBIT")


def short_title(question: str) -> str:
    q = question.lower()
    for pat, label in [(r"\bbonds?\b", "Bond measure"), (r"parcel tax", "Parcel tax"),
                       (r"sales tax|transactions and use", "Sales tax"), (r"\btax\b", "Tax measure"),
                       (r"charter", "Charter amendment")]:
        if re.search(pat, q):
            return label
    return "Measure"


def parse_measure_page(url: str, letter: str) -> dict:
    lines = [text(l) for l in html.unescape(re.sub(r"<(?:br|/p|/div|/h\d|/li)[^>]*>", "\n", get(url))).splitlines()]
    lines = [l for l in lines if l]
    hdr = f"MEASURE {letter}"
    i = lines.index(hdr)
    while lines[i + 1] == hdr:                    # some pages repeat the header line
        i += 1
    jur = lines[i + 1]
    k = i + 2
    title = None
    # Some pages carry an all-caps title line before the question ("CITY OF CLAYTON SALES TAX MEASURE.").
    if lines[k].isupper() and "IMPARTIAL ANALYSIS" not in lines[k]:
        title = lines[k].rstrip(".").capitalize(); k += 1
    question = lines[k]
    an = next((j for j in range(k, len(lines)) if "IMPARTIAL ANALYSIS" in lines[j].upper()), None)
    analysis = []
    if an is not None:
        j = an + 1
        if lines[j] == hdr:
            j += 1
        while j < len(lines) and not lines[j].startswith(STOP):
            analysis.append(lines[j]); j += 1

    def section(head: str) -> list:
        try:
            k2 = lines.index(head, k)
        except ValueError:
            return []
        body = []
        for l in lines[k2 + 1:]:
            if l == hdr and not body:
                continue
            if l.startswith(STOP):
                break
            body.append(l)
        return body
    return {"jurisdiction": jur.title().replace(" Of ", " of "), "title": title or TITLES.get(letter) or short_title(question),
            "question": question, "analysis": analysis,
            "arg_for": section("ARGUMENT IN FAVOR OF"), "arg_against": section("ARGUMENT AGAINST"),
            "source": url}


def fetch_measures(e: dict) -> list:
    out = []
    for level, qs in e.get("questions", {}).items():
        for q in qs:
            m = re.search(r'href="([^"]+)"', q["title"])
            letter = re.search(r"Measure\s+([A-Z]{1,2})\b", text(q["title"]))
            if not (m and letter):
                print("  skip question", text(q["title"])[:60]); continue
            try:
                d = parse_measure_page(m.group(1), letter.group(1))
            except (ValueError, IndexError) as err:
                print(f"  could not parse {m.group(1)}: {err}")
                d = {"jurisdiction": level, "title": f"Measure {letter.group(1)}", "source": m.group(1)}
            out.append({"letter": letter.group(1), **d})
            time.sleep(0.2)
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    e = jsonp(f"{API}getElection?eid={EID}&lang=en-US&callback=cb")
    contests = fetch_contests(e)
    measures = fetch_measures(e)
    (OUT / "contests.json").write_text(json.dumps(contests, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (OUT / "measures.json").write_text(json.dumps(measures, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"contracosta: {len(contests)} contests, {sum(len(c['candidates']) for c in contests)} candidates, {len(measures)} measures")
    for c in contests:
        print(f"  {c['title'][:62]:62} v{c['vote_for']} {', '.join(x['name'] for x in c['candidates'][:3])}")
    for m in measures:
        print(f"  Measure {m['letter']:3} {m.get('jurisdiction','')[:30]:30} {m.get('title','')[:50]}  analysis:{len(m.get('analysis',[]))}p")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
