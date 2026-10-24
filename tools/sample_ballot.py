"""Verify the guide against a real sample ballot, transcribed to CSV.

1. Generate a pre-filled CSV for a ballot type (our current lists, in our order):

       py tools/sample_ballot.py template --cd 11 --ad 17 --sup 8 --bart 8 > data-src/sample_ballots/ad17-sup8.csv

2. Edit it to match the printed sample ballot EXACTLY: fix the row order, fix
   name spellings and designations, add a row for each missing candidate
   (copy the contest's `id`), delete rows that aren't on the ballot. Columns:

       id, contest, choice, designation, party

   One row per candidate/justice/measure, top to bottom as printed. Leave
   `choice` blank for measures. Do NOT record how you voted.

3. Compare and (optionally) write the corrections into the skeleton:

       py tools/sample_ballot.py check data-src/sample_ballots/ad17-sup8.csv
       py tools/sample_ballot.py check data-src/sample_ballots/ad17-sup8.csv --apply
       py tools/build_ballot.py

`--apply` marks every office on the ballot `order: "verified"` with the ballot
type it came from, replacing the candidate list (in the ballot's order) where
it differed. Statewide offices rotate by Assembly District, so their order is
recorded per AD (`verified_order_by_ad`) and other ADs keep the computed order.
"""
import argparse
import csv
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKELETON = ROOT / "data-src" / "ballot_skeleton.json"
FIELDS = ["id", "contest", "choice", "designation", "party"]


def load_skeleton() -> dict:
    return json.loads(SKELETON.read_text(encoding="utf-8"))


def applies(contest: dict, districts: dict) -> bool:
    return all(districts.get(dim) in (None, want) for dim, want in (contest.get("applies") or {}).items())


def ballot_rows(skel: dict, districts: dict):
    """Our current view of this ballot type, top to bottom. Uses the built
    ballot.json so candidate order matches what the page shows."""
    built = json.loads((ROOT / "site" / "data" / "ballot.json").read_text(encoding="utf-8"))
    for section in built["sections"]:
        for c in section["contests"]:
            if not applies(c, districts):
                continue
            title = c["title"] + (f" ({c['subtitle']})" if c.get("subtitle") else "")
            if c["kind"] == "office":
                names = c["candidates"]
                if c.get("order_by_ad") and districts.get("ad"):
                    by = {x["name"]: x for x in names}
                    names = [by[n] for n in c["order_by_ad"][str(districts["ad"])]]
                for cand in names:
                    yield {"id": c["id"], "contest": title, "choice": cand["name"],
                           "designation": cand.get("designation", ""), "party": cand.get("party", "")}
            elif c["kind"] == "retention":
                yield {"id": c["id"], "contest": title, "choice": c["justice"], "designation": "", "party": ""}
            else:
                yield {"id": c["id"], "contest": f"{c['letter']} {c['title']}", "choice": "", "designation": "", "party": ""}


def cmd_template(args) -> None:
    districts = {k: getattr(args, k) for k in ("cd", "ad", "sup", "bart")}
    w = csv.DictWriter(sys.stdout, fieldnames=FIELDS, lineterminator="\n")
    w.writeheader()
    for row in ballot_rows(load_skeleton(), districts):
        w.writerow(row)


def read_csv(path: Path) -> list[dict]:
    with path.open(encoding="utf-8-sig", newline="") as f:
        rows = [{k: (v or "").strip() for k, v in r.items()} for r in csv.DictReader(f)]
    missing = [c for c in ("id", "choice") if rows and c not in rows[0]]
    if missing:
        sys.exit(f"{path}: missing column(s) {missing}; expected {FIELDS}")
    return rows


