"""Parse San Mateo County's official "Roster of Candidates" PDF into contests.

    py tools/county_sanmateo_roster.py path/to/roster.pdf

Source: https://smcacre.gov/media/8827 (linked from smcacre.gov's Nov 3 2026
election page). Contests appear in the county's contest-code order, which is
its ballot order. Writes data-src/counties/sanmateo/roster.json:
  [{code, title, vote_for, on_ballot, candidates: [{name, party, designation}]}]
Requires `pdftotext` (poppler).
"""
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONTEST = re.compile(r"^(\d{4})\s+(.+?)\s{2,}.*?Vote for (\d+)\s+On Ballot:\s*(Yes|No)")
CONTEST_NOVOTE = re.compile(r"^(\d{4})\s+(.+?)\s{2,}")
QUAL = re.compile(r"Qualified:\s*\d+\s+(.+?)(?:\s+(DEM|REP|NPP|LIB|GRN|AI|PF))?\s*(?:\s{2,}|$)")
NOISE = re.compile(r"(Res:|Mail:|Day:|Eve:|Website:|Email:|Candidate Stmt Filed|CFMR009|Print Date|Page \d+ of|^Contest$|requirements for the office)")


def titlecase_name(n: str) -> str:
    out = []
    for w in n.split():
        if re.fullmatch(r"\(?[A-Z]\.?\)?", w) or w in ("II", "III", "IV", "JR.", "SR."):
            out.append(w if len(w) > 2 else w)
        elif w.startswith("("):
            out.append("(" + w[1:].capitalize())
        elif "-" in w:
            out.append("-".join(p.capitalize() for p in w.split("-")))
        elif w.upper().startswith("MC") and len(w) > 2:
            out.append("Mc" + w[2:].capitalize())
        else:
            out.append(w.capitalize())
    return " ".join(out)


def main(pdf: str) -> None:
    text = subprocess.run(["pdftotext", "-enc", "UTF-8", "-layout", pdf, "-"], capture_output=True, check=True).stdout.decode("utf-8")
    contests, cur, pending = [], None, None
    for raw in text.splitlines():
        line = raw.rstrip()
        s = line.strip()
        if not s:
            continue
        m = CONTEST.match(s)
        if m:
            cur = {"code": m.group(1), "title": m.group(2).strip(), "vote_for": int(m.group(3)),
                   "on_ballot": m.group(4) == "Yes", "candidates": []}
            contests.append(cur); pending = None
            continue
        q = QUAL.search(s)
        if q and cur is not None:
            pending = {"name": titlecase_name(q.group(1).strip()), "party": q.group(2) or "", "designation": ""}
            cur["candidates"].append(pending)
            continue
        # The first non-noise text line after a candidate is their ballot designation.
        if pending is not None and not pending["designation"] and not NOISE.search(s):
            first = re.split(r"\s{2,}", s)[0].strip()
            if first and not first.isdigit() and first not in ("No", "Yes"):
                pending["designation"] = first
    dest = ROOT / "data-src" / "counties" / "sanmateo" / "roster.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(contests, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}: {len(contests)} contests, "
          f"{sum(len(c['candidates']) for c in contests)} candidates")
    for c in contests:
        print(f"  {c['code']} {c['title'][:60]:60} vote {c['vote_for']}  {len(c['candidates'])} cand  "
              f"{', '.join(x['name'] for x in c['candidates'][:4])}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1])
