"""Contributions to tracked groups' state PACs, from the Cal-Access bulk export.

    py tools/group_money.py path/to/dbwebexport.zip

Committees per guide are listed in data-src/group_committees.json
({guide id: [Cal-Access filer ids]}). Sums Form 460 Summary line 5 (total
contributions received) for reports covering 2025-01-01 onward, using the
latest filing per period and its latest amendment, the same rules as
tools/candidate_money_external.py. Prints the totals for endorsements.json.
"""
import json
import sys
from collections import defaultdict
from pathlib import Path
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from candidate_money_external import tsv, parse_dt, SINCE  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent


def main(zip_path: str) -> None:
    cfg = json.loads((ROOT / "data-src" / "group_committees.json").read_text(encoding="utf-8"))
    cfg.pop("_about", None)
    want = {str(f): g for g, ids in cfg.items() for f in ids}
    z = zipfile.ZipFile(zip_path)
    f460 = {}
    for r in tsv(z, "CVR_CAMPAIGN_DISCLOSURE_CD"):
        if r.get("FORM_TYPE") != "F460" or r.get("FILER_ID") not in want:
            continue
        thru = parse_dt(r.get("THRU_DATE")) or parse_dt(r.get("RPT_DATE"))
        if not thru or thru < SINCE:
            continue
        fid, amend = r["FILING_ID"], int(r.get("AMEND_ID") or 0)
        if fid not in f460 or amend > f460[fid][3]:
            f460[fid] = (r["FILER_ID"], parse_dt(r.get("FROM_DATE")), thru, amend)
    best = {}
    for fid, (filer, frm, thru, _) in f460.items():
        k = (filer, frm, thru)
        if k not in best or int(fid) > int(best[k]):
            best[k] = fid
    keep = {fid: f460[fid] for fid in best.values()}
    total, thru_max = defaultdict(float), {}
    for r in tsv(z, "SMRY_CD"):
        fid = r.get("FILING_ID")
        if fid in keep and int(r.get("AMEND_ID") or 0) == keep[fid][3] \
                and r.get("FORM_TYPE") == "F460" and r.get("LINE_ITEM") == "5":
            filer, _, thru, _ = keep[fid]
            total[filer] += float(r.get("AMOUNT_A") or 0)
            thru_max[filer] = max(filter(None, [thru_max.get(filer), thru]))
    for g, ids in cfg.items():
        for i in ids:
            i = str(i)
            t = thru_max.get(i)
            print(f"{g:8} filer {i}: ${total[i]:,.0f} contributions since Jan 2025"
                  f"{' (reports through ' + t.strftime('%Y-%m-%d') + ')' if t else ' (no Form 460s in period)'}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
