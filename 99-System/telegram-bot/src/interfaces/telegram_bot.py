#!/usr/bin/env python3
"""
Albatross Telegram Bot
Mobile interface for surplus arbitrage system
"""

import os
import sys
import logging
import asyncio
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, Any

# Try to import telegram library
try:
    from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
    from telegram.ext import (
        Application,
        CommandHandler,
        CallbackQueryHandler,
        MessageHandler,
        ContextTypes,
        filters
    )
    TELEGRAM_AVAILABLE = True
except ImportError:
    TELEGRAM_AVAILABLE = False
    # Create placeholder types for when library isn't installed
    Update = Any
    InlineKeyboardButton = Any
    InlineKeyboardMarkup = Any
    Application = Any
    CommandHandler = Any
    CallbackQueryHandler = Any
    MessageHandler = Any
    ContextTypes = type('ContextTypes', (), {'DEFAULT_TYPE': Any})
    filters = None

import yaml

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.utils.bid_tracker import BidTracker
from src.interfaces.telegram_alerts import TelegramAlerts, OpportunityData

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class AlbatrossBot:
    """
    Telegram bot for Albatross surplus arbitrage system.

    Commands:
    - /start - Welcome message
    - /help - Command list
    - /scanner - Run manual scan
    - /status - Show active bids and tracked items
    - /profit - This month's profit summary
    - /budget - View/set weekly spending limit
    - /track [id] - Add item to tracking
    - /bid [item] $XX - Log a bid decision
    - /history - Show completed flips
    - /alerts - Toggle notifications
    """

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize Albatross bot.

        Args:
            config_path: Path to telegram.yaml config
        """
        self.config = self._load_config(config_path)
        self.bot_token = os.environ.get('TELEGRAM_BOT_TOKEN')
        self.chat_id = os.environ.get('TELEGRAM_CHAT_ID')

        # Initialize components
        self.tracker = BidTracker()
        self.alerts = TelegramAlerts(self.bot_token, self.chat_id)

        # Application placeholder
        self.app: Optional['Application'] = None

        # User state tracking
        self.user_states: Dict[int, Dict] = {}

    def _load_config(self, config_path: Optional[str]) -> Dict:
        """Load configuration from YAML file"""
        if config_path is None:
            config_path = Path(__file__).parent.parent.parent / "config" / "telegram.yaml"

        try:
            with open(config_path, 'r') as f:
                return yaml.safe_load(f)
        except FileNotFoundError:
            logger.warning(f"Config not found at {config_path}, using defaults")
            return {}

    # ==================== Command Handlers ====================

    async def start_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        welcome_text = """
🎯 *ALBATROSS SURPLUS BOT*

Your mobile arbitrage assistant.

*Commands:*
/scanner - Run manual scan
/status - View tracked items
/profit - See earnings
/budget - Spending limits
/help - All commands

*You'll receive alerts for:*
• Monday/Wednesday opportunities
• High ROI items (100%+)
• Auctions ending soon

