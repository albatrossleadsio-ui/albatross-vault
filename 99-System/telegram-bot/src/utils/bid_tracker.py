#!/usr/bin/env python3
"""
Bid Tracker Database
SQLite database for tracking surplus items through their lifecycle
"""

import json
import os
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict


@dataclass
class TrackedItem:
    """Represents a tracked surplus item"""
    id: str
    title: str
    surplus_item_id: str
    surplus_url: str
    category: str
    condition: str

    # Pricing data
    current_bid: float
    max_bid: float
    ebay_avg_price: float
    ebay_price_range: str
    estimated_profit: float
    roi_percent: float

    # Auction timing
    auction_end: str
    first_alert_sent: bool
    final_alert_sent: bool

    # Status workflow
    status: str  # watching, bid_placed, won, lost, picked_up, listed, sold

    # Actuals (filled after purchase/sale)
    purchase_price: Optional[float]
    sale_price: Optional[float]
    fees: float
    actual_profit: Optional[float]
    days_to_sell: Optional[int]

    # Metadata
    created_at: str
    updated_at: str
    notes: str


class BidTracker:
    """
    SQLite database for tracking surplus items through their lifecycle.

    Status workflow:
        watching -> bid_placed -> won/lost -> picked_up -> listed -> sold

    Features:
    - Track items from discovery to sale
    - Calculate actual vs estimated profit
    - Generate profit reports
    - Alert management
    """

    VALID_STATUSES = [
        'watching', 'bid_placed', 'won', 'lost',
        'picked_up', 'listed', 'sold', 'cancelled'
    ]

    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize bid tracker.

        Args:
            db_path: Path to SQLite database file
        """
        if db_path is None:
            # Default: ~/albatross/data/surplus_bids.db
            data_dir = Path.home() / "albatross" / "data"
            data_dir.mkdir(parents=True, exist_ok=True)
            db_path = str(data_dir / "surplus_bids.db")

        self.db_path = db_path
        self._init_database()

    def _init_database(self):
        """Initialize database schema"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS surplus_items (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                surplus_item_id TEXT,
                surplus_url TEXT,
                category TEXT,
                condition TEXT,

                -- Pricing data
                current_bid REAL DEFAULT 0,
                max_bid REAL DEFAULT 0,
                ebay_avg_price REAL DEFAULT 0,
                ebay_price_range TEXT,
                estimated_profit REAL DEFAULT 0,
                roi_percent REAL DEFAULT 0,

                -- Auction timing
                auction_end TIMESTAMP,
                first_alert_sent BOOLEAN DEFAULT 0,
                final_alert_sent BOOLEAN DEFAULT 0,

                -- Status workflow
                status TEXT DEFAULT 'watching',

                -- Actuals (filled after purchase/sale)
                purchase_price REAL,
                sale_price REAL,
                fees REAL DEFAULT 0,
                actual_profit REAL,
                days_to_sell INTEGER,

                -- Metadata
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes TEXT DEFAULT ''
            )
        ''')

        # Indexes for common queries
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_status ON surplus_items(status)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_auction_end ON surplus_items(auction_end)')
        cursor.execute('CREATE INDEX IF NOT EXISTS idx_created_at ON surplus_items(created_at)')

        # Budget tracking table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS budget_settings (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                weekly_budget REAL DEFAULT 500,
                max_single_bid REAL DEFAULT 100,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        # Insert default budget if not exists
        cursor.execute('INSERT OR IGNORE INTO budget_settings (id) VALUES (1)')

        conn.commit()
        conn.close()

    def _get_connection(self) -> sqlite3.Connection:
        """Get database connection with row factory"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _row_to_dict(self, row: sqlite3.Row) -> Dict:
        """Convert sqlite3.Row to dictionary"""
        return dict(row)

    def _generate_id(self) -> str:
        """Generate unique item ID"""
        return f"track_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"

    # ==================== Item Management ====================

    def add_item(self, item_data: Dict) -> str:
        """
        Add a new item to track.

        Args:
            item_data: Dict with item details

        Returns:
            Generated item ID
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        item_id = item_data.get('id') or self._generate_id()
        now = datetime.now().isoformat()

        cursor.execute('''
            INSERT OR REPLACE INTO surplus_items (
                id, title, surplus_item_id, surplus_url, category, condition,
                current_bid, max_bid, ebay_avg_price, ebay_price_range,
                estimated_profit, roi_percent, auction_end, status,
                created_at, updated_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            item_id,
            item_data.get('title', 'Unknown Item'),
            item_data.get('surplus_item_id', ''),
            item_data.get('surplus_url', ''),
            item_data.get('category', ''),
            item_data.get('condition', 'Unknown'),
            item_data.get('current_bid', 0),
            item_data.get('max_bid', 0),
            item_data.get('ebay_avg_price', 0),
            item_data.get('ebay_price_range', ''),
            item_data.get('estimated_profit', 0),
            item_data.get('roi_percent', 0),
            item_data.get('auction_end'),
            item_data.get('status', 'watching'),
            now,
            now,
            item_data.get('notes', '')
        ))

        conn.commit()
        conn.close()

        return item_id

    def update_item(self, item_id: str, updates: Dict) -> bool:
        """
        Update an item's data.

        Args:
            item_id: Item ID to update
            updates: Dict of field:value pairs

        Returns:
            True if updated, False if item not found
        """
        if not updates:
            return False

        conn = self._get_connection()
        cursor = conn.cursor()

        # Build dynamic update query
        updates['updated_at'] = datetime.now().isoformat()
        set_clause = ', '.join([f'{k} = ?' for k in updates.keys()])
        values = list(updates.values()) + [item_id]

        cursor.execute(f'''
            UPDATE surplus_items SET {set_clause} WHERE id = ?
        ''', values)

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected > 0

    def get_item(self, item_id: str) -> Optional[Dict]:
        """
        Get item by ID.

        Args:
            item_id: Item ID

        Returns:
            Item dict or None
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM surplus_items WHERE id = ?', (item_id,))
        row = cursor.fetchone()

        conn.close()

        return self._row_to_dict(row) if row else None

    def delete_item(self, item_id: str) -> bool:
        """
        Delete an item.

        Args:
            item_id: Item ID to delete

        Returns:
            True if deleted, False if not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('DELETE FROM surplus_items WHERE id = ?', (item_id,))

        affected = cursor.rowcount
        conn.commit()
        conn.close()

        return affected > 0

    # ==================== Status Workflow ====================

    def update_status(self, item_id: str, new_status: str) -> bool:
        """
        Update item status.

        Args:
            item_id: Item ID
            new_status: New status (must be valid)

        Returns:
            True if updated
        """
        if new_status not in self.VALID_STATUSES:
            raise ValueError(f"Invalid status: {new_status}. Must be one of {self.VALID_STATUSES}")

        return self.update_item(item_id, {'status': new_status})

    def get_items_by_status(self, status: str) -> List[Dict]:
        """
        Get all items with a specific status.

        Args:
            status: Status to filter by

        Returns:
            List of items
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT * FROM surplus_items WHERE status = ? ORDER BY auction_end ASC',
            (status,)
        )
        rows = cursor.fetchall()

        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_active_bids(self) -> List[Dict]:
        """
        Get all active items (not yet resolved).

        Returns:
            List of active items
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM surplus_items
            WHERE status IN ('watching', 'bid_placed', 'won', 'picked_up', 'listed')
            ORDER BY auction_end ASC
        ''')
        rows = cursor.fetchall()

        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_all_items(self, limit: int = 100) -> List[Dict]:
        """
        Get all items.

        Args:
            limit: Maximum number to return

        Returns:
            List of items
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute(
            'SELECT * FROM surplus_items ORDER BY created_at DESC LIMIT ?',
            (limit,)
        )
        rows = cursor.fetchall()

        conn.close()

        return [self._row_to_dict(row) for row in rows]

    # ==================== Alerts ====================

    def get_pending_alerts(self, alert_type: str) -> List[Dict]:
        """
        Get items pending alerts.

        Args:
            alert_type: 'first' or 'final'

        Returns:
            List of items needing alerts
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now()

        if alert_type == 'first':
            # Items with auction ending in 24 hours, first alert not sent
            threshold = (now + timedelta(hours=24)).isoformat()
            cursor.execute('''
                SELECT * FROM surplus_items
                WHERE status IN ('watching', 'bid_placed')
                AND first_alert_sent = 0
                AND auction_end <= ?
                AND auction_end > ?
                ORDER BY auction_end ASC
            ''', (threshold, now.isoformat()))

        elif alert_type == 'final':
            # Items with auction ending in 15 minutes, final alert not sent
            threshold = (now + timedelta(minutes=15)).isoformat()
            cursor.execute('''
                SELECT * FROM surplus_items
                WHERE status IN ('watching', 'bid_placed')
                AND final_alert_sent = 0
                AND auction_end <= ?
                AND auction_end > ?
                ORDER BY auction_end ASC
            ''', (threshold, now.isoformat()))

        else:
            conn.close()
            return []

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def mark_alert_sent(self, item_id: str, alert_type: str) -> bool:
        """
        Mark an alert as sent.

        Args:
            item_id: Item ID
            alert_type: 'first' or 'final'

        Returns:
            True if updated
        """
        if alert_type == 'first':
            return self.update_item(item_id, {'first_alert_sent': True})
        elif alert_type == 'final':
            return self.update_item(item_id, {'final_alert_sent': True})
        return False

    # ==================== Profit Tracking ====================

    def record_sale(
        self,
        item_id: str,
        sale_price: float,
        fees: float = 0,
        notes: str = ""
    ) -> bool:
        """
        Record a completed sale.

        Args:
            item_id: Item ID
            sale_price: Sale price
            fees: Total fees (eBay, shipping, etc.)
            notes: Optional notes

        Returns:
            True if updated
        """
        item = self.get_item(item_id)
        if not item:
            return False

        purchase_price = item.get('purchase_price') or item.get('max_bid', 0)
        actual_profit = sale_price - purchase_price - fees

        # Calculate days to sell
        days_to_sell = None
        if item.get('auction_end'):
            try:
                auction_end = datetime.fromisoformat(item['auction_end'].replace('Z', '+00:00'))
                days_to_sell = (datetime.now() - auction_end).days
            except (ValueError, TypeError):
                pass

        updates = {
            'status': 'sold',
            'sale_price': sale_price,
            'fees': fees,
            'actual_profit': actual_profit,
            'days_to_sell': days_to_sell
        }

        if notes:
            updates['notes'] = (item.get('notes', '') + '\n' + notes).strip()

        return self.update_item(item_id, updates)

    def get_profit_summary(self, days: int = 30) -> Dict:
        """
        Get profit summary for a period.

        Args:
            days: Number of days to look back

        Returns:
            Profit summary dict
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cutoff = (datetime.now() - timedelta(days=days)).isoformat()

        cursor.execute('''
            SELECT
                COUNT(*) as total_items,
                SUM(CASE WHEN status = 'sold' THEN 1 ELSE 0 END) as items_sold,
                SUM(CASE WHEN status = 'sold' THEN actual_profit ELSE 0 END) as total_profit,
                SUM(CASE WHEN status = 'sold' THEN purchase_price ELSE 0 END) as total_invested,
                SUM(CASE WHEN status = 'sold' THEN sale_price ELSE 0 END) as total_revenue,
                SUM(CASE WHEN status = 'sold' THEN fees ELSE 0 END) as total_fees,
                AVG(CASE WHEN status = 'sold' THEN roi_percent END) as avg_roi,
                AVG(CASE WHEN status = 'sold' THEN days_to_sell END) as avg_days_to_sell
            FROM surplus_items
            WHERE updated_at >= ?
        ''', (cutoff,))

        row = cursor.fetchone()
        conn.close()

        return {
            'period_days': days,
            'total_items': row['total_items'] or 0,
            'items_sold': row['items_sold'] or 0,
            'total_profit': round(row['total_profit'] or 0, 2),
            'total_invested': round(row['total_invested'] or 0, 2),
            'total_revenue': round(row['total_revenue'] or 0, 2),
            'total_fees': round(row['total_fees'] or 0, 2),
            'avg_roi': round(row['avg_roi'] or 0, 1),
            'avg_days_to_sell': round(row['avg_days_to_sell'] or 0, 1)
        }

    def get_monthly_profit(self, year: int = None, month: int = None) -> Dict:
        """
        Get profit for a specific month.

        Args:
            year: Year (default: current)
            month: Month (default: current)

        Returns:
            Monthly profit dict
        """
        if year is None:
            year = datetime.now().year
        if month is None:
            month = datetime.now().month

        conn = self._get_connection()
        cursor = conn.cursor()

        start_date = f"{year}-{month:02d}-01"
        if month == 12:
            end_date = f"{year + 1}-01-01"
        else:
            end_date = f"{year}-{month + 1:02d}-01"

        cursor.execute('''
            SELECT
                COUNT(*) as items_sold,
                SUM(actual_profit) as total_profit,
                SUM(purchase_price) as total_invested,
                AVG(roi_percent) as avg_roi
            FROM surplus_items
            WHERE status = 'sold'
            AND updated_at >= ? AND updated_at < ?
        ''', (start_date, end_date))

        row = cursor.fetchone()
        conn.close()

        return {
            'year': year,
            'month': month,
            'items_sold': row['items_sold'] or 0,
            'total_profit': round(row['total_profit'] or 0, 2),
            'total_invested': round(row['total_invested'] or 0, 2),
            'avg_roi': round(row['avg_roi'] or 0, 1)
        }

    # ==================== Queries ====================

    def get_auctions_ending_soon(self, hours: int = 2) -> List[Dict]:
        """
        Get auctions ending within specified hours.

        Args:
            hours: Hours threshold

        Returns:
            List of items ending soon
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        now = datetime.now()
        threshold = (now + timedelta(hours=hours)).isoformat()

        cursor.execute('''
            SELECT * FROM surplus_items
            WHERE status IN ('watching', 'bid_placed')
            AND auction_end <= ?
            AND auction_end > ?
            ORDER BY auction_end ASC
        ''', (threshold, now.isoformat()))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def get_high_roi_items(self, min_roi: float = 100) -> List[Dict]:
        """
        Get items with ROI above threshold.

        Args:
            min_roi: Minimum ROI percentage

        Returns:
            List of high ROI items
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM surplus_items
            WHERE status IN ('watching', 'bid_placed')
            AND roi_percent >= ?
            ORDER BY roi_percent DESC
        ''', (min_roi,))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    def search_items(self, query: str) -> List[Dict]:
        """
        Search items by title.

        Args:
            query: Search query

        Returns:
            Matching items
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT * FROM surplus_items
            WHERE title LIKE ?
            ORDER BY created_at DESC
            LIMIT 20
        ''', (f'%{query}%',))

        rows = cursor.fetchall()
        conn.close()

        return [self._row_to_dict(row) for row in rows]

    # ==================== Budget ====================

    def get_budget(self) -> Dict:
        """Get current budget settings"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('SELECT * FROM budget_settings WHERE id = 1')
        row = cursor.fetchone()

        conn.close()

        return self._row_to_dict(row) if row else {'weekly_budget': 500, 'max_single_bid': 100}

    def set_budget(self, weekly_budget: float = None, max_single_bid: float = None) -> bool:
        """
        Update budget settings.

        Args:
            weekly_budget: Weekly spending limit
            max_single_bid: Max per item

        Returns:
            True if updated
        """
        conn = self._get_connection()
        cursor = conn.cursor()

        updates = []
        values = []

        if weekly_budget is not None:
            updates.append('weekly_budget = ?')
            values.append(weekly_budget)

        if max_single_bid is not None:
            updates.append('max_single_bid = ?')
            values.append(max_single_bid)

        if not updates:
            return False

        updates.append('updated_at = ?')
        values.append(datetime.now().isoformat())

        cursor.execute(f'''
            UPDATE budget_settings SET {', '.join(updates)} WHERE id = 1
        ''', values)

        conn.commit()
        conn.close()

        return True

    def get_weekly_spent(self) -> float:
        """Get total spent this week on active bids"""
        conn = self._get_connection()
        cursor = conn.cursor()

        # Start of current week (Monday)
        today = datetime.now()
        start_of_week = today - timedelta(days=today.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)

        cursor.execute('''
            SELECT SUM(COALESCE(purchase_price, max_bid)) as total
            FROM surplus_items
            WHERE status IN ('bid_placed', 'won', 'picked_up', 'listed')
            AND created_at >= ?
        ''', (start_of_week.isoformat(),))

        row = cursor.fetchone()
        conn.close()

        return round(row['total'] or 0, 2)

    # ==================== Utilities ====================

    def get_stats(self) -> Dict:
        """Get database statistics"""
        conn = self._get_connection()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'watching' THEN 1 ELSE 0 END) as watching,
                SUM(CASE WHEN status = 'bid_placed' THEN 1 ELSE 0 END) as bid_placed,
                SUM(CASE WHEN status = 'won' THEN 1 ELSE 0 END) as won,
                SUM(CASE WHEN status = 'lost' THEN 1 ELSE 0 END) as lost,
                SUM(CASE WHEN status = 'picked_up' THEN 1 ELSE 0 END) as picked_up,
                SUM(CASE WHEN status = 'listed' THEN 1 ELSE 0 END) as listed,
                SUM(CASE WHEN status = 'sold' THEN 1 ELSE 0 END) as sold
            FROM surplus_items
        ''')

        row = cursor.fetchone()
        conn.close()

        return self._row_to_dict(row)


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Bid Tracker Database")
    parser.add_argument('--db', type=str, help="Path to database file")
    parser.add_argument('--stats', action='store_true', help="Show database stats")
    parser.add_argument('--profit', type=int, default=30, help="Show profit summary for N days")
    parser.add_argument('--active', action='store_true', help="Show active bids")

    args = parser.parse_args()

    tracker = BidTracker(db_path=args.db)

    print("=" * 50)
    print("Bid Tracker Database")
    print("=" * 50)
    print(f"Database: {tracker.db_path}")

    if args.stats:
        print("\nDatabase Stats:")
        stats = tracker.get_stats()
        for key, value in stats.items():
            print(f"  {key}: {value}")

    if args.active:
        print("\nActive Bids:")
        items = tracker.get_active_bids()
        if items:
            for item in items:
                print(f"  - {item['title'][:40]}...")
                print(f"    Status: {item['status']} | Max: ${item['max_bid']}")
        else:
            print("  No active bids")

    print(f"\nProfit Summary ({args.profit} days):")
    profit = tracker.get_profit_summary(args.profit)
    for key, value in profit.items():
        print(f"  {key}: {value}")

    print("\nBudget:")
    budget = tracker.get_budget()
    spent = tracker.get_weekly_spent()
    print(f"  Weekly budget: ${budget['weekly_budget']}")
    print(f"  Max single bid: ${budget['max_single_bid']}")
    print(f"  Spent this week: ${spent}")


if __name__ == "__main__":
    main()
