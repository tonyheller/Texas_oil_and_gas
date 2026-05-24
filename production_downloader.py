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


class DownloadState:
    """Tracks what production data has been downloaded, per lease."""

    def __init__(self, state_file):
        self.state_file = Path(state_file)
        self._data = self._load()

    def _load(self):
        if self.state_file.exists():
            with open(self.state_file, 'r') as f:
                return json.load(f)
        return {'leases': {}}

    def save(self):
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.state_file, 'w') as f:
            json.dump(self._data, f, indent=2)

    def get_county(self, lease_key):
        """Get cached county name for a lease, or None."""
        lease_state = self._data['leases'].get(lease_key, {})
        return lease_state.get('_county')

    def set_county(self, lease_key, county_name):
        """Cache county name for a lease."""
        if lease_key not in self._data['leases']:
            self._data['leases'][lease_key] = {}
        self._data['leases'][lease_key]['_county'] = county_name

    def get_lat_lon(self, lease_key):
        """Get cached lat/lon for a lease."""
        lease_state = self._data['leases'].get(lease_key, {})
        lat = lease_state.get('_lat')
        lon = lease_state.get('_lon')
        if lat is not None and lon is not None:
            return (lat, lon)
        return None

    def set_lat_lon(self, lease_key, lat, lon):
        """Cache lat/lon for a lease."""
        if lease_key not in self._data['leases']:
            self._data['leases'][lease_key] = {}
        self._data['leases'][lease_key]['_lat'] = lat
        self._data['leases'][lease_key]['_lon'] = lon

    def get_operator(self, lease_key):
        """Get cached operator info for a lease."""
        lease_state = self._data['leases'].get(lease_key, {})
        name = lease_state.get('_operator')
        no = lease_state.get('_operator_no')
        if name:
            return (name, no)
        return None

    def set_operator(self, lease_key, name, no):
        """Cache operator info for a lease."""
        if lease_key not in self._data['leases']:
            self._data['leases'][lease_key] = {}
        self._data['leases'][lease_key]['_operator'] = name
        self._data['leases'][lease_key]['_operator_no'] = no

    def get_api_id(self, lease_key):
        """Get cached EWA API ID for a lease."""
        lease_state = self._data['leases'].get(lease_key, {})
        return lease_state.get('_api_id')

    def set_api_id(self, lease_key, api_id):
        """Cache EWA API ID for a lease."""
        if lease_key not in self._data['leases']:
            self._data['leases'][lease_key] = {}
        self._data['leases'][lease_key]['_api_id'] = api_id

    def get_downloaded_months(self, lease_key):
        """
        Return set of (year, month) tuples already downloaded for a lease.

        lease_key: 'district/lease_number' e.g. '01/162326'
        """
        lease_state = self._data['leases'].get(lease_key, {})
        months = set()
        for year_str, month_list in lease_state.items():
            # Skip internal keys like _county
            if year_str.startswith('_'):
                continue
            if isinstance(month_list, list):
                for m in month_list:
                    try:
                        months.add((int(year_str), m))
                    except ValueError:
                        pass
        return months

    def record_downloaded(self, lease_key, records):
        """
        Mark specific (year, month) combos as downloaded.

        records: list of dicts with 'year' and 'month' keys
        """
        if lease_key not in self._data['leases']:
            self._data['leases'][lease_key] = {}

        for rec in records:
            year = str(rec['year'])
            month = rec['month']
            if year not in self._data['leases'][lease_key]:
                self._data['leases'][lease_key][year] = []
            if month not in self._data['leases'][lease_key][year]:
                self._data['leases'][lease_key][year].append(month)

    def needs_download(self, lease_key, start_year, end_year):
        """
        Determine what (year, month) ranges still need downloading.

        Returns (needed, already_have) tuple:
          needed: list of (start, end) year ranges that need downloading
          already_have: count of months already downloaded in the requested range
        """
        have = self.get_downloaded_months(lease_key)

        # Build set of all months in requested range
        all_months = set()
        for year in range(start_year, end_year + 1):
            for month in range(1, 13):
                all_months.add((year, month))

        missing = all_months - have
        already_count = len(all_months & have)

        if not missing:
            return [], already_count

        # Consolidate missing months into year ranges
        missing_years = sorted(set(y for y, m in missing))
        ranges = []
        if missing_years:
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
        total_leases = len(self._data['leases'])
        total_months = sum(
            len(months)
            for lease_state in self._data['leases'].values()
            for key, months in lease_state.items()
            if not key.startswith('_')  # Skip metadata keys
        )
        return {'leases': total_leases, 'months': total_months}


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
        driver.get(url)
        time.sleep(5)

        html = driver.page_source

        # Parse: GIS LAT (NAD83) and GIS LONG (NAD83) from HTML table
        lat_match = re.search(r'GIS LAT \(NAD83\)</th>\s*<td[^>]*>([\d.\-]+)</td>', html)
        lon_match = re.search(r'GIS LONG \(NAD83\)</th>\s*<td[^>]*>([\d.\-]+)</td>', html)

        if lat_match and lon_match:
            lat = float(lat_match.group(1))
            lon = float(lon_match.group(1))
            log.debug(f'GIS Viewer: lat={lat}, lon={lon} for API {api_id}')
            return (lat, lon)

        # Fallback to NAD27 if NAD83 not found
        lat_match = re.search(r'GIS LAT \(NAD27\)</th>\s*<td[^>]*>([\d.\-]+)</td>', html)
        lon_match = re.search(r'GIS LONG \(NAD27\)</th>\s*<td[^>]*>([\d.\-]+)</td>', html)

        if lat_match and lon_match:
            lat = float(lat_match.group(1))
            lon = float(lon_match.group(1))
            log.debug(f'GIS Viewer (NAD27): lat={lat}, lon={lon} for API {api_id}')
            return (lat, lon)

        log.debug(f'No lat/lon found in GIS Viewer for API {api_id}')
        return None, None

    except Exception as e:
        log.debug(f'GIS Viewer lookup failed for {api_id}: {e}')
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
            return cached

    try:
        # Step 1: Search by lease number + district in Wellbore Query
        driver.get(EWA_WELLBORE_URL)
        time.sleep(2)

        # Check for session timeout or login redirect
        if 'Login' in driver.title or 'Choose an Application' in driver.page_source:
            log.debug('EWA session expired')
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
        driver.find_element(By.CSS_SELECTOR, 'input[type="submit"]').click()
        time.sleep(3)

        # Check results
        if 'No results found' in driver.page_source:
            log.debug(f'No wellbore results for lease {lease_number}, district {district}')
            return None, None

        # Extract the API ID from the results (e.g., "31133330")
        source = driver.page_source
        api_id_match = re.search(
            r'leaseDetailAction\.do\?[^>]*apiNo=(\d+)',
            source
        )
        if not api_id_match:
            log.debug(f'No API ID found in wellbore results for lease {lease_number}')
            return None, None

        api_id = api_id_match.group(1)

        # Cache the API ID for future GIS lookups
        if state and lease_key:
            state.set_api_id(lease_key, api_id)
            state.save()

        # Step 2: Click the API number link to go to Lease Detail page
        # (direct URL navigation causes session errors)
        api_link = driver.find_element(By.LINK_TEXT, api_id)
        api_link.click()
        time.sleep(4)

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
        # Find and click County Production link
        county_links = driver.find_elements(By.LINK_TEXT, 'County Production')
        if not county_links:
            return None

        county_links[0].click()
        time.sleep(3)

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
                return county_name

        # Fallback: look for county name in visible text near production numbers
        body_text = driver.find_element(By.TAG_NAME, 'body').text
        for county_name in TEXAS_COUNTY_FIPS:
            # County name followed by a number (production value)
            if re.search(rf'\b{county_name}\b\s+[\d,]', body_text):
                return county_name

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
        view_all_links = driver.find_elements(By.LINK_TEXT, 'View All Results')
        if view_all_links:
            view_all_links[0].click()
            time.sleep(3)

        # Get page source
        source = driver.page_source

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
        else:
            # Try without well number
            lease_match = re.search(
                r'Lease Name:\s*([^,]*),\s*Lease No:\s*(\d+)', source
            )
            if lease_match:
                lease_info['lease_name'] = lease_match.group(1).strip()
                lease_info['lease_number'] = lease_match.group(2)

        # Extract district
        district_match = re.search(r'District\s+(\d{2})', source)
        if district_match:
            lease_info['district'] = district_match.group(1)

        # Get county (from cache or by navigating to County Production view)
        county_name = None
        if state and lease_key:
            county_name = state.get_county(lease_key)

        if not county_name:
            county_name = _extract_county(driver, source)
            if county_name and state and lease_key:
                state.set_county(lease_key, county_name)
                state.save()

        if county_name:
            lease_info['county'] = county_name
            api = build_api_number(
                lease_info.get('lease_number', ''),
                county_name,
                lease_info.get('well_number', '')
            )
            if api:
                lease_info['api_number'] = api
        
        # Extract operator and field from the first data row in the table.
        # The HTML structure for each row is:
        # <tr><td><strong>Month Year</strong></td>
        #     <td>gas_prod</td><td>gas_disp</td>
        #     <td>oil_prod</td><td>oil_disp</td>
        #     <td>Operator Name</td><td>Operator No.</td>
        #     <td>Field Name</td><td>Field No.</td></tr>
        # Operator/field only appear in the first row; subsequent rows have empty cells.
        if not lease_info.get('operator'):
            op_match = re.search(
                r'<tr[^>]*>.*?<strong>\s*(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4}\s*</strong>'
                r'</td>\s*<td[^>]*>.*?</td>\s*<td[^>]*>.*?</td>'
                r'\s*<td[^>]*>.*?</td>\s*<td[^>]*>.*?</td>'
                r'\s*<td[^>]*>\s*([A-Z][A-Z\s\.\&\(\)\-]+?)\s*</td>'
                r'\s*<td[^>]*>\s*(\d+)\s*</td>'
                r'\s*<td[^>]*>\s*([A-Z][A-Z\s\.\(\)\-]+?)\s*</td>'
                r'\s*<td[^>]*>\s*(\d+)\s*</td>',
                source, re.DOTALL
            )
            if op_match:
                lease_info['operator'] = op_match.group(1).strip()
                lease_info['operator_no'] = op_match.group(2).strip()
                lease_info['field'] = op_match.group(3).strip()
                lease_info['field_no'] = op_match.group(4).strip()
        
        # Look for table rows with monthly data
        # Pattern: <td><strong>Jan 2020</strong></td> followed by value cells
        # "Jan 2020 932 932 0 0"
        
        # Find all table rows
        rows = re.findall(r'<tr[^>]*>(.*?)</tr>', source, re.DOTALL)
        
        # Track operator/field info (appears in first data row)
        operator_found = False
        
        # Process rows looking for month data
        for row in rows:
            # Look for month in this row
            month_match = re.search(r'<strong>\s*(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{4})\s*</strong>', row)
            
            if month_match:
                month = month_match.group(1)
                year = month_match.group(2)
                
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
        
        log.info(f'Extracted {len(records)} monthly records')
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
            log.debug(f'Lease {lease_key}: all {already_count} months already downloaded')
            return []

        # Use the needed ranges (combine if multiple)
        effective_start = ranges[0][0]
        effective_end = ranges[-1][1]
        log.debug(f'Lease {lease_key}: need {effective_start}-{effective_end} '
                  f'({already_count} months already have)')
    else:
        effective_start = start_year
        effective_end = end_year

    try:
        # Navigate to Specific Lease Query
        driver.get(f'{PDQ_BASE}/PDQ/quickLeaseReportBuilderAction.do')
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
        submit_btn = driver.find_element(By.XPATH, '//input[@type="submit" and @value="Submit"]')
        submit_btn.click()
        
        time.sleep(4)
        
        # Handle alerts
        try:
            alert = Alert(driver)
            alert_text = alert.text
            if 'invalid' in alert_text.lower() or 'not found' in alert_text.lower():
                log.debug(f'Lease {lease_number} invalid or not found')
                alert.accept()
                return []
            alert.accept()
        except:
            pass
        
        # Check results
        page_source = driver.page_source
        
        if 'Session Timed Out' in page_source:
            log.warning('Session timed out after submit')
            return None
        
        if 'No Data Found' in page_source or 'No Matches Found' in page_source:
            log.debug(f'No data for lease {lease_number}, {start_year}-{end_year}')
            return []
        
        # Extract production data
        all_records = extract_production_data(driver, state=state, lease_key=lease_key)

        # Add well_type to each record (from query parameter, not on page)
        if all_records:
            for rec in all_records:
                rec['well_type'] = well_type

            lease_key = f'{district}/{lease_number}'

            # --- Look up operator via EWA if not found on PDQ page ---
            operator_name = all_records[0].get('operator', '')
            operator_no = all_records[0].get('operator_no', '')
            if not operator_name and state:
                op_name, op_no = lookup_operator(
                    driver, district, lease_number, lease_key, state=state
                )
                if op_name:
                    operator_name = op_name
                    operator_no = op_no or ''

            # --- Look up lat/lon via GIS Viewer ---
            lat = None
            lon = None

            if state and lease_key:
                # Check cache first
                cached = state.get_lat_lon(lease_key)
                if cached:
                    lat, lon = cached
                else:
                    # Try to get EWA API ID from cache
                    api_id = state.get_api_id(lease_key)
                    if api_id:
                        lat, lon = lookup_lat_lon_from_gis_viewer(driver, api_id)
                    else:
                        # Need to query EWA first to get API ID
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

        # Filter to only new records (exclude already-downloaded months)
        if state and all_records:
            have = state.get_downloaded_months(lease_key)
            new_records = []
            for rec in all_records:
                key = (int(rec['year']), rec['month'])
                if key not in have:
                    new_records.append(rec)
            all_records = new_records

        # Update state with what we just downloaded
        if state and all_records:
            state.record_downloaded(lease_key, all_records)
            state.save()

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
