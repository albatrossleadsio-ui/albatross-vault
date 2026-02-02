#!/usr/bin/env python3
"""
Reddit Business Opportunities Scanner
Part of Albatross Phase 3.4 - VPS Research Agent

Scans Reddit for business opportunities, side hustles, and revenue posts.
Designed to run on VPS (Ubuntu 24.04, Python 3.12).

Usage:
    python reddit_scanner.py

Environment Variables Required:
    REDDIT_CLIENT_ID     - Reddit API client ID
    REDDIT_CLIENT_SECRET - Reddit API client secret
"""

import os
import sys
import json
import logging
from datetime import datetime
from pathlib import Path

import praw
from prawcore.exceptions import ResponseException, OAuthException

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Configuration
SUBREDDITS = [
    'sweatystartup',
    'beermoney',
    'Entrepreneur',
    'smallbusiness',
    'sidehustle',
    'Calgary',
    'Alberta',
]

KEYWORDS = [
    'made $',
    'revenue',
    'earnings',
    'profit',
    'monthly',
    'side hustle',
    'business idea',
]

POSTS_PER_SUBREDDIT = 15
OUTPUT_DIR = Path.home() / 'research' / 'output'
USER_AGENT = 'AlbatrossResearchAgent/1.0 (by /u/albatross_research)'


def get_reddit_client() -> praw.Reddit:
    """
    Initialize and return Reddit API client.

    Returns:
        praw.Reddit instance

    Raises:
        SystemExit: If credentials are missing
    """
    client_id = os.environ.get('REDDIT_CLIENT_ID')
    client_secret = os.environ.get('REDDIT_CLIENT_SECRET')

    if not client_id or not client_secret:
        logger.error("Missing Reddit credentials!")
        logger.error("Set REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET environment variables")
        sys.exit(1)

    try:
        reddit = praw.Reddit(
            client_id=client_id,
            client_secret=client_secret,
            user_agent=USER_AGENT,
        )
        # Test connection (read-only mode)
        reddit.read_only = True
        logger.info("Reddit client initialized successfully")
        return reddit
    except Exception as e:
        logger.error(f"Failed to initialize Reddit client: {e}")
        sys.exit(1)


def matches_keywords(text: str) -> bool:
    """Check if text contains any of the target keywords."""
    if not text:
        return False
    text_lower = text.lower()
    return any(keyword.lower() in text_lower for keyword in KEYWORDS)


def scan_subreddit(reddit: praw.Reddit, subreddit_name: str) -> list[dict]:
    """
    Scan a subreddit for relevant posts.

    Args:
        reddit: praw.Reddit instance
        subreddit_name: Name of subreddit to scan

    Returns:
        List of matching post dictionaries
    """
    posts = []

    try:
        subreddit = reddit.subreddit(subreddit_name)
        logger.info(f"Scanning r/{subreddit_name}...")

        for submission in subreddit.hot(limit=POSTS_PER_SUBREDDIT):
            # Check title and selftext for keywords
            title = submission.title or ''
            selftext = submission.selftext or ''

            if matches_keywords(title) or matches_keywords(selftext):
                post_data = {
                    'title': title,
                    'subreddit': subreddit_name,
                    'score': submission.score,
                    'comments': submission.num_comments,
                    'url': f"https://reddit.com{submission.permalink}",
                    'timestamp': datetime.fromtimestamp(submission.created_utc).isoformat(),
                }
                posts.append(post_data)
                logger.debug(f"  Found: {title[:50]}...")

        logger.info(f"  Found {len(posts)} matching posts in r/{subreddit_name}")

    except ResponseException as e:
        logger.warning(f"API error scanning r/{subreddit_name}: {e}")
    except Exception as e:
        logger.warning(f"Error scanning r/{subreddit_name}: {e}")

    return posts


def save_results(posts: list[dict]) -> Path:
    """
    Save scan results to JSON file.

    Args:
        posts: List of post dictionaries

    Returns:
        Path to saved file
    """
    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Generate filename with date
    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"reddit-{date_str}.json"
    filepath = OUTPUT_DIR / filename

    # Save to JSON
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(posts, f, indent=2, ensure_ascii=False)

    logger.info(f"Results saved to: {filepath}")
    return filepath


def main():
    """Main entry point for Reddit scanner."""
    logger.info("=" * 50)
    logger.info("Reddit Business Opportunities Scanner")
    logger.info("=" * 50)

    # Initialize Reddit client
    reddit = get_reddit_client()

    # Scan all subreddits
    all_posts = []
    for subreddit_name in SUBREDDITS:
        posts = scan_subreddit(reddit, subreddit_name)
        all_posts.extend(posts)

    # Sort by score (highest first)
    all_posts.sort(key=lambda x: x['score'], reverse=True)

    # Save results
    if all_posts:
        filepath = save_results(all_posts)
        logger.info(f"Scan complete. Found {len(all_posts)} total matching posts.")
    else:
        logger.info("Scan complete. No matching posts found.")
        # Still save empty results for consistency
        save_results([])

    # Print summary
    print("\n" + "=" * 50)
    print("SCAN SUMMARY")
    print("=" * 50)
    print(f"Subreddits scanned: {len(SUBREDDITS)}")
    print(f"Total matching posts: {len(all_posts)}")

    if all_posts:
        print("\nTop 5 posts by score:")
        for post in all_posts[:5]:
            print(f"  [{post['score']:>4}] r/{post['subreddit']}: {post['title'][:45]}...")


if __name__ == '__main__':
    main()
