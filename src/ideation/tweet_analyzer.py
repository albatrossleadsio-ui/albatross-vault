#!/usr/bin/env python3
"""
Tweet Analyzer for Albatross Ideation Engine
Part of Albatross Phase 4 - Ideation

Parse tweet/bookmark content to extract key information.
MVP: Pattern matching and keyword extraction.
Future: NLP with LLM.
"""

import re
from typing import Dict, List
from dataclasses import dataclass


@dataclass
class TweetAnalysis:
    """Analysis of a tweet/bookmark."""
    original_text: str
    key_claims: List[str]  # "Made $50K", "3 weeks to build"
    metrics: Dict[str, str]  # "$50K", "3 weeks"
    technology_mentions: List[str]  # "Python", "BeautifulSoup"
    market_indicators: List[str]  # "real estate", "investors"
    suggested_domain: str  # web_scraping, automation, etc.


class TweetAnalyzer:
    """
    Analyze tweet/bookmark content.

    MVP: Pattern matching and keyword extraction
    Future: NLP with LLM
    """

    # Domain keywords
    DOMAIN_PATTERNS = {
        'web_scraping': ['scrape', 'crawler', 'extract', 'data', 'website', 'spider', 'scraping'],
        'automation': ['automate', 'bot', 'cron', 'schedule', 'workflow', 'automated'],
        'api_integration': ['api', 'webhook', 'integration', 'connect', 'endpoint'],
        'data_analysis': ['analyze', 'dashboard', 'metrics', 'visualization', 'analytics'],
        'saas_microtool': ['tool', 'micro-saas', 'chrome extension', 'plugin', 'saas']
    }

    # Money patterns
    MONEY_PATTERN = r'\$[\d,]+(?:K|M)?|\d+K|\d+k|made \$\d+'

    # Time patterns
    TIME_PATTERN = r'\d+ (?:week|day|month|hour)s?'

    # Tech keywords to look for
    TECH_KEYWORDS = [
        'Python', 'BeautifulSoup', 'Selenium', 'JavaScript', 'TypeScript',
        'React', 'Node.js', 'API', 'scrapy', 'pandas', 'requests',
        'playwright', 'puppeteer', 'cheerio', 'axios', 'flask', 'django',
        'fastapi', 'nextjs', 'vercel', 'supabase', 'firebase'
    ]

    # Market keywords
    MARKET_KEYWORDS = [
        'real estate', 'investors', 'ecommerce', 'retail', 'contractors',
        'leads', 'b2b', 'saas', 'agencies', 'freelancers', 'startups',
        'small business', 'enterprise', 'marketing', 'sales'
    ]

    def analyze(self, text: str) -> TweetAnalysis:
        """
        Analyze tweet text.

        Args:
            text: Tweet content or bookmark text

        Returns:
            TweetAnalysis with extracted insights
        """
        # Extract key claims (sentences with numbers/money)
        sentences = [s.strip() for s in re.split(r'[.!?\n]', text) if s.strip()]
        key_claims = [s for s in sentences if self._has_metrics(s)]

        # Extract metrics
        metrics = {}
        money_matches = re.findall(self.MONEY_PATTERN, text, re.IGNORECASE)
        if money_matches:
            metrics['revenue'] = money_matches[0]

        time_matches = re.findall(self.TIME_PATTERN, text, re.IGNORECASE)
        if time_matches:
            metrics['time_to_build'] = time_matches[0]

        # Extract tech mentions
        technology_mentions = [t for t in self.TECH_KEYWORDS
                              if t.lower() in text.lower()]

        # Extract market indicators
        market_indicators = [m for m in self.MARKET_KEYWORDS
                            if m.lower() in text.lower()]

        # Determine domain
        suggested_domain = self._classify_domain(text)

        return TweetAnalysis(
            original_text=text,
            key_claims=key_claims[:3],  # Top 3 claims
            metrics=metrics,
            technology_mentions=technology_mentions,
            market_indicators=market_indicators,
            suggested_domain=suggested_domain
        )

    def _has_metrics(self, sentence: str) -> bool:
        """Check if sentence contains metrics (money, numbers, time)."""
        has_money = bool(re.search(self.MONEY_PATTERN, sentence))
        has_time = bool(re.search(self.TIME_PATTERN, sentence))
        has_number = bool(re.search(r'\d+', sentence))
        return has_money or has_time or has_number

    def _classify_domain(self, text: str) -> str:
        """Classify into domain based on keywords."""
        text_lower = text.lower()

        scores = {}
        for domain, keywords in self.DOMAIN_PATTERNS.items():
            score = sum(1 for k in keywords if k in text_lower)
            scores[domain] = score

        # Return highest scoring domain
        if scores:
            best = max(scores, key=scores.get)
            if scores[best] > 0:
                return best

        return 'general'

    def extract_opportunity_signals(self, text: str) -> Dict:
        """
        Extract signals that indicate a good opportunity.

        Returns dict with:
        - has_revenue: bool
        - has_timeframe: bool
        - has_tech_stack: bool
        - has_market: bool
        - signal_strength: int (0-4)
        """
        analysis = self.analyze(text)

        has_revenue = 'revenue' in analysis.metrics
        has_timeframe = 'time_to_build' in analysis.metrics
        has_tech_stack = len(analysis.technology_mentions) > 0
        has_market = len(analysis.market_indicators) > 0

        signal_strength = sum([
            has_revenue,
            has_timeframe,
            has_tech_stack,
            has_market
        ])

        return {
            'has_revenue': has_revenue,
            'has_timeframe': has_timeframe,
            'has_tech_stack': has_tech_stack,
            'has_market': has_market,
            'signal_strength': signal_strength
        }


# Convenience function
def analyze_tweet(text: str) -> TweetAnalysis:
    """Quick analysis function."""
    analyzer = TweetAnalyzer()
    return analyzer.analyze(text)


if __name__ == "__main__":
    # Test
    test_tweet = """
    Made $50K last year scraping county assessor data for real estate investors.
    Built it in 3 weeks with Python and BeautifulSoup.
    Now it runs automatically every day.
    """

    analysis = analyze_tweet(test_tweet)

    print(f"Domain: {analysis.suggested_domain}")
    print(f"Metrics: {analysis.metrics}")
    print(f"Tech: {analysis.technology_mentions}")
    print(f"Market: {analysis.market_indicators}")
    print(f"Claims: {analysis.key_claims}")
