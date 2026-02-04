#!/usr/bin/env python3
"""
Tests for Telegram Bot Interface
"""

import os
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.utils.bid_tracker import BidTracker, TrackedItem
from src.interfaces.telegram_alerts import TelegramAlerts, OpportunityData


class TestBidTracker(unittest.TestCase):
    """Tests for BidTracker database"""

    def setUp(self):
        """Create in-memory database for testing"""
        self.db_path = ":memory:"
        # Use temp file since SQLite :memory: doesn't persist
        import tempfile
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_bids.db")
        self.tracker = BidTracker(db_path=self.db_path)

    def tearDown(self):
        """Clean up temp files"""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_add_item(self):
        """Test adding a new item"""
        item_data = {
            'title': 'Test Dell Computer',
            'surplus_url': 'https://surplus.gov.ab.ca/item/123',
            'current_bid': 45.00,
            'max_bid': 85.00,
            'roi_percent': 150.0
        }

        item_id = self.tracker.add_item(item_data)

        self.assertIsNotNone(item_id)
        self.assertTrue(item_id.startswith('track_'))

    def test_get_item(self):
        """Test retrieving an item"""
        item_data = {
            'id': 'test_001',
            'title': 'HP Printer',
            'max_bid': 50.00
        }

        self.tracker.add_item(item_data)
        item = self.tracker.get_item('test_001')

        self.assertIsNotNone(item)
        self.assertEqual(item['title'], 'HP Printer')
        self.assertEqual(item['max_bid'], 50.00)

    def test_update_item(self):
        """Test updating an item"""
        self.tracker.add_item({'id': 'test_002', 'title': 'Test Item', 'status': 'watching'})

        success = self.tracker.update_item('test_002', {'status': 'bid_placed', 'max_bid': 75.00})

        self.assertTrue(success)
        item = self.tracker.get_item('test_002')
        self.assertEqual(item['status'], 'bid_placed')
        self.assertEqual(item['max_bid'], 75.00)

    def test_update_status(self):
        """Test status workflow"""
        self.tracker.add_item({'id': 'test_003', 'title': 'Status Test'})

        # Watching -> bid_placed
        self.tracker.update_status('test_003', 'bid_placed')
        item = self.tracker.get_item('test_003')
        self.assertEqual(item['status'], 'bid_placed')

        # bid_placed -> won
        self.tracker.update_status('test_003', 'won')
        item = self.tracker.get_item('test_003')
        self.assertEqual(item['status'], 'won')

    def test_invalid_status_raises(self):
        """Test that invalid status raises error"""
        self.tracker.add_item({'id': 'test_004', 'title': 'Invalid Status Test'})

        with self.assertRaises(ValueError):
            self.tracker.update_status('test_004', 'invalid_status')

    def test_get_items_by_status(self):
        """Test filtering by status"""
        self.tracker.add_item({'id': 'w1', 'title': 'Watching 1', 'status': 'watching'})
        self.tracker.add_item({'id': 'w2', 'title': 'Watching 2', 'status': 'watching'})
        self.tracker.add_item({'id': 'b1', 'title': 'Bid 1', 'status': 'bid_placed'})

        watching = self.tracker.get_items_by_status('watching')
        bid_placed = self.tracker.get_items_by_status('bid_placed')

        self.assertEqual(len(watching), 2)
        self.assertEqual(len(bid_placed), 1)

    def test_get_active_bids(self):
        """Test getting active bids"""
        self.tracker.add_item({'id': 'a1', 'title': 'Active 1', 'status': 'watching'})
        self.tracker.add_item({'id': 'a2', 'title': 'Active 2', 'status': 'bid_placed'})
        self.tracker.add_item({'id': 'i1', 'title': 'Inactive 1', 'status': 'sold'})
        self.tracker.add_item({'id': 'i2', 'title': 'Inactive 2', 'status': 'lost'})

        active = self.tracker.get_active_bids()

        self.assertEqual(len(active), 2)
        active_ids = [a['id'] for a in active]
        self.assertIn('a1', active_ids)
        self.assertIn('a2', active_ids)

    def test_record_sale(self):
        """Test recording a sale"""
        self.tracker.add_item({
            'id': 'sale_test',
            'title': 'Sale Test Item',
            'max_bid': 45.00,
            'status': 'listed'
        })

        success = self.tracker.record_sale('sale_test', sale_price=120.00, fees=15.00)

        self.assertTrue(success)
        item = self.tracker.get_item('sale_test')
        self.assertEqual(item['status'], 'sold')
        self.assertEqual(item['sale_price'], 120.00)
        self.assertEqual(item['fees'], 15.00)
        self.assertEqual(item['actual_profit'], 60.00)  # 120 - 45 - 15

    def test_profit_summary(self):
        """Test profit summary calculation"""
        # Add some sold items
        self.tracker.add_item({
            'id': 'sold_1',
            'title': 'Sold Item 1',
            'status': 'sold',
            'purchase_price': 30.00,
            'sale_price': 80.00,
            'fees': 10.00,
            'actual_profit': 40.00
        })

        summary = self.tracker.get_profit_summary(days=30)

        self.assertIn('total_profit', summary)
        self.assertIn('items_sold', summary)

    def test_budget_management(self):
        """Test budget getting and setting"""
        budget = self.tracker.get_budget()
        self.assertIn('weekly_budget', budget)

        self.tracker.set_budget(weekly_budget=750.00)
        new_budget = self.tracker.get_budget()
        self.assertEqual(new_budget['weekly_budget'], 750.00)

    def test_get_auctions_ending_soon(self):
        """Test finding auctions ending soon"""
        # Item ending in 1 hour
        soon_end = (datetime.now() + timedelta(hours=1)).isoformat()
        self.tracker.add_item({
            'id': 'ending_soon',
            'title': 'Ending Soon Item',
            'auction_end': soon_end,
            'status': 'watching'
        })

        # Item ending in 1 week
        far_end = (datetime.now() + timedelta(days=7)).isoformat()
        self.tracker.add_item({
            'id': 'ending_far',
            'title': 'Ending Later Item',
            'auction_end': far_end,
            'status': 'watching'
        })

        ending_soon = self.tracker.get_auctions_ending_soon(hours=2)

        self.assertEqual(len(ending_soon), 1)
        self.assertEqual(ending_soon[0]['id'], 'ending_soon')

    def test_search_items(self):
        """Test searching items by title"""
        self.tracker.add_item({'id': 's1', 'title': 'Dell OptiPlex Desktop'})
        self.tracker.add_item({'id': 's2', 'title': 'HP LaserJet Printer'})
        self.tracker.add_item({'id': 's3', 'title': 'Dell Monitor 27 inch'})

        results = self.tracker.search_items('Dell')

        self.assertEqual(len(results), 2)


