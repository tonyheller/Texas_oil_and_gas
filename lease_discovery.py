#!/usr/bin/env python3
"""
Lease discovery system for Texas RRC PDQ.

Searches for leases using common name patterns to build a lease database,
then downloads production data for discovered leases.

Usage:
    python lease_discovery.py [--districts 01,02,...] [--patterns AAA,BBB,...] [--output ./leases.csv]
"""

import argparse
import csv
import json
import logging
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import Select
from selenium.webdriver.common.alert import Alert
from selenium.common.exceptions import TimeoutException, NoSuchElementException

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger(__name__)

PDQ_BASE = 'https://webapps.rrc.texas.gov'

# Common patterns to search for lease names (MUST be 3+ characters)
# Single letters and common prefixes should catch most leases
COMMON_PATTERNS = [
    'AAA', 'ABB', 'ABC', 'ACE', 'ADA', 'ADO', 'AGE', 'ALE', 'ALL', 'AMA',
    'ANA', 'AND', 'ANN', 'APE', 'ARC', 'ARK', 'ARM', 'ASH', 'ATE', 'AUB',
    'BAD', 'BAR', 'BAY', 'BEE', 'BEL', 'BEN', 'BIG', 'BIR', 'BLE', 'BLU',
    'BOG', 'BOW', 'BOX', 'BOY', 'BRA', 'BRO', 'BRU', 'BRY', 'BUCK', 'BUF',
    'BUR', 'BUS', 'BYR', 'CAD', 'CAL', 'CAM', 'CAN', 'CAR', 'CAT', 'CED',
    'CHA', 'CHE', 'CHO', 'CIT', 'CLAY', 'CLE', 'CLI', 'CLO', 'COA', 'COD',
    'COL', 'COM', 'CON', 'COO', 'COR', 'COS', 'COV', 'COW', 'CRA', 'CRE',
    'CRO', 'CRY', 'CUB', 'CUT', 'DAL', 'DAN', 'DAV', 'DAY', 'DEE', 'DEL',
    'DEN', 'DEW', 'DIA', 'DIN', 'DOG', 'DON', 'DOT', 'DOV', 'DOW', 'DRY',
    'DUB', 'DUN', 'DUR', 'EAG', 'EAR', 'EAS', 'EDG', 'EDW', 'ELL', 'ELM',
    'ENG', 'ERS', 'ESC', 'ESS', 'EST', 'ETH', 'EUN', 'EVA', 'EVE', 'EWI',
    'FAL', 'FAN', 'FAR', 'FAY', 'FED', 'FEE', 'FEL', 'FEN', 'FER', 'FIN',
    'FIS', 'FIT', 'FLA', 'FLO', 'FLU', 'FOG', 'FOR', 'FOX', 'FRE', 'FUL',
    'GAL', 'GAM', 'GAR', 'GAS', 'GAY', 'GEO', 'GER', 'GIB', 'GIL', 'GIN',
    'GLO', 'GOD', 'GOO', 'GOR', 'GOT', 'GRA', 'GRE', 'GRI', 'GRO', 'GUL',
    'HAG', 'HAM', 'HAN', 'HAR', 'HAS', 'HAT', 'HAY', 'HEL', 'HEN', 'HIC',
    'HIL', 'HOD', 'HOG', 'HOL', 'HOP', 'HOU', 'HOW', 'HUB', 'HUD', 'HUN',
    'IAN', 'ICE', 'IDA', 'ILL', 'IND', 'ING', 'INK', 'ION', 'IRE', 'IRV',
    'JAC', 'JAM', 'JAY', 'JEN', 'JES', 'JEW', 'JIM', 'JOH', 'JON', 'JOR',
    'JUD', 'KAY', 'KEE', 'KEN', 'KID', 'KIN', 'KIT', 'LAB', 'LAC', 'LAF',
    'LAG', 'LAN', 'LAR', 'LAS', 'LAT', 'LEE', 'LEG', 'LEN', 'LEO', 'LES',
    'LEV', 'LEW', 'LEY', 'LIL', 'LIN', 'LIT', 'LIV', 'LOG', 'LON', 'LOU',
    'LOW', 'LUC', 'LUF', 'LYN', 'MAC', 'MAD', 'MAN', 'MAR', 'MAS', 'MAT',
    'MAY', 'MCD', 'MCK', 'MEL', 'MER', 'MIA', 'MIC', 'MID', 'MIL', 'MIN',
    'MIS', 'MIT', 'MOB', 'MOC', 'MOD', 'MOO', 'MOR', 'MOS', 'MOT', 'MUD',
    'NAN', 'NAT', 'NEE', 'NEW', 'NIB', 'NIC', 'NOL', 'NOR', 'OAK', 'OIL',
    'OLD', 'ONE', 'ORE', 'ORI', 'OSW', 'OTT', 'OWE', 'OXF', 'PAL', 'PAR',
    'PAT', 'PAU', 'PAY', 'PEA', 'PEE', 'PEN', 'PER', 'PET', 'PHE', 'PIE',
    'PIN', 'PIT', 'PLY', 'POC', 'POE', 'POL', 'PON', 'POP', 'POR', 'POS',
    'PRE', 'PRI', 'PRO', 'PUL', 'PUR', 'QUE', 'QUI', 'RAD', 'RAL', 'RAM',
    'RAN', 'RAP', 'RAY', 'REA', 'RED', 'REE', 'RES', 'RHO', 'RIC', 'RID',
    'RIG', 'RIL', 'RIS', 'RIV', 'ROA', 'ROB', 'ROC', 'ROD', 'ROG', 'ROL',
    'ROM', 'ROO', 'ROS', 'ROW', 'ROY', 'RUB', 'RUD', 'RUG', 'RUP', 'RUS',
    'SAC', 'SAD', 'SAL', 'SAN', 'SAP', 'SAT', 'SAU', 'SAV', 'SAY', 'SEA',
    'SEN', 'SER', 'SHA', 'SHE', 'SHI', 'SHO', 'SIC', 'SIM', 'SIN', 'SIS',
    'SKI', 'SMI', 'SMY', 'SOM', 'SON', 'SOR', 'SOU', 'SPA', 'SPI', 'SPR',
    'STA', 'STE', 'STO', 'STR', 'STU', 'SUL', 'SUN', 'SUP', 'SUR', 'SWI',
    'SYL', 'SYR', 'TAM', 'TAN', 'TAY', 'TED', 'TEN', 'TER', 'TEX', 'THE',
    'THO', 'TIL', 'TIM', 'TIT', 'TOB', 'TOD', 'TOM', 'TON', 'TOP', 'TOR',
    'TOW', 'TRI', 'TRO', 'TUB', 'TUC', 'TUN', 'TUR', 'UNI', 'UNIT', 'UPP',
    'VAN', 'VAS', 'VER', 'VIA', 'VIC', 'VIL', 'VIN', 'VIS', 'VOL', 'WAD',
    'WAL', 'WAN', 'WAR', 'WAT', 'WAX', 'WAY', 'WEB', 'WEL', 'WEN', 'WES',
    'WHI', 'WIC', 'WIL', 'WIN', 'WIS', 'WOA', 'WOL', 'WOO', 'WOR', 'WRI',
    'YAK', 'YAL', 'YAR', 'YEA', 'YOR', 'YOU', 'ZAC', 'ZAR', 'ZEE'
]