Ready to find profitable flips!
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')

    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        help_text = """
📖 *ALBATROSS COMMANDS*

*Scanning & Discovery:*
/scanner - Run surplus scan now
/status - See all tracked items

*Bidding:*
/track <id> - Track a surplus item
/bid <id> $XX - Log your max bid
/won <id> - Mark item as won
/lost <id> - Mark item as lost

*After Winning:*
/pickup <id> - Mark as picked up
/listed <id> - Mark as listed for sale
/sold <id> $XX - Record sale price

*Finances:*
/profit - This month's earnings
/history - Completed flips
/budget - View weekly budget
/budget $XXX - Set weekly budget

*Settings:*
/alerts on|off - Toggle notifications

*Examples:*
`/bid surplus_001 $45`
`/sold surplus_001 $120`
`/budget $500`
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def scanner_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /scanner command - run surplus scan"""
        await update.message.reply_text("🔍 Starting surplus scan...")

        try:
            # Import and run scanner
            from src.surplus.scanner import SurplusScanner
            from src.surplus.ebay_research_apify import ApifyEbayResearcher
            from src.surplus.calculator import ROICalculator

            scanner = SurplusScanner()
            items = scanner.scan(test_mode=False)  # Live data from surplus website

            if not items:
                await update.message.reply_text("No items found in Calgary area.")
                return

            # Research items
            researcher = ApifyEbayResearcher()
            research_data = researcher.research_batch(items, test_mode=False)

            # Calculate ROI
            calculator = ROICalculator()
            results = calculator.calculate_batch(items, research_data)

            # Get actionable items
            actionable = calculator.get_actionable_items()

            if not actionable:
                await update.message.reply_text(
                    f"✅ Scanned {len(items)} items\n"
                    f"No opportunities meeting ROI threshold."
                )
                return

            # Format opportunities
            opportunities = []
            for result in actionable[:5]:
                item = next((i for i in items if i.item_id == result.item_id), None)
                if item:
                    opp = OpportunityData(
                        item_id=result.item_id,
                        title=result.item_title,
                        current_bid=result.current_bid,
                        max_bid=result.max_bid,
                        ebay_avg_price=result.ebay_avg_price,
                        estimated_profit=result.estimated_profit,
                        roi_percent=result.roi_percent,
                        auction_end=item.auction_end,
                        surplus_url=item.url,
                        pickup_location=item.pickup_location,
                        condition=item.condition,
                        price_range=f"${result.ebay_avg_price:.0f}",
                        risk_factors=result.risk_factors
                    )
                    opportunities.append(opp)

                    # Add to tracker
                    self.tracker.add_item({
                        'id': result.item_id,
                        'title': result.item_title,
                        'surplus_url': item.url,
                        'category': item.category,
                        'condition': item.condition,
                        'current_bid': result.current_bid,
                        'max_bid': result.max_bid,
                        'ebay_avg_price': result.ebay_avg_price,
                        'estimated_profit': result.estimated_profit,
                        'roi_percent': result.roi_percent,
                        'auction_end': item.auction_end,
                        'status': 'watching'
                    })

            # Send formatted briefing
            text = self.alerts.format_morning_briefing(opportunities)
            keyboard = self.alerts.get_briefing_keyboard(opportunities)

            await update.message.reply_text(text, parse_mode='Markdown', reply_markup=keyboard)

        except Exception as e:
            logger.error(f"Scanner error: {e}")
            await update.message.reply_text(f"❌ Scan failed: {str(e)[:100]}")

    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command"""
        stats = self.tracker.get_stats()
        budget = self.tracker.get_budget()
        spent = self.tracker.get_weekly_spent()

        text = self.alerts.format_status(
            watching=stats.get('watching', 0),
            bid_placed=stats.get('bid_placed', 0),
            won=stats.get('won', 0),
            pending_pickup=stats.get('picked_up', 0),
            listed=stats.get('listed', 0),
            budget_remaining=budget['weekly_budget'] - spent
        )

        # Add active items
        active = self.tracker.get_active_bids()
        if active:
            text += "\n\n*Active Items:*\n"
            for item in active[:5]:
                emoji = {'watching': '👁️', 'bid_placed': '🎯', 'won': '✅'}.get(item['status'], '📦')
                text += f"{emoji} {item['title'][:30]}... (${item['max_bid']:.0f})\n"

        await update.message.reply_text(text, parse_mode='Markdown')

    async def profit_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /profit command"""
        # Get current month profit
        monthly = self.tracker.get_monthly_profit()
        summary = self.tracker.get_profit_summary(days=30)

        text = "📊 *PROFIT SUMMARY*\n\n"

        # This month
        month_name = datetime.now().strftime("%B %Y")
        text += f"*{month_name}:*\n"
        text += f"Items Sold: {monthly['items_sold']}\n"
        text += f"Total Profit: ${monthly['total_profit']:.0f}\n"
        text += f"Total Invested: ${monthly['total_invested']:.0f}\n"

        if monthly['items_sold'] > 0:
            text += f"Avg ROI: {monthly['avg_roi']:.0f}%\n"

        # Last 30 days detail
        text += f"\n*Last 30 Days:*\n"
        text += f"Revenue: ${summary['total_revenue']:.0f}\n"
        text += f"Fees: ${summary['total_fees']:.0f}\n"
        text += f"Net Profit: ${summary['total_profit']:.0f}\n"

        if summary['avg_days_to_sell'] > 0:
            text += f"Avg Days to Sell: {summary['avg_days_to_sell']:.0f}\n"

        await update.message.reply_text(text, parse_mode='Markdown')

    async def budget_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /budget command"""
        args = context.args

        if args and args[0].startswith('$'):
            # Set new budget
            try:
                new_budget = float(args[0].replace('$', ''))
                self.tracker.set_budget(weekly_budget=new_budget)
                await update.message.reply_text(f"✅ Weekly budget set to ${new_budget:.0f}")
                return
            except ValueError:
                await update.message.reply_text("❌ Invalid amount. Use: /budget $500")
                return

        # Show current budget
        budget = self.tracker.get_budget()
        spent = self.tracker.get_weekly_spent()
        remaining = budget['weekly_budget'] - spent

        text = "💰 *BUDGET STATUS*\n\n"
        text += f"Weekly Budget: ${budget['weekly_budget']:.0f}\n"
        text += f"Spent This Week: ${spent:.0f}\n"
        text += f"Remaining: ${remaining:.0f}\n"
        text += f"\nMax Single Bid: ${budget['max_single_bid']:.0f}\n"
        text += f"\nTo change: `/budget $XXX`"

        await update.message.reply_text(text, parse_mode='Markdown')

    async def track_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /track command"""
        args = context.args

        if not args:
            await update.message.reply_text(
                "Usage: `/track <item_id>`\n"
                "Example: `/track surplus_001`",
                parse_mode='Markdown'
            )
            return

        item_id = args[0]
        item = self.tracker.get_item(item_id)

        if item:
            text = f"📦 *{item['title']}*\n\n"
            text += f"Status: {item['status']}\n"
            text += f"Current Bid: ${item['current_bid']:.0f}\n"
            text += f"Your Max: ${item['max_bid']:.0f}\n"
            text += f"Est. Profit: ${item['estimated_profit']:.0f}\n"
            text += f"ROI: {item['roi_percent']:.0f}%\n"

            if item['auction_end']:
                text += f"\nAuction Ends: {item['auction_end'][:16]}"

            await update.message.reply_text(text, parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ Item `{item_id}` not found", parse_mode='Markdown')

    async def bid_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /bid command - log a bid decision"""
        args = context.args

        if len(args) < 2:
            await update.message.reply_text(
                "Usage: `/bid <item_id> $XX`\n"
                "Example: `/bid surplus_001 $45`",
                parse_mode='Markdown'
            )
            return

        item_id = args[0]
        try:
            max_bid = float(args[1].replace('$', ''))
        except ValueError:
            await update.message.reply_text("❌ Invalid bid amount")
            return

        # Update item
        success = self.tracker.update_item(item_id, {
            'max_bid': max_bid,
            'status': 'bid_placed'
        })

        if success:
            item = self.tracker.get_item(item_id)
            await update.message.reply_text(
                f"✅ Bid logged for *{item['title'][:40]}*\n"
                f"Max bid: ${max_bid:.0f}\n"
                f"Status: bid\\_placed",
                parse_mode='Markdown'
            )
        else:
            # Create new tracking entry
            self.tracker.add_item({
                'id': item_id,
                'title': f"Item {item_id}",
                'max_bid': max_bid,
                'status': 'bid_placed'
            })
            await update.message.reply_text(f"✅ New item tracked with max bid ${max_bid:.0f}")

    async def won_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /won command"""
        args = context.args

        if not args:
            await update.message.reply_text("Usage: `/won <item_id>`", parse_mode='Markdown')
            return

        item_id = args[0]
        purchase_price = float(args[1].replace('$', '')) if len(args) > 1 else None

        updates = {'status': 'won'}
        if purchase_price:
            updates['purchase_price'] = purchase_price

        success = self.tracker.update_item(item_id, updates)

        if success:
            await update.message.reply_text(
                f"🎉 Congratulations! Item marked as WON.\n"
                f"Next: `/pickup {item_id}` when collected",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Item `{item_id}` not found", parse_mode='Markdown')

    async def lost_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /lost command"""
        args = context.args

        if not args:
            await update.message.reply_text("Usage: `/lost <item_id>`", parse_mode='Markdown')
            return

        item_id = args[0]
        success = self.tracker.update_status(item_id, 'lost')

        if success:
            await update.message.reply_text("😔 Item marked as LOST. On to the next one!")
        else:
            await update.message.reply_text(f"❌ Item `{item_id}` not found", parse_mode='Markdown')

    async def pickup_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /pickup command"""
        args = context.args

        if not args:
            await update.message.reply_text("Usage: `/pickup <item_id>`", parse_mode='Markdown')
            return

        item_id = args[0]
        success = self.tracker.update_status(item_id, 'picked_up')

        if success:
            await update.message.reply_text(
                f"📦 Item picked up!\n"
                f"Next: Test, clean, photograph\n"
                f"Then: `/listed {item_id}`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Item `{item_id}` not found", parse_mode='Markdown')

    async def listed_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /listed command"""
        args = context.args

        if not args:
            await update.message.reply_text("Usage: `/listed <item_id>`", parse_mode='Markdown')
            return

        item_id = args[0]
        success = self.tracker.update_status(item_id, 'listed')

        if success:
            await update.message.reply_text(
                f"🏷️ Item listed for sale!\n"
                f"When sold: `/sold {item_id} $XX`",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Item `{item_id}` not found", parse_mode='Markdown')

    async def sold_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /sold command"""
        args = context.args

        if len(args) < 2:
            await update.message.reply_text(
                "Usage: `/sold <item_id> $XX [fees]`\n"
                "Example: `/sold surplus_001 $120 $15`",
                parse_mode='Markdown'
            )
            return

        item_id = args[0]
        try:
            sale_price = float(args[1].replace('$', ''))
            fees = float(args[2].replace('$', '')) if len(args) > 2 else 0
        except ValueError:
            await update.message.reply_text("❌ Invalid amount")
            return

        success = self.tracker.record_sale(item_id, sale_price, fees)

        if success:
            item = self.tracker.get_item(item_id)
            profit = item.get('actual_profit', 0)

            emoji = "🎉" if profit > 0 else "😕"
            await update.message.reply_text(
                f"{emoji} *FLIP COMPLETED!*\n\n"
                f"*{item['title'][:40]}*\n"
                f"Sale Price: ${sale_price:.0f}\n"
                f"Fees: ${fees:.0f}\n"
                f"Profit: ${profit:.0f}",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(f"❌ Item `{item_id}` not found", parse_mode='Markdown')

    async def history_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /history command"""
        sold_items = self.tracker.get_items_by_status('sold')

        if not sold_items:
            await update.message.reply_text("No completed flips yet.")
            return

        text = "📜 *FLIP HISTORY*\n\n"

        total_profit = 0
        for item in sold_items[:10]:
            profit = item.get('actual_profit', 0)
            total_profit += profit
            emoji = "✅" if profit > 0 else "❌"

            text += f"{emoji} *{item['title'][:30]}*\n"
            text += f"   ${item.get('purchase_price', 0):.0f} → ${item.get('sale_price', 0):.0f} = "
            text += f"${profit:.0f}\n"

        text += f"\n*Total: ${total_profit:.0f}*"

        await update.message.reply_text(text, parse_mode='Markdown')

    async def alerts_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /alerts command"""
        args = context.args

        if args and args[0].lower() in ['on', 'off']:
            state = args[0].lower()
            # Store in config or user preferences
            await update.message.reply_text(f"✅ Alerts turned {state}")
        else:
            await update.message.reply_text(
                "*Alert Settings*\n\n"
                "Use `/alerts on` or `/alerts off`\n\n"
                "You'll receive:\n"
                "• Morning briefings (Mon/Wed)\n"
                "• Strong opportunities (100%+ ROI)\n"
                "• Auction ending reminders",
                parse_mode='Markdown'
            )

    # ==================== Callback Handlers ====================

    async def button_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle inline keyboard button presses"""
        query = update.callback_query
        await query.answer()

        data = query.data

        if data.startswith('track_'):
            item_id = data.replace('track_', '')
            item = self.tracker.get_item(item_id)
            if item:
                await query.edit_message_text(
                    f"✅ Now tracking: {item['title'][:40]}...\n"
                    f"Use `/bid {item_id} $XX` to log your max bid",
                    parse_mode='Markdown'
                )

        elif data.startswith('bid_'):
            item_id = data.replace('bid_', '')
            self.tracker.update_status(item_id, 'bid_placed')
            await query.edit_message_text(f"✅ Marked as bidding on {item_id}")

        elif data.startswith('dismiss_'):
            await query.edit_message_text("✅ Dismissed")

        elif data == 'cmd_scanner':
            await query.edit_message_text("Running scan... use /scanner")

        elif data == 'cmd_history':
            await query.edit_message_text("Use /history to see completed flips")

    # ==================== Error Handler ====================

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle errors"""
        logger.error(f"Update {update} caused error {context.error}")

        if update and update.effective_message:
            await update.effective_message.reply_text(
                "❌ An error occurred. Please try again."
            )

    # ==================== Application Setup ====================

    def setup(self) -> 'Application':
        """Set up the bot application"""
        if not TELEGRAM_AVAILABLE:
            raise ImportError("python-telegram-bot not installed")

        if not self.bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN not set")

        self.app = Application.builder().token(self.bot_token).build()

        # Add command handlers
        self.app.add_handler(CommandHandler("start", self.start_command))
        self.app.add_handler(CommandHandler("help", self.help_command))
        self.app.add_handler(CommandHandler("scanner", self.scanner_command))
        self.app.add_handler(CommandHandler("status", self.status_command))
        self.app.add_handler(CommandHandler("profit", self.profit_command))
        self.app.add_handler(CommandHandler("budget", self.budget_command))
        self.app.add_handler(CommandHandler("track", self.track_command))
        self.app.add_handler(CommandHandler("bid", self.bid_command))
        self.app.add_handler(CommandHandler("won", self.won_command))
        self.app.add_handler(CommandHandler("lost", self.lost_command))
        self.app.add_handler(CommandHandler("pickup", self.pickup_command))
        self.app.add_handler(CommandHandler("listed", self.listed_command))
        self.app.add_handler(CommandHandler("sold", self.sold_command))
        self.app.add_handler(CommandHandler("history", self.history_command))
        self.app.add_handler(CommandHandler("alerts", self.alerts_command))

        # Add callback handler for buttons
        self.app.add_handler(CallbackQueryHandler(self.button_callback))

        # Add error handler
        self.app.add_error_handler(self.error_handler)

        return self.app

    def run(self):
        """Run the bot"""
        if not self.app:
            self.setup()

        logger.info("Starting Albatross Bot...")
        self.app.run_polling(allowed_updates=Update.ALL_TYPES)


def main():
    """CLI entry point"""
    import argparse

    parser = argparse.ArgumentParser(description="Albatross Telegram Bot")
    parser.add_argument('--config', type=str, help="Path to config file")
    parser.add_argument('--test', action='store_true', help="Test mode (don't start polling)")

    args = parser.parse_args()

    # Check for token
    if not os.environ.get('TELEGRAM_BOT_TOKEN'):
        print("=" * 50)
        print("TELEGRAM_BOT_TOKEN not set!")
        print("=" * 50)
        print("\nTo set up:")
        print("1. Message @BotFather on Telegram")
        print("2. Create new bot: /newbot")
        print("3. Copy the token")
        print("4. Set environment variable:")
        print("   export TELEGRAM_BOT_TOKEN='your_token_here'")
        print("\nAlso set TELEGRAM_CHAT_ID (get from @userinfobot)")
        return

    bot = AlbatrossBot(config_path=args.config)

    if args.test:
        print("=" * 50)
        print("Albatross Bot - Test Mode")
        print("=" * 50)
        print(f"Bot token: {bot.bot_token[:20]}...")
        print(f"Chat ID: {bot.chat_id}")
        print("\nBot would start with these commands:")
        print("  /start, /help, /scanner, /status, /profit")
        print("  /budget, /track, /bid, /won, /lost")
        print("  /pickup, /listed, /sold, /history, /alerts")
        print("\nRun without --test to start bot")
    else:
        bot.run()


if __name__ == "__main__":
    main()
