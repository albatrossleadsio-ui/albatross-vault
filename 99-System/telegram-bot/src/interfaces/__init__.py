"""
Albatross Interfaces Module
User-facing interfaces for the surplus arbitrage system
"""

try:
    from .telegram_bot import AlbatrossBot
except ImportError:
    AlbatrossBot = None

from .telegram_alerts import TelegramAlerts, OpportunityData

__all__ = [
    'AlbatrossBot',
    'TelegramAlerts',
    'OpportunityData',
]
