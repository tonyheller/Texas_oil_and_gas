#!/usr/bin/env python3
"""
Texas RRC Production Data Downloader

Downloads 15 years of monthly oil and gas production data for Texas leases.
Uses the PDQ (Production Data Query) system with Selenium browser automation.

Usage:
    python production_downloader.py [--years 2011-2025] [--leases ./leases_discovered.csv] [--output-dir ./data]
"""

import argparse
import csv
import datetime
import json
import logging
import os
import re
import sqlite3
import time
from pathlib import Path
from urllib.request import urlopen, Request
from urllib.parse import urlencode
from urllib.error import URLError

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.alert import Alert
from selenium.common.exceptions import TimeoutException, NoSuchElementException, UnexpectedAlertPresentException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

PDQ_BASE = 'https://webapps.rrc.texas.gov'

# District code mapping (form values)
DISTRICT_MAP = {
    '01': '01', '02': '02', '03': '03', '04': '04', '05': '05',
    '06': '06', '6E': '07', '7B': '08', '7C': '09', '08': '10',
    '8A': '11', '09': '13', '10': '14'
}

# Texas county FIPS codes — API = 42 + county_fips(3) + lease(6) + well(2)
# https://www.census.gov/library/reference/code-lists/ansi.html
TEXAS_COUNTY_FIPS = {
    'ANDERSON': '001', 'ANDREWS': '003', 'ANGELINA': '005', 'ARANSAS': '007',
    'ARCHER': '009', 'ARMSTRONG': '011', 'ATASCOSA': '013', 'AUSTIN': '015',
    'BAILEY': '017', 'BANDERA': '019', 'BASTROP': '021', 'BAYLOR': '023',
    'BEE': '025', 'BELL': '027', 'BEXAR': '029', 'BLANCO': '031',
    'BORDEN': '033', 'BOSQUE': '035', 'BOWIE': '037', 'BRAZORIA': '039',
    'BRAZOS': '041', 'BREWSTER': '043', 'BRISCOE': '045', 'BROOKS': '047',
    'BROWN': '049', 'BURLESON': '051', 'BURNET': '053', 'CALDWELL': '055',
    'CALHOUN': '057', 'CALLAHAN': '059', 'CAMERON': '061', 'CAMP': '063',
    'CARSON': '065', 'CASS': '067', 'CASTRO': '069', 'CHAMBERS': '071',
    'CHEROKEE': '073', 'CHILDRESS': '075', 'CLAY': '077', 'COCHRAN': '079',
    'COKE': '081', 'COLEMAN': '083', 'COLLIN': '085', 'COLLINGSWORTH': '087',
    'COLORADO': '089', 'COMAL': '091', 'COMANCHE': '093', 'CONCHO': '095',
    'COOKE': '097', 'CORYELL': '099', 'COTTLE': '101', 'CRANE': '103',
    'CROCKETT': '105', 'CROSBY': '107', 'CULBERSON': '109', 'DALLAM': '111',
    'DALLAS': '113', 'DAWSON': '115', 'DEAF SMITH': '117', 'DELTA': '119',
    'DENTON': '121', 'DE WITT': '123', 'DICKENS': '125', 'DIMMIT': '127',
    'DONLEY': '129', 'DUVAL': '131', 'EASTLAND': '133', 'ECTOR': '135',
    'EDWARDS': '137', 'ELLIS': '139', 'EL PASO': '141', 'ERATH': '143',
    'FALLS': '145', 'FANNIN': '147', 'FAYETTE': '149', 'FISHER': '151',
    'FLOYD': '153', 'FOARD': '155', 'FORT BEND': '157', 'FRANKLIN': '159',
    'FREESTONE': '161', 'FRIO': '163', 'GAINES': '165', 'GALVESTON': '167',
    'GARZA': '169', 'GILLESPIE': '171', 'GLASSCOCK': '173', 'GOLIAD': '175',
    'GONZALES': '177', 'GRAY': '179', 'GRAYSON': '181', 'GREGG': '183',
    'GRIMES': '185', 'GUADALUPE': '187', 'HALE': '189', 'HALL': '191',
    'HAMILTON': '193', 'HANSFORD': '195', 'HARDEMAN': '197', 'HARDIN': '199',
    'HARRIS': '201', 'HARRISON': '203', 'HARTLEY': '205', 'HASKELL': '207',
    'HAYS': '209', 'HEMPHILL': '211', 'HENDERSON': '213', 'HIDALGO': '215',
    'HILL': '217', 'HOCKLEY': '219', 'HOOD': '221', 'HOPKINS': '223',
    'HOUSTON': '225', 'HOWARD': '227', 'HUDSPETH': '229', 'HUNT': '231',
    'HUTCHINSON': '233', 'IRION': '235', 'JACK': '237', 'JACKSON': '239',
    'JASPER': '241', 'JEFF DAVIS': '243', 'JEFFERSON': '245', 'JIM HOGG': '247',
    'JIM WELLS': '249', 'JOHNSON': '251', 'JONES': '253', 'KARNES': '255',
    'KAUFMAN': '257', 'KENDALL': '259', 'KENEDY': '261', 'KENT': '263',
    'KERR': '265', 'KIMBLE': '267', 'KING': '269', 'KINNEY': '271',
    'KLEBERG': '273', 'KNOX': '275', 'LAMAR': '277', 'LAMB': '279',
    'LAMPASAS': '281', 'LA SALLE': '283', 'LAVACA': '285', 'LEE': '287',
    'LEON': '289', 'LIBERTY': '291', 'LIMESTONE': '293', 'LIPSCOMB': '295',
    'LIVE OAK': '297', 'LLANO': '299', 'LOVING': '301', 'LUBBOCK': '303',
    'LYNN': '305', 'MCCULLOCH': '307', 'MCLENNAN': '309', 'MCMULLEN': '311',
    'MADISON': '313', 'MARION': '315', 'MARTIN': '317', 'MASON': '319',
    'MATAGORDA': '321', 'MAVERICK': '323', 'MEDINA': '325', 'MENARD': '327',
    'MIDLAND': '329', 'MILAM': '331', 'MILLS': '333', 'MITCHELL': '335',
    'MONTAGUE': '337', 'MONTGOMERY': '339', 'MOORE': '341', 'MORRIS': '343',
    'MOTLEY': '345', 'NACOGDOCHES': '347', 'NAVARRO': '349', 'NEWTON': '351',
    'NOLAN': '353', 'NUECES': '355', 'OCHILTREE': '357', 'OLDHAM': '359',
    'ORANGE': '361', 'PALO PINTO': '363', 'PANOLA': '365', 'PARKER': '367',
    'PARMER': '369', 'PECOS': '371', 'POLK': '373', 'POTTER': '375',
    'PRESIDIO': '377', 'RAINS': '379', 'RANDALL': '381', 'REAGAN': '383',
    'REAL': '385', 'RED RIVER': '387', 'REEVES': '389', 'REFUGIO': '391',
    'ROBERTS': '393', 'ROBERTSON': '395', 'ROCKWALL': '397', 'RUNNELS': '399',
    'RUSK': '401', 'SABINE': '403', 'SAN AUGUSTINE': '405', 'SAN JACINTO': '407',
    'SAN PATRICIO': '409', 'SAN SABA': '411', 'SCHLEICHER': '413', 'SCURRY': '415',
    'SHACKELFORD': '417', 'SHELBY': '419', 'SHERMAN': '421', 'SMITH': '423',
    'SOMERVELL': '425', 'STARR': '427', 'STEPHENS': '429', 'STERLING': '431',
    'STONEWALL': '433', 'SUTTON': '435', 'SWISHER': '437', 'TARRANT': '439',
    'TAYLOR': '441', 'TERRELL': '443', 'TERRY': '445', 'THROCKMORTON': '447',
    'TITUS': '449', 'TOM GREEN': '451', 'TRAVIS': '453', 'TRINITY': '455',
    'TYLER': '457', 'UPSHUR': '459', 'UPTON': '461', 'UVALDE': '463',
    'VAL VERDE': '465', 'VAN ZANDT': '467', 'VICTORIA': '469', 'WALKER': '471',
    'WALLER': '473', 'WARD': '475', 'WASHINGTON': '477', 'WEBB': '479',
    'WHARTON': '481', 'WHEELER': '483', 'WICHITA': '485', 'WILBARGER': '487',
    'WILLACY': '489', 'WILLIAMSON': '491', 'WILSON': '493', 'WINKLER': '495',
    'WISE': '497', 'WOOD': '499', 'YOAKUM': '501', 'YOUNG': '503',
    'ZAPATA': '505', 'ZAVALA': '507',
}


