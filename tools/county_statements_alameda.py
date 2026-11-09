"""Alameda candidate statements, verbatim from the county's Voter Information Guide PDF.

    py tools/county_statements_alameda.py path/to/vig_nov2026_eng.pdf [first_page last_page]

The county posts statements only in its Voter Information Guide
(acvote.alamedacountyca.gov ... vig_nov2026_eng.pdf). Much of that 3,500-page PDF has a
broken text layer, but the candidate-statement pages (632-757 in the Nov 2026 edition)
have a clean one. Many pages set two candidates side by side in justified columns, and
plain text extraction interleaves those columns line by line (justification collapses the
gutter to one space), so the text is rebuilt from word coordinates (poppler's
`pdftotext -bbox`): words are grouped into lines, a line splits where a real gap crosses
the middle of the page, and each two-column stretch reads left column then right.
Poppler runs locally when it supports -bbox, otherwise in a throwaway container of the
congress_trader backend image (as tools/ocr_pdf.py does); nothing is sent anywhere.

Two layouts:
  * "Candidate's Statement <JURISDICTION> <OFFICE>", then per candidate
    "NAME Occupation: ... My education and qualifications are: <statement>".
  * Berkeley and Oakland's charter declarations, one candidate per page:
    "I, NAME, hereby declare ...", numbered items. Only the occupation item and the
    statement item are kept (Oakland item 5, Berkeley item 9); Berkeley's items also
    list the candidate's home address and birthplace, which are never copied.

Matching to ballot names (site/data/counties/alameda/ballot.json) needs a shared
surname plus the first name or a common nickname; a surname-only match is accepted only
inside the contest the page header names, so same-surname candidates in other races
never pick up each other's statements. Writes data-src/counties/alameda/statements.json:
  {contest title: {ballot name: {designation, website, paragraphs, source}}}
"""
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redact  # noqa: E402  (needs the sys.path line above)
from local_candidate_money import NICK  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data-src" / "counties" / "alameda" / "statements.json"
URL = ("https://acvote.alamedacountyca.gov/acvote-assets/02_election_information/PDFs/20261103/"
       "Voter%20Information%20Guide/vig_nov2026_eng.pdf")
PAGES = (632, 757)
IMAGE = "congress_trader-backend:latest"
FOOTER = re.compile(r"^\s*(\d{1,3}|[A-Z0-9]{2,8}-\d{1,2})\s*$")      # page number, "FCC2-1"
WEBSITE = re.compile(r"\s((?:https?://)?(?:www\.)?[\w-]+(?:\.[\w-]+)*\.(?:com|org|net|us|vote|info|co)(?:/\S*)?)\s*$", re.I)
GUTTER = 8.0          # points of empty space that separate two columns
PAGE_CODE = re.compile(r"\s[A-Z]{2,8}\d-\d{1,2}(?=\s|$)")              # "LCC2-1", "LVJUSDG2-1"
# "NAME [Age: N] My education ..." for a candidate with no occupation line.
NO_OCC = re.compile(r"\s([A-ZÀ-ÖØ-Þ][A-ZÀ-ÖØ-Þ.,'’\"“”() -]{3,}?)\s+(?:Age:?\s*(\d*)\s*)?(?=My education and qualifications are:)")


# ── text from word coordinates ────────────────────────────────────────────────
def bbox_html(pdf: str, first: int, last: int) -> str:
    args = ["-bbox", "-f", str(first), "-l", str(last)]
    local = shutil.which("pdftotext")
    if local:
        r = subprocess.run([local, *args, pdf, "-"], capture_output=True)
        if r.returncode == 0 and b"<word" in r.stdout:
            return r.stdout.decode("utf-8", "replace")
    folder, name = os.path.split(os.path.abspath(pdf))
    with tempfile.TemporaryDirectory(dir=folder) as tmp:
        out = f"{os.path.basename(tmp)}/bbox.html"
        subprocess.run(["docker", "run", "--rm", "-v", f"{folder}:/w", IMAGE, "pdftotext", *args,
                        f"/w/{name}", f"/w/{out}"], check=True, env={**os.environ, "MSYS_NO_PATHCONV": "1"})
        return Path(folder, out).read_text(encoding="utf-8")


