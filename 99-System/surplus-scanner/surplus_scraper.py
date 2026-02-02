#!/usr/bin/env python3
"""
Surplus Sales Alberta Scraper
Part of Albatross Phase 7 - Surplus Automation Module

Scrapes https://www.surplus.gov.ab.ca for auction items in monitored categories.
Filters for Calgary location and active auctions only.

Site uses ASP.NET with server-rendered HTML. No JavaScript/Selenium needed.
"""

import re
import logging
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Base URLs
BASE_URL = "https://www.surplus.gov.ab.ca"
AUCTION_BASE = f"{BASE_URL}/OA"

# Target categories to monitor (verified against site)
# Site categories: Audio-Visual(46), Computer Equipment(49), Lab Equipment(52),
# Medical/Veterinarian(55), Others(57), Office Equipment(56)
CATEGORIES = {
    '46': 'Audio/Visual Equipment',
    '49': 'Computers/Displays',
    '52': 'Lab/Scientific',
    '55': 'Medical/Accessibility',
    '57': 'Office Tech/GPS',
}

# Required location filter
TARGET_LOCATION = "Surplus Sales Calgary"

# Request configuration
REQUEST_TIMEOUT = 15
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Connection': 'keep-alive',
}


class SurplusScraper:
    """Scraper for Alberta Government Surplus Sales website."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(REQUEST_HEADERS)

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch a page and return BeautifulSoup object."""
        try:
            logger.info(f"Fetching: {url}")
            response = self.session.get(url, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.Timeout:
            logger.error(f"Timeout fetching {url}")
            return None
        except requests.RequestException as e:
            logger.error(f"Request failed for {url}: {e}")
            return None

    def _parse_price(self, price_text: str) -> float:
        """Extract numeric price from text like '$125.00' or 'CAD 125.00'."""
        if not price_text:
            return 0.0
        cleaned = re.sub(r'[^\d.]', '', price_text)
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def _parse_end_date(self, date_str: str) -> tuple[str, bool]:
        """
        Parse end date and determine if auction is active.
        Returns (formatted_date_str, is_active).
        """
        if not date_str:
            return '', True

        date_str = date_str.strip()

        # Site uses ISO-like format: "YYYY-MM-DDTHH:MM:SS" or "MM/DD/YYYY HH:MM:SS AM/PM"
        formats = [
            '%Y-%m-%dT%H:%M:%S',  # ISO format from closingdate attribute
            '%Y-%m-%d %H:%M:%S',
            '%m/%d/%Y %I:%M:%S %p',
            '%m/%d/%Y %H:%M:%S',
            '%Y-%m-%d',
            '%m/%d/%Y',
        ]

        for fmt in formats:
            try:
                end_date = datetime.strptime(date_str, fmt)
                is_active = end_date > datetime.now()
                # Return ISO format for consistency
                return end_date.strftime('%Y-%m-%d %H:%M:%S'), is_active
            except ValueError:
                continue

        # If parsing fails, return original and assume active
        return date_str, True

    def _get_category_url(self, category_id: str) -> str:
        """Build URL for a specific category listing."""
        return f"{AUCTION_BASE}/ItemList.aspx?categoryID={category_id}"

    def _scrape_category(self, category_id: str) -> list[dict]:
        """Scrape all items from a single category."""
        items = []
        category_name = CATEGORIES.get(category_id, 'Unknown')
        url = self._get_category_url(category_id)

        soup = self._fetch_page(url)
        if not soup:
            return items

        # Find the GridView table containing auction items
        gridview = soup.find('table', id=re.compile(r'GridView1', re.I))
        if not gridview:
            # Try alternate table patterns
            gridview = soup.find('table', class_=re.compile(r'grid|list', re.I))

        if not gridview:
            logger.warning(f"No item grid found for category {category_id}")
            return items

        # Get all data rows (skip header row)
        rows = gridview.find_all('tr')
        if len(rows) <= 1:
            logger.info(f"No items in category {category_id}")
            return items

        # Skip header row
        for row in rows[1:]:
            cells = row.find_all('td')
            if not cells:
                continue

            try:
                item = self._parse_row(cells, category_id, category_name)
                if item:
                    items.append(item)
            except Exception as e:
                logger.warning(f"Failed to parse row: {e}")
                continue

        logger.info(f"Found {len(items)} Calgary items in {category_name}")
        return items

    def _parse_row(self, cells: list, category_id: str, category_name: str) -> Optional[dict]:
        """Parse a table row into an item dictionary."""

        # Extract item ID from the first link (cell 0 has just the ID)
        item_id = None
        title = 'Unknown Item'
        item_url = AUCTION_BASE

        # First, find the auction ID from any ItemDetail link
        for cell in cells:
            link = cell.find('a', href=re.compile(r'ItemDetail\.aspx', re.I))
            if link:
                href = link.get('href', '')
                item_url = urljoin(AUCTION_BASE + '/', href)
                id_match = re.search(r'AuctionID=(\d+)', href, re.I)
                if id_match:
                    item_id = id_match.group(1)
                break

        if not item_id:
            return None

        # Find the title - look for link with 'hlTitle' in its ID (contains actual item name)
        for cell in cells:
            title_link = cell.find('a', id=re.compile(r'hlTitle', re.I))
            if title_link:
                title = title_link.get_text(strip=True)
                break

        # If no hlTitle found, try finding a descriptive link (not just the ID)
        if title == 'Unknown Item':
            for cell in cells:
                for link in cell.find_all('a', href=re.compile(r'ItemDetail\.aspx', re.I)):
                    link_text = link.get_text(strip=True)
                    # Skip if text is just the auction ID
                    if link_text and link_text != item_id and not link_text.isdigit():
                        title = link_text
                        break
                if title != 'Unknown Item':
                    break

        # Extract current bid - look for span with lblHighBidAmt in id
        current_bid = 0.0
        for cell in cells:
            bid_span = cell.find('span', id=re.compile(r'lblHighBidAmt|HighBid', re.I))
            if bid_span:
                current_bid = self._parse_price(bid_span.get_text())
                break
            # Also check for starting bid if no high bid
            start_bid = cell.find('span', id=re.compile(r'lblStartBid|StartingBid', re.I))
            if start_bid and current_bid == 0.0:
                current_bid = self._parse_price(start_bid.get_text())

        # Extract bid count - site may not show this directly
        bid_count = 0
        for cell in cells:
            bid_count_elem = cell.find('span', id=re.compile(r'lblBidCount|NumBids', re.I))
            if bid_count_elem:
                bid_text = bid_count_elem.get_text()
                match = re.search(r'(\d+)', bid_text)
                if match:
                    bid_count = int(match.group(1))
                break

        # Extract end date from countdown div's closingdate attribute
        end_date = ''
        is_active = True
        for cell in cells:
            countdown = cell.find('div', id=re.compile(r'pnlCountdown', re.I))
            if countdown and countdown.get('closingdate'):
                end_date, is_active = self._parse_end_date(countdown['closingdate'])
                break
            # Also try span with closing date
            close_span = cell.find('span', id=re.compile(r'lblClose|ClosingDate', re.I))
            if close_span:
                end_date, is_active = self._parse_end_date(close_span.get_text())
                break

        # Skip ended auctions
        if not is_active:
            return None

        # Extract location
        location = ''
        for cell in cells:
            cell_text = cell.get_text(strip=True)
            if 'Surplus Sales' in cell_text:
                location = cell_text
                break
            # Check for location span
            loc_span = cell.find('span', id=re.compile(r'lblLocation|Location', re.I))
            if loc_span:
                location = loc_span.get_text(strip=True)
                break

        # Filter by Calgary location
        if TARGET_LOCATION.lower() not in location.lower():
            if 'calgary' not in location.lower():
                return None

        # Extract condition (usually "As-Is" for surplus)
        condition = 'As-Is'
        for cell in cells:
            cond_span = cell.find('span', id=re.compile(r'lblCondition|Condition', re.I))
            if cond_span:
                condition = cond_span.get_text(strip=True) or 'As-Is'
                break

        return {
            'item_id': str(item_id),
            'title': title,
            'category': category_id,
            'category_name': category_name,
            'current_bid': current_bid,
            'bid_count': bid_count,
            'end_date': end_date,
            'location': location,
            'url': item_url,
            'condition': condition,
        }

    def scrape_all_categories(self) -> list[dict]:
        """Scrape all monitored categories and return combined results."""
        all_items = []

        logger.info(f"Starting scrape of {len(CATEGORIES)} categories...")

        for category_id in CATEGORIES:
            try:
                items = self._scrape_category(category_id)
                all_items.extend(items)
            except Exception as e:
                logger.error(f"Failed to scrape category {category_id}: {e}")
                continue

        logger.info(f"Scrape complete. Total Calgary items found: {len(all_items)}")
        return all_items


def scrape_surplus_items() -> list[dict]:
    """
    Main entry point for scraping surplus items.
    Returns list of item dictionaries filtered for Calgary location.

    This function is intended to be imported by surplus_scanner.py
    """
    scraper = SurplusScraper()
    return scraper.scrape_all_categories()


if __name__ == '__main__':
    # Test run
    print("=" * 60)
    print("Alberta Surplus Sales Scraper - Test Run")
    print("=" * 60)

    items = scrape_surplus_items()

    if not items:
        print("\nNo Calgary items found in monitored categories.")
        print("This may be normal if no Calgary auctions are currently active.")
    else:
        print(f"\nFound {len(items)} Calgary items:\n")
        for item in items:
            print(f"  [{item['category']}] {item['title']}")
            print(f"    ID: {item['item_id']} | Bid: ${item['current_bid']:.2f} ({item['bid_count']} bids)")
            print(f"    Ends: {item['end_date']} | Location: {item['location']}")
            print(f"    URL: {item['url']}")
            print()
