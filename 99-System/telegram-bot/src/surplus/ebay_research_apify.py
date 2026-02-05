#!/usr/bin/env python3
"""
Apify-based eBay Sold Price Research Module
Drop-in replacement for ebay_research.py that uses Apify instead of eBay API
"""

import os
import re
from datetime import datetime
from typing import Dict, List, Optional
from dataclasses import dataclass

from .scanner import SurplusItem


@dataclass
class EbayResearch:
    """Represents eBay research results for a surplus item"""
    item_id: str
    query: str
    avg_sold_price: float
    min_sold_price: float
    max_sold_price: float
    num_sold: int
    market_activity: str  # very_fast, fast, moderate, slow, very_slow
    price_range: str
    recommended_price: float
    confidence: str  # high, medium, low
    data_age_days: int
    researched_at: str


class ApifyEbayResearcher:
    """
    Researches eBay sold prices using Apify scraper.
    
    Cost: ~$0.05 per 50 items scraped
    Rate limit: 200 items max per run
    
    Requires:
        - Apify account (free tier available)
        - APIFY_TOKEN environment variable
    """
    
    ACTOR_ID = 'marielise.dev/ebay-sold-listings-intelligence'
    
    def __init__(self, api_token: Optional[str] = None, ebay_site: str = "ebay.ca"):
        """
        Initialize Apify researcher.
        
        Args:
            api_token: Apify API token (or from APIFY_TOKEN env var)
            ebay_site: eBay marketplace (ebay.ca, ebay.com, etc.)
        """
        self.api_token = api_token or os.environ.get('APIFY_TOKEN')
        self.ebay_site = ebay_site
        self.client = None
        
        if self.api_token:
            try:
                from apify_client import ApifyClient
                self.client = ApifyClient(self.api_token)
            except ImportError:
                raise ImportError("apify-client not installed. Run: pip install apify-client")
    
    def _clean_query(self, title: str) -> str:
        """
        Clean item title for eBay search.
        Removes surplus codes, limits length, keeps key model numbers.
        """
        # Remove surplus codes like (E), (D), (O)
        cleaned = re.sub(r'\s*\([A-Z]\)\s*', ' ', title)
        
        # Remove common surplus words
        words_to_remove = ['surplus', 'government', 'auction', 'as-is', 'untested']
        for word in words_to_remove:
            cleaned = re.sub(r'\b' + word + r'\b', '', cleaned, flags=re.I)
        
        # Clean up extra spaces
        cleaned = ' '.join(cleaned.split())
        
        # Limit to ~10 words for best results
        words = cleaned.split()
        if len(words) > 10:
            cleaned = ' '.join(words[:10])
        
        return cleaned.strip()
    
    def _parse_price(self, price_str: str) -> float:
        """Parse price string to float"""
        if not price_str:
            return 0.0
        try:
            # Remove $, CAD, commas, spaces
            cleaned = re.sub(r'[^\d.]', '', str(price_str))
            return float(cleaned) if cleaned else 0.0
        except (ValueError, TypeError):
            return 0.0
    
    def research_item(self, item: SurplusItem, test_mode: bool = False) -> Optional[EbayResearch]:
        """
        Research eBay sold prices for a single surplus item.
        
        Args:
            item: SurplusItem to research
            test_mode: If True, return mock data instead of calling API
            
        Returns:
            EbayResearch object or None if research failed
        """
        if test_mode:
            return self._get_mock_research(item)
        
        if not self.client:
            print(f"⚠️  No Apify client available for {item.title}")
            return None
        
        query = self._clean_query(item.title)
        
        try:
            print(f"  🔍 Researching: {query[:50]}...")
            
            # Call Apify actor
            run = self.client.actor(self.ACTOR_ID).call(run_input={
                'query': query,
                'ebaySite': self.ebay_site,
                'maxItems': 50,
                'soldWithinDays': 90,
                'includeAnalytics': True
            })
            
            # Get results
            dataset = self.client.dataset(run['defaultDatasetId'])
            items = list(dataset.list_items().items)
            
            if not items:
                print(f"    ⚠️  No eBay results found")
                return None
            
            summary = items[0].get('summary', {})
            
            # Extract pricing data
            rec_price = self._parse_price(
                summary.get('recommendedPrice', {}).get('display', '0')
            )
            price_range = summary.get('priceRange', {})
            min_price = self._parse_price(price_range.get('low', {}).get('display', '0'))
            max_price = self._parse_price(price_range.get('high', {}).get('display', '0'))
            
            # Use recommended price as average
            avg_price = rec_price if rec_price > 0 else (min_price + max_price) / 2
            
            # Determine market activity
            velocity = summary.get('marketVelocity', 'unknown')
            activity_map = {
                'very_fast': 'high',
                'fast': 'high',
                'moderate': 'medium',
                'slow': 'low',
                'very_slow': 'none'
            }
            market_activity = activity_map.get(velocity, 'unknown')
            
            return EbayResearch(
                item_id=item.item_id,
                query=query,
                avg_sold_price=round(avg_price, 2),
                min_sold_price=round(min_price, 2),
                max_sold_price=round(max_price, 2),
                num_sold=summary.get('totalSalesCount', 0) or 50,  # Estimate from maxItems
                market_activity=market_activity,
                price_range=f"${min_price:.0f}-${max_price:.0f}",
                recommended_price=rec_price,
                confidence=summary.get('confidence', 'unknown'),
                data_age_days=0,
                researched_at=datetime.now().isoformat()
            )
            
        except Exception as e:
            print(f"    ❌ Apify error: {e}")
            return None
    
    def research_batch(self, items: List[SurplusItem], test_mode: bool = False) -> Dict[str, EbayResearch]:
        """
        Research multiple items.
        
        Args:
            items: List of SurplusItems
            test_mode: Use mock data
            
        Returns:
            Dict mapping item_id to EbayResearch
        """
        results = {}
        
        for item in items:
            research = self.research_item(item, test_mode=test_mode)
            if research:
                results[item.item_id] = research
            
        return results
    
    def _get_mock_research(self, item: SurplusItem) -> EbayResearch:
        """Generate mock research data for testing"""
        # Mock prices based on item category
        mock_prices = {
            'printer': (80, 150, 120),
            'zebra': (60, 120, 90),
            'label': (50, 100, 75),
            'oculus': (80, 180, 130),
            'vr': (70, 160, 115),
            'computer': (100, 300, 200),
            'monitor': (50, 150, 100),
            'laptop': (150, 400, 275),
            'projector': (100, 250, 175),
            'tool': (40, 120, 80),
        }
        
        # Find matching category
        title_lower = item.title.lower()
        min_p, max_p, avg_p = 30, 80, 55  # defaults
        
        for keyword, (mn, mx, av) in mock_prices.items():
            if keyword in title_lower:
                min_p, max_p, avg_p = mn, mx, av
                break
        
        # Add some randomness
        import random
        variation = random.uniform(0.8, 1.2)
        
        return EbayResearch(
            item_id=item.item_id,
            query=item.title,
            avg_sold_price=round(avg_p * variation, 2),
            min_sold_price=round(min_p * variation, 2),
            max_sold_price=round(max_p * variation, 2),
            num_sold=random.randint(5, 50),
            market_activity=random.choice(['high', 'medium', 'low']),
            price_range=f"${int(min_p)}-${int(max_p)}",
            recommended_price=round(avg_p * variation, 2),
            confidence='medium',
            data_age_days=0,
            researched_at=datetime.now().isoformat()
        )