# All Texas RRC districts
ALL_DISTRICTS = ['01', '02', '03', '04', '05', '06', '6E', '7B', '7C', '08', '8A', '09', '10']

# District code mapping (form values)
DISTRICT_MAP = {
    '01': '01', '02': '02', '03': '03', '04': '04', '05': '05',
    '06': '06', '6E': '07', '7B': '08', '7C': '09', '08': '10',
    '8A': '11', '09': '13', '10': '14'
}


def create_driver():
    """Create a Chrome WebDriver."""
    chrome_options = Options()
    chrome_options.add_argument('--headless=new')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--disable-gpu')
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(60)
        return driver
    except Exception as e:
        log.error(f'Failed to create Chrome driver: {e}')
        raise


def search_leases(driver, district, pattern):
    """
    Search for leases in a district matching a pattern.
    
    Returns a list of dicts with lease info.
    """
    leases = []

    try:
        # Navigate to lease search
        driver.get(f'{PDQ_BASE}/PDQ/leaseSearchAction.do')
        time.sleep(2)

        # Check for session timeout BEFORE interacting with form elements
        if 'Session Timed Out' in driver.page_source:
            log.warning('Session timed out on initial page load')
            return None  # Signal to recreate driver

        # Select district (this will fail if page didn't load properly)
        try:
            district_select = Select(driver.find_element(By.NAME, 'district'))
        except Exception:
            log.warning('Could not find district select — page may not have loaded')
            return None

        district_value = DISTRICT_MAP.get(district, district)
        district_select.select_by_value(district_value)
        
        # Select "begins with"
        begins_radio = driver.find_element(By.XPATH, '//input[@name="leaseSearchCriteria" and @value="beginsWith"]')
        begins_radio.click()
        
        # Enter pattern
        search_input = driver.find_element(By.NAME, 'leaseSearchValue')
        search_input.clear()
        search_input.send_keys(pattern)
        
        # Submit
        submit_buttons = driver.find_elements(By.XPATH, '//input[@type="submit"]')
        for btn in submit_buttons:
            if btn.get_attribute('value') == 'Submit':
                btn.click()
                break
        
        time.sleep(3)
        
        # Handle alerts
        try:
            alert = Alert(driver)
            alert_text = alert.text
            if 'cannot be less than' in alert_text:
                log.debug(f'Pattern too short: {pattern}')
                alert.accept()
                return []
            alert.accept()
        except:
            pass
        
        # Check for results
        page_source = driver.page_source
        all_text = page_source  # Make available for regex below
        
        if 'Session Timed Out' in page_source:
            log.warning('Session timed out')
            return None  # Signal to recreate driver
        
        if 'No Matches Found' in page_source:
            log.debug(f'No leases for {district}/{pattern}')
            return []
        
        # Extract lease information from the select options
        # Format: LEASE_NUM^0^NAME^1^OIL_OR_GAS^2^DISTRICT^3^EXTRA
        import re
        
        # Find all option values in the LeaseSearchResultForm
        option_pattern = r'<option[^>]*value="(\d+)\^0\^([^^]+)\^1\^([OG])\^2\^(\d{2})\^3\^([^"]*)"[^>]*>'
        option_matches = re.findall(option_pattern, all_text)
        
        for lease_num, name, well_type, district_code, extra in option_matches:
            leases.append({
                'lease_number': lease_num.lstrip('0') or '0',  # Remove leading zeros
                'name': name.strip(),
                'well_type': 'Oil' if well_type == 'O' else 'Gas',
                'district': district_code,
                'pattern': pattern
            })
        
        # Also extract from display text as backup: (DISTRICT-LEASE_NUM):NAME
        if not leases:
            display_pattern = r'\((\d{2})-(\d+)\):([A-Z0-9\s]*)'
            display_matches = re.findall(display_pattern, all_text)
            for district_code, lease_num, name in display_matches:
                leases.append({
                    'lease_number': lease_num.lstrip('0') or '0',
                    'name': name.strip(),
                    'well_type': 'Unknown',  # Can't determine from display text
                    'district': district_code,
                    'pattern': pattern
                })
        
        log.info(f'Found {len(leases)} leases for {district}/{pattern}')
        return leases

    except Exception as e:
        log.warning(f'Error searching {district}/{pattern}: {e} (will retry)')
        return None