def build_api_number(lease_number, county_name, well_number):
    """
    Construct the 14-digit Texas API number.

    Format: 42 (state) + county_fips(3) + lease(6) + well(2)

    Returns the API string, or None if county can't be resolved.
    """
    county_fips = TEXAS_COUNTY_FIPS.get(county_name.upper())
    if not county_fips:
        return None
    lease_padded = str(lease_number).zfill(6)
    well_padded = str(well_number).zfill(2)
    return f'42{county_fips}{lease_padded}{well_padded}'

# Default year range: past 15 years
CURRENT_YEAR = datetime.date.today().year
DEFAULT_START_YEAR = CURRENT_YEAR - 15
DEFAULT_END_YEAR = CURRENT_YEAR


# Month abbreviation ↔ bit index mapping (bit 0 = Jan, bit 11 = Dec)
_MONTH_NAMES = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
                'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec']
_MONTH_BITS = {name: i for i, name in enumerate(_MONTH_NAMES)}


class DownloadState:
    """SQLite-backed state tracking for production downloads.

    Uses integer bitmasks for month tracking (12 months per year = one int)
    and a separate metadata table. WAL journaling enables fast writes
    without full-file rewrites. Scales to millions of leases.
    """

    def __init__(self, state_file):
        self.db_path = Path(state_file)
        # If the user pointed to a .json file, redirect to .db
        if self.db_path.suffix == '.json':
            self.db_path = self.db_path.with_suffix('.db')
        self._conn = sqlite3.connect(str(self.db_path), isolation_level=None)
        self._conn.execute('PRAGMA journal_mode=WAL')
        self._conn.execute('PRAGMA synchronous=NORMAL')
        self._create_tables()
        self._maybe_migrate_legacy_json(state_file)

    def _create_tables(self):
        self._conn.execute('''
            CREATE TABLE IF NOT EXISTS lease_metadata (
                lease_key TEXT PRIMARY KEY,
                county TEXT,
                api_id TEXT,
                operator TEXT,
                operator_no TEXT,
                lat REAL,
                lon REAL
            )
        ''')
        self._conn.execute('''
            CREATE TABLE IF NOT EXISTS downloaded_months (
                lease_key TEXT NOT NULL,
                year INTEGER NOT NULL,
                month_mask INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (lease_key, year)
            )
        ''')
        self._conn.execute('''
            CREATE INDEX IF NOT EXISTS idx_dl_lease
            ON downloaded_months(lease_key)
        ''')
        self._conn.commit()

    def _maybe_migrate_legacy_json(self, original_path):
        """Migrate old JSON state file to SQLite on first use, then delete JSON."""
        json_path = Path(original_path)
        if not json_path.exists() or json_path.suffix != '.json':
            return

        # Check if we already migrated (db has data)
        count = self._conn.execute('SELECT COUNT(*) FROM lease_metadata').fetchone()[0]
        if count > 0:
            return  # Already migrated or db was pre-populated

        log.info(f'Migrating legacy JSON state {json_path} to SQLite...')
        try:
            with open(json_path, 'r') as f:
                legacy = json.load(f)

            leases = legacy.get('leases', {})
            if not leases:
                return

            meta_rows = []
            month_rows = []
            for lease_key, lease_state in leases.items():
                county = lease_state.get('_county')
                api_id = lease_state.get('_api_id')
                operator = lease_state.get('_operator')
                operator_no = lease_state.get('_operator_no')
                lat = lease_state.get('_lat')
                lon = lease_state.get('_lon')

                if any(v is not None for v in [county, api_id, operator, lat]):
                    meta_rows.append((lease_key, county, api_id, operator, operator_no, lat, lon))

                for year_str, month_list in lease_state.items():
                    if year_str.startswith('_'):
                        continue
                    if not isinstance(month_list, list):
                        continue
                    try:
                        year = int(year_str)
                    except ValueError:
                        continue
                    mask = 0
                    for m in month_list:
                        if m in _MONTH_BITS:
                            mask |= (1 << _MONTH_BITS[m])
                    if mask:
                        month_rows.append((lease_key, year, mask))

            if meta_rows:
                self._conn.execute('BEGIN')
                self._conn.executemany(
                    'INSERT OR IGNORE INTO lease_metadata VALUES (?,?,?,?,?,?,?)',
                    meta_rows
                )
            if month_rows:
                if not meta_rows:
                    self._conn.execute('BEGIN')
                self._conn.executemany(
                    'INSERT OR IGNORE INTO downloaded_months VALUES (?,?,?)',
                    month_rows
                )
            self._conn.execute('COMMIT')
            log.info(f'Migrated {len(meta_rows)} lease metadata and {len(month_rows)} month records')

            # Back up and remove old JSON file
            backup = json_path.with_suffix('.json.bak')
            json_path.rename(backup)
            log.info(f'Legacy JSON state backed up to {backup}')

        except Exception as e:
            log.warning(f'Failed to migrate legacy JSON state: {e}')

    def save(self):
        """No-op for SQLite backend. Data is committed atomically on every write."""
        pass

    def _commit(self):
        """Force a commit (used at lease boundaries)."""
        self._conn.commit()

    def get_county(self, lease_key):
        """Get cached county name for a lease, or None."""
        row = self._conn.execute(
            'SELECT county FROM lease_metadata WHERE lease_key = ?',
            (lease_key,)
        ).fetchone()
        return row[0] if row else None

    def set_county(self, lease_key, county_name):
        """Cache county name for a lease."""
        self._conn.execute(
            'INSERT INTO lease_metadata (lease_key, county) VALUES (?, ?) '
            'ON CONFLICT(lease_key) DO UPDATE SET county = ?',
            (lease_key, county_name, county_name)
        )

    def get_lat_lon(self, lease_key):
        """Get cached lat/lon for a lease."""
        row = self._conn.execute(
            'SELECT lat, lon FROM lease_metadata WHERE lease_key = ?',
            (lease_key,)
        ).fetchone()
        if row and row[0] is not None and row[1] is not None:
            return (row[0], row[1])
        return None

    def set_lat_lon(self, lease_key, lat, lon):
        """Cache lat/lon for a lease."""
        self._conn.execute(
            'INSERT INTO lease_metadata (lease_key, lat, lon) VALUES (?, ?, ?) '
            'ON CONFLICT(lease_key) DO UPDATE SET lat = ?, lon = ?',
            (lease_key, lat, lon, lat, lon)
        )

    def get_operator(self, lease_key):
        """Get cached operator info for a lease."""
        row = self._conn.execute(
            'SELECT operator, operator_no FROM lease_metadata WHERE lease_key = ?',
            (lease_key,)
        ).fetchone()
        if row and row[0]:
            return (row[0], row[1])
        return None

    def set_operator(self, lease_key, name, no):
        """Cache operator info for a lease."""
        self._conn.execute(
            'INSERT INTO lease_metadata (lease_key, operator, operator_no) VALUES (?, ?, ?) '
            'ON CONFLICT(lease_key) DO UPDATE SET operator = ?, operator_no = ?',
            (lease_key, name, no, name, no)
        )

    def get_api_id(self, lease_key):
        """Get cached EWA API ID for a lease."""
        row = self._conn.execute(
            'SELECT api_id FROM lease_metadata WHERE lease_key = ?',
            (lease_key,)
        ).fetchone()
        return row[0] if row else None

    def set_api_id(self, lease_key, api_id):
        """Cache EWA API ID for a lease."""
        self._conn.execute(
            'INSERT INTO lease_metadata (lease_key, api_id) VALUES (?, ?) '
            'ON CONFLICT(lease_key) DO UPDATE SET api_id = ?',
            (lease_key, api_id, api_id)
        )

    def get_downloaded_months(self, lease_key):
        """
        Return set of (year, month_name) tuples already downloaded for a lease.
        """
        rows = self._conn.execute(
            'SELECT year, month_mask FROM downloaded_months WHERE lease_key = ?',
            (lease_key,)
        ).fetchall()

        months = set()
        for year, mask in rows:
            for bit in range(12):
                if mask & (1 << bit):
                    months.add((year, _MONTH_NAMES[bit]))
        return months

    def record_downloaded(self, lease_key, records):
        """
        Mark specific (year, month) combos as downloaded.
        Uses bitwise OR to merge new months with existing bitmask.
        """
        # Build bitmask per year
        year_masks = {}
        for rec in records:
            year = int(rec['year'])
            month_name = rec['month']
            bit = _MONTH_BITS.get(month_name)
            if bit is None:
                continue
            year_masks[year] = year_masks.get(year, 0) | (1 << bit)

        for year, mask in year_masks.items():
            self._conn.execute(
                'INSERT INTO downloaded_months (lease_key, year, month_mask) '
                'VALUES (?, ?, ?) '
                'ON CONFLICT(lease_key, year) DO UPDATE SET month_mask = month_mask | ?',
                (lease_key, year, mask, mask)
            )

    def needs_download(self, lease_key, start_year, end_year):
        """
        Determine what year ranges still need downloading.

        Uses bitmasks: if month_mask == 0xFFF (all 12 bits set), the year is complete.
        Returns (needed, already_have) tuple:
          needed: list of (start, end) year ranges that need downloading
          already_have: count of months already downloaded
        """
        rows = self._conn.execute(
            'SELECT year, month_mask FROM downloaded_months WHERE lease_key = ?',
            (lease_key,)
        ).fetchall()

        # Build lookup of known masks
        known_masks = {year: mask for year, mask in rows}

        already_count = 0
        missing_years = []

        for year in range(start_year, end_year + 1):
            mask = known_masks.get(year, 0)
            # Count set bits
            bits = bin(mask).count('1')
            already_count += bits
            if bits < 12:
                missing_years.append(year)

        if not missing_years:
            return [], already_count

        # Consolidate into contiguous ranges
        ranges = []
        range_start = missing_years[0]
        range_end = missing_years[0]
        for y in missing_years[1:]:
            if y == range_end + 1:
                range_end = y
            else:
                ranges.append((range_start, range_end))
                range_start = y
                range_end = y
        ranges.append((range_start, range_end))

        return ranges, already_count

    def stats(self):
        """Return summary of download progress."""
        total_leases = self._conn.execute(
            'SELECT COUNT(DISTINCT lease_key) FROM ('
            '  SELECT lease_key FROM lease_metadata'
            '  UNION'
            '  SELECT lease_key FROM downloaded_months'
            ')'
        ).fetchone()[0]

        total_months = self._conn.execute(
            'SELECT SUM(month_mask_bit_count) FROM ('
            '  SELECT SUM('
            '    (month_mask >> 0 & 1) + (month_mask >> 1 & 1) + (month_mask >> 2 & 1) +'
            '    (month_mask >> 3 & 1) + (month_mask >> 4 & 1) + (month_mask >> 5 & 1) +'
            '    (month_mask >> 6 & 1) + (month_mask >> 7 & 1) + (month_mask >> 8 & 1) +'
            '    (month_mask >> 9 & 1) + (month_mask >> 10 & 1) + (month_mask >> 11 & 1)'
            '  ) AS month_mask_bit_count'
            '  FROM downloaded_months GROUP BY lease_key'
            ')'
        ).fetchone()[0] or 0

        return {'leases': total_leases, 'months': total_months}

    def close(self):
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def __del__(self):
        self.close()


