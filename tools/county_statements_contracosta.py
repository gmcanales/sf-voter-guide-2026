"""Contra Costa candidate statements, verbatim from the county's contest pages.

    py tools/county_statements_contracosta.py

The Elections Division publishes every contest's candidate statements on a page
linked from its election data (the `href` in each office name returned by the
election API used in tools/county_contracosta.py). Each candidate block is a bold
NAME, the ballot designation, then the statement's paragraphs. This keeps them
verbatim: they are the candidates' own words, and the page labels them so.
Statements are optional, so candidates without one are simply absent.

Writes data-src/counties/contracosta/statements.json:
  {contest title: {ballot name: {designation, website, paragraphs, source}}}
"""
import html
import json
import re
import sys
import time
import unicodedata
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import redact  # noqa: E402  (needs the sys.path line above)
from county_contracosta import jsonp, API, EID, UA  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data-src" / "counties" / "contracosta" / "statements.json"


def fold(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def get_html(url: str) -> str:
    resp = urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=60)
    raw = resp.read()
    charset = resp.headers.get_content_charset() or "utf-8"
    try:
        return raw.decode(charset)
    except UnicodeDecodeError:
        return raw.decode("cp1252")


def text(fragment: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def parse(page: str) -> list[dict]:
    body = page.split('class="entry-content"', 1)[-1].split("</article>", 1)[0]
    parts = re.split(r"<strong>(.*?)</strong>", body, flags=re.S)
    out = []
    for i in range(1, len(parts) - 1, 2):
        name = text(parts[i])
        if not name or name != name.upper():
            continue                                   # bold text inside a statement, not a name
        chunk = parts[i + 1].split("</td>", 1)[0]
        # Pages separate paragraphs with </p><p> or with <br />&nbsp;<br />; some omit the
        # designation, which otherwise sits on the line right after the name.
        has_designation = re.match(r"\s*<br\s*/?>\s*[^&<\s]", chunk) is not None
        paras = [text(p) for p in re.split(r"</p>|<p[^>]*>|<br\s*/?>", chunk)]
        paras = [p for p in paras if p]
        if not paras:
            continue
        # Other pages put it in its own first paragraph: a short line with no closing period.
        if not has_designation and len(paras) > 1 and len(paras[0]) <= 70 and not paras[0].endswith((".", "!", "?", "”", '"')):
            has_designation = True
        designation, rest = (paras[0], paras[1:]) if has_designation else ("", paras)
        website = rest.pop(0) if rest and re.fullmatch(r"(https?://)?(www\.)?[\w.-]+\.\w{2,}(/\S*)?", rest[0], re.I) else ""
        out.append({"name": name, "designation": designation, "website": website, "paragraphs": rest})
    return out


def ballot_name(name: str, ballot: list[str]) -> str | None:
    """Match a statement's NAME to the ballot list. The two lists are typed separately
    by the county and disagree on hyphens ("PABON ALVARADO" / "Pabon-Alvarado"),
    nicknames (Steve / Steven) and spelling (Stacey / Stacy; the ballot list has
    "Watson-Alavarado"). Accept a shared surname part plus either the same first-name
    stem or being the only candidate with that surname part."""
    def parts(s):
        w = re.sub(r"[.\"()]", " ", fold(s)).split()
        return (w[0] if w else ""), set(re.split(r"-", w[-1])) | set(w[1:]) if w else set()
    f_first, f_sur = parts(name)
    hits = [c for c in ballot if parts(c)[1] & f_sur]
    for c in hits:
        if parts(c)[0][:3] == f_first[:3]:
            return c
    return hits[0] if len(hits) == 1 else None


def main() -> None:
    e = jsonp(f"{API}getElection?eid={EID}&lang=en-US&callback=cb")
    contests = {c["title"].lower(): c for c in json.loads(
        (ROOT / "data-src" / "counties" / "contracosta" / "contests.json").read_text(encoding="utf-8"))}
    out, missing = {}, []
    for level, groups in e["offices"].items():
        for group, offices in groups.items():
            for o in offices:
                m = re.search(r'href\s*=\s*"([^"]+)"', o["name"])
                title = text(o["name"])
                if not (m and o["hasCand"]):
                    continue
                url = m.group(1).strip()
                c = contests.get(title.lower())
                if not c:
                    missing.append(title); continue
                ballot = [x["name"] for x in c["candidates"]]
                for st in parse(get_html(url)):
                    bn = ballot_name(st["name"], ballot)
                    if not bn:
                        print(f"  ? {title}: statement name {st['name']!r} not matched to {ballot}")
                        continue
                    out.setdefault(c["title"], {})[bn] = {"designation": st["designation"], "website": st["website"],
                                                          "paragraphs": st["paragraphs"], "source": url}
                time.sleep(0.3)
    # Candidates often sign off with a personal address; drop those before
    # anything reaches disk. See tools/redact.py for why.
    n_mail = redact.count(out)
    out = redact.redact(out)
    if n_mail:
        print(f"  redacted {n_mail} contact email(s) from statements")
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    n = sum(len(v) for v in out.values())
    print(f"wrote {OUT.relative_to(ROOT)}: {n} statements in {len(out)} contests")
    if missing:
        print("  pages with no matching contest:", missing)


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
