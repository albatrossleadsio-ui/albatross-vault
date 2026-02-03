#!/usr/bin/env python3
"""
eBay Sold Price Researcher
Part of Albatross Phase 7 - Surplus Automation Module

Researches eBay.ca sold listings to determine market value for surplus items.
Called by surplus_scanner.py for each item found by surplus_scraper.py.
"""

import re
import time
import logging
from typing import Optional
from urllib.parse import quote_plus

import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# eBay configuration
EBAY_BASE_URL = "https://www.ebay.ca"
# Parameters: _nkw=search, _sop=12 (newest first), LH_Sold=1&LH_Complete=1 (sold items)
EBAY_SEARCH_URL = (
    "{base}/sch/i.html?_nkw={query}&_sacat=0&_from=R40&_sop=12&rt=nc&LH_Sold=1&LH_Complete=1"
)

# Request configuration
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1.0  # Be nice to eBay - 1 second between requests
REQUEST_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-CA,en-US;q=0.9,en;q=0.8',
    'Connection': 'keep-alive',
}

# Price filtering
MIN_VALID_PRICE = 5.0  # Filter out prices under $5 (likely parts/accessories)
MAX_RESULTS = 15  # Maximum number of results to analyze

# Track last request time for rate limiting
_last_request_time = 0


def _rate_limit():
    """Enforce rate limiting between requests."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < REQUEST_DELAY:
        time.sleep(REQUEST_DELAY - elapsed)
    _last_request_time = time.time()


def _clean_price(price_text: str) -> Optional[float]:
    """
    Extract and clean price from text.
    Handles formats like: $125.00, $1,234.56, C $99.00, CAD 50.00
    """
    if not price_text:
        return None

    # Find price pattern - handles currency symbols and commas
    match = re.search(r'\$\s*([\d,]+\.?\d*)', price_text)
    if not match:
        # Try without $ symbol (some listings show just numbers)
        match = re.search(r'([\d,]+\.\d{2})', price_text)

    if match:
        try:
            # Remove commas and convert to float
            price_str = match.group(1).replace(',', '')
            return float(price_str)
        except ValueError:
            return None

    return None


def _fetch_search_results(search_term: str) -> Optional[BeautifulSoup]:
    """Fetch eBay search results page."""
    _rate_limit()

    encoded_query = quote_plus(search_term)
    url = EBAY_SEARCH_URL.format(base=EBAY_BASE_URL, query=encoded_query)

    try:
        logger.info(f"Searching eBay for: {search_term}")
        response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        return BeautifulSoup(response.text, 'html.parser'), url
    except requests.Timeout:
        logger.error(f"Timeout searching eBay for: {search_term}")
        return None, url
    except requests.RequestException as e:
        logger.error(f"eBay search failed: {e}")
        return None, url


def _extract_prices(soup: BeautifulSoup) -> list[float]:
    """Extract sold prices from eBay search results."""
    prices = []

    # eBay uses various selectors for sold items - try multiple patterns
    # Primary: s-item containers with sold price
    items = soup.select('.s-item')

    for item in items[:MAX_RESULTS]:
        # Skip "Shop on eBay" promotional items
        title_elem = item.select_one('.s-item__title')
        if title_elem and 'shop on ebay' in title_elem.get_text().lower():
            continue

        # Look for the sold price (not the original/strikethrough price)
        price_elem = (
            item.select_one('.s-item__price') or
            item.select_one('.s-item__detail--primary') or
            item.select_one('[class*="price"]')
        )

        if price_elem:
            price_text = price_elem.get_text(strip=True)
            price = _clean_price(price_text)

            if price and price >= MIN_VALID_PRICE:
                prices.append(price)

    # Also try alternate layout (sometimes eBay shows different formats)
    if not prices:
        # Try finding price spans directly
        price_spans = soup.find_all('span', class_=re.compile(r'price|sold', re.I))
        for span in price_spans[:MAX_RESULTS]:
            price = _clean_price(span.get_text())
            if price and price >= MIN_VALID_PRICE:
                prices.append(price)

    return prices


def _calculate_confidence(sold_count: int) -> str:
    """Determine confidence level based on number of results."""
    if sold_count >= 10:
        return 'high'
    elif sold_count >= 5:
        return 'medium'
    else:
        return 'low'


def research(search_term: str) -> Optional[dict]:
    """
    Research eBay sold prices for a given search term.

    Args:
        search_term: Item description to search for (e.g., "Dell 3400MP Projector")

    Returns:
        Dictionary with price research data, or None if no results found.

    Example:
        >>> result = research("Dell 3400MP Projector")
        >>> print(result['average_price'])
        45.50
    """
    if not search_term or not search_term.strip():
        logger.warning("Empty search term provided")
        return None

    search_term = search_term.strip()

    # Fetch search results
    result = _fetch_search_results(search_term)
    if result[0] is None:
        return None

    soup, search_url = result

    # Extract prices from results
    prices = _extract_prices(soup)

    if not prices:
        logger.info(f"No sold items found for: {search_term}")
        return None

    # Calculate statistics
    sold_count = len(prices)
    average_price = sum(prices) / sold_count
    low_price = min(prices)
    high_price = max(prices)
    price_range = f"${low_price:.2f} - ${high_price:.2f}"
    confidence = _calculate_confidence(sold_count)

    logger.info(
        f"Found {sold_count} sold items for '{search_term}': "
        f"avg ${average_price:.2f} ({confidence} confidence)"
    )

    return {
        'search_term': search_term,
        'average_price': round(average_price, 2),
        'sold_count': sold_count,
        'price_range': price_range,
        'low_price': round(low_price, 2),
        'high_price': round(high_price, 2),
        'search_url': search_url,
        'confidence': confidence,
    }


def research_batch(search_terms: list[str]) -> list[Optional[dict]]:
    """
    Research multiple items with proper rate limiting.

    Args:
        search_terms: List of item descriptions to search

    Returns:
        List of research results (None for items with no results)
    """
    results = []
    for term in search_terms:
        result = research(term)
        results.append(result)
    return results


if __name__ == '__main__':
    # Test run
    print("=" * 60)
    print("eBay Sold Price Researcher - Test Run")
    print("=" * 60)

    test_terms = [
        "Dell 3400MP Projector",
        "HP LaserJet Printer",
    ]

    for term in test_terms:
        print(f"\nSearching: {term}")
        result = research(term)

        if result:
            print(f"  Average Price: ${result['average_price']:.2f}")
            print(f"  Price Range: {result['price_range']}")
            print(f"  Sold Count: {result['sold_count']}")
            print(f"  Confidence: {result['confidence']}")
            print(f"  Search URL: {result['search_url']}")
        else:
            print("  No results found")