# GIS Viewer endpoint (gis2 REST API is down, use Viewer page instead)
GIS_VIEWER_URL = 'https://gis.rrc.texas.gov/GISViewer/index.html?api={api_id}'

# EWA system for operator lookup
EWA_WELLBORE_URL = 'https://webapps2.rrc.state.tx.us/EWA/wellboreQueryAction.do'
EWA_LEASE_DETAIL_URL = 'https://webapps2.rrc.state.tx.us/EWA/leaseDetailAction.do'


def lookup_lat_lon_from_gis_viewer(driver, api_id):
    """
    Look up latitude/longitude for a well using the RRC GIS Viewer page.

    The GIS Viewer page at gis.rrc.texas.gov renders well coordinates via JavaScript.
    driver: a Selenium WebDriver instance (must be provided by caller)
    api_id: the internal EWA API ID (e.g., '31133330')

    Returns (lat, lon) tuple using NAD83 datum, or (None, None) if not found.
    """
    if not api_id:
        return None, None

    url = GIS_VIEWER_URL.format(api_id=api_id)

    try:
        log.info(f'GIS Viewer: requesting lat/lon for API {api_id}')
        driver.get(url)
        log.info(f'GIS Viewer: URL={driver.current_url}')
        log.info(f'GIS Viewer: page loaded for API {api_id}, waiting for JS render...')
        time.sleep(5)

        # Dismiss any JS alert (e.g., "Map feature was not found")
        try:
            alert = Alert(driver)
            alert_text = alert.text
            log.info(f'GIS Viewer: alert detected: "{alert_text}", dismissing')
            alert.accept()
            time.sleep(1)
        except:
            pass

        html = driver.page_source

        # Parse: GIS LAT (NAD83) and GIS LONG (NAD83) from HTML table
        lat_match = re.search(r'GIS LAT \(NAD83\)</th>\s*<td[^>]*>([\d.\-]+)</td>', html)
        lon_match = re.search(r'GIS LONG \(NAD83\)</th>\s*<td[^>]*>([\d.\-]+)</td>', html)

        if lat_match and lon_match:
            lat = float(lat_match.group(1))
            lon = float(lon_match.group(1))
            log.info(f'GIS Viewer: found lat={lat}, lon={lon} (NAD83) for API {api_id}')
            return (lat, lon)

        # Fallback to NAD27 if NAD83 not found
        lat_match = re.search(r'GIS LAT \(NAD27\)</th>\s*<td[^>]*>([\d.\-]+)</td>', html)
        lon_match = re.search(r'GIS LONG \(NAD27\)</th>\s*<td[^>]*>([\d.\-]+)</td>', html)

        if lat_match and lon_match:
            lat = float(lat_match.group(1))
            lon = float(lon_match.group(1))
            log.info(f'GIS Viewer: found lat={lat}, lon={lon} (NAD27) for API {api_id}')
            return (lat, lon)

        log.info(f'GIS Viewer: no lat/lon found in page for API {api_id}')
        return None, None

    except UnexpectedAlertPresentException as e:
        log.info(f'GIS Viewer: unexpected alert for {api_id}, dismissing')
        try:
            Alert(driver).accept()
        except:
            pass
        return None, None
    except Exception as e:
        log.info(f'GIS Viewer lookup failed for {api_id}: {e}')
        return None, None