def cmd_check(args) -> None:
    path = Path(args.csv)
    rows = read_csv(path)
    skel = load_skeleton()
    index = {c["id"]: c for s in skel["sections"] for c in s["contests"]}
    order_seen = []
    by_contest: dict[str, list[dict]] = {}
    problems = 0
    for r in rows:
        if r["id"] not in index:
            print(f"✗ unknown contest id {r['id']!r} (row: {r.get('contest')} / {r['choice']})")
            problems += 1
            continue
        if r["id"] not in by_contest:
            order_seen.append(r["id"])
        by_contest.setdefault(r["id"], []).append(r)

    # Contest order: must follow the skeleton's order.
    skel_order = [cid for cid in index if cid in by_contest]
    if order_seen != skel_order:
        print("✗ contest order differs from the guide:")
        print("    ballot: " + ", ".join(order_seen))
        print("    guide:  " + ", ".join(skel_order))
        problems += 1

    # Guess the ballot type from which district-specific contests appear.
    ballot_type = {}
    for cid in order_seen:
        ballot_type.update(index[cid].get("applies") or {})

    changes = []
    for cid in order_seen:
        c = index[cid]
        if c["kind"] != "office":
            continue
        ours = [x["name"] for x in c["candidates"]]
        theirs = [r["choice"] for r in by_contest[cid]]
        if c.get("order") in ("statewide", "sos_alphabet"):
            ours_ordered = ours_in_built_order(cid, ballot_type)
        else:
            ours_ordered = ours
        if theirs == ours_ordered:
            print(f"✓ {cid}: list and order match")
            changes.append((c, by_contest[cid]))     # still record it as verified
            continue
        problems += 1
        added = [n for n in theirs if n not in ours]
        dropped = [n for n in ours if n not in theirs]
        print(f"✗ {cid}:")
        if added:
            print(f"    on ballot, missing from guide: {added}")
        if dropped:
            print(f"    in guide, not on ballot:       {dropped}")
        if not added and not dropped:
            print(f"    order differs\n      ballot: {theirs}\n      guide:  {ours_ordered}")
        changes.append((c, by_contest[cid]))

    print(f"\n{problems} difference(s). Ballot type inferred from contests present: {ballot_type or 'citywide only'}")
    if args.apply and changes:
        apply_changes(skel, changes, ballot_type, path.name)
        SKELETON.write_text(json.dumps(skel, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"marked {len(changes)} office contest(s) verified in {SKELETON.relative_to(ROOT)} "
              f"(corrections applied where they differed); now run tools/build_ballot.py")


def ours_in_built_order(cid: str, ballot_type: dict) -> list[str]:
    built = json.loads((ROOT / "site" / "data" / "ballot.json").read_text(encoding="utf-8"))
    for s in built["sections"]:
        for c in s["contests"]:
            if c["id"] == cid:
                if c.get("order_by_ad") and ballot_type.get("ad"):
                    return c["order_by_ad"][str(ballot_type["ad"])]
                return [x["name"] for x in c["candidates"]]
    return []


def apply_changes(skel: dict, changes, ballot_type: dict, source_name: str) -> None:
    for contest, rows in changes:
        old = {x["name"]: x for x in contest["candidates"]}
        new = []
        for r in rows:
            cand = dict(old.get(r["choice"], {"name": r["choice"]}))
            cand["name"] = r["choice"]
            if r.get("designation"):
                cand["designation"] = r["designation"]
            if r.get("party"):
                cand["party"] = r["party"]
            cand.pop("surname_uncertain", None)
            new.append(cand)
        if contest.get("order") == "statewide" and ballot_type.get("ad"):
            # Rotation: this ballot only tells us its own AD's order.
            contest.setdefault("verified_order_by_ad", {})[str(ballot_type["ad"])] = [c["name"] for c in new]
            known = {c["name"] for c in contest["candidates"]}
            contest["candidates"] += [c for c in new if c["name"] not in known]
        else:
            contest["candidates"] = new
            contest["order"] = "verified"
            contest.pop("local_list", None)
        contest["verified_from"] = {"file": source_name, "ballot_type": ballot_type}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    t = sub.add_parser("template", help="write a pre-filled CSV for a ballot type to stdout")
    for dim in ("cd", "ad", "sup", "bart"):
        t.add_argument(f"--{dim}", type=int)
    c = sub.add_parser("check", help="compare a transcribed sample ballot CSV with the guide")
    c.add_argument("csv")
    c.add_argument("--apply", action="store_true", help="write corrections into data-src/ballot_skeleton.json")
    args = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    {"template": cmd_template, "check": cmd_check}[args.cmd](args)


if __name__ == "__main__":
    main()
