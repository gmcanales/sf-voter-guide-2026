"""Build site/data/ballot.json from the curated skeleton and the official extracts.

    py tools/build_ballot.py

Inputs (all in data-src/):
  ballot_skeleton.json  sections, contest order, candidates, district applicability
  vip_measures.json     SF local + regional measure facts (tools/extract_vip.py)
  sos_props.json        state proposition facts (tools/extract_sos_props.py)

Candidate order is computed from the Secretary of State's randomized alphabet
(Elections Code §13112: compare surnames letter by letter in the drawn order).
Statewide offices also rotate by Assembly District (§13111: AD 1 uses the drawn
order and each later AD moves the top name to the bottom), so SF's two ADs can
see different orders. Every computed order carries an `order_note`. Nothing
here reproduces the official sample ballot, so the page always points voters
to it.
"""
import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data-src"
OUT = ROOT / "site" / "data" / "ballot.json"

ORDER_NOTES = {
    "statewide": "Order computed from the Secretary of State's randomized alphabet with "
                 "statewide rotation by Assembly District.",
    "sos_alphabet": "Order computed from the Secretary of State's randomized alphabet. "
                    "Confirm on your sample ballot.",
    "county_draw": "Order set by a county drawing we haven't verified yet. Check your sample ballot.",
    "verified": "List and order checked against an official sample ballot.",
}
LOCAL_LIST_NOTE = ("Candidate list taken from statements in the official pamphlet. Statements are "
                   "voluntary, so candidates who didn't submit one may be missing. Your sample "
                   "ballot has the complete list.")


def load(name: str) -> dict:
    return json.loads((SRC / name).read_text(encoding="utf-8"))


def alpha_key(alphabet: str):
    rank = {ch: i for i, ch in enumerate(alphabet)}

    def word_key(s: str) -> list[int]:
        # Letters only; accents folded so "Joaquín" sorts as "JOAQUIN".
        folded = s.upper().translate(str.maketrans("ÁÉÍÓÚÑÜ", "AEIOUNU"))
        return [rank[c] for c in folded if c in rank]

    def key(cand: dict):
        given = cand["name"].replace(cand["surname"], " ")
        return (word_key(cand["surname"]), word_key(given))
    return key


def ballot_type_label(bt: dict) -> str:
    names = {"cd": "Congressional District", "ad": "Assembly District",
             "sup": "Supervisor District", "bart": "BART District"}
    return ", ".join(f"{names[k]} {v}" for k, v in bt.items() if k in names)


def order_candidates(contest: dict, key, ad_options: list[int]) -> None:
    rule = contest.get("order")
    cands = contest.get("candidates")
    if not cands or rule not in ORDER_NOTES:
        return
    if rule in ("statewide", "sos_alphabet"):
        cands.sort(key=key)
    contest["order_note"] = ORDER_NOTES[rule]
    vf = contest.get("verified_from")
    if rule == "verified" and vf and vf.get("ballot_type"):
        contest["order_note"] = ORDER_NOTES[rule].rstrip(".") + f" ({ballot_type_label(vf['ballot_type'])})."
    if any(c.get("surname_uncertain") for c in cands):
        contest["order_note"] += " (One surname is ambiguous, so its position is uncertain.)"
    if rule == "statewide" and len(cands) > 1:
        by_ad = {}
        for ad in ad_options:
            shift = (ad - 1) % len(cands)
            by_ad[str(ad)] = [c["name"] for c in cands[shift:] + cands[:shift]]
        # A transcribed sample ballot (tools/sample_ballot.py) beats the computation.
        verified = contest.pop("verified_order_by_ad", {})
        by_ad.update(verified)
        if verified:
            ads = ", ".join(f"AD {a}" for a in sorted(verified))
            contest["order_note"] += f" Checked against an official sample ballot for {ads}."
        if len({tuple(v) for v in by_ad.values()}) > 1:
            contest["order_by_ad"] = by_ad
    contest.pop("verified_from", None)
    for c in cands:
        c.pop("surname", None)
        c.pop("surname_uncertain", None)


def merge_local_measure(contest: dict, m: dict, vip_source: dict) -> None:
    contest.update({
        "question": m.get("question"),
        "threshold": m.get("threshold"),
        "way_it_is_now": m.get("way_it_is_now"),
        "proposal": m.get("proposal") or m.get("analysis"),
        "yes_means": m.get("yes_means"),
        "no_means": m.get("no_means"),
        "fiscal": m.get("fiscal"),
        "how_placed": m.get("how_placed"),
    })
    contest["sources"] = [{
        "id": "VIP", "label": f"{vip_source['label']}, p. {m['vip_page']}",
        "url": f"{vip_source['url']}#page={m['vip_page'] + 2}",
    }]


def merge_state_prop(contest: dict, p: dict, accessed: str) -> None:
    contest.update({
        "type": p.get("type"),
        "placed_by": p.get("placed_by"),
        "summary": p.get("summary"),
        "fiscal": p.get("fiscal"),
        "yes_means": p.get("yes_means"),
        "no_means": p.get("no_means"),
        "official_args": {"for": p.get("argument_pro"), "against": p.get("argument_con")},
        "listed_supporters": p.get("supporters"),
        "listed_opponents": p.get("opponents"),
    })
    contest["sources"] = [{
        "id": "VIG", "label": f"CA Official Voter Information Guide — Prop {p['number']}",
        "url": p["url"], "accessed": accessed,
    }]


def main() -> None:
    skel = load("ballot_skeleton.json")
    vip = load("vip_measures.json")
    sos = load("sos_props.json")
    key = alpha_key(skel["randomized_alphabet"]["letters"])
    ad_options = skel["districts"]["ad"]["options"]
    problems = []

    for section in skel["sections"]:
        for c in section["contests"]:
            if c["kind"] == "office":
                order_candidates(c, key, ad_options)
                if c.pop("local_list", False):
                    c["list_note"] = LOCAL_LIST_NOTE
            elif c["kind"] == "measure":
                if c["level"] == "state":
                    p = sos["props"].get(c["letter"])
                    if not p:
                        problems.append(f"{c['id']}: not in sos_props.json")
                        continue
                    merge_state_prop(c, p, sos["accessed"])
                else:
                    m = vip["measures"].get(c["letter"])
                    if not m:
                        problems.append(f"{c['id']}: not in vip_measures.json")
                        continue
                    if m.get("title") and re.sub(r"\W", "", m["title"]) != re.sub(r"\W", "", c["title"]) \
                            and c["level"] == "city":
                        problems.append(f"{c['id']}: skeleton title differs from VIP digest title "
                                        f"({m['title']!r})")
                    merge_local_measure(c, m, vip["source"])

    out = {
        "election": skel["election"],
        "built": date.today().isoformat(),
        "randomized_alphabet": skel["randomized_alphabet"],
        "districts": skel["districts"],
        "sections": skel["sections"],
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(s["contests"]) for s in skel["sections"])
    print(f"wrote {OUT.relative_to(ROOT)}: {len(skel['sections'])} sections, {n} contests")
    for p in problems:
        print("warning:", p, file=sys.stderr)


if __name__ == "__main__":
    main()
