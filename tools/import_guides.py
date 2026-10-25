"""Merge hand-transcribed county guides into site/data/endorsements.json.

    py tools/import_guides.py

Reads every data-src/guides/*.json that has an "entries" list (machine-imported
guides such as eastbaydsa_2026.json have "races" instead and are skipped):
  {"guide": "<guide id>", "entries": [
     {"county": "alameda", "contest": "<exact ballot title or contest id>",
      "picks": [...] | "vote": "yes"|"no" | "none": "<their wording>", "note": "..."}]}
Each contest is resolved in that county's preview ballot; each picked name is
matched to the ballot spelling (accents, middle initials). Any miss stops the
import, so a transcription slip can't reach the page. The guide's previous
positions are replaced wholesale.
"""
import json
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c)).replace(".", "")


def ballot_name(name: str, ballot: list[str]) -> str | None:
    f = fold(name).split()
    hits = [c for c in ballot if fold(c).split()[:1] == f[:1] and fold(c).split()[-1:] == f[-1:]]
    return hits[0] if len(hits) == 1 else None


def main() -> None:
    contests = {}
    for county in ("alameda", "sanmateo", "contracosta"):
        b = json.loads((ROOT / "site" / "data" / "counties" / county / "ballot.json").read_text(encoding="utf-8"))
        idx = {}
        for s in b["sections"]:
            for c in s["contests"]:
                idx[c["id"]] = c
                idx[c["title"]] = c
        contests[county] = idx
    ep = ROOT / "site" / "data" / "endorsements.json"
    data = json.loads(ep.read_text(encoding="utf-8"))
    errors = []
    for path in sorted((ROOT / "data-src" / "guides").glob("*.json")):
        g = json.loads(path.read_text(encoding="utf-8"))
        if "entries" not in g:
            continue
        gid = g["guide"]
        if g.get("mode") != "merge":       # "merge": add county positions to a guide that has others (e.g. SF)
            for byg in data["positions"].values():
                byg.pop(gid, None)
        n = 0
        for e in g["entries"]:
            c = contests[e["county"]].get(e["contest"])
            if not c:
                errors.append(f"{path.name}: no contest {e['contest']!r} in {e['county']}")
                continue
            if "picks" in e:
                ballot = [x["name"] for x in c.get("candidates", [])]
                names = [ballot_name(n_, ballot) for n_ in e["picks"]]
                if None in names:
                    errors.append(f"{path.name}: {e['contest']}: {e['picks']} vs ballot {ballot}")
                    continue
                value = {"picks": names, "note": e["note"]} if e.get("note") else names
            elif "vote" in e:
                value = {"vote": e["vote"], "note": e["note"]} if e.get("note") else e["vote"]
            else:
                value = {"none": e["none"]}
            data["positions"].setdefault(c["id"], {})[gid] = value
            n += 1
        print(f"{path.name}: {n} positions for {gid}")
    if errors:
        print("\n".join("  ERROR " + x for x in errors))
        sys.exit("import stopped; nothing written")
    ep.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
