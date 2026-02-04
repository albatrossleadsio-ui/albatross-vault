#!/usr/bin/env python3
"""
Opportunity Matcher for Albatross Ideation Engine
Part of Albatross Phase 4 - Ideation

Match opportunities to existing Albatross patterns.
This helps estimate build time and identify reusable code.
"""

from typing import Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class PatternMatch:
    """Match between opportunity and Albatross pattern."""
    pattern_name: str
    similarity_score: int  # 1-10
    reusable_components: List[str]
    estimated_adaptation_time: str
    confidence: str  # "high", "medium", "low"


class OpportunityMatcher:
    """
    Match opportunities to existing Albatross patterns.

    This helps estimate build time and identify reusable code.
    """

    # Existing Albatross patterns
    PATTERNS = {
        'surplus_scanner': {
            'description': 'Government surplus scraping + eBay research',
            'domain': 'web_scraping',
            'components': ['scraper.py', 'ebay_researcher.py', 'roi_calculator.py'],
            'tech': ['BeautifulSoup', 'requests', 'eBay API'],
            'iterations': 7,
            'keywords': ['surplus', 'auction', 'ebay', 'resale', 'government']
        },
        'lead_scraper': {
            'description': 'Kijiji/Facebook scraping for leads',
            'domain': 'web_scraping',
            'components': ['kijiji_scraper.py', 'lead_classifier.py'],
            'tech': ['BeautifulSoup', 'requests', 'selenium'],
            'iterations': 5,
            'keywords': ['leads', 'kijiji', 'facebook', 'marketplace', 'classified']
        },
        'content_generator': {
            'description': 'LPGA content generation',
            'domain': 'data_analysis',
            'components': ['roundup.py', 'preview.py', 'llm_client.py'],
            'tech': ['OpenCode Zen API', 'templates', 'markdown'],
            'iterations': 6,
            'keywords': ['content', 'blog', 'newsletter', 'generate', 'write']
        },
        'vps_research': {
            'description': '24/7 Reddit/LPGA monitoring',
            'domain': 'automation',
            'components': ['reddit_scanner.py', 'lpga_monitor.py', 'alert_sender.py'],
            'tech': ['praw', 'requests', 'cron'],
            'iterations': 4,
            'keywords': ['monitor', 'reddit', 'alert', 'watch', 'notify']
        },
        'telegram_bot': {
            'description': 'Telegram bot for notifications and commands',
            'domain': 'automation',
            'components': ['telegram.py', 'command_handler.py'],
            'tech': ['python-telegram-bot', 'requests'],
            'iterations': 4,
            'keywords': ['telegram', 'bot', 'notify', 'command', 'chat']
        },
        'price_tracker': {
            'description': 'Track prices across websites',
            'domain': 'web_scraping',
            'components': ['price_scraper.py', 'price_db.py', 'alert.py'],
            'tech': ['BeautifulSoup', 'requests', 'sqlite'],
            'iterations': 5,
            'keywords': ['price', 'track', 'monitor', 'deal', 'discount']
        }
    }

    def match(self, domain: str, tech_mentions: List[str],
              market_indicators: List[str], original_text: str = "") -> List[PatternMatch]:
        """
        Match opportunity to existing patterns.

        Args:
            domain: Domain from tweet_analyzer
            tech_mentions: Tech stack mentioned
            market_indicators: Market keywords
            original_text: Original tweet text for keyword matching

        Returns:
            List of PatternMatch objects, sorted by score
        """
        matches = []

        for pattern_name, pattern in self.PATTERNS.items():
            score = self._calculate_score(
                domain, tech_mentions, market_indicators, original_text, pattern
            )

            if score >= 4:  # Include reasonable matches
                confidence = 'high' if score >= 8 else ('medium' if score >= 6 else 'low')

                matches.append(PatternMatch(
                    pattern_name=pattern_name,
                    similarity_score=score,
                    reusable_components=pattern['components'],
                    estimated_adaptation_time=f"{max(1, pattern['iterations']-2)}-{pattern['iterations']} iterations",
                    confidence=confidence
                ))

        # Sort by score descending
        matches.sort(key=lambda x: x.similarity_score, reverse=True)
        return matches

    def _calculate_score(self, domain: str, tech_mentions: List[str],
                        market_indicators: List[str], original_text: str,
                        pattern: Dict) -> int:
        """Calculate similarity score."""
        score = 0

        # Domain match (4 points)
        if domain == pattern['domain']:
            score += 4

        # Tech overlap (up to 3 points)
        pattern_tech = [t.lower() for t in pattern['tech']]
        tech_matches = 0
        for tech in tech_mentions:
            if any(tech.lower() in pt for pt in pattern_tech):
                tech_matches += 1
        score += min(tech_matches, 3)

        # Keyword match (up to 3 points)
        text_lower = original_text.lower()
        keyword_matches = sum(1 for k in pattern.get('keywords', []) if k in text_lower)
        score += min(keyword_matches, 3)

        return min(score, 10)  # Cap at 10

    def get_best_match(self, domain: str, tech_mentions: List[str],
                      market_indicators: List[str], original_text: str = "") -> PatternMatch:
        """Get the single best matching pattern."""
        matches = self.match(domain, tech_mentions, market_indicators, original_text)
        if matches:
            return matches[0]

        # Return a generic match if nothing found
        return PatternMatch(
            pattern_name="generic_tool",
            similarity_score=3,
            reusable_components=['main.py', 'config.py'],
            estimated_adaptation_time="6-8 iterations",
            confidence="low"
        )

    def list_patterns(self) -> List[Dict]:
        """List all available patterns."""
        return [
            {
                'name': name,
                'description': pattern['description'],
                'domain': pattern['domain'],
                'components': pattern['components']
            }
            for name, pattern in self.PATTERNS.items()
        ]


# Convenience function
def find_matches(domain: str, tech: List[str], market: List[str],
                text: str = "") -> List[PatternMatch]:
    """Quick matching function."""
    matcher = OpportunityMatcher()
    return matcher.match(domain, tech, market, text)


if __name__ == "__main__":
    # Test
    matcher = OpportunityMatcher()

    matches = matcher.match(
        domain="web_scraping",
        tech_mentions=["BeautifulSoup", "requests"],
        market_indicators=["real estate"],
        original_text="Scraping county assessor data for real estate investors"
    )

    print("Matches found:")
    for match in matches:
        print(f"  - {match.pattern_name}: {match.similarity_score}/10 ({match.confidence})")
        print(f"    Components: {match.reusable_components}")
