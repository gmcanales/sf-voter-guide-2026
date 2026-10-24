"""Statewide proposition money from the CA Secretary of State's official
"Ballot Measure Contribution Totals" pages.

    py tools/state_money.py

For each proposition: total reported contributions to support/oppose committees
and the committees themselves, as listed by the SoS. Writes site/data/state_money.json
(merged into the Money tab by the page). Multi-measure committees appear under
every measure they name, so amounts can't be summed across props.
"""
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = "https://www.sos.ca.gov/campaign-lobbying/helpful-resources/measure-contributions/2026-ballot-measure-contribution-totals"
UA = {"User-Agent": "Mozilla/5.0 (sf_voter_guide/1.0)"}


def get(url: str) -> str:
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode("utf-8", "replace")


def lines_of(page: str) -> list[str]:
    page = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", page)
    text = html.unescape(re.sub(r"(?i)<br\s*/?>|</(p|div|li|h\d|tr|td|th)>", "\n", page))
    text = re.sub(r"<[^>]+>", " ", text).replace("​", "")
    return [re.sub(r"\s+", " ", l).strip() for l in text.splitlines() if l.strip()]


def parse(page: str) -> dict:
    L = lines_of(page)
    out, side, asof = {}, None, None
    i = 0
    while i < len(L):
        l = L[i]
        if re.match(r"(?i)in support of this measure", l):
            side = "support"
        elif re.match(r"(?i)in opposition to this measure", l):
            side = "oppose"
        m = re.search(r"Total amount of reported contributions to this measure: \$([\d,]+)", l)
        if m and side:
            out[side] = {"total": int(m.group(1).replace(",", "")), "committees": []}
        # Committee rows: an ID line, a name line, then a $ amount line.
        if side in out and re.fullmatch(r"\d{6,8}", l) and i + 2 < len(L) and L[i + 2].startswith("$"):
            out[side]["committees"].append({"id": l, "name": L[i + 1],
                                            "total": int(re.sub(r"[^\d]", "", L[i + 2]))})
            i += 3
            continue
        a = re.search(r"Through (\d{1,2}/\d{1,2}/\d{4})", l)
        if a:
            asof = a.group(1)
        i += 1
    out["as_of"] = asof
    return out


def main() -> None:
    idx = get(INDEX)
    urls = sorted(set(re.findall(r'href="([^"]*2026-ballot-measure-contribution-totals/proposition-\d+[^"]*)"', idx)))
    props = {}
    for u in urls:
        if u.startswith("/"):
            u = "https://www.sos.ca.gov" + u
        n = re.search(r"proposition-(\d+)", u).group(1)
        rec = parse(get(u))
        rec["url"] = u
        props[f"prop-{n}"] = rec
        s, o = rec.get("support", {}).get("total"), rec.get("oppose", {}).get("total")
        print(f"prop-{n:3} support {('$' + format(s, ',')) if s else '—':>14}  oppose {('$' + format(o, ',')) if o else '—':>14}  "
              f"({len(rec.get('support', {}).get('committees', []))}/{len(rec.get('oppose', {}).get('committees', []))} committees, through {rec['as_of']})")
    out = {"built": date.today().isoformat(),
           "source": {"label": "CA Secretary of State: 2026 Ballot Measure Contribution Totals", "url": INDEX},
           "props": props}
    dest = ROOT / "site" / "data" / "state_money.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {dest.relative_to(ROOT)}")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
