# Texas RRC Scraper — Documentation

## Overview

Downloads Texas Railroad Commission (RRC) oil and gas production data using automated browser scraping. The system has two phases:

1. **Lease Discovery** — Search for leases across all 13 Texas districts using common name patterns
2. **Production Download** — Download monthly production data for discovered leases (includes built-in enrichment)

```
Phase 1                Phase 2
┌───────────────┐   ┌──────────────────────────┐
│ Lease          │──>│ Production Download      │
│ Discovery      │   │ + Enrichment (built-in)  │
│ (Selenium)     │   │ (multi-threaded)         │
└───────────────┘   └──────────────────────────┘
       │                          │
       ▼                          ▼
  leases_discovered.csv    texas_production_data.csv
```

## Prerequisites

```bash
pip install selenium beautifulsoup4 requests
```

Google Chrome (or Chromium) must be installed. The scraper uses Chrome's built-in WebDriver.

## Quick Start

### 1. Discover Leases

```bash
# Full discovery across all 13 districts (~10-15 hours)
./discover_all_leases.sh

# Resume after interruption (state is saved automatically)
./discover_all_leases.sh

# Clear history and start fresh
./discover_all_leases.sh --clear
```

### 2. Download Production Data

```bash
# Full download for all discovered leases (10 threads by default)
python3 production_downloader.py \
    --leases ./leases_discovered.csv \
    --years 2011-2025 \
    --output-dir ./data

# Downloads are incremental — running again only fetches new months
python3 production_downloader.py \
    --leases ./leases_discovered.csv \
    --years 2011-2026
```

Output: `./data/texas_production_data.csv`

---

## Phase 1: Lease Discovery

### What It Does

The RRC PDQ system requires searching by lease name pattern (minimum 3 characters). There is no "list all leases" endpoint, so the discovery script searches common prefixes (AAA, ABB, ABC, etc.) across all 13 districts to build a complete lease database.

### Running Discovery

#### Shell Script (Recommended)

```bash
# Run full discovery
./discover_all_leases.sh

# Resume from checkpoint
./discover_all_leases.sh

# Start over (deletes checkpoint)
./discover_all_leases.sh --clear
```

The script runs one district at a time, saving `leases_district_XX.csv` per district. If interrupted, partial results are preserved. At the end, it merges all district files into `leases_discovered.csv`.

#### Python Script (Manual Control)

```bash
# Single district, specific patterns
python3 lease_discovery.py \
    --districts 01 \
    --patterns "SMITH,JONES,WILLIAMS" \
    --output ./my_leases.csv

# Multiple districts
python3 lease_discovery.py \
    --districts 01,02,03 \
    --patterns "SMI,SMO,STA,STE" \
    --output ./my_leases.csv

# Test mode (one district, one pattern)
python3 lease_discovery.py \
    --test \
    --districts 01 \
    --patterns SMI

# With state tracking (resumes from checkpoint)
python3 lease_discovery.py \
    --districts 01,02 \
    --patterns "SMITH,JONES,WILLIAMS" \
    --output ./my_leases.csv \
    --state-file ./data/discovery_state.json

# Clear discovery state and redo all searches
python3 lease_discovery.py \
    --districts 01 \
    --patterns SMITH \
    --state-file ./data/discovery_state.json \
    --clear-history
```

### Command-Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--districts` | All 13 districts | Comma-separated district codes (01,02,03,04,05,06,6E,7B,7C,08,8A,09,10) |
| `--patterns` | First 5 patterns | Comma-separated lease name prefixes |
| `--output` | `./leases_discovered.csv` | Output CSV file |
| `--test` | Off | Test mode: one district, one pattern |
| `--state-file` | `./data/discovery_state.json` | File tracking completed searches |
| `--clear-history` | Off | Delete state and redo all searches |

### Discovery State

Progress is saved after each (district, pattern) search completes. On restart, already-completed searches are skipped:

```
Total: 5694 searches, 5690 already done, 4 remaining
```

State file format (`discovery_state.json`):
```json
{
  "01": ["AAA", "ABB", "SMITH", ...],
  "02": ["AAA", "ABB", ...]
}
```

