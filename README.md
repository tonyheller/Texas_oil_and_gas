# Texas RRC Scraper

Tools for discovering and downloading Texas Railroad Commission (RRC) oil and gas production data.

## Quick Start

```bash
# Install dependencies
pip install selenium beautifulsoup4 requests

# 1. Discover all leases (~10-15 hours)
./discover_all_leases.sh

# 2. Download production data (10 threads by default)
python3 production_downloader.py \
    --leases ./leases_discovered.csv \
    --years 2011-2025 \
    --output-dir ./data
```

## Scripts

| Script | Purpose |
|--------|---------|
| `discover_all_leases.sh` | Full lease discovery across all 13 Texas districts |
| `lease_discovery.py` | Discover leases by searching name patterns (run manually) |
| `production_downloader.py` | Multi-threaded production download with built-in enrichment |

See [DOCUMENTATION.md](DOCUMENTATION.md) for complete documentation.

## How It Works

1. **Lease Discovery** — Searches common 3-letter prefixes (AAA, ABB, ABC...) across all 13 RRC districts to build a complete lease database. Progress is checkpointed so interrupted runs can resume.

2. **Production Download** — Queries the RRC PDQ system for each lease's monthly production data (1993-present). Runs **10 concurrent browser sessions** by default for ~10× speedup. Downloads are incremental — running again only fetches new months.

3. **Enrichment** — Each record is automatically enriched with operator name/number, GPS coordinates, county, and API number via the EWA system and GIS Viewer.

## Requirements

- Python 3.8+
- Google Chrome (or Chromium)
- `pip install selenium beautifulsoup4 requests`

## License

&copy; 2013 dwt | [terminus data science, LLC](http://www.terminusdatascience.com)
