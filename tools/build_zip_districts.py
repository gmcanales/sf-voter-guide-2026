"""Compute which ballot districts each San Francisco ZIP code overlaps.

Writes site/data/zip_districts.json, which the page uses to narrow the
district pickers from a ZIP code. ZIPs don't follow district lines, so for
each ZIP we keep EVERY district it overlaps (above a sliver threshold) with
its share of the ZIP's in-SF area. The page only auto-selects a district when
the ZIP sits entirely inside it, and otherwise asks the reader to choose among
the overlapping ones. Over-including is safe; dropping a real district isn't.

    .venv/Scripts/python tools/build_zip_districts.py      (needs shapely, see tools/requirements.txt)

Sources (all official, queried live as GeoJSON):
  ZIPs        U.S. Census Bureau 2020 ZCTAs (TIGERweb)
  Supervisor  DataSF "Supervisor Districts (2022)"
  Assembly    CA "State Assembly Districts 2024 to 2026" (2021 Citizens Redistricting Commission map)
  Congress    CA "AB 604 Congressional Districts as enacted by Proposition 50"
  BART        BART "Board of Directors District 2022"
"""
import json
import math
import urllib.parse
import urllib.request
from datetime import date
from pathlib import Path

from shapely.geometry import shape
from shapely.ops import unary_union
from shapely.validation import make_valid

OUT = Path(__file__).resolve().parent.parent / "site" / "data" / "zip_districts.json"

# Rough SF county bounding box (lon/lat) — just to keep the queries small.
BBOX = (-122.62, 37.69, -122.33, 37.84)
SLIVER = 0.002          # ignore overlaps under 0.2% of a ZIP's in-SF area (digitising mismatch)
MIN_ZIP_IN_SF = 0.02    # skip ZCTAs with under 2% of their area inside SF

ARCGIS = {
    "zip":  ("https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/PUMA_TAD_TAZ_UGA_ZCTA/MapServer/4",
             "ZCTA5", "U.S. Census Bureau, 2020 ZIP Code Tabulation Areas (TIGERweb)"),
    "cd":   ("https://services3.arcgis.com/uknczv4rpevve42E/arcgis/rest/services/"
             "AB_604_-_California_Congressional_Districts_2027-2032_as_enacted_by_Proposition_50_view/FeatureServer/0",
             "DISTRICT", "CA AB 604 Congressional Districts (Proposition 50), data.ca.gov"),
    "ad":   ("https://services3.arcgis.com/uknczv4rpevve42E/arcgis/rest/services/"
             "CA_State_Assembly_Districts_and_Memberships_2024_to_2026/FeatureServer/5",
             "DISTRICT", "CA State Assembly Districts 2024–2026 (2021 CRC map), data.ca.gov"),
    "bart": ("https://services.arcgis.com/sqS7RNuF1BQinj5N/arcgis/rest/services/"
             "Board_of_Directors_District_Boundary_Viewer_Base_Data_WFL1/FeatureServer/2",
             "District", "BART Board of Directors Districts (2022), BART"),
}
SUP_URL = "https://data.sf.gov/resource/f2zs-jevy.geojson?$limit=50"
SUP_LABEL = "DataSF, Supervisor Districts (2022)"


def get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "sf_voter_guide/1.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def arcgis_features(url: str, field: str) -> list[tuple[str, object]]:
    params = {
        "where": "1=1", "outFields": field, "returnGeometry": "true", "outSR": "4326", "f": "geojson",
        "geometry": ",".join(map(str, BBOX)), "geometryType": "esriGeometryEnvelope",
        "inSR": "4326", "spatialRel": "esriSpatialRelIntersects",
    }
    data = get_json(f"{url}/query?{urllib.parse.urlencode(params)}")
    if "error" in data:
        raise RuntimeError(f"{url}: {data['error']}")
    return [(str(f["properties"][field]).strip(), make_valid(shape(f["geometry"])))
            for f in data["features"] if f.get("geometry")]


def to_local(geom):
    """Project lon/lat to an equirectangular plane at SF's latitude so areas
    compare fairly (only ratios are used, so this is plenty accurate)."""
    from shapely.ops import transform
    k = math.cos(math.radians(37.76))
    return transform(lambda x, y, z=None: (x * k, y), geom)


def district_num(raw: str) -> int:
    return int(float("".join(ch for ch in raw if ch.isdigit() or ch == ".")))


def main() -> None:
    sup = [(str(f["properties"]["sup_dist"]), make_valid(shape(f["geometry"])))
           for f in get_json(SUP_URL)["features"]]
    sf = unary_union([g for _, g in sup])        # SF's land area, per the City's own district map
    layers = {"sup": sup}
    for dim in ("cd", "ad", "bart"):
        url, field, _ = ARCGIS[dim]
        layers[dim] = arcgis_features(url, field)
    zips = arcgis_features(*ARCGIS["zip"][:2])

    sf_l = to_local(sf)
    proj = {dim: [(district_num(n), to_local(g)) for n, g in feats] for dim, feats in layers.items()}
    out = {}
    for z, geom in sorted(zips):
        zg = to_local(geom)
        in_sf = zg.intersection(sf_l)
        if zg.area == 0 or in_sf.area / zg.area < MIN_ZIP_IN_SF:
            continue
        rec = {"in_sf": round(in_sf.area / zg.area, 3)}
        for dim, feats in proj.items():
            shares = []
            for n, dg in feats:
                s = in_sf.intersection(dg).area / in_sf.area
                if s >= SLIVER:
                    shares.append([n, round(s, 3)])
            rec[dim] = sorted(shares, key=lambda t: -t[1])
        out[z] = rec

    payload = {
        "_about": "Per SF ZIP: share of its in-SF area falling in each district ([district, share]). "
                  "Built by tools/build_zip_districts.py; overlaps under "
                  f"{SLIVER:.1%} are dropped as boundary-digitising slivers.",
        "built": date.today().isoformat(),
        "sources": [ARCGIS[k][2] for k in ("zip", "cd", "ad", "bart")] + [SUP_LABEL],
        "zips": out,
    }
    OUT.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {OUT.name}: {len(out)} ZIPs")
    for z, r in out.items():
        print(z, f"inSF={r['in_sf']}", *(f"{d}={r[d]}" for d in ("cd", "ad", "sup", "bart")))


if __name__ == "__main__":
    main()
