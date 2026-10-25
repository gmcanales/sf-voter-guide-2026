"""Import East Bay DSA's 2026 voter guide into endorsements.json (guide id "ebdsa").

    py tools/guide_eastbaydsa.py

Source: https://vote.eastbaydsa.org, the chapter's published guide. Its race data
ships as a JavaScript module; this fetches the current build, has Node load it,
and keeps only explicit positions:
  - candidates marked "endorse" or "recommend"  -> a pick list
  - measures with voteDirection yes / no        -> "yes" / "no"
  - voteDirection "no-position"                 -> {"none": ...}
Positions the guide credits to California DSA (statewide props, offices, RTM)
carry a note saying so. Race ids are mapped to this guide's contest ids
explicitly below; candidate names are matched to the ballot spelling.
Writes data-src/guides/eastbaydsa_2026.json (raw races, for traceability) and
updates site/data/endorsements.json positions[...]["ebdsa"]. Requires node.
"""
import json
import re
import subprocess
import sys
import tempfile
import unicodedata
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BASE = "https://vote.eastbaydsa.org"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) sf_voter_guide/1.0"
GUIDE_ID = "ebdsa"

MEASURES = {   # their race id -> our contest id (unlettered ids resolved from the county lists)
    "dublin-usd-measure": "ala-measure-i", "san-lorenzo-usd-measure": "ala-measure-j",
    "sunol-glen-usd-measure": "ala-measure-k", "emeryville-measure": "ala-measure-bb",
    "hayward-measure": "ala-measure-cc", "newark-measure": "ala-measure-dd",
    "piedmont-measure": "ala-measure-gg", "pleasanton-measure": "ala-measure-hh",
    "union-city-measure": "ala-measure-ii",
    "hercules-measure": "cc-measure-p", "richmond-measure": "cc-measure-q",
    "west-contra-costa-usd-measure": "cc-measure-v", "acalanes-union-high-measure": "cc-measure-w",
    "liberty-union-high-measure": "cc-measure-x",
}
ALAMEDA_CITIES = ("alameda", "albany", "berkeley", "oakland")
CC_CITIES = ("clayton", "concord", "san-pablo", "walnut-creek")


def our_id(rid: str) -> str | None:
    if rid in MEASURES:
        return MEASURES[rid]
    if m := re.fullmatch(r"([a-z-]+)-measure-([a-z]{1,2})", rid):
        city, letter = m.groups()
        if city in ALAMEDA_CITIES:
            return f"ala-measure-{letter}"
        if city in CC_CITIES:
            return f"cc-measure-{letter}"
    if m := re.fullmatch(r"ca-prop-(\d+)-.*", rid):
        return f"prop-{m.group(1)}"
    if rid.startswith("rtm-"):
        return "rtm"
    fixed = {"ca-insurance-commissioner": "insurance-commissioner", "ca-board-of-equalization-2": "boe-2",
             "richmond-mayor": "cc-city-of-richmond-mayor",
             "berkeley-rent-board": "ala-rent-stabilization-board-commissioners-berkeley"}
    if rid in fixed:
        return fixed[rid]
    for pat, fmt in [(r"ca-assembly-(\d+)", "assembly-{}"), (r"ca-senate-(\d+)", "state-senate-{}"),
                     (r"us-house-(\d+)", "us-rep-{}"),
                     (r"oakland-council-(\d+)", "ala-councilmember-district-no-{}-oakland"),
                     (r"oakland-school-board-(\d+)", "ala-school-director-district-no-{}-oakland"),
                     (r"hayward-council-(\d+)", "ala-members-of-city-council-district-{}-hayward"),
                     (r"berkeley-council-(\d+)", "ala-member-of-city-council-district-{}-berkeley")]:
        if m := re.fullmatch(pat, rid):
            return fmt.format(m.group(1))
    return None


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def ballot_name(name: str, candidates: list[str]) -> str | None:
    """Match a guide's spelling to the ballot's ("Sally Lieber" -> "Sally J. Lieber")."""
    f = fold(name).split()
    for c in candidates:
        cf = fold(c).replace(".", "").split()
        if cf and f and cf[-1] == f[-1] and cf[0] == f[0]:
            return c
    return None


def get(url: str) -> str:
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60).read().decode("utf-8")


def fetch_races() -> list:
    index = get(BASE)
    app = re.search(r'src="(/assets/index-[^"]+\.js)"', index).group(1)
    js = get(BASE + app)
    mod = re.search(r"\./(guide-2026-[A-Za-z0-9_-]+\.js)", js).group(1)
    src = get(f"{BASE}/assets/{mod}")
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "guide.mjs"
        path.write_text(src, encoding="utf-8")
        out = subprocess.run(["node", "--input-type=module", "-e",
                              f"import {{ races }} from {json.dumps(path.as_uri())}; process.stdout.write(JSON.stringify(races));"],
                             capture_output=True, check=True)
    races = json.loads(out.stdout.decode("utf-8"))
    for r in races:            # long explainer text stays on their site
        r.pop("content", None)
    return races


def main() -> None:
    races = fetch_races()
    raw = ROOT / "data-src" / "guides" / "eastbaydsa_2026.json"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(json.dumps({"source": BASE, "fetched": date.today().isoformat(), "races": races},
                              ensure_ascii=False, indent=1) + "\n", encoding="utf-8")

    contests = {}
    for county in ("alameda", "contracosta"):
        b = json.loads((ROOT / "site" / "data" / "counties" / county / "ballot.json").read_text(encoding="utf-8"))
        for s in b["sections"]:
            for c in s["contests"]:
                contests[c["id"]] = c
    ep = ROOT / "site" / "data" / "endorsements.json"
    data = json.loads(ep.read_text(encoding="utf-8"))
    pos = data["positions"]
    for byg in pos.values():
        byg.pop(GUIDE_ID, None)
    added, skipped = 0, []
    for r in races:
        cid = our_id(r["id"])
        if not cid or cid not in contests:
            if any(x.get("position") for x in r.get("candidates", [])) or r.get("voteDirection"):
                skipped.append(r["id"])
            continue
        note = "California DSA's position, carried in East Bay DSA's guide." if r.get("sourceFrom") == "California DSA" else None
        if r.get("candidates"):
            names = [x["name"] for x in r["candidates"] if x.get("position") in ("endorse", "recommend")]
            if not names:
                continue
            ballot = [c["name"] for c in contests[cid].get("candidates", [])]
            matched = [ballot_name(n, ballot) for n in names]
            if None in matched:
                print(f"  WARNING {r['id']}: couldn't match {names} to {ballot}")
                continue
            value = {"picks": matched, "note": note} if note else matched
        else:
            d = r.get("voteDirection")
            if d in ("yes", "no"):
                value = {"vote": d, "note": note} if note else d
            elif d == "no-position":
                value = {"none": "No position"}
            else:
                continue
        pos.setdefault(cid, {})[GUIDE_ID] = value
        added += 1
    ep.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"ebdsa: {len(races)} races in guide, {added} positions on our ballots")
    print("  not on our ballots (other counties):", ", ".join(skipped) or "none")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
