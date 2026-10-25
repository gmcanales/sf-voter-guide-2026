"""Which ballot districts each focus city overlaps (county previews).

    .venv/Scripts/python tools/build_focus_districts.py      (needs shapely)

For every focus city in tools/build_county_ballot.py FOCUS, intersects the city's
official boundary with each district layer and keeps every district covering more
than a sliver of the city, with its share of the city's area. The page uses this
like a ZIP in SF: picking a focus city narrows the district pickers to these
options and auto-selects a district only when the city sits entirely inside it.
Over-including is safe; dropping a real district isn't.

Sources (official, queried live as GeoJSON):
  Cities    U.S. Census Bureau TIGERweb, Incorporated Places (current)
  Congress  CA "AB 604 Congressional Districts as enacted by Proposition 50"
  Assembly  CA "State Assembly Districts 2024 to 2026" (2021 CRC map)
  Senate    CA "State Senate Districts and Membership" (2021 CRC map)
  BART      BART "Board of Directors District 2022"
Writes data-src/counties/focus_districts.json.
"""
import json
import sys
import urllib.parse
from datetime import date
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import make_valid

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_zip_districts import ARCGIS, get_json, to_local, district_num  # noqa: E402
from build_county_ballot import FOCUS, COUNTIES  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data-src" / "counties" / "focus_districts.json"
PLACES = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Places_CouSub_ConCity_SubMCD/MapServer/4"
LAYERS = {
    "cd": (ARCGIS["cd"][0], ARCGIS["cd"][1]),
    "ad": (ARCGIS["ad"][0], ARCGIS["ad"][1]),
    "sd": ("https://services3.arcgis.com/uknczv4rpevve42E/arcgis/rest/services/"
           "CA_State_Senate_Districts_and_Membership/FeatureServer/0", "district"),
    "bart": (ARCGIS["bart"][0], ARCGIS["bart"][1]),
}
SLIVER = 0.005      # ignore overlaps under 0.5% of the city's area (boundary digitising mismatch)


def query(url: str, where: str, fields: str, geom=None) -> list:
    params = {"where": where, "outFields": fields, "returnGeometry": "true", "outSR": "4326", "f": "geojson"}
    if geom is not None:
        minx, miny, maxx, maxy = geom.bounds
        params.update({"geometry": f"{minx},{miny},{maxx},{maxy}", "geometryType": "esriGeometryEnvelope",
                       "inSR": "4326", "spatialRel": "esriSpatialRelIntersects"})
    data = get_json(f"{url}/query?{urllib.parse.urlencode(params)}")
    if "error" in data:
        raise RuntimeError(f"{url}: {data['error']}")
    return [f for f in data["features"] if f.get("geometry")]


def main() -> None:
    out = {"built": date.today().isoformat(), "sources": {
        "cities": "U.S. Census Bureau TIGERweb, Incorporated Places", "cd": ARCGIS["cd"][2], "ad": ARCGIS["ad"][2],
        "sd": "CA State Senate Districts (2021 CRC map), data.ca.gov", "bart": ARCGIS["bart"][2]}, "cities": {}}
    for county, focus in FOCUS.items():
        valid = COUNTIES[county]["districts"]
        for f in focus:
            feats = query(PLACES, f"STATE='06' AND BASENAME='{f['city']}'", "BASENAME,NAME,GEOID")
            if not feats:
                sys.exit(f"no Census place named {f['city']}")
            city = unary_union([make_valid(shape(x["geometry"])) for x in feats])
            city_l = to_local(city)
            res = {}
            for dim, (url, field) in LAYERS.items():
                if dim not in valid:
                    continue                              # e.g. no state Senate race in San Mateo County
                rows = []
                for x in query(url, "1=1", field, city):
                    g = to_local(make_valid(shape(x["geometry"])))
                    share = g.intersection(city_l).area / city_l.area
                    if share > SLIVER:
                        rows.append([district_num(str(x["properties"][field])), round(share, 3)])
                res[dim] = sorted(rows, key=lambda r: -r[1])
            out["cities"].setdefault(county, {})[f["city"]] = res
            print(f"{county:12} {f['city']:20} " + "  ".join(f"{d}:{[r[0] for r in v]}" for d, v in res.items()))
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
