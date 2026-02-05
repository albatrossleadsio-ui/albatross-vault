#!/usr/bin/env python3
"""
Alberta Government Surplus Scanner
Scrapes surplus.gov.ab.ca for auction items in Calgary
"""

import json
import os
import re
import time
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

import requests
from bs4 import BeautifulSoup
import yaml

# Add parent directory for imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

try:
    from albatross_security_module import SecurityGuard
except ImportError:
    SecurityGuard = None


@dataclass
class SurplusItem:
    """Represents a surplus auction item"""
    item_id: str
    title: str
    description: str
    category: str
    category_id: int
    condition: str
    current_bid: float
    min_bid: Optional[float]
    num_bids: int
    auction_end: str
    location: str
    pickup_location: str
    url: str
    image_url: Optional[str]
    scraped_at: str
    status: str = "found"


class SurplusScanner:
    """
    Scrapes Alberta Government Surplus for auction items.

    Features:
    - Monitor specific categories (Electronics, Tools, Office Equipment)
    - Filter Calgary-only locations
    - Rate limiting (1 request/3 seconds)
    - SecurityGuard integration
    - JSON output to vault
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize surplus scanner.

        Args:
            config_path: Path to surplus.yaml config
        """
        self.config = self._load_config(config_path)
        self.session = requests.Session()
        self.guard = SecurityGuard() if SecurityGuard else None
        self.items: List[SurplusItem] = []
        self._request_count = 0

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from YAML file"""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "surplus.yaml"

        with open(config_path, 'r') as f:
            return yaml.safe_load(f)

    def _get_user_agent(self) -> str:
        """Get a random user agent from config"""
        agents = self.config.get('scanner', {}).get('user_agents', [
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        ])
        return random.choice(agents)

    def _rate_limit(self):
        """Enforce rate limiting between requests"""
        delay = self.config.get('scanner', {}).get('rate_limit_seconds', 3)
        if self._request_count > 0:
            time.sleep(delay)
        self._request_count += 1

    def _fetch_page(self, url: str) -> Optional[BeautifulSoup]:
        """Fetch and parse a page with rate limiting"""
        self._rate_limit()

        headers = {
            'User-Agent': self._get_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-CA,en-US;q=0.7,en;q=0.3',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }

        try:
            response = self.session.get(url, headers=headers, timeout=30)
            response.raise_for_status()
            return BeautifulSoup(response.text, 'html.parser')
        except requests.RequestException as e:
            print(f"Error fetching {url}: {e}")
            return None

    def _parse_price(self, price_text: str) -> float:
        """Parse price from text like '$25.00' or 'CAD 25.00'"""
        if not price_text:
            return 0.0
        # Remove currency symbols and whitespace
        cleaned = re.sub(r'[^0-9.]', '', price_text)
        try:
            return float(cleaned) if cleaned else 0.0
        except ValueError:
            return 0.0

    def _parse_auction_end(self, date_text: str) -> str:
        """Parse auction end date from various formats"""
        if not date_text:
            return datetime.now().isoformat()

        # Try common formats
        formats = [
            '%Y-%m-%d %H:%M:%S',
            '%Y-%m-%d %H:%M',
            '%B %d, %Y %H:%M',
            '%b %d, %Y %I:%M %p',
            '%m/%d/%Y %H:%M'
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(date_text.strip(), fmt)
                return parsed.isoformat()
            except ValueError:
                continue

        # Return as-is if parsing fails
        return date_text

    def _parse_item(self, item_element: BeautifulSoup, category_id: int, category_name: str) -> Optional[SurplusItem]:
        """Parse a single auction item from HTML"""
        try:
            # Extract item ID from URL or element
            link = item_element.find('a', href=re.compile(r'item|auction|lot', re.I))
            if not link:
                link = item_element.find('a')

            if not link:
                return None

            url = link.get('href', '')
            if not url.startswith('http'):
                url = self.config.get('scanner', {}).get('base_url', '') + url

            # Extract item ID
            item_id_match = re.search(r'(\d+)', url)
            item_id = item_id_match.group(1) if item_id_match else str(hash(url))[:8]

            # Extract title
            title_elem = item_element.find(['h2', 'h3', 'h4']) or link
            title = title_elem.get_text(strip=True) if title_elem else "Unknown Item"

            # Extract description
            desc_elem = item_element.find('p', class_=re.compile(r'desc|detail', re.I))
            if not desc_elem:
                desc_elem = item_element.find('div', class_=re.compile(r'desc|detail', re.I))
            description = desc_elem.get_text(strip=True) if desc_elem else ""

            # Extract condition
            condition_elem = item_element.find(string=re.compile(r'condition', re.I))
            condition = "Unknown"
            if condition_elem:
                condition_text = condition_elem.parent.get_text() if condition_elem.parent else str(condition_elem)
                if 'excellent' in condition_text.lower():
                    condition = "Excellent"
                elif 'good' in condition_text.lower():
                    condition = "Good"
                elif 'fair' in condition_text.lower():
                    condition = "Fair"
                elif 'poor' in condition_text.lower():
                    condition = "Poor"

            # Extract current bid
            bid_elem = item_element.find(string=re.compile(r'bid|price|current', re.I))
            current_bid = 0.0
            if bid_elem:
                bid_text = bid_elem.parent.get_text() if bid_elem.parent else str(bid_elem)
                current_bid = self._parse_price(bid_text)

            # Extract number of bids
            num_bids = 0
            bids_elem = item_element.find(string=re.compile(r'\d+\s*bids?', re.I))
            if bids_elem:
                bids_match = re.search(r'(\d+)\s*bids?', str(bids_elem), re.I)
                num_bids = int(bids_match.group(1)) if bids_match else 0

            # Extract auction end date
            date_elem = item_element.find(string=re.compile(r'ends?|closing', re.I))
            auction_end = datetime.now().isoformat()
            if date_elem:
                date_text = date_elem.parent.get_text() if date_elem.parent else str(date_elem)
                auction_end = self._parse_auction_end(date_text)

            # Extract location
            location_elem = item_element.find(string=re.compile(r'location|pickup', re.I))
            location = "Unknown"
            pickup_location = "Unknown"
            if location_elem:
                loc_text = location_elem.parent.get_text() if location_elem.parent else str(location_elem)
                location = loc_text.strip()
                pickup_location = location

            # Extract image URL
            img_elem = item_element.find('img')
            image_url = img_elem.get('src') if img_elem else None

            # Validate with SecurityGuard
            if self.guard:
                full_text = f"{title} {description}"
                validation = self.guard.validate(full_text, source="surplus")
                if not validation['safe']:
                    print(f"Skipping item {item_id}: failed security check")
                    return None

            return SurplusItem(
                item_id=f"surplus_{item_id}",
                title=title,
                description=description[:500],
                category=category_name,
                category_id=category_id,
                condition=condition,
                current_bid=current_bid,
                min_bid=None,
                num_bids=num_bids,
                auction_end=auction_end,
                location=location,
                pickup_location=pickup_location,
                url=url,
                image_url=image_url,
                scraped_at=datetime.now().isoformat()
            )

        except Exception as e:
            print(f"Error parsing item: {e}")
            return None

    def _get_mock_items(self, count: int = 5) -> List[SurplusItem]:
        """Generate mock items for testing"""
        mock_items = [
            SurplusItem(
                item_id="surplus_mock001",
                title="Dell OptiPlex 7080 Desktop Computer",
                description="Intel Core i7, 16GB RAM, 512GB SSD. Working condition, includes power cable.",
                category="Computer Equipment",
                category_id=46,
                condition="Good",
                current_bid=45.00,
                min_bid=25.00,
                num_bids=3,
                auction_end=(datetime.now() + timedelta(days=2)).isoformat(),
                location="Calgary",
                pickup_location="Calgary - 44 Capital Boulevard",
                url="https://surplus.gov.ab.ca/item/mock001",
                image_url=None,
                scraped_at=datetime.now().isoformat()
            ),
            SurplusItem(
                item_id="surplus_mock002",
                title="HP LaserJet Pro M404dn Printer",
                description="Network printer, prints double-sided. Low page count, includes toner.",
                category="Office Equipment",
                category_id=52,
                condition="Excellent",
                current_bid=35.00,
                min_bid=20.00,
                num_bids=2,
                auction_end=(datetime.now() + timedelta(days=3)).isoformat(),
                location="Calgary",
                pickup_location="Calgary - Government Centre",
                url="https://surplus.gov.ab.ca/item/mock002",
                image_url=None,
                scraped_at=datetime.now().isoformat()
            ),
            SurplusItem(
                item_id="surplus_mock003",
                title="Lot of 5 - Cisco IP Phones 7841",
                description="VoIP phones, tested working. Includes handsets and stands.",
                category="Electronics",
                category_id=49,
                condition="Good",
                current_bid=25.00,
                min_bid=15.00,
                num_bids=1,
                auction_end=(datetime.now() + timedelta(hours=18)).isoformat(),
                location="Calgary",
                pickup_location="Calgary - Southland Building",
                url="https://surplus.gov.ab.ca/item/mock003",
                image_url=None,
                scraped_at=datetime.now().isoformat()
            ),
            SurplusItem(
                item_id="surplus_mock004",
                title="DeWalt 20V MAX Drill Set",
                description="Cordless drill with 2 batteries and charger. Light use, government surplus.",
                category="Tools & Shop Equipment",
                category_id=55,
                condition="Good",
                current_bid=55.00,
                min_bid=30.00,
                num_bids=4,
                auction_end=(datetime.now() + timedelta(days=1)).isoformat(),
                location="Calgary",
                pickup_location="Calgary - Maintenance Depot",
                url="https://surplus.gov.ab.ca/item/mock004",
                image_url=None,
                scraped_at=datetime.now().isoformat()
            ),
            SurplusItem(
                item_id="surplus_mock005",
                title="Epson PowerLite 1781W Projector",
                description="3200 lumens, WXGA resolution. Low lamp hours, includes remote and case.",
                category="Audio Visual Equipment",
                category_id=57,
                condition="Excellent",
                current_bid=75.00,
                min_bid=50.00,
                num_bids=5,
                auction_end=(datetime.now() + timedelta(hours=6)).isoformat(),
                location="Calgary",
                pickup_location="Calgary - Training Centre",
                url="https://surplus.gov.ab.ca/item/mock005",
                image_url=None,
                scraped_at=datetime.now().isoformat()
            ),
            SurplusItem(
                item_id="surplus_mock006",
                title="Samsung 27\" Monitor LF27T350",
                description="Full HD IPS display, HDMI input. Minor scratch on bezel.",
                category="Computer Equipment",
                category_id=46,
                condition="Fair",
                current_bid=40.00,
                min_bid=25.00,
                num_bids=2,
                auction_end=(datetime.now() + timedelta(days=4)).isoformat(),
                location="Calgary",
                pickup_location="Calgary - Downtown Office",
                url="https://surplus.gov.ab.ca/item/mock006",
                image_url=None,
                scraped_at=datetime.now().isoformat()
            ),
        ]

        return mock_items[:count]

    def _is_calgary_location(self, item: SurplusItem) -> bool:
        """Check if item is in Calgary (pickup only)"""
        location_filter = self.config.get('scanner', {}).get('location_filter', 'Calgary')
        location_text = f"{item.location} {item.pickup_location}".lower()
        return location_filter.lower() in location_text

    def scan(self, test_mode: bool = False) -> List[SurplusItem]:
        """
        Scan Alberta Government Surplus for auction items.

        Args:
            test_mode: If True, use mock data and limit items

        Returns:
            List of SurplusItem objects
        """
        self.items = []
        scanner_config = self.config.get('scanner', {})

        max_items = (
            scanner_config.get('test_mode_items', 5)
            if test_mode
            else scanner_config.get('max_items_per_scan', 100)
        )

        if test_mode:
            print("Using mock surplus data for testing...")
            self.items = self._get_mock_items(max_items)
            return self.items

        # Real Alberta Surplus URL structure
        base_url = "https://surplus.gov.ab.ca"

        # Category IDs to scan (from config or defaults)
        # 46=Audio Visual, 49=Electronics, 52=Lab Equipment, 55=Tools, 57=Office
        default_categories = [46, 49, 52, 55, 57]
        categories = scanner_config.get('categories', default_categories)

        # Ensure categories is a list of integers (not dict or other)
        if isinstance(categories, dict):
            categories = list(categories.keys())
        elif not isinstance(categories, list):
            categories = default_categories
        categories = [int(c) for c in categories if str(c).isdigit()]
        category_names = {
            46: "Audio Visual",
            49: "Electronics",
            52: "Lab Equipment",
            55: "Tools & Shop",
            57: "Office Equipment"
        }

        items_found = 0
        seen_ids = set()
        all_item_links = []  # Store tuples of (link, category_id, category_name)

        # Loop through each category
        for category_id in categories:
            category_name = category_names.get(category_id, f"Category {category_id}")
            category_url = f"{base_url}/OA/ItemList.aspx?categoryID={category_id}"

            print(f"\nFetching {category_name} (ID: {category_id})...")
            print(f"  URL: {category_url}")

            soup = self._fetch_page(category_url)

            if not soup:
                print(f"  Failed to fetch {category_name}")
                continue

            # Find auction item links on this category page
            item_links = soup.find_all('a', href=re.compile(r'ItemDetail\.aspx\?AuctionID=', re.I))

            if not item_links:
                # Try finding table rows with auction data
                tables = soup.find_all('table')
                for table in tables:
                    rows = table.find_all('tr')
                    for row in rows:
                        link = row.find('a', href=re.compile(r'ItemDetail|AuctionID', re.I))
                        if link:
                            item_links.append(link)

            print(f"  Found {len(item_links)} items in {category_name}")

            # Add to master list with category info
            for link in item_links:
                all_item_links.append((link, category_id, category_name))

        print(f"\nTotal item links found across all categories: {len(all_item_links)}")

        for link, category_id, category_name in all_item_links:
            if items_found >= max_items:
                break

            href = link.get('href', '')

            # Extract auction ID
            id_match = re.search(r'AuctionID=(\d+)', href)
            if not id_match:
                continue

            auction_id = id_match.group(1)
            if auction_id in seen_ids:
                continue
            seen_ids.add(auction_id)

            # Get item title from link text or parent
            title = link.get_text(strip=True)
            if not title or len(title) < 3:
                parent = link.find_parent('tr') or link.find_parent('div')
                if parent:
                    title = parent.get_text(strip=True)[:100]

            # Build full URL
            item_url = href if href.startswith('http') else f"{base_url}/OA/{href}"

            # Fetch item detail page for more info
            print(f"  Fetching item {auction_id}: {title[:40]}...")
            detail_soup = self._fetch_page(item_url)

            location = "Unknown"
            current_bid = 0.0
            condition = "Unknown"
            description = ""
            auction_end = datetime.now().isoformat()
            category = category_name  # Use the category from the loop

            if detail_soup:
                # Extract location - look for Calgary
                page_text = detail_soup.get_text().lower()
                if 'calgary' in page_text:
                    location = "Calgary"
                elif 'edmonton' in page_text:
                    location = "Edmonton"

                # Try to find bid/price
                bid_text = detail_soup.find(string=re.compile(r'current|bid|price', re.I))
                if bid_text:
                    price_text = str(bid_text.parent) if bid_text.parent else str(bid_text)
                    current_bid = self._parse_price(price_text)

                # Try to find closing date
                date_text = detail_soup.find(string=re.compile(r'clos|end|expires', re.I))
                if date_text:
                    auction_end = self._parse_auction_end(str(date_text.parent) if date_text.parent else str(date_text))

                # Get description
                desc_elem = detail_soup.find('div', class_=re.compile(r'desc|detail', re.I))
                if desc_elem:
                    description = desc_elem.get_text(strip=True)[:500]

            item = SurplusItem(
                item_id=f"surplus_{auction_id}",
                title=title[:200],
                description=description,
                category=category,
                category_id=category_id,
                condition=condition,
                current_bid=current_bid,
                min_bid=None,
                num_bids=0,
                auction_end=auction_end,
                location=location,
                pickup_location=location,
                url=item_url,
                image_url=None,
                scraped_at=datetime.now().isoformat()
            )

            # Only add Calgary items
            if self._is_calgary_location(item):
                self.items.append(item)
                items_found += 1
                print(f"    ✅ Added: {title[:40]}... (${current_bid}) - {location}")
            else:
                print(f"    ⏭️ Skipped (not Calgary): {location}")

        print(f"\nTotal items found: {len(self.items)} (Calgary only)")
        return self.items

    def save_to_vault(self, vault_path: Optional[str] = None) -> str:
        """
        Save scraped items to vault as JSON.

        Args:
            vault_path: Path to vault directory

        Returns:
            Path to saved file
        """
        if vault_path is None:
            vault_path = os.path.expanduser("~/albatross-vault")

        inbox_path = os.path.join(
            vault_path,
            self.config.get('output', {}).get('inbox', '01-Inbox')
        )
        os.makedirs(inbox_path, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = self.config.get('output', {}).get('file_prefix', 'surplus_')
        filename = f"{prefix}{timestamp}.json"
        filepath = os.path.join(inbox_path, filename)

        output = {
            "source": "alberta_surplus",
            "scraped_at": datetime.now().isoformat(),
            "count": len(self.items),
            "items": [asdict(item) for item in self.items]
        }

        with open(filepath, 'w') as f:
            json.dump(output, f, indent=2)

        print(f"Saved {len(self.items)} items to {filepath}")
        return filepath

    def get_stats(self) -> Dict:
        """Get scanning statistics"""
        categories = {}
        conditions = {}
        total_bid_value = 0

        for item in self.items:
            categories[item.category] = categories.get(item.category, 0) + 1
            conditions[item.condition] = conditions.get(item.condition, 0) + 1
            total_bid_value += item.current_bid

        return {
            "total_items": len(self.items),
            "by_category": categories,
            "by_condition": conditions,
            "total_bid_value": round(total_bid_value, 2),
            "avg_bid": round(total_bid_value / len(self.items), 2) if self.items else 0,
            "requests_made": self._request_count
        }


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Scan Alberta Government Surplus")
    parser.add_argument('--test', action='store_true', help="Run in test mode (mock data)")
    parser.add_argument('--config', type=str, help="Path to config file")
    parser.add_argument('--vault', type=str, help="Path to vault directory")
    parser.add_argument('--no-save', action='store_true', help="Don't save to vault")

    args = parser.parse_args()

    print("=" * 50)
    print("Alberta Government Surplus Scanner")
    print("=" * 50)

    scanner = SurplusScanner(config_path=args.config)
    items = scanner.scan(test_mode=args.test)

    if items:
        print("\nSample items found:")
        for item in items[:3]:
            print(f"\n  {item.title}")
            print(f"    Bid: ${item.current_bid} | Bids: {item.num_bids}")
            print(f"    Location: {item.pickup_location}")
            print(f"    Ends: {item.auction_end}")

        if not args.no_save and not args.test:
            scanner.save_to_vault(vault_path=args.vault)

    print("\nStats:", scanner.get_stats())


if __name__ == "__main__":
    main()