# Legacy compatibility - can be used as drop-in replacement
EbayResearcher = ApifyEbayResearcher


def main():
    """CLI test entry point"""
    import yaml
    from pathlib import Path
    
    print("=" * 60)
    print("Apify eBay Research Module Test")
    print("=" * 60)
    
    # Check for token
    token = os.environ.get('APIFY_TOKEN')
    if not token:
        print("\n⚠️  APIFY_TOKEN not set in environment")
        print("Get your token from: https://console.apify.com/account#/integrations")
        print("Then set: export APIFY_TOKEN='your_token_here'")
        print("\nRunning in TEST MODE with mock data...")
    
    # Create researcher
    try:
        researcher = ApifyEbayResearcher(api_token=token, ebay_site="ebay.ca")
    except ImportError as e:
        print(f"\n❌ {e}")
        return
    
    # Test with mock items
    from .scanner import SurplusScanner
    scanner = SurplusScanner()
    mock_items = scanner._get_mock_items(3)
    
    print(f"\nResearching {len(mock_items)} test items...")
    print("-" * 60)
    
    results = researcher.research_batch(mock_items, test_mode=not token)
    
    print("\n" + "=" * 60)
    print("Results:")
    print("=" * 60)
    
    for item_id, research in results.items():
        print(f"\n📦 {research.query[:40]}...")
        print(f"   Avg Sold: ${research.avg_sold_price}")
        print(f"   Range: {research.price_range}")
        print(f"   Activity: {research.market_activity}")
        print(f"   Sales: {research.num_sold}")
    
    print("\n" + "=" * 60)
    print("Test complete!")


if __name__ == "__main__":
    main()