def lookup_operator(driver, district, lease_number, lease_key, state=None):
    """
    Look up current operator for a lease using the EWA Wellbore Query + Lease Detail.

    Returns (operator_name, operator_no) tuple or (None, None) if not found.
    """
    # Check cache first
    if state and lease_key:
        cached = state.get_operator(lease_key)
        if cached:
            log.info(f'Operator lookup (cache hit): {cached[0]} ({cached[1]}) for {lease_key}')
            return cached

    log.info(f'Operator lookup (EWA): district={district} lease={lease_number} key={lease_key}')

    try:
        # Step 1: Search by lease number + district in Wellbore Query
        log.info(f'Operator step 1: navigating to EWA Wellbore Query...')
        driver.get(EWA_WELLBORE_URL)
        log.info(f'Operator step 1: URL={driver.current_url} (title: {driver.title}), filling form...')
        time.sleep(2)

        # Check for session timeout or login redirect
        if 'Login' in driver.title or 'Choose an Application' in driver.page_source:
            log.info(f'Operator lookup: EWA session expired, cannot proceed')
            return None, None

        # Fill lease number
        lease_input = driver.find_element(By.NAME, 'searchArgs.leaseNumberArg')
        lease_input.clear()
        lease_input.send_keys(lease_number)

        # Select district
        Select(driver.find_element(By.NAME, 'searchArgs.districtCodeArg')).select_by_value(district)

        # Select "Current" schedule type (Y)
        current_radio = driver.find_element(By.CSS_SELECTOR, 'input[name="searchArgs.scheduleTypeArg"][value="Y"]')
        current_radio.click()

        # Submit
        log.info(f'Operator step 1: submitting query for lease {lease_number}...')
        driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]').click()
        time.sleep(3)
        log.info(f'Operator step 1: results URL={driver.current_url} (title: {driver.title})')

        # Check results
        if 'No results found' in driver.page_source:
            log.info(f'Operator lookup: no wellbore results for lease {lease_number}, district {district}')
            return None, None

        # Extract the API ID from the results (e.g., "31133330")
        source = driver.page_source
        api_id_match = re.search(
            r'leaseDetailAction\.do\?[^>]*apiNo=(\d+)',
            source
        )
        if not api_id_match:
            log.info(f'Operator lookup: no API ID found in wellbore results for lease {lease_number}')
            return None, None

        api_id = api_id_match.group(1)
        log.info(f'Operator step 1: found API ID {api_id}')

        # Cache the API ID for future GIS lookups
        if state and lease_key:
            state.set_api_id(lease_key, api_id)
            state.save()

        # Step 2: Click the API number link to go to Lease Detail page
        # (direct URL navigation causes session errors)
        log.info(f'Operator step 2: clicking API link {api_id} to view lease detail...')
        api_link = driver.find_element(By.LINK_TEXT, api_id)
        api_link.click()
        time.sleep(4)
        log.info(f'Operator step 2: URL={driver.current_url} (title: {driver.title})')

        detail_source = driver.page_source

        # Extract current operator name and number from <strong> tags
        # HTML structure:
        # Current Operator Number: <strong id="...">945936</strong>
        # Current Operator Name: <strong id="...">XTO ENERGY INC.</strong>
        op_no_match = re.search(
            r'Current Operator Number:\s*<strong[^>]*>\s*(\d+)\s*</strong>',
            detail_source
        )
        operator_name_match = re.search(
            r'Current Operator Name:\s*<strong[^>]*>\s*([A-Z][A-Z\s\.\&\(\)\-]+?)\s*</strong>',
            detail_source
        )

        if operator_name_match and op_no_match:
            operator_name = operator_name_match.group(1).strip()
            operator_no = op_no_match.group(1).strip()
            log.debug(f'Operator found: {operator_name} ({operator_no}) for API {api_id}')

            if state and lease_key:
                state.set_operator(lease_key, operator_name, operator_no)
                state.save()

            return (operator_name, operator_no)

        log.debug(f'No operator found in lease detail for API {api_id}')
        return None, None

    except Exception as e:
        log.debug(f'Error looking up operator for lease {lease_number}: {e}')
        return None, None


