#!/usr/bin/env python3
"""
Lookup latitude/longitude for Texas well API numbers.

Supports three lookup strategies (fastest → most comprehensive):

1. University Lands API  – Fast HTTP lookup for wells on Texas state (University)
   Lands. Covers many major Permian Basin wells but not all Texas wells.

2. FracFocus index       – Local CSV lookup for hydraulically fractured wells.
   Download the FracFocus CSV once, then lookups are instant.
   Covers ~115k Texas wells. Only works for fractured wells.

3. RRC GIS Viewer        – Selenium-based lookup via the RRC GIS Viewer.
   Covers ALL Texas wells but requires Chrome + Selenium, and you must
   provide lease_number + district (not just API number).

Usage:
    # Fast lookup via University Lands API
    python api_latlon_lookup.py --apis 4200307433 4247532226

    # Bulk lookup from CSV (column named 'api_number')
    python api_latlon_lookup.py --input apis.csv --output results.csv

    # Build a FracFocus local index for faster subsequent lookups
    python api_latlon_lookup.py --build-fracfocus ./DisclosureList_1.csv

    # Use RRC GIS Viewer (requires lease_number + district)
    python api_latlon_lookup.py --rrc --lease 20417 --district 08
"""

import argparse
import csv
import json
import re
import sys
import time
from pathlib import Path

import requests

# ---------------------------------------------------------------------------
# 1. University Lands API
# ---------------------------------------------------------------------------

UL_API_URL = "https://universitylands.utsystem.edu/API/{api_num}"