### Output Format

`leases_discovered.csv`:
```csv
lease_number,district,name,well_type
7063,01,SMITH,Oil
162326,01,SMITH,Gas
```

### Texas RRC Districts

| Code | Name | Code | Name |
|------|------|------|------|
| 01 | District 1 | 08 | District 8 |
| 02 | District 2 | 8A | District 8A |
| 03 | District 3 | 09 | District 9 |
| 04 | District 4 | 10 | District 10 |
| 05 | District 5 | 6E | District 6E |
| 06 | District 6 | 7B | District 7B |
| | | 7C | District 7C |

### Estimated Runtime

| Operation | Scope | Time |
|-----------|-------|------|
| Single district, 10 patterns | ~1 district | ~1 minute |
| Full discovery | 13 districts × 438 patterns = 5,694 searches | ~10-15 hours |

---

## Phase 2: Production Download

### What It Does

For each discovered lease, queries the RRC Production Data Query (PDQ) system to retrieve monthly oil and gas production data from January 1993 to present. Downloads run in **10 parallel threads** by default, each with its own browser instance.

### Running the Downloader

```bash
# Full download (10 threads, default)
python3 production_downloader.py \
    --leases ./leases_discovered.csv \
    --years 2011-2025 \
    --output-dir ./data

# Custom thread count
python3 production_downloader.py \
    --leases ./leases_discovered.csv \
    --years 2020-2025 \
    --threads 5

# Test mode (first lease only, single-threaded)
python3 production_downloader.py \
    --leases ./leases_discovered.csv \
    --years 2020-2020 \
    --test
```

### Command-Line Options

| Flag | Default | Description |
|------|---------|-------------|
| `--years` | `2011-2025` | Year range (e.g., `2020-2023`) |
| `--leases` | `./leases_discovered.csv` | CSV file with discovered leases |
| `--output-dir` | `./data` | Output directory for CSV files |
| `--state-file` | `./data/download_state.json` | SQLite database for tracking progress |
| `--test` | Off | Test mode: download first lease only |
| `--no-incremental` | Off | Disable incremental tracking (re-download everything) |
| `--threads` | `10` | Number of concurrent download threads |

### Multi-Threading

The downloader uses `ThreadPoolExecutor` with 10 workers by default:

- Each thread gets its own Chrome browser instance
- Each thread gets its own SQLite connection (WAL mode handles concurrent access)
- CSV writes are lock-protected to prevent interleaving
- Progress is logged every 50 completed leases

If you don't have enough RAM/CPU for 10 browsers, reduce `--threads`. For small lease sets, the overhead of spawning many browsers may make fewer threads faster.

### Incremental Downloads

The downloader remembers what's already been downloaded. Each lease tracks which (year, month) combinations have been retrieved, stored in a SQLite database.

| Run | Command | Result |
|-----|---------|--------|
| First time | `python3 production_downloader.py --years 2020-2023` | Downloads all 48 months |
| Same range | `python3 production_downloader.py --years 2020-2023` | Skips — already have all 48 months |
| Expanded range | `python3 production_downloader.py --years 2020-2024` | Downloads only 2024 (12 months) |
| Next month | `python3 production_downloader.py --years 2011-2026` | Downloads only new months |

Cross-range independence: running `2022-2026` then `2015-2021` works correctly — zero overlap, no duplication.

### Resuming Interrupted Runs

If a run is interrupted (Ctrl+C, crash, timeout), just run the same command again. The state file tracks what was successfully saved, so only missing data will be re-downloaded.

### Download State (SQLite)

State is stored in a SQLite database (`.db` file) for fast random access. The first run on an old `.json` state file will auto-migrate it and create a `.json.bak` backup.

Database schema:
```sql
-- Per-lease metadata (operator, lat/lon, county, etc.)
CREATE TABLE lease_metadata (
    lease_key TEXT PRIMARY KEY,
    county TEXT,
    api_id TEXT,
    operator TEXT,
    operator_no TEXT,
    lat REAL,
    lon REAL
);

-- Month tracking with bitmasks (12 bits = one year)
CREATE TABLE downloaded_months (
    lease_key TEXT,
    year INTEGER,
    month_mask INTEGER,  -- e.g., 0xFFF = all 12 months
    PRIMARY KEY (lease_key, year)
);
```