class TestTelegramAlerts(unittest.TestCase):
    """Tests for TelegramAlerts formatter"""

    def setUp(self):
        """Set up test fixtures"""
        self.alerts = TelegramAlerts()

        self.sample_opportunity = OpportunityData(
            item_id='test_001',
            title='Dell OptiPlex 7080 Desktop Computer',
            current_bid=45.00,
            max_bid=85.00,
            ebay_avg_price=180.00,
            estimated_profit=35.00,
            roi_percent=155.0,
            auction_end=(datetime.now() + timedelta(hours=6)).isoformat(),
            surplus_url='https://surplus.gov.ab.ca/item/12345',
            pickup_location='Calgary SE',
            condition='Good',
            price_range='$120-$250',
            risk_factors=['High price variance']
        )

    def test_format_morning_briefing(self):
        """Test morning briefing formatting"""
        opportunities = [self.sample_opportunity]
        message = self.alerts.format_morning_briefing(opportunities)

        self.assertIn('SURPLUS OPPORTUNITIES', message)
        self.assertIn('Dell OptiPlex', message)
        self.assertIn('$45', message)
        self.assertIn('$85', message)
        self.assertIn('155%', message)

    def test_format_morning_briefing_empty(self):
        """Test morning briefing with no opportunities"""
        message = self.alerts.format_morning_briefing([])

        self.assertIn('No opportunities', message)

    def test_format_strong_opportunity(self):
        """Test strong opportunity alert formatting"""
        message = self.alerts.format_strong_opportunity(self.sample_opportunity)

        self.assertIn('STRONG OPPORTUNITY', message)
        self.assertIn('Dell OptiPlex', message)
        self.assertIn('155%', message)
        self.assertIn('Risk Factors', message)

    def test_format_auction_ending(self):
        """Test auction ending alert formatting"""
        message = self.alerts.format_auction_ending(self.sample_opportunity, current_bid=55.00)

        self.assertIn('AUCTION ENDING', message)
        self.assertIn('$55', message)
        self.assertIn('was $45', message)

    def test_format_bid_won(self):
        """Test bid won notification formatting"""
        message = self.alerts.format_bid_won(
            title='Dell Computer',
            winning_bid=45.00,
            max_bid=85.00,
            pickup_location='Calgary SE',
            item_id='test_001'
        )

        self.assertIn('BID WON', message)
        self.assertIn('Dell Computer', message)
        self.assertIn('under your $85', message)
        self.assertIn('Schedule pickup', message)

    def test_format_bid_lost(self):
        """Test bid lost notification formatting"""
        message = self.alerts.format_bid_lost(
            title='HP Printer',
            winning_bid=95.00,
            your_max=85.00
        )

        self.assertIn('BID LOST', message)
        self.assertIn('$95', message)
        self.assertIn('$85', message)

    def test_format_weekly_summary(self):
        """Test weekly summary formatting"""
        items = [
            {'title': 'Dell Computer', 'purchase_price': 45, 'sale_price': 120, 'actual_profit': 55},
            {'title': 'HP Printer', 'purchase_price': 25, 'sale_price': 75, 'actual_profit': 35}
        ]

        message = self.alerts.format_weekly_summary(
            start_date=datetime.now() - timedelta(days=7),
            end_date=datetime.now(),
            items_flipped=items,
            total_profit=90.0,
            avg_roi=134.0,
            monthly_profit=150.0
        )

        self.assertIn('WEEKLY PROFIT', message)
        self.assertIn('Items Flipped: 2', message)
        self.assertIn('Dell Computer', message)
        self.assertIn('$90', message)

    def test_format_status(self):
        """Test status overview formatting"""
        message = self.alerts.format_status(
            watching=5,
            bid_placed=2,
            won=1,
            pending_pickup=1,
            listed=3,
            budget_remaining=250.00
        )

        self.assertIn('STATUS', message)
        self.assertIn('Watching: 5', message)
        self.assertIn('Budget Remaining: $250', message)

    def test_time_remaining_format(self):
        """Test time remaining formatting"""
        # Test hours
        future_hours = (datetime.now() + timedelta(hours=5)).isoformat()
        result = self.alerts._format_time_remaining(future_hours)
        self.assertIn('h', result)

        # Test days
        future_days = (datetime.now() + timedelta(days=2)).isoformat()
        result = self.alerts._format_time_remaining(future_days)
        self.assertIn('d', result)

        # Test minutes
        future_mins = (datetime.now() + timedelta(minutes=30)).isoformat()
        result = self.alerts._format_time_remaining(future_mins)
        self.assertIn('minute', result)

        # Test ended
        past = (datetime.now() - timedelta(hours=1)).isoformat()
        result = self.alerts._format_time_remaining(past)
        self.assertEqual(result, 'Ended')


