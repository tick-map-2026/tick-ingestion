import io
import os
import time
from collections import defaultdict
from pathlib import Path

import pandas as pd
import requests
from dotenv import load_dotenv

DPID = "DP1.10093.001"
OUTDIR = Path("data/raw")
API = "https://data.neonscience.org/api/v0"

STARTDATE = None  # "YYYY-MM" 
ENDDATE = None  
PACKAGE = "basic" 


TABLES = ("tck_fielddata", "tck_taxonomyProcessed")
METADATA = ("variables", "validation", "categoricalCodes")

DELAY = 0.1  
TIMEOUT = 60


def api_get(path, token):
    r = requests.get(
        f"{API}/{path}",
        headers={"X-API-TOKEN": token, "accept": "application/json"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["data"]


def in_range(month):
    if STARTDATE is not None and month < STARTDATE:
        return False
    if ENDDATE is not None and month > ENDDATE:
        return False
    return True


def site_months(token):
    product = api_get(f"products/{DPID}", token)
    for site in product["siteCodes"]:
        for month in site["availableMonths"]:
            if in_range(month):
                yield site["siteCode"], month


def table_of(filename):
    parts = filename.split(".")
    return parts[6] if len(parts) > 6 else ""


def read_csv(url):
    r = requests.get(url, timeout=TIMEOUT)
    r.raise_for_status()
    return pd.read_csv(io.StringIO(r.text))


def main():
    load_dotenv()
    token = os.environ.get("NEON_TOKEN")
    if not token:
        raise SystemExit("NEON_TOKEN not set - see .env")

    targets = list(site_months(token))
    print(f"{len(targets)} site-months, {STARTDATE} to {ENDDATE}")

    collected = defaultdict(list)
    metadata = {}
    failed = []

    for i, (site, month) in enumerate(targets, 1):
        try:
            files = api_get(f"data/{DPID}/{site}/{month}", token)["files"]
        except requests.RequestException as exc:
            print(f"  {site} {month}: {exc}")
            failed.append(f"{site} {month}")
            continue

        for f in files:
            name, table = f["name"], table_of(f["name"])
            if not name.endswith(".csv"):
                continue
            #No need to concatinate metadata
            if table in METADATA and table not in metadata:
                metadata[table] = read_csv(f["url"])
            elif table in TABLES and f".{PACKAGE}." in name:
                collected[table].append(read_csv(f["url"]))

        if i % 25 == 0 or i == len(targets):
            print(f"  [{i}/{len(targets)}] {site} {month}")
        time.sleep(DELAY)

    if failed:
        raise SystemExit(f"{len(failed)} site-months failed: {failed[:5]}")

    OUTDIR.mkdir(parents=True, exist_ok=True)
    for name, parts in {**collected, **metadata}.items():
        df = pd.concat(parts, ignore_index=True) if isinstance(parts, list) else parts
        df.to_csv(OUTDIR / f"{name}.csv", index=False)
        print(f"{name:<28} {len(df):>7} rows")


if __name__ == "__main__":
    main()