def create_driver():
    """Create a Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(90)
        return driver
    except Exception as e:
        log.error(f'Failed to create Chrome driver: {e}')
        raise


def load_leases(lease_file):
    """Load discovered leases from CSV file."""
    leases = []
    lease_path = Path(lease_file)
    
    if not lease_path.exists():
        log.error(f'Lease file not found: {lease_file}')
        return leases
    
    with open(lease_path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            leases.append(row)
    
    log.info(f'Loaded {len(leases)} leases from {lease_file}')
    return leases


def _extract_county(driver, production_source):
    """
    Navigate to County Production view and extract county name.

    Returns to the original production view afterwards.
    Returns county name string or None if not found.
    """
    try:
        log.info(f'County lookup: clicking "County Production" link...')
        # Find and click County Production link
        county_links = driver.find_elements(By.LINK_TEXT, 'County Production')
        if not county_links:
            log.info(f'County lookup: no County Production link found, URL={driver.current_url}')
            return None

        county_links[0].click()
        log.info(f'County lookup: navigating to county view...')
        time.sleep(3)
        log.info(f'County lookup: county view URL={driver.current_url}')

        county_source = driver.page_source

        # County name appears in the county production table
        # Pattern: county name followed by production numbers
        # e.g., "MCMULLEN 7,778 0"
        # Also the header says "County Production"
        # The county name is in a <td> before the numbers
        county_match = re.search(
            r'<td[^>]*>\s*([A-Z][A-Z\s\.]+?)\s*</td>\s*<td[^>]*>\s*[\d,]+\s*</td>',
            county_source
        )
        if county_match:
            county_name = county_match.group(1).strip()
            if county_name in TEXAS_COUNTY_FIPS:
                log.info(f'County lookup: found {county_name} (HTML table match)')
                return county_name

        # Fallback: look for county name in visible text near production numbers
        log.info(f'County lookup: no HTML match, scanning visible text for county name...')
        body_text = driver.find_element(By.TAG_NAME, 'body').text
        for county_name in TEXAS_COUNTY_FIPS:
            # County name followed by a number (production value)
            if re.search(rf'\b{county_name}\b\s+[\d,]', body_text):
                log.info(f'County lookup: found {county_name} (body text match)')
                return county_name

        log.info(f'County lookup: no match found')
        return None

    except Exception as e:
        log.debug(f'Error extracting county: {e}')
        return None


def extract_production_data(driver, state=None, lease_key=None):
    """
    Extract production data from the results page.

    Also navigates to County Production view to get county (cached in state),
    then constructs the full 14-digit API number.

    Returns list of dicts with monthly production records.
    """
    records = []

    try:
        # Try to click "View All Results" to avoid pagination
        log.info(f'Extract: clicking "View All Results" to get full page...')
        view_all_links = driver.find_elements(By.LINK_TEXT, 'View All Results')
        if view_all_links:
            view_all_links[0].click()
            time.sleep(3)
            log.info(f'Extract: clicked "View All Results" — URL={driver.current_url}')
        else:
            log.info(f'Extract: no "View All Results" link found, URL={driver.current_url}')

        # Get page source
        source = driver.page_source
        log.info(f'Extract: page source loaded ({len(source)} chars)')

        # Extract lease info from page
        # Pattern: "Lease Name: SMITH, Lease No: 162326, Well No: 5"
        lease_info = {}
        lease_match = re.search(
            r'Lease Name:\s*([^,]*),\s*Lease No:\s*(\d+).*?Well No:\s*(\d+)',
            source
        )
        if lease_match:
            lease_info['lease_name'] = lease_match.group(1).strip()
            lease_info['lease_number'] = lease_match.group(2)
            lease_info['well_number'] = lease_match.group(3)
            log.info(f'Extract: lease={lease_match.group(1).strip()}, no={lease_match.group(2)}, well={lease_match.group(3)}')
        else:
            # Try without well number
            lease_match = re.search(
                r'Lease Name:\s*([^,]*),\s*Lease No:\s*(\d+)', source
            )
            if lease_match:
                lease_info['lease_name'] = lease_match.group(1).strip()
                lease_info['lease_number'] = lease_match.group(2)
                log.info(f'Extract: lease={lease_match.group(1).strip()}, no={lease_match.group(2)}, well=not found')

        # Extract district
        district_match = re.search(r'District\s+(\d{2})', source)
        if district_match:
            lease_info['district'] = district_match.group(1)
            log.info(f'Extract: district={district_match.group(1)}')

        # Get county (from cache or by navigating to County Production view)
        county_name = None
        if state and lease_key:
            county_name = state.get_county(lease_key)
            if county_name:
                log.info(f'Extract: county from cache: {county_name}')

        if not county_name:
            log.info(f'Extract: county not cached, navigating to County Production view...')
            county_name = _extract_county(driver, source)
            if county_name and state and lease_key:
                state.set_county(lease_key, county_name)
                state.save()
                log.info(f'Extract: county cached as {county_name}')

        if county_name:
            lease_info['county'] = county_name
            api = build_api_number(
                lease_info.get('lease_number', ''),
                county_name,
                lease_info.get('well_number', '')
            )
            if api:
                lease_info['api_number'] = api
                log.info(f'Extract: API number built: {api}')
            else:
                log.info(f'Extract: could not build API number (county "{county_name}" not in FIPS table)')

        # Extract operator and field from the first data row in the table.
        # The HTML structure for each row is:
        # <tr><td><strong>Month Year</strong></td>
        #     <td>gas_prod</td><td>gas_disp</td>
        #     <td>oil_prod</td><td>oil_disp</td>
        #     <td>Operator Name</td><td>Operator No.</td>
        #     <td>Field Name</td><td>Field No.</td></tr>
        # Operator/field only appear in the first row; subsequent rows have empty cells.
        # We extract them below from the first data row during row processing.
        # (The old full-page regex with re.DOTALL caused catastrophic backtracking
        # on 65KB+ pages, hanging for minutes.)
        log.info(f'Extract: operator will be extracted from the first data row below')

        # Find all table rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', source, re.DOTALL)
        log.info(f'Extract: found {len(rows)} HTML rows in page source')

        # Track operator/field info (appears in first data row)
        operator_found = False

        # Process rows looking for month data
        months_parsed = 0
        for row in rows:
            # Look for month in this row
            month_match = re.search(r'<strong>\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\s*</strong>', row)

            if month_match:
                month = month_match.group(1)
                year = month_match.group(2)
                months_parsed += 1

                # Extract numeric values from the row
                # Remove the month TD, then find value TDs
                row_without_month = re.sub(r'<td[^>]*><strong>.*?</strong></td>', '', row, count=1)
                value_tds = re.findall(r'<td[^>]*>([^<]*)</td>', row_without_month)

                values = []
                for val in value_tds[:6]:  # Take up to 6 values (prod, disp, oil_prod, oil_disp, operator, field)
                    val_clean = val.strip().replace(',', '')
                    # Try to parse as number, otherwise keep as text
                    try:
                        values.append(float(val_clean) if val_clean else 0.0)
                    except ValueError:
                        values.append(val_clean)  # Keep as text (operator/field name)

                # Extract operator and field from first row
                if not operator_found and len(values) >= 6:
                    if isinstance(values[4], str) and values[4]:
                        lease_info['operator'] = values[4]
                    if isinstance(values[5], str) and values[5]:
                        lease_info['field'] = values[5]
                    operator_found = True
                    log.info(f'Extract: operator from row values: {values[4]}, field: {values[5]}')

                # Ensure we have at least 4 numeric values
                numeric_values = []
                for v in values[:4]:
                    if isinstance(v, (int, float)):
                        numeric_values.append(v)
                    else:
                        numeric_values.append(0.0)

                if len(numeric_values) >= 4:
                    record = {
                        'month': month,
                        'year': year,
                        'date': f'{month} {year}',
                        'gas_production': numeric_values[0],
                        'gas_disposition': numeric_values[1],
                        'oil_condensate_production': numeric_values[2],
                        'oil_condensate_disposition': numeric_values[3],
                        'latitude': '',
                        'longitude': '',
                    }
                    record.update(lease_info)
                    records.append(record)

        log.info(f'Extract: parsed {months_parsed} months with data, built {len(records)} records')
        return records

    except Exception as e:
        log.error(f'Error extracting production data: {e}')
        return records


def download_lease_production(driver, lease_number, district, well_type, start_year, end_year, state=None):
    """
    Download production data for a specific lease and year range.

    If state is provided, only downloads months not already tracked.

    Returns list of monthly production records (newly downloaded only).
    """
    lease_key = f'{district}/{lease_number}'

    # Check what we already have
    if state:
        ranges, already_count = state.needs_download(lease_key, start_year, end_year)
        if not ranges:
            log.info(f'Lease {lease_key}: all {already_count} months already downloaded, skipping')
            return []

        # Use the needed ranges (combine if multiple)
        effective_start = ranges[0][0]
        effective_end = ranges[-1][1]
        log.info(f'Lease {lease_key}: need {effective_start}-{effective_end} ({already_count} months already have)')
    else:
        effective_start = start_year
        effective_end = end_year

    try:
        # Navigate to Specific Lease Query
        log.info(f'PDQ: navigating to lease query form...')
        driver.get(f'{PDQ_BASE}/PDQ/quickLeaseReportBuilderAction.do')
        log.info(f'PDQ: URL={driver.current_url} (title: {driver.title})')
        time.sleep(2)

        # Check for session timeout
        if 'Session Timed Out' in driver.page_source:
            log.warning('Session timed out')
            return None

        # Fill in the form
        well_type_value = 'Oil' if well_type == 'Oil' else 'Gas'
        well_type_radio = driver.find_element(By.XPATH, f'//input[@type="radio" and @value="{well_type_value}"]')
        well_type_radio.click()

        # Enter lease number (with leading zeros if needed)
        lease_input = driver.find_element(By.NAME, 'leaseNumber')
        lease_input.clear()
        lease_input.send_keys(lease_number.zfill(5))

        # Select district
        district_select = Select(driver.find_element(By.NAME, 'district'))
        district_value = DISTRICT_MAP.get(district, district)
        district_select.select_by_value(district_value)

        # Select date range
        Select(driver.find_element(By.NAME, 'startMonth')).select_by_value('01')
        Select(driver.find_element(By.NAME, 'startYear')).select_by_value(str(effective_start))
        Select(driver.find_element(By.NAME, 'endMonth')).select_by_value('12')
        Select(driver.find_element(By.NAME, 'endYear')).select_by_value(str(effective_end))

        # Submit form
        log.info(f'PDQ: submitting query for lease {lease_number} (district {district}, {well_type}, {effective_start}-{effective_end})...')
        submit_btn = driver.find_element(By.XPATH, '//input[@type="submit" and @value="Submit"]')
        submit_btn.click()

        time.sleep(4)
        log.info(f'PDQ: results URL={driver.current_url} (title: {driver.title})')

        # Handle alerts
        try:
            alert = Alert(driver)
            alert_text = alert.text
            if 'invalid' in alert_text.lower() or 'not found' in alert_text.lower():
                log.info(f'PDQ: lease {lease_number} invalid or not found')
                alert.accept()
                return []
            log.info(f'PDQ: alert dismissed: {alert_text}')
            alert.accept()
        except:
            pass

        # Check results
        log.info(f'PDQ: checking results page...')
        page_source = driver.page_source

        if 'Session Timed Out' in page_source:
            log.warning('Session timed out after submit')
            return None

        if 'No Data Found' in page_source or 'No Matches Found' in page_source:
            log.info(f'PDQ: no data for lease {lease_number}, {effective_start}-{effective_end}')
            return []

        # Extract production data
        log.info(f'PDQ: extracting production data...')
        all_records = extract_production_data(driver, state=state, lease_key=lease_key)
        log.info(f'PDQ: extracted {len(all_records)} production records for lease {lease_key}')

        # Add well_type to each record (from query parameter, not on page)
        if all_records:
            for rec in all_records:
                rec['well_type'] = well_type

            lease_key = f'{district}/{lease_number}'

            # --- Look up operator via EWA if not found on PDQ page ---
            operator_name = all_records[0].get('operator', '')
            operator_no = all_records[0].get('operator_no', '')
            if not operator_name and state:
                log.info(f'Enrichment: operator not on PDQ page, looking up via EWA...')
                op_name, op_no = lookup_operator(
                    driver, district, lease_number, lease_key, state=state
                )
                if op_name:
                    operator_name = op_name
                    operator_no = op_no or ''
            elif operator_name:
                log.info(f'Enrichment: operator from PDQ page: {operator_name} ({operator_no})')

            # --- Look up lat/lon via GIS Viewer ---
            lat = None
            lon = None

            if state and lease_key:
                # Check cache first
                cached = state.get_lat_lon(lease_key)
                if cached:
                    lat, lon = cached
                    log.info(f'Enrichment: lat/lon from cache: {lat}, {lon}')
                else:
                    log.info(f'Enrichment: lat/lon not cached, looking up...')
                    # Try to get EWA API ID from cache
                    api_id = state.get_api_id(lease_key)
                    if api_id:
                        lat, lon = lookup_lat_lon_from_gis_viewer(driver, api_id)
                    else:
                        # Need to query EWA first to get API ID
                        log.info(f'Enrichment: no API ID cached, querying EWA operator lookup first...')
                        _, _ = lookup_operator(
                            driver, district, lease_number, lease_key, state=state
                        )
                        api_id = state.get_api_id(lease_key)
                        if api_id:
                            lat, lon = lookup_lat_lon_from_gis_viewer(driver, api_id)

                    if lat is not None:
                        state.set_lat_lon(lease_key, lat, lon)
                        state.save()
            elif state:
                # No state but try operator lookup to get API ID
                _, _ = lookup_operator(
                    driver, district, lease_number, lease_key, state=state
                )
                api_id = state.get_api_id(lease_key) if state else None
                if api_id:
                    lat, lon = lookup_lat_lon_from_gis_viewer(driver, api_id)

            # Populate operator and lat/lon on all records
            for rec in all_records:
                if operator_name and not rec.get('operator'):
                    rec['operator'] = operator_name
                    rec['operator_no'] = operator_no
                if lat is not None:
                    rec['latitude'] = lat
                    rec['longitude'] = lon

            log.info(f'Enrichment: operator={operator_name or "(unknown)"}, lat/lon={lat or "?"},{lon or "?"}')

        # Filter to only new records (exclude already-downloaded months)
        if state and all_records:
            have = state.get_downloaded_months(lease_key)
            new_records = []
            for rec in all_records:
                key = (int(rec['year']), rec['month'])
                if key not in have:
                    new_records.append(rec)
            log.info(f'PDQ: {len(new_records)} new records (out of {len(all_records)} extracted, {len(have)} already had)')
            all_records = new_records

        # Update state with what we just downloaded
        if state and all_records:
            state.record_downloaded(lease_key, all_records)
            state.save()
            log.info(f'PDQ: state saved for {lease_key}')

        return all_records

    except UnexpectedAlertPresentException as e:
        log.warning(f'Unexpected alert: {e}')
        try:
            alert = Alert(driver)
            alert.accept()
        except:
            pass
        return None
    except Exception as e:
        log.error(f'Error downloading lease {lease_number}: {e}')
        return None


def save_records(records, output_file):
    """Save production records to CSV file."""
    if not records:
        return
    
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    fieldnames = [
        'api_number', 'lease_number', 'lease_name', 'well_number',
        'district', 'county', 'latitude', 'longitude', 'well_type',
        'operator', 'operator_no', 'field', 'field_no',
        'date', 'month', 'year',
        'gas_production', 'gas_disposition',
        'oil_condensate_production', 'oil_condensate_disposition'
    ]
    
    file_exists = output_path.exists()
    
    with open(output_path, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerows(records)
    
    log.info(f'Saved {len(records)} records to {output_file}')


def download_all(leases, start_year, end_year, output_dir, state=None):
    """Download production data for all leases across all years."""
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    output_file = output_path / 'texas_production_data.csv'

    # Don't remove existing file - we append incrementally
    # (state tracking prevents duplicate downloads)

    driver = create_driver()
    total_records = 0
    skipped_count = 0

    try:
        total_leases = len(leases)

        for i, lease in enumerate(leases, 1):
            lease_num = lease['lease_number']
            district = lease['district']
            well_type = lease['well_type']

            result = download_lease_production(
                driver, lease_num, district, well_type, start_year, end_year, state=state
            )

            if result is None:
                # Session timeout - recreate driver and retry
                log.warning('Recreating driver due to session issue')
                driver.quit()
                driver = create_driver()
                result = download_lease_production(
                    driver, lease_num, district, well_type, start_year, end_year, state=state
                )

                if result is None:
                    log.warning('Retry failed, skipping lease')
                    skipped_count += 1
                    continue

            if result:
                save_records(result, output_file)
                total_records += len(result)
                log.info(f'Lease {i}/{total_leases}: {len(result)} new records '
                         f'({lease_num}, {district})')
            else:
                skipped_count += 1

            # Rate limiting
            time.sleep(2)

        stats = state.stats() if state else {}
        log.info(f'Download complete: {total_records} new records, '
                 f'{skipped_count} leases skipped/had no new data')
        if stats:
            log.info(f'  Total tracked: {stats["leases"]} leases, '
                     f'{stats["months"]} months of production data')

    finally:
        driver.quit()
        if state:
            state.close()

    return total_records


def main():
    parser = argparse.ArgumentParser(
        description='Download Texas RRC monthly oil & gas production data'
    )
    parser.add_argument(
        '--years',
        type=str,
        default=f'{DEFAULT_START_YEAR}-{DEFAULT_END_YEAR}',
        help=f'Year range (e.g., 2011-2025). Default: {DEFAULT_START_YEAR}-{DEFAULT_END_YEAR}'
    )
    parser.add_argument(
        '--leases',
        type=str,
        default='./leases_discovered.csv',
        help='CSV file with discovered leases'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='./data',
        help='Output directory for CSV files. Default: ./data'
    )
    parser.add_argument(
        '--state-file',
        type=str,
        default='./data/download_state.json',
        help='File to track download progress. Default: ./data/download_state.json'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: only download one lease for one year'
    )
    parser.add_argument(
        '--no-incremental',
        action='store_true',
        help='Disable incremental download (re-download everything)'
    )

    args = parser.parse_args()

    # Parse year range
    try:
        start_year, end_year = map(int, args.years.split('-'))
    except ValueError:
        print(f'Invalid year range: {args.years}', file=sys.stderr)
        sys.exit(1)

    # Load leases
    leases = load_leases(args.leases)

    if not leases:
        log.error('No leases to process. Run lease_discovery.py first.')
        sys.exit(1)

    # Set up download state (unless disabled)
    if args.no_incremental:
        state = None
        log.info('Incremental tracking disabled (--no-incremental)')
    else:
        state = DownloadState(args.state_file)
        stats = state.stats()
        if stats['leases'] > 0:
            log.info(f'Loaded download state: {stats["leases"]} leases, '
                     f'{stats["months"]} months tracked')
        else:
            log.info('No previous download state found — starting fresh')

    if args.test:
        # Test with first lease
        test_lease = leases[0]
        log.info(f'TEST MODE: Downloading production for lease {test_lease["lease_number"]}, '
                 f'years {start_year}-{end_year}')

        driver = create_driver()
        try:
            result = download_lease_production(
                driver,
                test_lease['lease_number'],
                test_lease['district'],
                test_lease['well_type'],
                start_year,
                end_year,
                state=state
            )
            if result is not None:
                log.info(f'Got {len(result)} new records')
                if result:
                    log.info(f'First record: {result[0]}')
                    save_records(result, './data/test_production.csv')
            else:
                log.warning('No data returned')
        finally:
            driver.quit()
    else:
        log.info(f'Downloading production data for {start_year}-{end_year}')
        log.info(f'Processing {len(leases)} leases')
        log.info(f'Output directory: {args.output_dir}')

        total = download_all(leases, start_year, end_year, args.output_dir, state=state)
        log.info(f'Done! Downloaded {total} new records')


if __name__ == '__main__':
    main()