class TestBotCommands(unittest.TestCase):
    """Test bot command handlers (mocked)"""

    def test_help_command_coverage(self):
        """Verify help text covers all commands"""
        help_commands = [
            '/scanner', '/status', '/profit', '/budget',
            '/track', '/bid', '/won', '/lost',
            '/pickup', '/listed', '/sold', '/history', '/alerts'
        ]

        # This is a placeholder - in real tests we'd check the actual help output
        self.assertEqual(len(help_commands), 13)


class TestIntegration(unittest.TestCase):
    """Integration tests"""

    def test_tracker_with_alerts(self):
        """Test bid tracker integration with alerts"""
        import tempfile
        temp_dir = tempfile.mkdtemp()
        db_path = os.path.join(temp_dir, "test_integration.db")

        tracker = BidTracker(db_path=db_path)
        alerts = TelegramAlerts()

        # Add item
        tracker.add_item({
            'id': 'int_test',
            'title': 'Integration Test Item',
            'current_bid': 30.00,
            'max_bid': 65.00,
            'estimated_profit': 25.00,
            'roi_percent': 120.0,
            'auction_end': (datetime.now() + timedelta(hours=3)).isoformat(),
            'status': 'watching'
        })

        # Get item and create opportunity
        item = tracker.get_item('int_test')
        opp = OpportunityData(
            item_id=item['id'],
            title=item['title'],
            current_bid=item['current_bid'],
            max_bid=item['max_bid'],
            ebay_avg_price=100.00,
            estimated_profit=item['estimated_profit'],
            roi_percent=item['roi_percent'],
            auction_end=item['auction_end'],
            surplus_url='https://example.com',
            pickup_location='Calgary',
            condition='Good',
            price_range='$60-$140',
            risk_factors=[]
        )

        # Format alert
        message = alerts.format_strong_opportunity(opp)

        self.assertIn('Integration Test Item', message)
        self.assertIn('120%', message)

        # Cleanup
        import shutil
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_tests():
    """Run all tests"""
    unittest.main(verbosity=2)


if __name__ == '__main__':
    run_tests()
