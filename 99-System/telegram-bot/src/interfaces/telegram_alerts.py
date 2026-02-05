#!/usr/bin/env python3
"""
Telegram Alert Formatter
Formats and sends Telegram alerts for the surplus arbitrage system
"""

import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass
import asyncio

# Try to import telegram library
try:
    from telegram import Bot, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.constants import ParseMode
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    Bot = None

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@dataclass
class OpportunityData:
    """Data for an opportunity alert"""
    item_id: str
    title: str
    current_bid: float
    max_bid: float
    ebay_avg_price: float
    estimated_profit: float
    roi_percent: float
    auction_end: str
    surplus_url: str
    pickup_location: str
    condition: str
    price_range: str
    risk_factors: List[str]


class TelegramAlerts:
    """
    Formats and sends Telegram alerts for surplus opportunities.

    Alert types:
    - Morning briefing (Mon/Wed 6:05 AM)
    - Strong opportunity (immediate, ROI >100%)
    - Auction ending (15 min before)
    - Bid won/lost
    - Weekly profit summary
    """

    def __init__(self, bot_token: Optional[str] = None, chat_id: Optional[str] = None):
        """
        Initialize Telegram alerts.

        Args:
            bot_token: Telegram bot token (or from TELEGRAM_BOT_TOKEN env)
            chat_id: Chat ID to send to (or from TELEGRAM_CHAT_ID env)
        """
        self.bot_token = bot_token or os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.environ.get('TELEGRAM_CHAT_ID')
        self.bot = None

        if TELEGRAM_AVAILABLE and self.bot_token:
            self.bot = Bot(token=self.bot_token)

    def _format_time_remaining(self, auction_end: str) -> str:
        """Format time remaining until auction ends"""
        try:
            end_dt = datetime.fromisoformat(auction_end.replace('Z', '+00:00'))
            now = datetime.now(end_dt.tzinfo) if end_dt.tzinfo else datetime.now()
            delta = end_dt - now

            if delta.total_seconds() < 0:
                return "Ended"

            hours = int(delta.total_seconds() // 3600)
            minutes = int((delta.total_seconds() % 3600) // 60)

            if hours > 24:
                days = hours // 24
                return f"{days}d {hours % 24}h"
            elif hours > 0:
                return f"{hours}h {minutes}m"
            else:
                return f"{minutes} minutes"

        except (ValueError, TypeError):
            return "Unknown"

    def _format_date(self, date_str: str) -> str:
        """Format date for display"""
        try:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return dt.strftime("%a %I:%M %p")
        except (ValueError, TypeError):
            return date_str

    # ==================== Morning Briefing ====================

    def format_morning_briefing(
        self,
        opportunities: List[OpportunityData],
        date: datetime = None
    ) -> str:
        """
        Format morning briefing message.

        Args:
            opportunities: List of opportunities (should be top 3-5)
            date: Date for briefing (default: today)

        Returns:
            Formatted Telegram message
        """
        if date is None:
            date = datetime.now()

        day_name = date.strftime("%A")
        date_str = date.strftime("%b %d")

        if not opportunities:
            return (
                f"🎯 *SURPLUS OPPORTUNITIES - {day_name}, {date_str}*\n\n"
                f"No opportunities meeting criteria today.\n\n"
                f"I'll keep scanning on schedule."
            )

        message = f"🎯 *SURPLUS OPPORTUNITIES - {day_name}, {date_str}*\n"
        message += f"{len(opportunities)} items found from Alberta Gov Surplus\n\n"

        for i, opp in enumerate(opportunities[:5], 1):
            roi_emoji = "🔥" if opp.roi_percent >= 200 else "✅" if opp.roi_percent >= 100 else "⚪"
            time_remaining = self._format_time_remaining(opp.auction_end)
            end_time = self._format_date(opp.auction_end)

            message += f"*{i}. {opp.title[:40]}*\n"
            message += f"   Current: ${opp.current_bid:.0f} | Max: ${opp.max_bid:.0f} | "
            message += f"Profit: ${opp.estimated_profit:.0f} ({opp.roi_percent:.0f}% ROI) {roi_emoji}\n"
            message += f"   Ends: {end_time} ({time_remaining})\n"

            # Add warnings if needed
            if opp.risk_factors:
                warning = opp.risk_factors[0][:30]
                message += f"   ⚠️ {warning}\n"

            message += "\n"

        message += "─────────────────\n"
        message += "Reply with item # to track, or tap buttons below"

        return message

    def get_briefing_keyboard(self, opportunities: List[OpportunityData]) -> Optional['InlineKeyboardMarkup']:
        """
        Create inline keyboard for briefing.

        Args:
            opportunities: List of opportunities

        Returns:
            InlineKeyboardMarkup or None
        """
        if not TELEGRAM_AVAILABLE:
            return None

        buttons = []

        for i, opp in enumerate(opportunities[:5], 1):
            buttons.append([
                InlineKeyboardButton(
                    f"#{i} View",
                    url=opp.surplus_url if opp.surplus_url.startswith('http') else f"https://surplus.gov.ab.ca{opp.surplus_url}"
                ),
                InlineKeyboardButton(
                    f"Track #{i}",
                    callback_data=f"track_{opp.item_id}"
                )
            ])

        buttons.append([
            InlineKeyboardButton("Run New Scan", callback_data="cmd_scanner")
        ])

        return InlineKeyboardMarkup(buttons)

    # ==================== Strong Opportunity ====================

    def format_strong_opportunity(self, opp: OpportunityData) -> str:
        """
        Format immediate alert for strong opportunity.

        Args:
            opp: Opportunity data

        Returns:
            Formatted message
        """
        time_remaining = self._format_time_remaining(opp.auction_end)
        end_time = self._format_date(opp.auction_end)

        message = "⚡ *STRONG OPPORTUNITY DETECTED*\n\n"
        message += f"*{opp.title}*\n\n"
        message += f"Current Bid: ${opp.current_bid:.0f}\n"
        message += f"Your Max: ${opp.max_bid:.0f}\n"
        message += f"Potential Profit: ${opp.estimated_profit:.0f} ({opp.roi_percent:.0f}% ROI)\n\n"
        message += f"Auction ends: {end_time} ({time_remaining})\n"

        if opp.price_range:
            message += f"eBay Price Range: {opp.price_range}\n"

        if opp.condition:
            message += f"Condition: {opp.condition}\n"

        if opp.pickup_location:
            message += f"Pickup: {opp.pickup_location}\n"

        if opp.risk_factors:
            message += "\n⚠️ *Risk Factors:*\n"
            for risk in opp.risk_factors[:3]:
                message += f"  • {risk}\n"

        return message

    def get_opportunity_keyboard(self, opp: OpportunityData) -> Optional['InlineKeyboardMarkup']:
        """Create keyboard for opportunity alert"""
        if not TELEGRAM_AVAILABLE:
            return None

        url = opp.surplus_url if opp.surplus_url.startswith('http') else f"https://surplus.gov.ab.ca{opp.surplus_url}"

        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("View Now", url=url),
                InlineKeyboardButton("Set Reminder", callback_data=f"remind_{opp.item_id}")
            ],
            [
                InlineKeyboardButton("I'm Bidding", callback_data=f"bid_{opp.item_id}"),
                InlineKeyboardButton("Dismiss", callback_data=f"dismiss_{opp.item_id}")
            ]
        ])

    # ==================== Auction Ending ====================

    def format_auction_ending(
        self,
        opp: OpportunityData,
        current_bid: float = None
    ) -> str:
        """
        Format auction ending reminder.

        Args:
            opp: Opportunity data
            current_bid: Updated current bid if available

        Returns:
            Formatted message
        """
        time_remaining = self._format_time_remaining(opp.auction_end)
        actual_bid = current_bid if current_bid else opp.current_bid

        message = "⏰ *AUCTION ENDING SOON*\n\n"
        message += f"*{opp.title}*\n\n"
        message += f"Current Bid: ${actual_bid:.0f}"

        if current_bid and current_bid != opp.current_bid:
            message += f" (was ${opp.current_bid:.0f})"

        message += "\n"
        message += f"Your Max: ${opp.max_bid:.0f}\n"
        message += f"Time Left: {time_remaining}\n\n"

        # Warning if approaching max
        if actual_bid >= opp.max_bid * 0.85:
            message += "⚠️ *Current bid approaching your max!*\n\n"

        return message

    def get_auction_ending_keyboard(self, opp: OpportunityData) -> Optional['InlineKeyboardMarkup']:
        """Create keyboard for auction ending alert"""
        if not TELEGRAM_AVAILABLE:
            return None

        url = opp.surplus_url if opp.surplus_url.startswith('http') else f"https://surplus.gov.ab.ca{opp.surplus_url}"

        return InlineKeyboardMarkup([
            [
                InlineKeyboardButton("Go Bid Now", url=url),
                InlineKeyboardButton("Increase Max", callback_data=f"increase_{opp.item_id}")
            ],
            [
                InlineKeyboardButton("Let It Go", callback_data=f"skip_{opp.item_id}")
            ]
        ])

    # ==================== Bid Results ====================

    def format_bid_won(
        self,
        title: str,
        winning_bid: float,
        max_bid: float,
        pickup_location: str,
        item_id: str
    ) -> str:
        """Format bid won notification"""
        message = "🎉 *BID WON!*\n\n"
        message += f"*{title}*\n\n"
        message += f"Winning Bid: ${winning_bid:.0f}"

        if winning_bid < max_bid:
            message += f" (under your ${max_bid:.0f} max)"

        message += "\n"
        message += f"Pickup: {pickup_location}\n\n"
        message += "*Next steps:*\n"
        message += "1. Schedule pickup\n"
        message += "2. Test thoroughly\n"
        message += "3. List on eBay/Kijiji\n"
        message += f"4. Track profit: `/track {item_id}`\n"

        return message

    def format_bid_lost(
        self,
        title: str,
        winning_bid: float,
        your_max: float
    ) -> str:
        """Format bid lost notification"""
        message = "😔 *BID LOST*\n\n"
        message += f"*{title}*\n\n"
        message += f"Winning Bid: ${winning_bid:.0f}\n"
        message += f"Your Max: ${your_max:.0f}\n\n"

        if winning_bid <= your_max * 1.1:
            message += "💡 Close one! Consider higher max next time for similar items."
        else:
            message += "✅ Good discipline staying under your max."

        return message

    # ==================== Profit Summary ====================

    def format_weekly_summary(
        self,
        start_date: datetime,
        end_date: datetime,
        items_flipped: List[Dict],
        total_profit: float,
        avg_roi: float,
        monthly_profit: float = 0
    ) -> str:
        """
        Format weekly profit summary.

        Args:
            start_date: Week start
            end_date: Week end
            items_flipped: List of sold items
            total_profit: Total profit for week
            avg_roi: Average ROI

        Returns:
            Formatted message
        """
        date_range = f"{start_date.strftime('%b %d')}-{end_date.strftime('%d')}, {end_date.year}"

        message = "📊 *WEEKLY PROFIT SUMMARY*\n\n"
        message += f"{date_range}\n\n"

        if items_flipped:
            message += f"*Items Flipped: {len(items_flipped)}*\n"

            for item in items_flipped[:5]:
                profit = item.get('actual_profit', 0)
                emoji = "✅" if profit > 0 else "❌"
                message += f"{emoji} {item.get('title', 'Unknown')[:30]}: "
                message += f"${item.get('purchase_price', 0):.0f} → ${item.get('sale_price', 0):.0f} = "
                message += f"${profit:.0f} profit\n"

            message += f"\n*Total Profit: ${total_profit:.0f}*\n"
            message += f"Avg ROI: {avg_roi:.0f}%\n"

        else:
            message += "No items sold this week.\n"

        if monthly_profit > 0:
            message += f"\nThis Month: ${monthly_profit:.0f}"

        return message

    def get_summary_keyboard(self) -> Optional['InlineKeyboardMarkup']:
        """Create keyboard for summary"""
        if not TELEGRAM_AVAILABLE:
            return None

        return InlineKeyboardMarkup([
            [InlineKeyboardButton("View Full History", callback_data="cmd_history")]
        ])

    # ==================== Status Messages ====================

    def format_status(
        self,
        watching: int,
        bid_placed: int,
        won: int,
        pending_pickup: int,
        listed: int,
        budget_remaining: float
    ) -> str:
        """Format status overview message"""
        message = "📋 *ALBATROSS STATUS*\n\n"
        message += f"👁️ Watching: {watching}\n"
        message += f"🎯 Bid Placed: {bid_placed}\n"
        message += f"✅ Won (pending): {won}\n"
        message += f"📦 Pending Pickup: {pending_pickup}\n"
        message += f"🏷️ Listed: {listed}\n"
        message += f"\n💰 Budget Remaining: ${budget_remaining:.0f}"

        return message

    # ==================== Sending ====================

    async def send_message(
        self,
        text: str,
        keyboard: 'InlineKeyboardMarkup' = None,
        parse_mode: str = 'Markdown'
    ) -> bool:
        """
        Send a message via Telegram.

        Args:
            text: Message text
            keyboard: Optional inline keyboard
            parse_mode: Parse mode (Markdown/HTML)

        Returns:
            True if sent successfully
        """
        if not self.bot or not self.chat_id:
            print(f"[TELEGRAM] {text[:100]}...")
            return False

        try:
            await self.bot.send_message(
                chat_id=self.chat_id,
                text=text,
                parse_mode=parse_mode,
                reply_markup=keyboard
            )
            return True

        except Exception as e:
            print(f"Telegram send failed: {e}")
            return False

    def send_sync(
        self,
        text: str,
        keyboard: 'InlineKeyboardMarkup' = None
    ) -> bool:
        """
        Synchronous wrapper for sending messages.

        Args:
            text: Message text
            keyboard: Optional keyboard

        Returns:
            True if sent
        """
        try:
            return asyncio.run(self.send_message(text, keyboard))
        except RuntimeError:
            # Already in an async context
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.send_message(text, keyboard))

    async def send_morning_briefing(self, opportunities: List[OpportunityData]) -> bool:
        """Send morning briefing"""
        text = self.format_morning_briefing(opportunities)
        keyboard = self.get_briefing_keyboard(opportunities)
        return await self.send_message(text, keyboard)

    async def send_strong_opportunity(self, opp: OpportunityData) -> bool:
        """Send strong opportunity alert"""
        text = self.format_strong_opportunity(opp)
        keyboard = self.get_opportunity_keyboard(opp)
        return await self.send_message(text, keyboard)

    async def send_auction_ending(self, opp: OpportunityData, current_bid: float = None) -> bool:
        """Send auction ending reminder"""
        text = self.format_auction_ending(opp, current_bid)
        keyboard = self.get_auction_ending_keyboard(opp)
        return await self.send_message(text, keyboard)

    async def send_test_message(self) -> bool:
        """Send a test message to verify bot works"""
        text = "🤖 *Albatross Bot Test*\n\nBot is connected and working!"
        return await self.send_message(text)