Month bitmasks are integers where each bit represents a month (bit 0 = Jan, bit 11 = Dec). A fully downloaded year has mask `4095` (0xFFF = 111111111111₂).

Cached metadata keys:
- `_county` — County name (extracted from PDQ)
- `_api_id` — Internal EWA API ID (for GIS/operator lookup)
- `_operator` / `_operator_no` — Current operator name and number
- `_lat` / `_lon` — GPS coordinates (NAD83 datum)

### Output Format

`texas_production_data.csv` columns:

| Column | Description | Example |
|--------|-------------|---------|
| `api_number` | 14-digit Texas API number | `4231116232605` |
| `lease_number` | RRC lease number | `162326` |
| `lease_name` | Lease name | `SMITH` |
| `well_number` | Well number within lease | `5` |
| `district` | RRC district code | `01` |
| `county` | County name | `MCMULLEN` |
| `latitude` | GPS latitude (NAD83) | `28.413687` |
| `longitude` | GPS longitude (NAD83) | `-98.496463` |
| `well_type` | Oil or Gas | `Gas` |
| `operator` | Operating company name | `XTO ENERGY INC.` |
| `operator_no` | Operator number | `945936` |
| `field` | Field name | `A.W.P. (OLMOS)` |
| `field_no` | Field number | `00256500` |
| `date` | Month Year | `Jan 2020` |
| `month` | Month abbreviation | `Jan` |
| `year` | Year | `2020` |
| `gas_production` | Gas production (MCF) | `932.0` |
| `gas_disposition` | Gas disposition (MCF) | `932.0` |
| `oil_condensate_production` | Oil production (BBL) | `0.0` |
| `oil_condensate_disposition` | Oil disposition (BBL) | `0.0` |

### Enrichment (Built-In)

The downloader automatically enriches records with:

1. **Operator name/number** — Extracted from the PDQ production page. If missing, looks up via the EWA Wellbore Query system.
2. **GPS coordinates** — Looked up via the RRC GIS Viewer (`gis.rrc.texas.gov`). Uses the EWA API ID obtained during operator lookup.
3. **County name** — Extracted from the PDQ County Production view, cached to avoid repeated page loads.
4. **API number** — Constructed from state code (42) + county FIPS + lease number + well number.

All enrichment results are cached in the download state, so subsequent runs skip the extra lookups.

### Logging

Dual logging is configured automatically:

| Destination | Level | Purpose |
|-------------|-------|---------|
| **Console** | INFO+ | Clean output for normal monitoring |
| **File** | DEBUG+ | Full detail for debugging hangs |

Log file: `logs/production_downloader.log`
- Automatically appends across runs
- Rotates at 50MB, keeps 5 backups
- Includes Selenium HTTP wire logs (request/response, timeouts)

### Estimated Runtime

| Operation | Scope | 1 thread | 10 threads |
|-----------|-------|----------|------------|
| Single lease, 1 year | 1 lease | ~30 sec | ~30 sec |
| 1,000 leases, 15 years | 1K leases | ~8 hours | ~50 min |
| 100,000 leases, 15 years | 100K leases | ~33 days | ~3 days |

---

## System Architecture

### Data Sources

| System | URL | Purpose | Access Method |
|--------|-----|---------|---------------|
| **PDQ** (Production Data Query) | `webapps.rrc.texas.gov/PDQ/` | Lease search, production data | Selenium (JS session) |
| **EWA** (Expanded Web Access) | `webapps2.rrc.state.tx.us/EWA/` | Wellbore query, operator info, lease details | Selenium (session cookies) |
| **GIS Viewer** | `gis.rrc.texas.gov/GISViewer/` | GPS coordinates for wells | Selenium (JS-rendered) |

### Session Handling

The RRC systems use Java servlet sessions (`JSESSIONID`) embedded in URLs and cookies. Key rules:

