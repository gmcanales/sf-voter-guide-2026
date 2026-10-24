"""Extract local measure facts from the SF Voter Information Pamphlet (VIP).

Reads the official pamphlet PDF and writes data-src/vip_measures.json: for each
measure, the ballot question, vote threshold, Ballot Simplification Council
digest (The Way It Is Now / The Proposal / YES means / NO means), the
Controller's statement (first paragraph) and "How X Got on the Ballot". All
text is verbatim from the pamphlet so it can be cited as Tier-1.

    py tools/extract_vip.py path/to/N26_EN_VIP.pdf

Requires `pdftotext` (poppler) on PATH. The digest page numbers below are the
PRINTED page numbers from the pamphlet's table of contents; PDF_OFFSET maps
them to PDF page indices.
"""
import json
import re
import subprocess
import sys
from pathlib import Path

PDF_OFFSET = 2  # printed page N is PDF page N + 2 (cover + inside cover)

# measure key -> printed page where its digest / impartial analysis starts
DIGEST_PAGES = {
    "RTM": 52, "A": 64, "B": 70, "C": 78, "D": 84, "E": 94,
    "F": 100, "G": 108, "H": 124, "I": 132, "J": 144,
}

SOURCE = {
    "label": "SF Voter Information Pamphlet, Nov 3 2026 (Dept. of Elections)",
    "url": "https://media.api.sf.gov/documents/N26_EN_VIP.pdf",
}

# Page furniture that pdftotext interleaves with the body text.
NOISE = [
    re.compile(r"^\d*\s*Local Ballot Measures – Proposition [A-Z]+\s*\d*$"),
    re.compile(r"^\d*\s*Regional Measure RTM\s*\d*$"),
    re.compile(r"^38-EN-N26-CP\d+$"),
    re.compile(r"^(YES|NO|YES NO)$"),
    re.compile(r"^The above statement is an impartial analysis"),
    re.compile(r"^Map provided by"),
]


def page_text(pdf: Path, printed_page: int, n_pages: int = 2) -> str:
    first = printed_page + PDF_OFFSET
    out = subprocess.run(
        ["pdftotext", "-enc", "UTF-8", "-f", str(first), "-l", str(first + n_pages - 1), str(pdf), "-"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")
    # The typesetter mixes straight and curly apostrophes ("Controller's" on D,
    # "Controller’s" elsewhere); normalise so section markers match.
    out = out.replace("'", "’")
    lines = [ln.strip() for ln in out.splitlines()]
    return "\n".join(ln for ln in lines if ln and not any(p.search(ln) for p in NOISE))


def between(text: str, start: str, ends: list[str]) -> str | None:
    """Text after `start` up to the earliest of `ends`, whitespace-normalised."""
    i = text.find(start)
    if i < 0:
        return None
    i += len(start)
    stops = [j for e in ends if (j := text.find(e, i)) >= 0]
    chunk = text[i:min(stops)] if stops else text[i:]
    return clean(chunk)


def clean(s: str) -> str:
    s = re.sub(r"[ \t]*\n[ \t]*", "\n", s.strip())
    # Re-join soft-wrapped lines but keep bullet items on their own lines.
    s = re.sub(r"\n(?!•)", " ", s)
    s = re.sub(r"\s*•\s*", "\n• ", s)
    return re.sub(r" {2,}", " ", s).strip()


def extract_local(key: str, text: str) -> dict:
    title_m = re.search(rf"^{key} – (.+)$", text, re.M)
    question_m = re.search(r"^(Shall .+?\?)$", text, re.M | re.S)
    threshold_m = re.search(r"This measure requires (.+?) affirmative votes to pass", text)
    yes_marker, no_marker = "A “YES” Vote Means:", "A “NO” Vote Means:"
    controller_hdr = f"Controller’s Statement on “{key}”"
    how_hdr = f"How “{key}” Got on the Ballot"
    controller = between(text, controller_hdr, [how_hdr, "Note that the proposed"])
    # Keep only the headline opinion paragraph ("Should the proposed ... would ...").
    if controller:
        m = re.search(r"(Should the proposed.+?\.)\s", controller + " ")
        controller = m.group(1) if m else controller
    return {
        "letter": key,
        "title": title_m.group(1).strip() if title_m else None,
        "question": clean(question_m.group(1)) if question_m else None,
        "threshold": threshold_m.group(1) if threshold_m else None,
        "way_it_is_now": between(text, "The Way It Is Now:", ["The Proposal:"]),
        "proposal": between(text, "The Proposal:", [yes_marker, controller_hdr]),
        "yes_means": between(text, yes_marker, [no_marker]),
        "no_means": between(text, no_marker, [controller_hdr, how_hdr]),
        "fiscal": controller,
        "how_placed": between(text, how_hdr, ["Arguments for and against", "The full text"]),
        "vip_page": DIGEST_PAGES[key],
    }


def extract_regional(key: str, text: str) -> dict:
    q_start = text.find("To prevent")
    q_end = text.find("be adopted?")
    return {
        "letter": key,
        "title": "Regional Transit Measure",
        "question": clean(text[q_start:q_end + len("be adopted?")]) if q_start >= 0 else None,
        "threshold": "50%+1 of all votes cast in the five Bay Area counties",
        "analysis": between(text, "Impartial Analysis of Regional Transit Measure",
                            ["A “yes” vote is"]),
        "yes_means": between(text, "A “yes” vote is", ["A “no” vote is"]),
        "no_means": between(text, "A “no” vote is", ["/s/"]),
        "how_placed": between(text, f"How “{key}” Got on the Ballot", ["The full text"]),
        "vip_page": DIGEST_PAGES[key],
    }


def main(pdf_path: str) -> None:
    pdf = Path(pdf_path)
    out = {"source": SOURCE, "measures": {}}
    for key, page in DIGEST_PAGES.items():
        text = page_text(pdf, page)
        rec = extract_regional(key, text) if key == "RTM" else extract_local(key, text)
        missing = [k for k, v in rec.items() if v is None]
        if missing:
            print(f"warning: {key} missing {missing}", file=sys.stderr)
        out["measures"][key] = rec
    dest = Path(__file__).resolve().parent.parent / "data-src" / "vip_measures.json"
    dest.parent.mkdir(exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {dest} ({len(out['measures'])} measures)")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