def pages_from_bbox(doc: str, first: int) -> dict[int, str]:
    out = {}
    for i, (width, body) in enumerate(re.findall(r'<page width="([\d.]+)"[^>]*>(.*?)</page>', doc, re.S)):
        words = [(float(a), float(b), float(c), float(d), html.unescape(w)) for a, b, c, d, w in re.findall(
            r'<word xMin="([\d.]+)" yMin="([\d.]+)" xMax="([\d.]+)" yMax="([\d.]+)">(.*?)</word>', body)]
        out[first + i] = layout_text(words, float(width))
    return out


def layout_text(words: list, width: float) -> str:
    words.sort(key=lambda w: (round(w[1]), w[0]))
    lines = []                                       # [(y, [words])]
    for w in words:
        if lines and abs(lines[-1][0] - w[1]) < 2.5:
            lines[-1][1].append(w)
        else:
            lines.append((w[1], [w]))
    mid = width / 2
    out, left, right = [], [], []

    def flush():
        out.extend(left); out.extend(right); left.clear(); right.clear()

    for _, ws in lines:
        ws.sort(key=lambda w: w[0])
        split = next((k for k in range(1, len(ws))
                      if ws[k][0] - ws[k - 1][2] >= GUTTER and ws[k - 1][2] < mid + 40 and ws[k][0] > mid - 40), None)
        text = lambda seq: " ".join(w[4] for w in seq)
        if split is not None:
            left.append(text(ws[:split])); right.append(text(ws[split:]))
        elif ws[-1][2] < mid + 10 and (left or right):
            left.append(text(ws))                    # a short line inside the left column
        elif ws[0][0] > mid - 10 and (left or right):
            right.append(text(ws))
        else:
            flush(); out.append(text(ws))
    flush()
    t = unicodedata.normalize("NFKC", "\n".join(out))          # ﬁ, ﬂ ligatures
    lines = t.rstrip().splitlines()
    while lines and (not lines[-1].strip() or FOOTER.match(lines[-1])):
        lines.pop()
    return "\n".join(lines)


def flat(s: str) -> str:
    s = re.sub(r"(\w)-\n(\w)", r"\1-\2", s)                   # a word split across lines
    return re.sub(r"\s+", " ", s).strip()


def split_website(text: str) -> tuple[str, str]:
    m = WEBSITE.search(text)
    return (text[:m.start()].strip(), m.group(1)) if m else (text, "")


# ── the two statement layouts ─────────────────────────────────────────────────
def parse_standard(t: str) -> tuple[str, list[dict]]:
    """Each candidate is a NAME line followed by an "Occupation:" line."""
    lines = [l for l in t.splitlines() if l.strip()]
    occ = [i for i, l in enumerate(lines) if l.lstrip().startswith("Occupation:") and i > 0]
    if not occ:
        return "", []
    header = " ".join(lines[:occ[0] - 1]).replace("Candidate’s Statement", "").replace("Candidate's Statement", "")
    out = []
    for k, i in enumerate(occ):
        end = occ[k + 1] - 1 if k + 1 < len(occ) else len(lines)
        chunk = PAGE_CODE.sub(" ", flat("\n".join(lines[i:end]))[len("Occupation:"):])
        # Candidates without an occupation line start with just "NAME [Age: N] My education ...";
        # look for them only after this candidate's own "My education ..." line.
        own = chunk.find("My education and qualifications are:")
        cuts = [m for m in NO_OCC.finditer(chunk) if own >= 0 and m.start() > own]
        entries, prev, prev_name = [], 0, flat(lines[i - 1])
        for m in cuts:
            entries.append((prev_name, chunk[prev:m.start()]))
            prev, prev_name = m.end(), flat(m.group(1))
        entries.append((prev_name, chunk[prev:]))
        for name, text in entries:
            designation, _, statement = text.partition("My education and qualifications are:")
            if not statement:
                designation, statement = "", text
            designation = re.sub(r"\s*Age:?\s*\d*\s*$", "", flat(designation))
            statement, website = split_website(flat(statement))
            out.append({"name": name, "designation": designation, "website": website,
                        "paragraphs": [statement] if statement else []})
    return flat(header), out


def parse_declaration(t: str) -> tuple[str, list[dict]]:
    body = flat(t)
    head = body.split(" I, ", 1)[0] if " I, " in body else ""
    name = re.search(r"\bI, (.+?), hereby declare", body)
    if not name:
        return head, []
    occ = (re.search(r"\b3\. My occupation for the past 5 years:\s*(.+?)\s+4\.", body)
           or re.search(r"\b5\. My present occupation is\s*(.+?)\s+6\.", body))
    stmt = (re.search(r"\b5\. Statement of General Qualifications:\s*(.+?)\s+6\. The signatures", body)
            or re.search(r"\b8\. I am a taxpayer[^.]*\.\s*9\.\s*(.+?)\s+10\. I refer", body))
    statement, website = split_website(stmt.group(1)) if stmt else ("", "")
    return head, [{"name": name.group(1), "designation": occ.group(1) if occ else "", "website": website,
                   "paragraphs": [statement] if statement else []}]


