#!/usr/bin/env python3
"""
Daily Briefing Cron Script
Part of Albatross Phase 4 - Core Build

Runs via cron at 7:00 AM daily to send the morning briefing.

Cron entry:
    0 7 * * * /home/kg/albatross/venv/bin/python /home/kg/albatross/src/utils/send_daily_briefing.py

Usage:
    python send_daily_briefing.py
"""

import os
import sys
from datetime import datetime
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.utils.telegram import send_daily_briefing, send_error_alert


def get_system_status() -> dict:
    """
    Gather system status information.

    In production, this would check actual services.
    """
    # TODO: Implement actual system checks
    # - Check token guardian balance
    # - Ping T490 services
    # - Check VPS connectivity
    # - Get last git sync time

    return {
        'token_guardian': '1.23 / 5.00',  # TODO: Read from actual source
        't490_status': 'online',
        'vps_status': 'online',
        'last_sync': datetime.now().strftime('%H:%M'),
    }


def get_leads_summary() -> dict:
    """
    Gather lead generation summary.

    In production, this would read from leads database/files.
    """
    # TODO: Implement actual lead checking
    # - Count new leads from surplus scanner
    # - Check Reddit scanner results
    # - Count qualified leads

    return {
        'new_leads': 0,
        'qualified': 0,
        'needs_action': 0,
    }


def get_content_status() -> dict:
    """
    Gather NGN content status.

    In production, this would check content files/queue.
    """
    # TODO: Implement actual content checking
    # - Check if Monday roundup is drafted
    # - Check Wednesday preview status
    # - Count queued social posts

    today = datetime.now()
    day_of_week = today.weekday()  # 0=Monday

    # Default status based on day
    monday_status = 'ready' if day_of_week == 0 else 'pending'
    wednesday_status = 'ready' if day_of_week == 2 else 'pending'

    return {
        'monday_roundup': monday_status,
        'wednesday_preview': wednesday_status,
        'social_content': 0,
    }


def get_decisions_needed() -> list:
    """
    Gather items that need human decision.

    In production, this would check action items.
    """
    # TODO: Implement actual decision checking
    # - Check for leads needing qualification
    # - Check for content needing approval
    # - Check for errors needing attention

    decisions = []

    # Example: Check if there are unreviewed surplus leads
    surplus_output = Path.home() / 'research' / 'output'
    if surplus_output.exists():
        today = datetime.now().strftime('%Y-%m-%d')
        surplus_file = surplus_output / f'surplus-scan-{today}.json'
        # Could parse and check for strong bids needing review

    return decisions


def main():
    """Main entry point for daily briefing."""
    print(f"[{datetime.now()}] Generating daily briefing...")

    try:
        # Gather all status information
        system_status = get_system_status()
        leads_summary = get_leads_summary()
        content_status = get_content_status()
        decisions_needed = get_decisions_needed()

        # Send the briefing
        success = send_daily_briefing(
            system_status=system_status,
            leads_summary=leads_summary,
            content_status=content_status,
            decisions_needed=decisions_needed if decisions_needed else None
        )

        if success:
            print(f"[{datetime.now()}] Daily briefing sent successfully")
        else:
            print(f"[{datetime.now()}] Failed to send daily briefing")

    except Exception as e:
        print(f"[{datetime.now()}] Error: {e}")
        # Try to send error alert
        send_error_alert("Daily Briefing", str(e))


if __name__ == '__main__':
    main()