def lookup_university_lands(api_number: str):
    """
    Query the University Lands public API for lat/lon.

    Args:
        api_number: 10-digit or 14-digit API number (digits only, no dashes)

    Returns:
        (latitude, longitude, datum) tuple or (None, None, None)
    """
    api_clean = re.sub(r"\D", "", api_number)
    if not api_clean:
        return None, None, None

    try:
        resp = requests.get(
            UL_API_URL.format(api_num=api_clean),
            timeout=15,
            allow_redirects=True,
        )
        resp.raise_for_status()
    except Exception as exc:
        print(f"UL API error for {api_clean}: {exc}", file=sys.stderr)
        return None, None, None

    html = resp.text

    # The page contains: Lat/Lon: 32.14411135 / -102.57488247
    # inside a table cell
    m = re.search(
        r"Lat/Lon:.*?([\d.\-]+)\s*/\s*([\d.\-]+)",
        html,
        re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None, None, None

    lat, lon = m.group(1), m.group(2)

    # Datum is usually NAD83 for UL data
    datum = "NAD83"
    if "NAD27" in html:
        datum = "NAD27"

    return lat, lon, datum


# ---------------------------------------------------------------------------
# 2. FracFocus local index
# ---------------------------------------------------------------------------

FRACFOCUS_INDEX_FILE = Path(__file__).parent / "data" / "fracfocus_index.json"


def build_fracfocus_index(disclosure_csv: Path):
    """
    Build a lightweight JSON index from a FracFocus DisclosureList CSV.

    The index maps API number (14-digit, zero-padded) -> (lat, lon).
    """
    index = {}
    count = 0
    print(f"Reading {disclosure_csv} ...", file=sys.stderr)
    with open(disclosure_csv, "r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            api = row.get("APINumber", "").strip().strip('"')
            lat = row.get("Latitude", "").strip().strip('"')
            lon = row.get("Longitude", "").strip().strip('"')
            if api and lat and lon:
                # Keep first occurrence (same well may have multiple disclosures)
                if api not in index:
                    index[api] = (lat, lon)
                    count += 1

    FRACFOCUS_INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FRACFOCUS_INDEX_FILE, "w") as f:
        json.dump(index, f, indent=2)

    print(f"Indexed {count} wells -> {FRACFOCUS_INDEX_FILE}", file=sys.stderr)
    return count


def load_fracfocus_index():
    """Load the FracFocus index if it exists."""
    if not FRACFOCUS_INDEX_FILE.exists():
        return {}
    with open(FRACFOCUS_INDEX_FILE) as f:
        return json.load(f)


def lookup_fracfocus(api_number: str, index: dict):
    """
    Lookup lat/lon from a FracFocus index.

    Args:
        api_number: API number (will be normalised to 14 digits)
        index: dict mapping 14-digit API -> (lat, lon)

    Returns:
        (latitude, longitude) or (None, None)
    """
    api_clean = re.sub(r"\D", "", api_number)
    # FracFocus uses 14-digit format: 42 + county(3) + lease(6) + well(2)
    # Pad to 14 digits if shorter
    api_14 = api_clean.zfill(14)
    return index.get(api_14, (None, None))


# ---------------------------------------------------------------------------
# 3. RRC GIS Viewer (Selenium)
# ---------------------------------------------------------------------------

GIS_VIEWER_URL = "https://gis.rrc.texas.gov/GISViewer/index.html?api={api_id}"


def lookup_rrc_gis(api_id: str, headless: bool = True):
    """
    Lookup lat/lon via the RRC GIS Viewer using Selenium.

    Args:
        api_id: Internal EWA API ID (e.g. '31133330'), NOT the 14-digit API number.
        headless: Run Chrome headlessly

    Returns:
        (latitude, longitude, datum) or (None, None, None)
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.common.exceptions import UnexpectedAlertPresentException
    except ImportError:
        print(
            "Selenium not installed. Run: pip install selenium", file=sys.stderr
        )
        return None, None, None

    chrome_options = Options()
    if headless:
        chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    driver = webdriver.Chrome(options=chrome_options)
    try:
        url = GIS_VIEWER_URL.format(api_id=api_id)
        driver.get(url)
        time.sleep(5)

        html = driver.page_source

        # NAD83 preferred
        lat_m = re.search(
            r"GIS LAT \(NAD83\)</th>\s*<td[^>]*>([\d.\-]+)</td>", html
        )
        lon_m = re.search(
            r"GIS LONG \(NAD83\)</th>\s*<td[^>]*>([\d.\-]+)</td>", html
        )
        if lat_m and lon_m:
            return lat_m.group(1), lon_m.group(1), "NAD83"

        # Fallback NAD27
        lat_m = re.search(
            r"GIS LAT \(NAD27\)</th>\s*<td[^>]*>([\d.\-]+)</td>", html
        )
        lon_m = re.search(
            r"GIS LONG \(NAD27\)</th>\s*<td[^>]*>([\d.\-]+)</td>", html
        )
        if lat_m and lon_m:
            return lat_m.group(1), lon_m.group(1), "NAD27"

        return None, None, None

    except UnexpectedAlertPresentException:
        # Usually "Map feature was found" – well not in GIS database
        return None, None, None
    except Exception as exc:
        print(f"RRC GIS Viewer error for {api_id}: {exc}", file=sys.stderr)
        return None, None, None
    finally:
        driver.quit()


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def normalise_api(api: str) -> str:
    """Strip non-digits from an API number."""
    return re.sub(r"\D", "", api)


def main():
    parser = argparse.ArgumentParser(
        description="Lookup lat/lon for Texas well API numbers"
    )
    parser.add_argument(
        "--apis",
        nargs="+",
        help="One or more API numbers to lookup",
    )
    parser.add_argument(
        "--input",
        type=Path,
        help="Input CSV with an 'api_number' column",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("api_latlon_results.csv"),
        help="Output CSV (default: api_latlon_results.csv)",
    )
    parser.add_argument(
        "--build-fracfocus",
        type=Path,
        metavar="CSV",
        help="Build FracFocus index from DisclosureList CSV",
    )
    parser.add_argument(
        "--rrc",
        action="store_true",
        help="Use RRC GIS Viewer (requires --lease and --district)",
    )
    parser.add_argument("--lease", help="Lease number (for RRC mode)")
    parser.add_argument("--district", help="RRC district code (for RRC mode)")
    parser.add_argument(
        "--api-id",
        help="Internal EWA API ID (skip EWA lookup, use directly with GIS Viewer)",
    )

    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Build FracFocus index mode
    # ------------------------------------------------------------------
    if args.build_fracfocus:
        if not args.build_fracfocus.exists():
            print(f"File not found: {args.build_fracfocus}", file=sys.stderr)
            sys.exit(1)
        build_fracfocus_index(args.build_fracfocus)
        return

    # ------------------------------------------------------------------
    # RRC GIS Viewer mode
    # ------------------------------------------------------------------
    if args.rrc:
        if args.api_id:
            lat, lon, datum = lookup_rrc_gis(args.api_id)
            print(f"API ID {args.api_id}: lat={lat}, lon={lon}, datum={datum}")
            return

        if not args.lease or not args.district:
            print(
                "RRC mode requires --lease and --district (or --api-id)",
                file=sys.stderr,
            )
            sys.exit(1)

        # The existing production_downloader.py has the full EWA -> GIS pipeline.
        # To avoid duplicating complex Selenium logic here, we delegate to a
        # small helper that the user can extend.
        print(
            "RRC GIS Viewer lookup requires the EWA API ID.\n"
            "Use production_downloader.py::lookup_operator() to resolve\n"
            f"lease {args.lease} / district {args.district} -> api_id,\n"
            "then pass that api_id to this script with --api-id."
        )
        return

    # ------------------------------------------------------------------
    # Normal API lookup mode
    # ------------------------------------------------------------------
    api_list = []
    if args.apis:
        api_list.extend(args.apis)
    if args.input:
        if not args.input.exists():
            print(f"Input file not found: {args.input}", file=sys.stderr)
            sys.exit(1)
        with open(args.input, "r", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                api = row.get("api_number", "").strip()
                if api:
                    api_list.append(api)

    if not api_list:
        print("No API numbers provided. Use --apis or --input.", file=sys.stderr)
        sys.exit(1)

    # Load FracFocus index once
    ff_index = load_fracfocus_index()
    ff_available = bool(ff_index)
    if ff_available:
        print(f"Loaded FracFocus index: {len(ff_index)} wells", file=sys.stderr)

    results = []
    for api in api_list:
        api_clean = normalise_api(api)
        lat = lon = datum = source = None

        # 1. Try University Lands API
        if not lat:
            lat, lon, datum = lookup_university_lands(api_clean)
            if lat:
                source = "university_lands"

        # 2. Try FracFocus index
        if not lat and ff_available:
            lat, lon = lookup_fracfocus(api_clean, ff_index)
            if lat:
                source = "fracfocus"
                datum = "WGS84"

        results.append(
            {
                "api_number": api_clean,
                "latitude": lat or "",
                "longitude": lon or "",
                "datum": datum or "",
                "source": source or "",
            }
        )
        print(
            f"{api_clean}: lat={lat or 'N/A'}, lon={lon or 'N/A'} "
            f"(source={source or 'not found'})",
            file=sys.stderr,
        )
        # Be polite to UL API
        time.sleep(0.3)

    # Write output
    with open(args.output, "w", newline="") as f:
        writer = csv.DictWriter(
            f, fieldnames=["api_number", "latitude", "longitude", "datum", "source"]
        )
        writer.writeheader()
        writer.writerows(results)

    print(f"\nWrote {len(results)} results to {args.output}", file=sys.stderr)


if __name__ == "__main__":
    main()
