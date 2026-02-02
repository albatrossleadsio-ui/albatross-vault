#!/usr/bin/env python3
"""
ROI Calculator for Surplus Auctions
Part of Albatross Phase 7 - Surplus Automation Module

Calculates ROI and bidding recommendations based on eBay market data.
Called by surplus_scanner.py after eBay research is complete.
"""

import logging
from typing import Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Cost constants
AS_IS_DISCOUNT = 0.25        # 25% discount for as-is condition
EBAY_FEE_PERCENT = 0.13      # 13% eBay fees (including PayPal/payment processing)
SHIPPING_COST = 15.00        # Estimated average shipping cost
MIN_ROI_PERCENT = 100        # Minimum ROI for STRONG BID recommendation


def calculate(current_bid: float, ebay_data: Optional[dict]) -> Optional[dict]:
    """
    Calculate ROI and bidding recommendation for a surplus auction item.

    Args:
        current_bid: Current auction bid amount (must be > 0)
        ebay_data: Output from ebay_researcher.research(), containing 'average_price'

    Returns:
        Dictionary with ROI analysis and recommendation, or None if inputs invalid.

    Example:
        >>> result = calculate(15.00, {'average_price': 127.50})
        >>> print(result['roi_percent'])
        227.08
        >>> print(result['recommendation'])
        'STRONG BID'
    """
    # Validate current_bid
    if current_bid is None or current_bid <= 0:
        logger.warning("Invalid current_bid: must be > 0")
        return None

    # Validate ebay_data
    if ebay_data is None:
        logger.warning("No eBay data provided - cannot calculate ROI")
        return None

    if 'average_price' not in ebay_data or ebay_data['average_price'] is None:
        logger.warning("eBay data missing 'average_price'")
        return None

    average_price = ebay_data['average_price']
    if average_price <= 0:
        logger.warning("Invalid average_price: must be > 0")
        return None

    # Calculate expected sale price (discounted for as-is condition)
    expected_sale = average_price * (1 - AS_IS_DISCOUNT)

    # Calculate costs
    ebay_fees = expected_sale * EBAY_FEE_PERCENT
    shipping = SHIPPING_COST

    # Calculate net proceeds after all costs
    net_proceeds = expected_sale - ebay_fees - shipping

    # Calculate profit and ROI
    profit = net_proceeds - current_bid
    roi_percent = (profit / current_bid) * 100

    # Calculate max bid for 100% ROI (2x return = 100% profit)
    # For 100% ROI: profit = cost, so net_proceeds = 2 * cost
    max_bid_100_roi = net_proceeds / 2

    # Determine recommendation
    if roi_percent >= MIN_ROI_PERCENT:
        recommendation = 'STRONG BID'
    else:
        recommendation = 'WATCH'

    result = {
        'expected_sale': round(expected_sale, 2),
        'ebay_fees': round(ebay_fees, 2),
        'shipping': round(shipping, 2),
        'net_proceeds': round(net_proceeds, 2),
        'profit': round(profit, 2),
        'roi_percent': round(roi_percent, 2),
        'max_bid_100_roi': round(max_bid_100_roi, 2),
        'recommendation': recommendation,
    }

    logger.debug(
        f"ROI calculated: {roi_percent:.1f}% profit=${profit:.2f} -> {recommendation}"
    )

    return result


def calculate_batch(items: list[tuple[float, Optional[dict]]]) -> list[Optional[dict]]:
    """
    Calculate ROI for multiple items.

    Args:
        items: List of (current_bid, ebay_data) tuples

    Returns:
        List of ROI calculation results
    """
    return [calculate(bid, data) for bid, data in items]


def get_recommendation_summary(roi_result: Optional[dict]) -> str:
    """
    Get a human-readable summary of the ROI analysis.

    Args:
        roi_result: Output from calculate()

    Returns:
        Formatted summary string
    """
    if roi_result is None:
        return "Unable to calculate ROI - insufficient data"

    return (
        f"{roi_result['recommendation']} | "
        f"ROI: {roi_result['roi_percent']:.0f}% | "
        f"Profit: ${roi_result['profit']:.2f} | "
        f"Max bid for 100% ROI: ${roi_result['max_bid_100_roi']:.2f}"
    )


if __name__ == '__main__':
    # Test run
    print("=" * 60)
    print("ROI Calculator - Test Run")
    print("=" * 60)

    # Test case 1: Good ROI scenario
    print("\nTest 1: Low bid, high eBay value")
    ebay_data = {'average_price': 127.50}
    result = calculate(15.00, ebay_data)
    if result:
        print(f"  Current Bid: $15.00")
        print(f"  eBay Avg: ${ebay_data['average_price']:.2f}")
        print(f"  Expected Sale (after 25% discount): ${result['expected_sale']:.2f}")
        print(f"  eBay Fees (13%): ${result['ebay_fees']:.2f}")
        print(f"  Shipping: ${result['shipping']:.2f}")
        print(f"  Net Proceeds: ${result['net_proceeds']:.2f}")
        print(f"  Profit: ${result['profit']:.2f}")
        print(f"  ROI: {result['roi_percent']:.2f}%")
        print(f"  Max Bid for 100% ROI: ${result['max_bid_100_roi']:.2f}")
        print(f"  Recommendation: {result['recommendation']}")

    # Test case 2: Poor ROI scenario
    print("\nTest 2: High bid, lower margin")
    ebay_data = {'average_price': 50.00}
    result = calculate(25.00, ebay_data)
    if result:
        print(f"  Current Bid: $25.00")
        print(f"  eBay Avg: ${ebay_data['average_price']:.2f}")
        print(f"  Profit: ${result['profit']:.2f}")
        print(f"  ROI: {result['roi_percent']:.2f}%")
        print(f"  Recommendation: {result['recommendation']}")

    # Test case 3: Negative ROI
    print("\nTest 3: Negative ROI scenario")
    ebay_data = {'average_price': 30.00}
    result = calculate(50.00, ebay_data)
    if result:
        print(f"  Current Bid: $50.00")
        print(f"  eBay Avg: ${ebay_data['average_price']:.2f}")
        print(f"  Profit: ${result['profit']:.2f}")
        print(f"  ROI: {result['roi_percent']:.2f}%")
        print(f"  Recommendation: {result['recommendation']}")

    # Test case 4: Edge cases
    print("\nTest 4: Edge cases")
    print(f"  calculate(0, {{'average_price': 100}}): {calculate(0, {'average_price': 100})}")
    print(f"  calculate(10, None): {calculate(10, None)}")
    print(f"  calculate(None, {{'average_price': 100}}): {calculate(None, {'average_price': 100})}")
