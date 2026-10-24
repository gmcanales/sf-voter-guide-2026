"""San Mateo County's official contest + measure lists for Nov 3 2026.

    py tools/county_sanmateo.py path/to/roster.pdf

Candidates: the county's "Roster of Candidates" PDF.
Source: https://smcacre.gov/media/8827 (linked from smcacre.gov's Nov 3 2026
election page). Contests appear in the county's contest-code order, which is
its ballot order. Writes data-src/counties/sanmateo/roster.json:
  [{code, title, vote_for, on_ballot, candidates: [{name, party, designation}]}]

Reads `pdftotext -raw` output, where each contest is
    <title> / <code> On Ballot: Yes|No / Vote for N
and each candidate is
    <NAME [PARTY]> / Qualified: N Candidate Stmt Filed? ... / <designation>
"On Ballot: No" marks an uncontested seat the county appoints instead.
Measures: the "County / Regional / School District / City Measures" lists on
https://smcacre.gov/elections/november-3-2026-statewide-general-election,
written to data-src/counties/sanmateo/measures.json as
  [{letter, jurisdiction, title}]
Requires `pdftotext` (poppler).
"""
import html
import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ELEC_URL = "https://smcacre.gov/elections/november-3-2026-statewide-general-election"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) sf_voter_guide/1.0"
CODE = re.compile(r"^(\d{4}) On Ballot:\s*(Yes|No)$")
VOTE = re.compile(r"^Vote for (\d+)$")
QUAL = re.compile(r"^Qualified:\s*\d+\b")
PARTY = re.compile(r"\s+(DEM|REP|NPP|LIB|GRN|AI|PF)$")
NOISE = re.compile(r"^(Res:|Mail:|Day:|Eve:|Website:|Email:|Not Auth|CFMR009|Print Date|Contest$|All Contests|"
                   r"Qualified Candidates|All Qualified|\*Qualified|requirements for|MARK CHURCH|CHIEF ELECTIONS|"
                   r"STATEWIDE GENERAL|NOVEMBER 3|ROSTER OF)")


def titlecase_name(n: str) -> str:
    out = []
    for w in n.split():
        if re.fullmatch(r"(?:[A-Z]\.?){1,3}", w) and (len(w) == 1 or "." in w) or w in ("II", "III", "IV"):
            out.append(w)
        elif w in ("JR.", "SR.", "JR", "SR"):
            out.append(w.capitalize())
        elif w.startswith("("):
            out.append("(" + w[1:].capitalize())
        elif "-" in w:
            out.append("-".join(p.capitalize() for p in w.split("-")))
        elif w.startswith("MC") and len(w) > 2:
            out.append("Mc" + w[2:].capitalize())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def fetch_measures() -> list:
    req = urllib.request.Request(ELEC_URL, headers={"User-Agent": UA})
    page = urllib.request.urlopen(req).read().decode("utf-8")
    text = html.unescape(re.sub(r"<[^>]+>", "\n", page))
    out, seen = [], set()
    for line in (l.strip() for l in text.splitlines()):
        # One line on the page has a double space and a mis-encoded dash, so match loosely.
        m = re.match(r"^Measure\s+([A-Z]{1,2})\s+\S\s+(.+)$", line)
        if m and m.group(1) not in seen:
            seen.add(m.group(1))
            rest = m.group(2)
            if ":" in rest:
                jur, title = (x.strip() for x in rest.split(":", 1))
            else:  # "San Mateo County Charter Amendment Measure – Extreme Weather Events"
                jur, title = "San Mateo County", re.sub(r"^San Mateo County\s+", "", rest)
            out.append({"letter": m.group(1), "jurisdiction": jur, "title": title})
    return out


def main(pdf: str) -> None:
    lines = [l.strip() for l in subprocess.run(["pdftotext", "-enc", "UTF-8", "-raw", pdf, "-"],
             capture_output=True, check=True).stdout.decode("utf-8").splitlines()]
    lines = [l for l in lines if l]
    contests, cur = [], None
    for i, s in enumerate(lines):
        m = CODE.match(s)
        if m:
            cur = {"code": m.group(1), "title": lines[i - 1], "vote_for": 1,
                   "on_ballot": m.group(2) == "Yes", "candidates": []}
            contests.append(cur)
            continue
        v = VOTE.match(s)
        if v and cur is not None:
            cur["vote_for"] = int(v.group(1))
            continue
        if QUAL.match(s) and cur is not None:
            name = lines[i - 1]
            party = PARTY.search(name)
            name = PARTY.sub("", name)
            nxt = lines[i + 1] if i + 1 < len(lines) else ""
            cur["candidates"].append({"name": titlecase_name(name), "party": party.group(1) if party else "",
                                      "designation": "" if NOISE.match(nxt) else nxt})
    measures = fetch_measures()
    mdest = ROOT / "data-src" / "counties" / "sanmateo" / "measures.json"
    mdest.parent.mkdir(parents=True, exist_ok=True)
    mdest.write_text(json.dumps(measures, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {mdest.relative_to(ROOT)}: {len(measures)} measures")
    for m in measures:
        print(f"  Measure {m['letter']:3} {m['jurisdiction'][:40]:40} {m['title'][:60]}")
    dest = ROOT / "data-src" / "counties" / "sanmateo" / "roster.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(contests, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}: {len(contests)} contests "
          f"({sum(c['on_ballot'] for c in contests)} on ballot), "
          f"{sum(len(c['candidates']) for c in contests)} candidates")
    for c in contests:
        print(f"  {c['code']} {'B' if c['on_ballot'] else '-'} {c['title'][:58]:58} v{c['vote_for']} "
              f"{', '.join(x['name'] + (' (' + x['designation'][:18] + ')' if x['designation'] else '') for x in c['candidates'][:3])}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