def discover_leases(districts, patterns, output_file, state_file=None, clear_history=False):
    """
    Discover leases by searching common patterns across districts.
    
    state_file: path to file that tracks completed (district, pattern) searches
    clear_history: if True, ignore existing state and redo all searches
    """
    output_path = Path(output_file)

    # Load discovery state
    state = {}
    if state_file and not clear_history:
        state_path = Path(state_file)
        if state_path.exists():
            with open(state_path) as f:
                state = json.load(f)
            completed = sum(len(pats) for pats in state.values())
            total = len(districts) * len(patterns)
            log.info(f'Loaded discovery state: {completed}/{total} searches already done')

    def mark_completed(district, pattern):
        """Record that a (district, pattern) search is complete."""
        if district not in state:
            state[district] = []
        if pattern not in state[district]:
            state[district].append(pattern)

    def is_completed(district, pattern):
        """Check if a (district, pattern) search has already been done."""
        return pattern in state.get(district, [])

    def save_state():
        """Persist discovery state to file."""
        if state_file:
            state_path = Path(state_file)
            state_path.parent.mkdir(parents=True, exist_ok=True)
            with open(state_path, 'w') as f:
                json.dump(state, f, indent=2)

    driver = create_driver()
    all_leases = {}  # Use dict to avoid duplicates, keyed by (lease_number, district)
    
    try:
        # Count how many searches will actually run
        pending = sum(
            1 for d in districts for p in patterns if not is_completed(d, p)
        )
        total_searches = len(districts) * len(patterns)
        log.info(f'Total: {total_searches} searches, {total_searches - pending} already done, {pending} remaining')

        search_count = 0

        for district in districts:
            for pattern in patterns:
                if is_completed(district, pattern):
                    log.debug(f'Skipping already completed: {district}/"{pattern}"')
                    continue

                search_count += 1
                log.info(f'Search {search_count}/{pending}: District {district}, Pattern "{pattern}"')

                result = search_leases(driver, district, pattern)

                if result is None:
                    # Session timed out - recreate driver
                    log.warning('Recreating driver due to session timeout')
                    driver.quit()
                    driver = create_driver()
                    # Retry this search
                    result = search_leases(driver, district, pattern)
                    if result is None:
                        driver.quit()
                        driver = create_driver()
                        result = search_leases(driver, district, pattern)

                # Mark this search as completed regardless of result
                mark_completed(district, pattern)
                save_state()

                if result:
                    for lease in result:
                        key = (lease['lease_number'], lease['district'])
                        if key not in all_leases:
                            all_leases[key] = lease

                # Rate limiting
                time.sleep(1)
        
        # Save discovered leases
        if all_leases:
            log.info(f'Saving {len(all_leases)} unique leases to {output_file}')
            with open(output_path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(['lease_number', 'district', 'name', 'well_type'])
                for lease in sorted(all_leases.values(), key=lambda x: (x['district'], x['lease_number'])):
                    writer.writerow([
                        lease['lease_number'],
                        lease['district'],
                        lease['name'],
                        lease['well_type']
                    ])
        else:
            log.warning('No leases discovered')
        
        return len(all_leases)
        
    finally:
        driver.quit()


def main():
    parser = argparse.ArgumentParser(
        description='Discover Texas RRC leases by searching common name patterns'
    )
    parser.add_argument(
        '--districts',
        type=str,
        default=','.join(ALL_DISTRICTS),
        help=f'Comma-separated district codes. Default: all'
    )
    parser.add_argument(
        '--patterns',
        type=str,
        default=','.join(COMMON_PATTERNS[:5]),  # Start with just A-E
        help=f'Comma-separated search patterns. Default: first 5 letters'
    )
    parser.add_argument(
        '--output',
        type=str,
        default='./leases_discovered.csv',
        help='Output file for discovered leases'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Test mode: only search one district with one pattern'
    )
    parser.add_argument(
        '--state-file',
        type=str,
        default='./data/discovery_state.json',
        help='File to track completed searches. Default: ./data/discovery_state.json'
    )
    parser.add_argument(
        '--clear-history',
        action='store_true',
        help='Ignore previous discovery state and redo all searches'
    )
    
    args = parser.parse_args()
    
    districts = [d.strip() for d in args.districts.split(',')]
    patterns = [p.strip() for p in args.patterns.split(',')]
    
    if args.test:
        test_district = districts[0] if districts else '01'
        test_pattern = patterns[0] if patterns else 'SMI'  # SMI catches SMITH leases
        log.info(f'TEST MODE: Searching district {test_district}, pattern "{test_pattern}"')
        driver = create_driver()
        try:
            result = search_leases(driver, test_district, test_pattern)
            if result:
                log.info(f'Found {len(result)} leases')
                for lease in result[:5]:
                    log.info(f'  {lease}')
            else:
                log.info('No leases found')
        finally:
            driver.quit()
    else:
        if args.clear_history:
            state_path = Path(args.state_file)
            if state_path.exists():
                state_path.unlink()
            log.info('Discovery history cleared (--clear-history)')

        log.info(f'Discovering leases for {len(districts)} districts, {len(patterns)} patterns')
        count = discover_leases(
            districts, patterns, args.output,
            state_file=args.state_file,
            clear_history=args.clear_history
        )
        log.info(f'Discovery complete: {count} unique leases')


if __name__ == '__main__':
    main()