# ── matching to the ballot ────────────────────────────────────────────────────
def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def name_parts(name: str) -> tuple[set, set, str]:
    """(surname parts, first-name stems incl. nicknames, folded full name)."""
    name = re.sub(r",?\s+(PHD|PH\.D\.|MD|M\.D\.|MBA|ESQ\.?|DDS|JR\.?|SR\.?|III|II)$", "", name.strip(), flags=re.I)
    nick = re.findall(r"[\"“(]([^\"”)]+)[\"”)]", name)
    w = re.sub(r"[\"“”().,]", " ", fold(re.sub(r"[\"“(][^\"”)]+[\"”)]", " ", name))).split()
    if not w:
        return set(), set(), ""
    stem = lambda x: NICK.get(x, x)[:3]
    firsts = {stem(w[0])} | {stem(fold(n).split()[0]) for n in nick if n.strip()}
    return set(re.split(r"-", w[-1])), firsts, " ".join(w)


def header_score(header: str, title: str) -> int:
    generic = {"for", "of", "the", "member", "members", "city", "district", "board", "director", "directors", "area"}
    h = set(re.findall(r"[a-z]+|\d+", fold(header))) - generic
    return len(h & (set(re.findall(r"[a-z]+|\d+", fold(title))) - generic))


def pick_contest(stmt_name: str, header: str, contests: list) -> tuple[dict, str] | None:
    sur, firsts, _ = name_parts(stmt_name)
    strong, weak = [], []
    for c in contests:
        for x in c["candidates"]:
            csur, cfirsts, _ = name_parts(x["name"])
            if not sur & csur:
                continue
            (strong if firsts & cfirsts else weak).append((c, x["name"]))
    if strong:
        return max(strong, key=lambda cb: header_score(header, cb[0]["title"]))
    # Surname only (spelling differences): only inside the contest the header names.
    best = max((header_score(header, c["title"]) for c, _ in weak), default=0)
    near = [cb for cb in weak if header_score(header, cb[0]["title"]) == best and best >= 2]
    return near[0] if len(near) == 1 else None


def main(pdf: str, first: int, last: int) -> None:
    ballot = json.loads((ROOT / "site" / "data" / "counties" / "alameda" / "ballot.json").read_text(encoding="utf-8"))
    contests = [c for s in ballot["sections"] for c in s["contests"] if c.get("candidates")]
    out, unmatched, n, seen = {}, [], 0, {}
    for p, t in pages_from_bbox(bbox_html(pdf, first, last), first).items():
        if re.match(r"\s*Candidate.s Statement", t):
            header, stmts = parse_standard(t)
        elif "hereby declare" in t:
            header, stmts = parse_declaration(t)
        else:
            continue
        for st in stmts:
            if not st["paragraphs"]:
                continue
            hit = pick_contest(st["name"], header, contests)
            if not hit:
                unmatched.append(f"p{p} {st['name']} ({header[:70]})")
                continue
            c, bn = hit
            key = (c["title"], bn)
            if key in seen:
                if out[c["title"]][bn]["paragraphs"] == st["paragraphs"]:
                    continue                          # the guide prints some pages twice
                print(f"  ! {bn} ({c['title']}) matched twice: p{seen[key]} and p{p}; kept the first")
                continue
            seen[key] = p
            out.setdefault(c["title"], {})[bn] = {k: st[k] for k in ("designation", "website", "paragraphs")} | {
                "source": f"{URL}#page={p}"}
            n += 1
    # Candidates often sign off with a personal address; drop those before
    # anything reaches disk. See tools/redact.py for why.
    n_mail = redact.count(out)
    out = redact.redact(out)
    if n_mail:
        print(f"  redacted {n_mail} contact email(s) from statements")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: {n} statements in {len(out)} contests")
    for u in unmatched:
        print("  ? not matched to the ballot list:", u)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) not in (2, 4):
        sys.exit(__doc__)
    main(sys.argv[1], *(map(int, sys.argv[2:4]) if len(sys.argv) == 4 else PAGES))
