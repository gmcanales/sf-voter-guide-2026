"""Propose Cal-Access committee ids for state-legislative candidates (for review).

    py tools/find_state_committees.py path/to/dbwebexport.zip need.json

need.json: {contest id: [ballot names]} for assembly-N / state-senate-N contests.
Scans Form 460 cover pages for reports ending 2025-01-01 or later and proposes, per
candidate, committees whose filer name contains the candidate's surname and the
office ("ASSEMBLY" / "SENATE"), preferring names that also mention 2026 and the
district number. Prints the proposals with the matching names; a human copies the
right ids into data-src/state_committees.json. Nothing is written automatically.
"""
import json
import re
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from candidate_money_external import tsv, parse_dt, SINCE, surname  # noqa: E402


def main(zip_path: str, need_path: str) -> None:
    need = {k: v for k, v in json.loads(Path(need_path).read_text(encoding="utf-8")).items()
            if k.startswith(("assembly-", "state-senate-"))}
    z = zipfile.ZipFile(zip_path)
    filers = {}
    for r in tsv(z, "CVR_CAMPAIGN_DISCLOSURE_CD"):
        if r.get("FORM_TYPE") != "F460":
            continue
        thru = parse_dt(r.get("THRU_DATE")) or parse_dt(r.get("RPT_DATE"))
        if thru and thru >= SINCE:
            filers.setdefault(r["FILER_ID"], r.get("FILER_NAML", "").upper())
    out = {}
    for cid, names in need.items():
        office = "ASSEMBLY" if cid.startswith("assembly") else "SENATE"
        dist = cid.split("-")[-1]
        for name in names:
            last, first = surname(name)
            hits = []
            for fid, fn in filers.items():
                if re.search(rf"\b{re.escape(last)}\b", fn) and office in fn:
                    score = ("2026" in fn) * 2 + bool(re.search(rf"\b{dist}\b|{dist}(ST|ND|RD|TH)", fn)) + (first in fn)
                    hits.append((score, fid, fn))
            hits.sort(reverse=True)
            out.setdefault(cid, {})[name] = [h[1] for h in hits[:1]] if hits and hits[0][0] >= 2 else []
            print(f"{cid:16} {name:26} -> " + ("; ".join(f"{fid} [{s}] {fn[:70]}" for s, fid, fn in hits[:3]) or "none"))
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    sys.stdout.reconfigure(encoding="utf-8")
    main(sys.argv[1], sys.argv[2])
