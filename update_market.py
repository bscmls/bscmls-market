"""Pulls monthly market stats from Cotality Trestle and writes data.json."""
import json, os, statistics, sys, datetime as dt
import requests

BASE = "https://api.cotality.com/trestle"
AREA = "Big Sky Country MLS"
CONDO = {"Condominium", "Townhouse"}

def token():
    r = requests.post(f"{BASE}/oidc/connect/token", data={
        "client_id": os.environ["TRESTLE_CLIENT_ID"],
        "client_secret": os.environ["TRESTLE_CLIENT_SECRET"],
        "grant_type": "client_credentials", "scope": "api"}, timeout=60)
    r.raise_for_status()
    return r.json()["access_token"]

def fetch(tok, flt, select):
    url = f"{BASE}/odata/Property"
    params = {"$filter": flt, "$select": select, "$top": 1000}
    rows = []
    while url:
        r = requests.get(url, params=params, headers={"Authorization": f"Bearer {tok}"}, timeout=120)
        r.raise_for_status()
        j = r.json()
        rows += j.get("value", [])
        url, params = j.get("@odata.nextLink"), None
    return rows

def month_bounds(y, m):
    start = dt.date(y, m, 1)
    end = (dt.date(y + (m == 12), m % 12 + 1, 1) - dt.timedelta(days=1))
    return start, end

def med(xs):
    return statistics.median(xs) if xs else None

def stats(tok, y, m):
    s, e = month_bounds(y, m)
    closed = fetch(tok,
        f"StandardStatus eq 'Closed' and PropertyType eq 'Residential' and CloseDate ge {s} and CloseDate le {e}",
        "PropertySubType,ClosePrice,ListPrice,DaysOnMarket,LivingArea")
    listed = fetch(tok,
        f"PropertyType eq 'Residential' and ListingContractDate ge {s} and ListingContractDate le {e}",
        "PropertySubType")
    out = {}
    for key, match in (("sfh", lambda t: t == "SingleFamilyResidence"), ("condo", lambda t: t in CONDO)):
        c = [r for r in closed if match(r.get("PropertySubType"))]
        n = sum(1 for r in listed if match(r.get("PropertySubType")))
        prices = [r["ClosePrice"] for r in c if r.get("ClosePrice")]
        doms = [r["DaysOnMarket"] for r in c if r.get("DaysOnMarket") is not None and r["DaysOnMarket"] >= 0]
        ratios = [r["ClosePrice"] / r["ListPrice"] * 100 for r in c if r.get("ClosePrice") and r.get("ListPrice")]
        sf = [(r["ClosePrice"], r["LivingArea"]) for r in c if r.get("ClosePrice") and r.get("LivingArea")]
        ppsf = sum(p for p, _ in sf) / sum(a for _, a in sf) if sf else None
        out[key] = {"closed": len(c), "price": med(prices), "dom": med(doms),
                    "newl": n, "ratio": med(ratios), "ppsf": ppsf}
    return out

def main():
    today = dt.date.today()
    y, m = (today.year, today.month - 1) if today.month > 1 else (today.year - 1, 12)
    if len(sys.argv) == 3:                      # optional: python update_market.py 2026 10
        y, m = int(sys.argv[1]), int(sys.argv[2])
    py, pm = (y, m - 1) if m > 1 else (y - 1, 12)
    periods = [(y, m), (py, pm), (y - 1, m)]
    tok = token()
    res = [stats(tok, *p) for p in periods]
    data = {
        "area": AREA,
        "periods": [dt.date(a, b, 1).strftime("%B %Y") for a, b in periods],
        "asOf": f"Source: {AREA}. Updated {today:%b %d, %Y}. Closed sales by close date; new listings by listing contract date.",
    }
    for key in ("sfh", "condo"):
        data[key] = {k: [r[key][k] for r in res] for k in ("closed", "price", "dom", "newl", "ratio", "ppsf")}
    with open("data.json", "w") as f:
        json.dump(data, f, indent=2)
    print("Wrote data.json for", data["periods"][0])

if __name__ == "__main__":
    main()
