"""Extract statewide proposition facts from the CA Secretary of State's
Official Voter Information Guide (voterguide.sos.ca.gov).

Writes data-src/sos_props.json: per proposition, the official title, how it
got on the ballot, the summary, fiscal impact, listed supporters/opponents,
"What your vote means" (YES/NO) and the short PRO/CON ballot arguments from
the Quick Reference Guide. All text is verbatim from the state guide.

    py tools/extract_sos_props.py            # fetch live pages
    py tools/extract_sos_props.py DIR        # parse saved pDIR/p<N>.html files
"""
import html
import json
import re
import sys
import urllib.request
from datetime import date
from pathlib import Path

PROPS = [1, 2, 3, 4, 5, 37, 38, 39, 40, 41, 42, 43, 44, 45]
URL = "https://voterguide.sos.ca.gov/propositions/{n}/"

# Section headers as they appear (one per line) once tags are stripped.
HEADERS = ["SUMMARY", "WHAT YOUR VOTE MEANS", "ARGUMENTS", "FOR ADDITIONAL INFORMATION"]


def fetch(n: int) -> str:
    req = urllib.request.Request(URL.format(n=n), headers={"User-Agent": "sf_voter_guide/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def to_lines(page: str) -> list[str]:
    text = re.sub(r"<[^>]+>", "\n", page)
    # The site entity-encodes punctuation, sometimes without the trailing ';'.
    text = re.sub(r"&#(\d+)(?!\d|;)", r"&#\1;", text)
    text = html.unescape(text).replace("\xa0", " ")
    return [ln.strip() for ln in text.splitlines() if ln.strip()]


def after(lines: list[str], label: str) -> str | None:
    """The line(s) following a label line, joined, until the next known label.
    Labels appear both with and without a trailing colon ("Fiscal Impact:")."""
    key = lambda ln: ln.rstrip(":").strip()
    stop = set(HEADERS) | {"YES", "NO", "PRO", "CON", "FOR", "AGAINST", "Fiscal Impact",
                           "Supporters", "Opponents"}
    try:
        i = next(j for j, ln in enumerate(lines) if key(ln) == key(label)) + 1
    except StopIteration:
        return None
    out = []
    while i < len(lines) and key(lines[i]) not in stop:
        out.append(lines[i])
        i += 1
    return " ".join(out).lstrip(": ").strip() or None


SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on", "or", "that", "the", "to", "unless"}


def title_case(s: str) -> str:
    """'INCREASES STATE’S RAINY DAY FUND' -> 'Increases State’s Rainy Day Fund'."""
    words = s.lower().split()
    out = [w if (i and w in SMALL) else w[:1].upper() + w[1:] for i, w in enumerate(words)]
    return " ".join(out).replace(". ", ". ")


def parse(n: int, page: str) -> dict:
    lines = to_lines(page)
    # Title line follows "PROP" / "<n>" at the top of the content.
    title_line = next(lines[i + 2] for i in range(len(lines) - 2)
                      if lines[i] == "PROP" and lines[i + 1] == str(n))
    m = re.match(r"(.+?)\.\s+((?:LEGISLATIVE|INITIATIVE|REFERENDUM)[A-Z ,]*)\.?$", title_line)
    title, kind = (m.group(1), title_case(m.group(2))) if m else (title_line, None)
    s = lines.index("SUMMARY")
    placed_by, summary = lines[s + 1], lines[s + 2]
    yes = after(lines, "YES")
    no = after(lines, "NO")
    strip_lead = lambda t: re.sub(r"^A (YES|NO) vote on this measure means:\s*", "", t or "") or None
    return {
        "number": n,
        "title": title_case(title) if title.isupper() else title,
        "title_official": title,
        "type": kind,
        "placed_by": placed_by,
        "summary": summary,
        "fiscal": after(lines, "Fiscal Impact"),
        "supporters": after(lines, "Supporters"),
        "opponents": after(lines, "Opponents"),
        "yes_means": strip_lead(yes),
        "no_means": strip_lead(no),
        "argument_pro": after(lines, "PRO"),
        "argument_con": after(lines, "CON"),
        "url": URL.format(n=n),
    }


def main(saved_dir: str | None) -> None:
    out = {
        "source": {"label": "CA Official Voter Information Guide, Nov 3 2026 (Secretary of State)",
                   "url": "https://voterguide.sos.ca.gov/"},
        "accessed": date.today().isoformat(),
        "props": {},
    }
    for n in PROPS:
        page = (Path(saved_dir) / f"p{n}.html").read_text(encoding="utf-8") if saved_dir else fetch(n)
        rec = parse(n, page)
        missing = [k for k, v in rec.items() if v is None]
        if missing:
            print(f"warning: prop {n} missing {missing}", file=sys.stderr)
        out["props"][str(n)] = rec
    dest = Path(__file__).resolve().parent.parent / "data-src" / "sos_props.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {dest} ({len(out['props'])} props)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else None)
