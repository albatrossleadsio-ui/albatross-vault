#!/usr/bin/env python3
"""
Surplus Scanner - Main Orchestrator
Part of Albatross Phase 7 - Surplus Automation Module

Orchestrates the complete surplus scanning pipeline:
1. Scrapes Alberta Surplus Sales for Calgary items
2. Researches eBay sold prices for each item
3. Calculates ROI and bidding recommendations
4. Generates markdown report for vault
5. Sends Telegram alerts for STRONG BID items

Usage:
    python surplus_scanner.py           # Full run with vault save
    python surplus_scanner.py --test    # Test run without saving
"""

import sys
import os
import argparse
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests

# Add current directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from surplus_scraper import scrape_surplus_items, CATEGORIES
from ebay_researcher import research as research_ebay
from roi_calculator import calculate as calculate_roi

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Vault configuration
VAULT_PATH = Path.home() / "albatross-vault" / "04-Patterns" / "Surplus-Leads"

# Telegram configuration (from environment)
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def send_telegram_alert(strong_bids: list[dict]) -> bool:
    """
    Send Telegram alert for STRONG BID items.

    Args:
        strong_bids: List of items with STRONG BID recommendation

    Returns:
        True if message sent successfully, False otherwise
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        logger.warning("Telegram credentials not configured - skipping alert")
        return False

    if not strong_bids:
        return False

    # Build message
    date_str = datetime.now().strftime('%Y-%m-%d')
    lines = [
        f"📦 SURPLUS SCAN: {date_str}",
        "",
        f"🎯 STRONG BIDS: {len(strong_bids)}",
    ]

    for item in strong_bids[:10]:  # Limit to 10 items in alert
        roi = item.get('roi', {}).get('roi_percent', 0)
        title = item.get('title', 'Unknown')[:40]
        lines.append(f"• {title} - ROI: {roi:.0f}%")

    if len(strong_bids) > 10:
        lines.append(f"• ... and {len(strong_bids) - 10} more")

    lines.append("")
    lines.append("Check vault for full report.")

    message = "\n".join(lines)

    try:
        url = TELEGRAM_API_URL.format(token=TELEGRAM_BOT_TOKEN)
        response = requests.post(
            url,
            json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': 'HTML'
            },
            timeout=10
        )
        response.raise_for_status()
        logger.info("Telegram alert sent successfully")
        return True
    except requests.RequestException as e:
        logger.error(f"Failed to send Telegram alert: {e}")
        return False


def generate_report(items: list[dict], scan_time: datetime) -> str:
    """
    Generate markdown report for vault.

    Args:
        items: List of processed items with eBay data and ROI
        scan_time: Timestamp of scan

    Returns:
        Markdown formatted report string
    """
    date_str = scan_time.strftime('%Y-%m-%d')
    time_str = scan_time.strftime('%H:%M')

    # Separate items by recommendation
    strong_bids = [i for i in items if i.get('roi', {}).get('recommendation') == 'STRONG BID']
    watch_items = [i for i in items if i.get('roi', {}).get('recommendation') == 'WATCH']
    no_data_items = [i for i in items if i.get('roi') is None]

    # Build report
    lines = [
        f"# Surplus Scan Report - {date_str}",
        "",
        "## Summary",
        "",
        f"- **Scan Time:** {time_str}",
        f"- **Categories Monitored:** {', '.join(CATEGORIES.values())}",
        f"- **Total Items Found:** {len(items)}",
        f"- **STRONG BID Items:** {len(strong_bids)}",
        f"- **WATCH Items:** {len(watch_items)}",
        f"- **No eBay Data:** {len(no_data_items)}",
        "",
    ]

    # STRONG BID section
    if strong_bids:
        lines.extend([
            "## 🎯 STRONG BID Items",
            "",
            "| Item | Current Bid | eBay Avg | ROI | Max Bid |",
            "|------|-------------|----------|-----|---------|",
        ])

        for item in sorted(strong_bids, key=lambda x: x.get('roi', {}).get('roi_percent', 0), reverse=True):
            title = item.get('title', 'Unknown')[:35]
            current = item.get('current_bid', 0)
            ebay_avg = item.get('ebay', {}).get('average_price', 0)
            roi = item.get('roi', {}).get('roi_percent', 0)
            max_bid = item.get('roi', {}).get('max_bid_100_roi', 0)
            url = item.get('url', '')

            lines.append(
                f"| [{title}]({url}) | ${current:.2f} | ${ebay_avg:.2f} | {roi:.0f}% | ${max_bid:.2f} |"
            )

        lines.append("")

    # WATCH section
    if watch_items:
        lines.extend([
            "## 👀 WATCH Items",
            "",
            "| Item | Current Bid | eBay Avg | ROI | Notes |",
            "|------|-------------|----------|-----|-------|",
        ])

        for item in sorted(watch_items, key=lambda x: x.get('roi', {}).get('roi_percent', 0), reverse=True):
            title = item.get('title', 'Unknown')[:35]
            current = item.get('current_bid', 0)
            ebay_avg = item.get('ebay', {}).get('average_price', 0)
            roi = item.get('roi', {}).get('roi_percent', 0)
            url = item.get('url', '')

            if roi < 0:
                note = "Negative ROI"
            elif roi < 50:
                note = "Low margin"
            else:
                note = "Monitor price"

            lines.append(
                f"| [{title}]({url}) | ${current:.2f} | ${ebay_avg:.2f} | {roi:.0f}% | {note} |"
            )

        lines.append("")

    # No data section
    if no_data_items:
        lines.extend([
            "## ❓ No eBay Data",
            "",
            "These items had no matching eBay sold listings:",
            "",
        ])

        for item in no_data_items:
            title = item.get('title', 'Unknown')
            url = item.get('url', '')
            lines.append(f"- [{title}]({url})")

        lines.append("")

    # Detailed breakdowns for STRONG BIDs
    if strong_bids:
        lines.extend([
            "---",
            "",
            "## Detailed Analysis - STRONG BID Items",
            "",
        ])

        for item in strong_bids:
            title = item.get('title', 'Unknown')
            item_id = item.get('item_id', 'N/A')
            category = item.get('category_name', 'Unknown')
            current = item.get('current_bid', 0)
            url = item.get('url', '')
            ebay = item.get('ebay', {})
            roi = item.get('roi', {})

            lines.extend([
                f"### {title}",
                "",
                f"- **Item ID:** {item_id}",
                f"- **Category:** {category}",
                f"- **Location:** {item.get('location', 'N/A')}",
                f"- **Current Bid:** ${current:.2f}",
                f"- **Auction Ends:** {item.get('end_date', 'N/A')}",
                f"- **URL:** {url}",
                "",
                "**eBay Research:**",
                f"- Average Sold: ${ebay.get('average_price', 0):.2f}",
                f"- Price Range: {ebay.get('price_range', 'N/A')}",
                f"- Sold Count: {ebay.get('sold_count', 0)}",
                f"- Confidence: {ebay.get('confidence', 'N/A')}",
                f"- [View eBay Search]({ebay.get('search_url', '')})",
                "",
                "**ROI Analysis:**",
                f"- Expected Sale (after 25% discount): ${roi.get('expected_sale', 0):.2f}",
                f"- eBay Fees (13%): ${roi.get('ebay_fees', 0):.2f}",
                f"- Shipping: ${roi.get('shipping', 0):.2f}",
                f"- Net Proceeds: ${roi.get('net_proceeds', 0):.2f}",
                f"- **Profit: ${roi.get('profit', 0):.2f}**",
                f"- **ROI: {roi.get('roi_percent', 0):.0f}%**",
                f"- Max Bid for 100% ROI: ${roi.get('max_bid_100_roi', 0):.2f}",
                "",
            ])

    # Action items
    lines.extend([
        "---",
        "",
        "## Action Items",
        "",
        "- [ ] Review STRONG BID items",
        "- [ ] Place bids on priority items",
        "- [ ] Set calendar reminders for auction end times",
        "- [ ] Research any items without eBay data manually",
        "",
        "---",
        "",
        f"*Generated by Albatross Surplus Scanner at {scan_time.strftime('%Y-%m-%d %H:%M:%S')}*",
    ])

    return "\n".join(lines)


def save_report(report: str, scan_time: datetime) -> Path:
    """
    Save report to vault.

    Args:
        report: Markdown report content
        scan_time: Timestamp for filename

    Returns:
        Path to saved file
    """
    # Ensure directory exists
    VAULT_PATH.mkdir(parents=True, exist_ok=True)

    # Generate filename
    filename = f"surplus-scan-{scan_time.strftime('%Y-%m-%d')}.md"
    filepath = VAULT_PATH / filename

    # Write report
    filepath.write_text(report, encoding='utf-8')
    logger.info(f"Report saved to: {filepath}")

    return filepath


def run_scan(test_mode: bool = False) -> dict:
    """
    Run the complete surplus scanning pipeline.

    Args:
        test_mode: If True, don't save report or send alerts

    Returns:
        Dictionary with scan results
    """
    scan_time = datetime.now()
    logger.info("=" * 60)
    logger.info("Starting Surplus Scan")
    logger.info("=" * 60)

    # Step 1: Scrape surplus items
    logger.info("Step 1: Scraping Alberta Surplus Sales...")
    items = scrape_surplus_items()

    if not items:
        logger.warning("No items found from surplus scraper")
        return {
            'success': False,
            'items': [],
            'strong_bids': [],
            'message': 'No items found'
        }

    logger.info(f"Found {len(items)} Calgary items")

    # Step 2 & 3: Research eBay and calculate ROI for each item
    logger.info("Step 2-3: Researching eBay prices and calculating ROI...")

    processed_items = []
    for i, item in enumerate(items, 1):
        logger.info(f"Processing item {i}/{len(items)}: {item['title'][:40]}...")

        # Research eBay
        ebay_data = research_ebay(item['title'])
        item['ebay'] = ebay_data

        # Calculate ROI
        current_bid = item.get('current_bid', 0)
        if current_bid == 0:
            current_bid = 1.0  # Assume $1 starting bid if 0

        if ebay_data:
            roi_data = calculate_roi(current_bid, ebay_data)
            item['roi'] = roi_data
        else:
            item['roi'] = None

        processed_items.append(item)

    # Separate by recommendation (handle None roi safely)
    strong_bids = [i for i in processed_items if (i.get('roi') or {}).get('recommendation') == 'STRONG BID']
    watch_items = [i for i in processed_items if (i.get('roi') or {}).get('recommendation') == 'WATCH']

    logger.info(f"Results: {len(strong_bids)} STRONG BID, {len(watch_items)} WATCH")

    # Step 4: Generate report
    logger.info("Step 4: Generating report...")
    report = generate_report(processed_items, scan_time)

    if test_mode:
        logger.info("TEST MODE - Report preview:")
        print("\n" + "=" * 60)
        # Handle potential Unicode issues on Windows console
        try:
            print(report[:2000])
        except UnicodeEncodeError:
            print(report[:2000].encode('ascii', 'replace').decode('ascii'))
        if len(report) > 2000:
            print(f"\n... [{len(report) - 2000} more characters]")
        print("=" * 60)
    else:
        # Step 5: Save to vault
        logger.info("Step 5: Saving to vault...")
        filepath = save_report(report, scan_time)

        # Step 6: Send Telegram alert
        if strong_bids:
            logger.info("Step 6: Sending Telegram alert...")
            send_telegram_alert(strong_bids)
        else:
            logger.info("Step 6: No STRONG BID items - skipping Telegram alert")

    logger.info("=" * 60)
    logger.info("Surplus Scan Complete")
    logger.info("=" * 60)

    return {
        'success': True,
        'scan_time': scan_time,
        'items': processed_items,
        'strong_bids': strong_bids,
        'watch_items': watch_items,
        'total_items': len(processed_items),
        'strong_count': len(strong_bids),
        'watch_count': len(watch_items),
    }


def main():
    """Main entry point with argument parsing."""
    parser = argparse.ArgumentParser(
        description='Albatross Surplus Scanner - Scan Alberta Surplus for arbitrage opportunities'
    )
    parser.add_argument(
        '--test',
        action='store_true',
        help='Run in test mode (no vault save, no Telegram alerts)'
    )
    parser.add_argument(
        '--quiet',
        action='store_true',
        help='Suppress detailed logging output'
    )

    args = parser.parse_args()

    if args.quiet:
        logging.getLogger().setLevel(logging.WARNING)

    result = run_scan(test_mode=args.test)

    # Print summary
    print(f"\n{'=' * 40}")
    print("SCAN SUMMARY")
    print(f"{'=' * 40}")
    print(f"Total Items: {result.get('total_items', 0)}")
    print(f"STRONG BID: {result.get('strong_count', 0)}")
    print(f"WATCH: {result.get('watch_count', 0)}")

    if result.get('strong_bids'):
        print(f"\nTop STRONG BID Items:")
        for item in result['strong_bids'][:5]:
            title = item.get('title', 'Unknown')[:35]
            roi = (item.get('roi') or {}).get('roi_percent', 0)
            print(f"  * {title} - ROI: {roi:.0f}%")


if __name__ == '__main__':
    main()
