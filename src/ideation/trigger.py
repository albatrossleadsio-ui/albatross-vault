#!/usr/bin/env python3
"""
Ideation Trigger for Albatross Ideation Engine
Part of Albatross Phase 4 - Ideation

Main loop - poll for APPROVED decisions and trigger Ralph-Lite.
This is the ENTRY POINT for automated building.
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from src.ideation.docs_reader import (
    GoogleDocsReader, get_docs_reader, AnalysisEntry
)
from src.ideation.tweet_analyzer import analyze_tweet
from src.ideation.deep_researcher import do_research
from src.ideation.opportunity_matcher import find_matches
from src.ideation.proposal_generator import (
    create_proposal, create_proposal_object, ProposalGenerator
)

logger = logging.getLogger(__name__)


class IdeationTrigger:
    """
    Main ideation engine that polls for bookmarks and triggers builds.

    This is the ENTRY POINT for automated building.
    """

    def __init__(self, poll_interval_minutes: int = 30):
        self.docs = get_docs_reader()
        self.poll_interval = poll_interval_minutes * 60  # Convert to seconds
        self.running = False

    def run_once(self):
        """
        Process one cycle: check bookmarks, analyze, trigger builds.

        Call this manually or from cron.
        """
        logger.info("Ideation cycle started")

        # Step 1: Check for new bookmarks (Section 1)
        bookmarks = self.docs.read_section_1()
        logger.info(f"Found {len(bookmarks)} pending bookmarks")

        for bookmark in bookmarks:
            logger.info(f"Processing bookmark: {bookmark.id}")

            try:
                # Mark as analyzing
                self.docs.update_bookmark_status(bookmark.id, 'analyzing')

                # Step 2: Analyze tweet/content
                analysis = analyze_tweet(bookmark.content)
                logger.info(f"Domain: {analysis.suggested_domain}")

                # Step 3: Deep research
                research = do_research(
                    analysis.suggested_domain,
                    bookmark.content
                )

                # Step 4: Find pattern matches
                matches = find_matches(
                    analysis.suggested_domain,
                    analysis.technology_mentions,
                    analysis.market_indicators,
                    bookmark.content
                )

                # Step 5: Generate proposal
                proposal = create_proposal_object(
                    bookmark.id,
                    analysis,
                    research,
                    matches
                )
                proposal_text = ProposalGenerator().format_for_telegram(proposal)

                # Step 6: Write to Section 2 (analysis)
                entry = AnalysisEntry(
                    bookmark_id=bookmark.id,
                    domain=analysis.suggested_domain,
                    market_research=research.market_size,
                    opportunity_score=proposal.confidence_score,
                    proposal=proposal_text,
                    estimated_cost=proposal.estimated_metrics['cost'],
                    estimated_iterations=proposal.estimated_metrics['iterations']
                )
                self.docs.write_section_2(entry)

                # Mark as analyzed
                self.docs.update_bookmark_status(bookmark.id, 'analyzed')

                # Send Telegram notification (if available)
                self._notify_proposal_ready(bookmark.id, proposal)

                logger.info(f"Bookmark {bookmark.id} analyzed successfully")

            except Exception as e:
                logger.error(f"Error processing bookmark {bookmark.id}: {e}")
                self.docs.update_bookmark_status(bookmark.id, 'error')

        # Step 7: Check for APPROVED decisions (Section 3)
        decisions = self.docs.read_section_3()
        logger.info(f"Found {len(decisions)} approved decisions")

        for decision in decisions:
            if decision.decision == 'APPROVED':
                logger.info(f"Triggering build for: {decision.bookmark_id}")

                try:
                    # Trigger Ralph-Lite
                    self._trigger_build(decision)

                    # Mark as processed
                    self.docs.update_bookmark_status(decision.bookmark_id, 'building')

                except Exception as e:
                    logger.error(f"Error triggering build: {e}")

        logger.info("Ideation cycle complete")

    def _notify_proposal_ready(self, bookmark_id: str, proposal):
        """Send Telegram notification about new proposal."""
        try:
            from src.utils.telegram import send_message
            send_message(
                f"New proposal ready: <b>{proposal.title}</b>\n\n"
                f"Confidence: {proposal.confidence_score}/10\n"
                f"Recommendation: {proposal.recommendation}\n\n"
                f"Reply BUILD to approve, or check ideation_queue.json"
            )
        except Exception as e:
            logger.warning(f"Could not send Telegram notification: {e}")

    def _trigger_build(self, decision):
        """Trigger Ralph-Lite build."""
        # Get bookmark details
        bookmark = self.docs.get_bookmark_by_id(decision.bookmark_id)
        if not bookmark:
            logger.error(f"Bookmark not found: {decision.bookmark_id}")
            return

        # Create project name
        project_name = f"ideation-{bookmark.id[:8]}"

        try:
            from src.core.ralph_lite import RalphLiteOrchestrator

            # Trigger Ralph-Lite
            orch = RalphLiteOrchestrator(
                project_name=project_name,
                source_idea=bookmark.content
            )

            # Run build
            result = orch.run()

            logger.info(f"Build result: {result}")

            # Notify user
            self._notify_build_complete(project_name, result)

        except ImportError:
            logger.error("Ralph-Lite not available")
        except Exception as e:
            logger.error(f"Build failed: {e}")
            self._notify_build_failed(project_name, str(e))

    def _notify_build_complete(self, project_name: str, result: dict):
        """Notify user of build completion."""
        try:
            from src.utils.telegram import send_message

            if result.get('success'):
                send_message(
                    f"Build complete: <b>{project_name}</b>\n\n"
                    f"Location: {result.get('project_path')}\n"
                    f"Cost: ${result.get('total_cost', 0):.2f}"
                )
            else:
                send_message(
                    f"Build paused: <b>{project_name}</b>\n\n"
                    f"Reason: {result.get('reason', 'Unknown')}"
                )
        except Exception as e:
            logger.warning(f"Could not send notification: {e}")

    def _notify_build_failed(self, project_name: str, error: str):
        """Notify user of build failure."""
        try:
            from src.utils.telegram import send_alert
            send_alert("Build Failed", f"{project_name}: {error}", "error")
        except Exception as e:
            logger.warning(f"Could not send notification: {e}")

    def run_continuous(self):
        """Run ideation engine continuously (background)."""
        self.running = True

        logger.info(f"Ideation engine started (poll every {self.poll_interval}s)")

        while self.running:
            try:
                self.run_once()
            except Exception as e:
                logger.error(f"Ideation cycle error: {e}")

            # Sleep until next poll
            time.sleep(self.poll_interval)

    def stop(self):
        """Stop continuous run."""
        self.running = False
        logger.info("Ideation engine stopping...")


# Convenience functions
def process_bookmarks():
    """Process one ideation cycle."""
    trigger = IdeationTrigger()
    trigger.run_once()


def start_ideation_engine(poll_minutes: int = 30):
    """Start continuous ideation engine."""
    trigger = IdeationTrigger(poll_interval_minutes=poll_minutes)
    trigger.run_continuous()


def add_and_process_bookmark(content: str, notes: str = "") -> str:
    """
    Add bookmark and immediately process it.

    Usage:
        from src.ideation.trigger import add_and_process_bookmark
        add_and_process_bookmark(
            "Made $50K with county assessor scraper...",
            "Research real estate opportunity"
        )
    """
    from src.ideation.docs_reader import add_bookmark_manual

    # Add bookmark
    bookmark_id = add_bookmark_manual(content, notes)

    # Process immediately
    trigger = IdeationTrigger()
    trigger.run_once()

    return bookmark_id


def quick_analyze(content: str) -> dict:
    """
    Quick analysis without saving to queue.

    Returns analysis results for review.
    """
    analysis = analyze_tweet(content)
    research = do_research(analysis.suggested_domain, content)
    matches = find_matches(
        analysis.suggested_domain,
        analysis.technology_mentions,
        analysis.market_indicators,
        content
    )

    proposal = create_proposal_object("quick_analysis", analysis, research, matches)

    return {
        'domain': analysis.suggested_domain,
        'metrics': analysis.metrics,
        'tech': analysis.technology_mentions,
        'market': analysis.market_indicators,
        'confidence': proposal.confidence_score,
        'recommendation': proposal.recommendation,
        'matches': [m.pattern_name for m in matches],
        'proposal': ProposalGenerator().format_for_telegram(proposal)
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Albatross Ideation Engine")
    parser.add_argument('--once', action='store_true', help="Run once and exit")
    parser.add_argument('--continuous', action='store_true', help="Run continuously")
    parser.add_argument('--poll', type=int, default=30, help="Poll interval in minutes")
    parser.add_argument('--analyze', type=str, help="Quick analyze a string")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    if args.analyze:
        result = quick_analyze(args.analyze)
        print(f"\nDomain: {result['domain']}")
        print(f"Confidence: {result['confidence']}/10")
        print(f"Recommendation: {result['recommendation']}")
        print(f"Matches: {result['matches']}")
        print(f"\n{result['proposal']}")

    elif args.continuous:
        print(f"Starting continuous ideation engine (poll every {args.poll} min)")
        start_ideation_engine(args.poll)

    else:
        print("Running single ideation cycle...")
        process_bookmarks()
        print("Done.")
