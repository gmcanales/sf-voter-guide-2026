"""ZIP-code lookup data for the county previews (Alameda, San Mateo, Contra Costa).

    .venv/Scripts/python tools/build_county_zips.py      (needs shapely)

Like tools/build_zip_districts.py does for SF: for each Census ZIP area (ZCTA)
overlapping the county, clip it to the county and record every district,
city and K-12 school district it overlaps, with its share of the ZIP's
in-county area. The page narrows the pickers from a ZIP, auto-selects only
when the ZIP sits entirely inside one district, and hides school races whose
district the ZIP doesn't touch. Over-including is safe; dropping a real
district isn't.

Sources (official, queried live as GeoJSON):
  ZIPs, counties, cities,  U.S. Census Bureau TIGERweb (2020 ZCTAs; current
  school districts         counties, incorporated places, unified /
                           secondary / elementary school districts)
  Congress / Assembly /    CA data.ca.gov layers (Prop 50; 2021 CRC maps)
  Senate, BART             BART Board of Directors districts (2022)
Writes site/data/counties/<county>/zip_districts.json and
site/data/zip_counties.json (ZIP -> counties, so a reader on the wrong
county's page can be pointed to the right one).
"""
import json
import sys
from datetime import date
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import make_valid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_zip_districts import ARCGIS, to_local, district_num  # noqa: E402
from build_focus_districts import LAYERS, PLACES, query  # noqa: E402
from build_county_ballot import COUNTIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
FIPS = {"alameda": "001", "sanmateo": "081", "contracosta": "013"}
COUNTY_LAYER = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/State_County/MapServer/1"
SCHOOL_LAYERS = [f"https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/School/MapServer/{i}" for i in (0, 1, 2)]
SLIVER = 0.005          # ignore overlaps under 0.5% of a ZIP's in-county area
MIN_ZIP_IN_COUNTY = 0.02


def overlaps(zg, feats, key):
    rows = []
    for k, g in feats:
        share = zg.intersection(g).area / zg.area
        if share > SLIVER:
            rows.append([key(k), round(share, 3)])
    return sorted(rows, key=lambda r: -r[1])


def main() -> None:
    zip_counties = {}
    for county, fips in FIPS.items():
        cfg = COUNTIES[county]
        cty = unary_union([make_valid(shape(f["geometry"]))
                           for f in query(COUNTY_LAYER, f"STATE='06' AND COUNTY='{fips}'", "NAME")])
        cty_l = to_local(cty)
        layers = {}
        for dim, (url, field) in LAYERS.items():
            if dim in cfg["districts"]:
                layers[dim] = [(str(f["properties"][field]), to_local(make_valid(shape(f["geometry"]))))
                               for f in query(url, "1=1", field, cty)]
        places = [(f["properties"]["BASENAME"], to_local(make_valid(shape(f["geometry"]))))
                  for f in query(PLACES, "STATE='06'", "BASENAME", cty)
                  if f["properties"]["BASENAME"] in cfg["cities"]]
        schools = [(f["properties"]["NAME"], to_local(make_valid(shape(f["geometry"]))))
                   for url in SCHOOL_LAYERS for f in query(url, "STATE='06'", "NAME", cty)]
        zips = query(ARCGIS["zip"][0], "1=1", ARCGIS["zip"][1], cty)
        out = {}
        for f in sorted(zips, key=lambda f: f["properties"][ARCGIS["zip"][1]]):
            z = str(f["properties"][ARCGIS["zip"][1]])
            zg_full = to_local(make_valid(shape(f["geometry"])))
            zg = zg_full.intersection(cty_l)
            in_county = zg.area / zg_full.area if zg_full.area else 0
            if in_county < MIN_ZIP_IN_COUNTY or zg.is_empty:
                continue
            zip_counties.setdefault(z, []).append([county, round(in_county, 3)])
            rec = {"in_county": round(in_county, 3)}
            for dim, feats in layers.items():
                rows = overlaps(zg, feats, district_num)
                # Districts with no race here fold into "Another district" (0) where offered.
                opts = cfg["districts"][dim]["options"]
                agg = {}
                for n, s in rows:
                    v = n if n in opts else (0 if 0 in opts else None)
                    if v is not None:
                        agg[v] = round(agg.get(v, 0) + s, 3)
                rec[dim] = sorted(([k, v] for k, v in agg.items()), key=lambda r: -r[1])
            city_rows = overlaps(zg, places, lambda n: cfg["cities"].index(n) + 1)
            rest = round(1 - sum(s for _, s in city_rows), 3)
            if rest > SLIVER:
                city_rows.append([0, rest])                # unincorporated area
            rec["city"] = city_rows
            rec["schools"] = [n for n, _ in overlaps(zg, schools, str)]
            out[z] = rec
        dest = ROOT / "site" / "data" / "counties" / county / "zip_districts.json"
        dest.write_text(json.dumps({
            "_about": "Per ZIP (Census ZCTA), the districts, cities (index into the city picker; 0 = unincorporated) "
                      "and K-12 school districts it overlaps, with shares of its in-county area. Built by "
                      "tools/build_county_zips.py.",
            "built": date.today().isoformat(),
            "sources": ["U.S. Census Bureau TIGERweb: 2020 ZCTAs, counties, incorporated places, school districts",
                        ARCGIS["cd"][2], ARCGIS["ad"][2], "CA State Senate Districts (2021 CRC map), data.ca.gov",
                        ARCGIS["bart"][2]],
            "zips": out}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"{county}: {len(out)} ZIPs -> {dest.relative_to(ROOT)}")
    # SF ZIPs too, so a reader on a county page who types an SF ZIP gets pointed home.
    sf = json.loads((ROOT / "site" / "data" / "zip_districts.json").read_text(encoding="utf-8"))
    for z, rec in sf["zips"].items():
        zip_counties.setdefault(z, []).append(["sf", rec.get("in_sf", 1.0)])
    for z in zip_counties:
        zip_counties[z].sort(key=lambda r: -r[1])
    (ROOT / "site" / "data" / "zip_counties.json").write_text(
        json.dumps({"built": date.today().isoformat(), "zips": zip_counties}, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"zip_counties: {len(zip_counties)} ZIPs")


if __name__ == "__main__":
    main()
