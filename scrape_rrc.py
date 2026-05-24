import csv
import io
import re
import sys
from bs4 import BeautifulSoup
import requests
import pdfplumber

BASE_URL = "https://www.rrc.texas.gov"
URL = f"{BASE_URL}/oil-and-gas/research-and-statistics/well-information/oil-leases-and-gas-wells-by-district-and-operator/"

# Precompiled regex for PDF data rows
# Matches: OIL/GAS  lease_number  lease_name  field_number(8)  field_name  county_number  county_name
ROW_RE = re.compile(
    r'^(OIL|GAS)\s+(\d+)\s+(.+?)\s+(\d{8})\s+(.+?)\s+(\d{1,3})\s+(\S.*)$'
)


def get_latest_district_pdf_urls():
    print("Scraping RRC landing page for the latest district PDF links...", file=sys.stderr)
    try:
        response = requests.get(URL, headers={"User-Agent": "Mozilla/5.0"}, timeout=30)
        response.raise_for_status()
    except Exception as e:
        print(f"Error accessing RRC landing page: {e}", file=sys.stderr)
        return []

    soup = BeautifulSoup(response.text, 'html.parser')
    pdf_links = []
    links = soup.find_all('a', href=re.compile(r'\.pdf$', re.IGNORECASE))

    seen_districts = set()
    for link in links:
        text = link.get_text(strip=True)
        href = link.get('href')

        match = re.search(r'District\s+([0-9a-zA-Z]+)', text, re.IGNORECASE)
        if match:
            district_num = match.group(1).zfill(2) if match.group(1).isdigit() else match.group(1).upper()

            # Once we hit a duplicate district we've already seen, we've moved to older months.
            if district_num in seen_districts:
                break

            seen_districts.add(district_num)
            full_url = href if href.startswith('http') else BASE_URL + href
            pdf_links.append((district_num, full_url))

    return sorted(pdf_links, key=lambda x: x[0])


def parse_rrc_pdf(district, pdf_url, csv_writer):
    print(f"Downloading and parsing District {district}...", file=sys.stderr)
    try:
        pdf_response = requests.get(pdf_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=60)
        pdf_response.raise_for_status()
    except Exception as e:
        print(f"Failed to download PDF for District {district}: {e}", file=sys.stderr)
        return

    with pdfplumber.open(io.BytesIO(pdf_response.content)) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue

            for line in text.splitlines():
                line = line.strip()
                if not line.startswith('OIL ') and not line.startswith('GAS '):
                    continue

                # Skip header lines that happen to start with OIL/GAS
                if 'LEASES AND GAS WELLS BY' in line:
                    continue

                m = ROW_RE.match(line)
                if not m:
                    continue

                well_type_flag = m.group(1)
                lease_number = m.group(2)
                lease_name = m.group(3).strip()

                if not lease_number.isdigit() or not lease_name:
                    continue

                well_type = "Oil" if well_type_flag == "OIL" else "Gas"
                csv_writer.writerow([lease_number, district, lease_name, well_type])


def main():
    writer = csv.writer(sys.stdout, quoting=csv.QUOTE_MINIMAL)
    writer.writerow(['lease_number', 'district', 'name', 'well_type'])

    district_pdfs = get_latest_district_pdf_urls()
    if not district_pdfs:
        print("No index links found. The RRC site structure may have changed.", file=sys.stderr)
        return

    for district, pdf_url in district_pdfs:
        parse_rrc_pdf(district, pdf_url, writer)


if __name__ == "__main__":
    main()