- **PDQ**: Use a single Selenium browser session for all interactions. Form submissions must use the exact action URL from the page (includes jsessionid). Sessions timeout after inactivity — detect "Session Timed Out" in page source and recreate the driver.
- **EWA**: Requires session cookies. **Important**: Direct URL navigation to `leaseDetailAction.do` causes "General Exception" errors. You must navigate from the wellbore results page by clicking the API number link.
- **GIS Viewer**: JS-rendered page. Requires `time.sleep(5)` after navigation for the well data to load. May show a "Map feature was not found" alert for wells not mapped — this is automatically dismissed.

### Operator Lookup Flow

```
EWA Wellbore Query                    EWA Lease Detail
┌───────────────────┐   click API    ┌───────────────────┐
│ Search by:        │   ─────────>  │ Parse from HTML:  │
│  - District       │   link         │  Current Operator │
│  - Lease Number   │                │  Number: 945936   │
│  - Schedule: Curr │                │  Name: XTO ENERGY │
└───────────────────┘                │  INC.             │
                                     └───────────────────┘
                                            │
                                            │ cache
                                            ▼
                                     _operator, _operator_no
                                     _api_id
```

### Lat/Lon Lookup Flow

```
EWA API ID (cached)                GIS Viewer Page
┌───────────────────┐              ┌───────────────────┐
│ api_id: 31133330  │────────────>│ Parse from HTML:  │
│ (from operator    │  Selenium    │  GIS LAT (NAD83)  │
│  lookup)          │  GET         │  GIS LONG (NAD83) │
└───────────────────┘              └───────────────────┘
                                           │
                                           ▼
                                    _lat, _lon (cached)
```

### Texas API Number Format

14 digits: `AA` + `CCC` + `LLLLLL` + `WW`

| Part | Digits | Description |
|------|--------|-------------|
| State | 2 | Always `42` for Texas |
| County FIPS | 3 | County code (e.g., McMullen = `311`) |
| Lease | 6 | Lease number, zero-padded |
| Well | 2 | Well number, zero-padded |

Example: `4231116232605` = `42-311-162326-05`

---

## Project Structure

```
rrc-scraper/
├── lease_discovery.py            # Phase 1: Discover leases
├── production_downloader.py      # Phase 2: Multi-threaded download + enrichment
├── discover_all_leases.sh        # Shell wrapper for full discovery
├── data/
│   └── county_bboxes.json        # County bounding boxes (pre-computed)
├── logs/
│   └── production_downloader.log # Debug log (auto-created)
└── .git/
```

## Troubleshooting

### Session Timeouts

The RRC PDQ system uses Java sessions that timeout. The scripts automatically detect this and recreate the browser session. If you see repeated timeouts, try:
- Reducing the number of leases processed per run
- Running year-by-year instead of all years at once
- Reducing `--threads` (fewer concurrent sessions = fewer timeouts)

### "Lease number is invalid"

Some leases discovered via pattern search may not be directly queryable. The script skips these gracefully.

### "No Data Found"

Many leases don't have production in recent years. The script logs these and moves on.

### Browser Driver Issues

The script uses Chrome's built-in WebDriver. If you get driver errors, ensure Chrome is installed and accessible.

### No lat/lon in output

Possible causes:
1. GIS Viewer page failed to load — check for network issues to `gis.rrc.texas.gov`
2. Well doesn't exist in GIS database — some older wells may not have GPS coordinates
3. EWA operator lookup failed — the API ID was not obtained, so GIS lookup couldn't proceed

### EWA "General Exception"

Direct URL navigation to `leaseDetailAction.do` without proper session context causes this error. The scraper avoids this by clicking the API number link from the wellbore results page instead.

### State file corruption

If the SQLite state file becomes corrupted, delete it and re-run. The CSV output file is not affected (it's appended to, not overwritten):

```bash
rm ./data/download_state.db       # Reset production download state
rm ./data/discovery_state.json    # Reset lease discovery state
```

### Debugging hangs

Check `logs/production_downloader.log` for the last INFO/DEBUG line before the hang. The log includes full Selenium HTTP wire logs, so you can see exactly which request stalled.

---

## License

See `LICENSE` file for details.