def main():
    """Test alert formatting"""
    print("=" * 50)
    print("Telegram Alerts Test")
    print("=" * 50)

    alerts = TelegramAlerts()

    # Test opportunity
    opp = OpportunityData(
        item_id="test_001",
        title="Dell OptiPlex 7080 Desktop Computer",
        current_bid=45.00,
        max_bid=85.00,
        ebay_avg_price=180.00,
        estimated_profit=35.00,
        roi_percent=155.0,
        auction_end=(datetime.now() + timedelta(hours=6)).isoformat(),
        surplus_url="https://surplus.gov.ab.ca/item/12345",
        pickup_location="Calgary SE",
        condition="Good",
        price_range="$120-$250",
        risk_factors=["High price variance"]
    )

    print("\n--- Morning Briefing ---")
    print(alerts.format_morning_briefing([opp, opp]))

    print("\n--- Strong Opportunity ---")
    print(alerts.format_strong_opportunity(opp))

    print("\n--- Auction Ending ---")
    print(alerts.format_auction_ending(opp, 55.00))

    print("\n--- Bid Won ---")
    print(alerts.format_bid_won(opp.title, 45.00, 85.00, "Calgary SE", "test_001"))

    print("\n--- Weekly Summary ---")
    items = [
        {'title': 'Dell Computer', 'purchase_price': 45, 'sale_price': 120, 'actual_profit': 55},
        {'title': 'HP Printer', 'purchase_price': 25, 'sale_price': 75, 'actual_profit': 35}
    ]
    print(alerts.format_weekly_summary(
        datetime.now() - timedelta(days=7),
        datetime.now(),
        items,
        90.0,
        134.0,
        150.0
    ))

    # Test sending if credentials available
    if alerts.bot and alerts.chat_id:
        print("\n--- Sending Test Message ---")
        asyncio.run(alerts.send_test_message())
        print("Test message sent!")
    else:
        print("\n[No Telegram credentials - messages printed only]")


if __name__ == "__main__":
    main()
