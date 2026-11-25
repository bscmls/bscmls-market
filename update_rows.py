"""Pulls 36 months of closed sales + new listings for the 11 BSCMLS service-area counties (Montana only)
from Cotality Trestle and writes rows.json for the Market Overview page."""
import json, os, sys, datetime as dt
from collections import Counter
import requests

BASE = "https://api.cotality.com/trestle"
COUNTIES = ["Beaverhead", "Broadwater", "Deer Lodge", "Gallatin", "Granite", "Jefferson",
            "Madison", "Meagher", "Park", "Silver Bow", "Sweet Grass"]
TYPES = ["sfh", "condo", "th", "mh", "land_struct", "vacant", "c_bldg", "c_condo", "c_land", "biz_lease", "biz_bldg"]
# (PropertyType, PropertySubType) -> our type key. Anything not listed (leases, income property, farm) is skipped.
TYPE_MAP = {
    ("Residential", "SingleFamilyResidence"): "sfh",
    ("Residential", "Condominium"): "condo",
    ("Residential", "Townhouse"): "th",
    ("Residential", "ManufacturedHome"): "mh",
    ("Land", "BuildingLand"): "land_struct",
    ("Land", "ManufacturedOnLand"): "land_struct",
    ("Land", "UnimprovedLand"): "vacant",
    ("Land", "Commercial"): "c_land",
    ("CommercialSale", "Building"): "c_bldg",
    ("CommercialSale", "Condominium"): "c_condo",
    ("CommercialSale", "Business"): "biz_lease",
    ("CommercialSale", "BuildingBusiness"): "biz_bldg",
}

def token():
    r = requests.post(f"{BASE}/oidc/connect/token", data={
        "client_id": os.environ["TRESTLE_CLIENT_ID"],
        "client_secret": os.environ["TRESTLE_CLIENT_SECRET"],
        "grant_type": "client_credentials", "scope": "api"}, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]

def fetch(tok, flt, select):
    url, params, rows = f"{BASE}/odata/Property", {"$filter": flt, "$select": select, "$top": 1000}, []
    while url:
        r = requests.get(url, params=params, headers={"Authorization": f"Bearer {tok}"}, timeout=120)
        r.raise_for_status()
        j = r.json()
        rows += j.get("value", [])
        url, params = j.get("@odata.nextLink"), None
    return rows

def bounds(y, m):
    s = dt.date(y, m, 1)
    return s, dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1)

def month_list(y, m, n=36):
    """The n months ending with (y, m), oldest first."""
    out = []
    for i in range(n - 1, -1, -1):
        yy, mm = y, m - i
        while mm < 1:
            mm += 12; yy -= 1
        out.append((yy, mm))
    return out

def main():
    today = dt.date.today()
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    if len(sys.argv) == 3:
        y, m = int(sys.argv[1]), int(sys.argv[2])
    periods = month_list(y, m)
    county_flt = "(" + " or ".join(f"CountyOrParish eq '{c}'" for c in COUNTIES) + ")"
    base = f"StateOrProvince eq 'MT' and {county_flt}"
    tok = token()
    areas, closed, listed = [], [], Counter()
    def area_idx(a):
        a = a or "Unassigned"
        if a not in areas: areas.append(a)
        return areas.index(a)
    for p, (yy, mm) in enumerate(periods):
        s, e = bounds(yy, mm)
        for r in fetch(tok, f"{base} and StandardStatus eq 'Closed' and CloseDate ge {s} and CloseDate le {e}",
                       "PropertyType,PropertySubType,CountyOrParish,MLSAreaMajor,ClosePrice,ListPrice,DaysOnMarket,LivingArea,BuildingAreaTotal,LotSizeAcres"):
            t = TYPE_MAP.get((r.get("PropertyType"), r.get("PropertySubType")))
            if not t or r.get("CountyOrParish") not in COUNTIES: continue
            closed.append([p, COUNTIES.index(r["CountyOrParish"]), area_idx(r.get("MLSAreaMajor")), TYPES.index(t),
                           r.get("ClosePrice"), r.get("ListPrice"), r.get("DaysOnMarket"),
                           r.get("LivingArea") or r.get("BuildingAreaTotal"), r.get("LotSizeAcres")])
        for r in fetch(tok, f"{base} and ListingContractDate ge {s} and ListingContractDate le {e}",
                       "PropertyType,PropertySubType,CountyOrParish,MLSAreaMajor"):
            t = TYPE_MAP.get((r.get("PropertyType"), r.get("PropertySubType")))
            if not t or r.get("CountyOrParish") not in COUNTIES: continue
            listed[(p, COUNTIES.index(r["CountyOrParish"]), area_idx(r.get("MLSAreaMajor")), TYPES.index(t))] += 1
    data = {"updated": today.isoformat(),
            "periods": [f"{a}-{b:02d}" for a, b in periods],
            "counties": COUNTIES, "areas": areas, "types": TYPES, "closed": closed,
            "listed": [list(k) + [n] for k, n in sorted(listed.items())]}
    with open("rows.json", "w") as f:
        json.dump(data, f, separators=(",", ":"))
    print(f"Wrote rows.json: {len(closed)} closed rows, {sum(listed.values())} new listings, latest month {periods[-1]}")

if __name__ == "__main__":
    main()
