#!/usr/bin/env python3
"""
Enhanced Golf News Monitor (v2)
Part of Albatross Phase 3 - VPS Research Agent

Multi-source golf news aggregator covering professional and amateur women's golf.
Sources: Google News, DuckDuckGo, LPGA, Epson Tour, NCAA, Amateur circuits.

Usage:
    python lpga_monitor.py

NOTE: Some sites may require JavaScript rendering (Selenium).
      This script uses requests/BeautifulSoup for static scraping.
"""

import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from urllib.parse import quote_plus, urljoin

import requests
from bs4 import BeautifulSoup

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Enable/disable sources
SOURCES = {
    'google_news': True,
    'duckduckgo': True,
    'lpga_com': True,
    'epson_tour': True,
    'ncaa': True,
    'golf_channel': True,
    'golfweek': True,
    'usga': False,  # Often requires JavaScript
    'espn': False,  # Heavy JavaScript
}

# Search keywords
KEYWORDS = {
    'core': [
        'LPGA',
        'Ladies Professional Golf Association',
        "women's golf",
        'Epson Tour',
        'symetra tour',
    ],
    'events': [
        'major championship',
        'tournament results',
        'US Women Open',
        'Women PGA Championship',
        'Chevron Championship',
        'AIG Women Open',
        'Evian Championship',
        'NCAA women golf',
        'college golf',
        'amateur golf',
    ],
    'news_types': [
        'winner',
        'final round',
        'leaderboard',
        'qualifier',
        'rookie',
        'withdrawal',
        'injury',
        'sponsorship',
    ],
}

# All keywords flattened for matching
ALL_KEYWORDS = KEYWORDS['core'] + KEYWORDS['events'] + KEYWORDS['news_types']

# URLs
URLS = {
    'google_news_rss': 'https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en',
    'duckduckgo': 'https://html.duckduckgo.com/html/?q={query}',
    'lpga_com': 'https://www.lpga.com',
    'epson_tour': 'https://www.epsontour.com',
    'ncaa': 'https://www.ncaa.com/sports/golf-women',
    'golf_channel': 'https://www.golfchannel.com/tours/lpga',
    'golfweek': 'https://golfweek.usatoday.com/lpga/',
    'usga': 'https://www.usga.org',
}

# Output
OUTPUT_DIR = Path.home() / 'research' / 'output'

# Request settings
REQUEST_TIMEOUT = 15
REQUEST_DELAY = 1.0  # Rate limiting between requests
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
]

# Track scraped URLs to avoid duplicates
_scraped_urls = set()
_current_user_agent_idx = 0


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_headers() -> dict:
    """Get request headers with rotating User-Agent."""
    global _current_user_agent_idx
    ua = USER_AGENTS[_current_user_agent_idx % len(USER_AGENTS)]
    _current_user_agent_idx += 1
    return {
        'User-Agent': ua,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }


def rate_limit():
    """Enforce rate limiting between requests."""
    time.sleep(REQUEST_DELAY)


def fetch_page(url: str, is_xml: bool = False) -> Optional[BeautifulSoup | ET.Element]:
    """Fetch a page with error handling."""
    if url in _scraped_urls:
        logger.debug(f"Skipping already scraped: {url}")
        return None

    rate_limit()
    _scraped_urls.add(url)

    try:
        logger.info(f"Fetching: {url[:80]}...")
        response = requests.get(url, headers=get_headers(), timeout=REQUEST_TIMEOUT)
        response.raise_for_status()

        if is_xml:
            return ET.fromstring(response.content)
        return BeautifulSoup(response.text, 'html.parser')

    except requests.Timeout:
        logger.warning(f"Timeout: {url}")
    except requests.RequestException as e:
        logger.warning(f"Request failed: {url} - {e}")
    except ET.ParseError as e:
        logger.warning(f"XML parse error: {url} - {e}")

    return None


def match_keywords(text: str) -> list[str]:
    """Return list of keywords found in text."""
    if not text:
        return []
    text_lower = text.lower()
    return [kw for kw in ALL_KEYWORDS if kw.lower() in text_lower]


def categorize_article(title: str, content: str = '') -> str:
    """Categorize article as lpga/epson/college/amateur/general."""
    text = f"{title} {content}".lower()

    if any(term in text for term in ['ncaa', 'college golf', 'university', 'collegiate']):
        return 'college'
    if any(term in text for term in ['amateur', 'usga amateur', 'us amateur', 'junior golf', 'ajga']):
        return 'amateur'
    if any(term in text for term in ['epson tour', 'symetra', 'developmental']):
        return 'epson'
    if any(term in text for term in ['lpga', 'ladies professional']):
        return 'lpga'
    return 'general'


def clean_text(text: str) -> str:
    """Clean and normalize text."""
    if not text:
        return ''
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# =============================================================================
# SOURCE SCRAPERS
# =============================================================================

def scrape_google_news(query: str = 'LPGA women golf news') -> list[dict]:
    """
    Scrape Google News RSS for golf-related articles.

    Google News RSS is reliable and doesn't require JavaScript.
    """
    articles = []
    encoded_query = quote_plus(query)
    url = URLS['google_news_rss'].format(query=encoded_query)

    root = fetch_page(url, is_xml=True)
    if root is None:
        logger.warning("Google News: Failed to fetch RSS feed")
        return articles

    # Parse RSS items
    for item in root.findall('.//item'):
        try:
            title = item.find('title')
            link = item.find('link')
            pub_date = item.find('pubDate')
            source = item.find('source')

            title_text = title.text if title is not None else ''
            keywords = match_keywords(title_text)

            if not keywords:
                continue  # Skip if no relevant keywords

            articles.append({
                'title': clean_text(title_text),
                'source': source.text if source is not None else 'Google News',
                'url': link.text if link is not None else '',
                'published_date': pub_date.text if pub_date is not None else '',
                'category': categorize_article(title_text),
                'keywords_matched': keywords,
                'summary': '',
            })
        except Exception as e:
            logger.debug(f"Error parsing Google News item: {e}")
            continue

    logger.info(f"Google News: Found {len(articles)} articles")
    return articles


def scrape_duckduckgo(query: str = 'LPGA golf news') -> list[dict]:
    """
    Scrape DuckDuckGo HTML search results.

    Fallback when Google blocks or rate limits.
    """
    articles = []
    encoded_query = quote_plus(query)
    url = URLS['duckduckgo'].format(query=encoded_query)

    soup = fetch_page(url)
    if soup is None:
        logger.warning("DuckDuckGo: Failed to fetch search results")
        return articles

    # DuckDuckGo HTML results structure
    results = soup.select('.result, .results_links')

    for result in results[:15]:
        try:
            title_elem = result.select_one('.result__title, .result__a, a.result__url')
            snippet_elem = result.select_one('.result__snippet, .result__body')
            link_elem = result.select_one('a.result__a, a[href]')

            title = title_elem.get_text(strip=True) if title_elem else ''
            keywords = match_keywords(title)

            if not keywords:
                continue

            href = ''
            if link_elem and link_elem.get('href'):
                href = link_elem['href']
                # DuckDuckGo wraps URLs, try to extract actual URL
                if 'uddg=' in href:
                    match = re.search(r'uddg=([^&]+)', href)
                    if match:
                        from urllib.parse import unquote
                        href = unquote(match.group(1))

            articles.append({
                'title': clean_text(title),
                'source': 'DuckDuckGo',
                'url': href,
                'published_date': '',
                'category': categorize_article(title),
                'keywords_matched': keywords,
                'summary': clean_text(snippet_elem.get_text() if snippet_elem else ''),
            })
        except Exception as e:
            logger.debug(f"Error parsing DuckDuckGo result: {e}")
            continue

    logger.info(f"DuckDuckGo: Found {len(articles)} articles")
    return articles


def scrape_lpga_com() -> tuple[list[dict], list[dict]]:
    """
    Scrape LPGA.com for news and tournament info.

    NOTE: LPGA.com uses heavy JavaScript. Results may be limited.
    """
    articles = []
    tournaments = []

    # Try news page
    soup = fetch_page(f"{URLS['lpga_com']}/news")
    if soup:
        news_items = soup.select('article, .news-item, [class*="article"], [class*="news"]')

        for item in news_items[:10]:
            try:
                title_elem = item.select_one('h2, h3, .title, a')
                link_elem = item.select_one('a[href]')

                title = title_elem.get_text(strip=True) if title_elem else ''
                if not title:
                    continue

                href = ''
                if link_elem:
                    href = link_elem.get('href', '')
                    if not href.startswith('http'):
                        href = urljoin(URLS['lpga_com'], href)

                articles.append({
                    'title': clean_text(title),
                    'source': 'LPGA.com',
                    'url': href,
                    'published_date': '',
                    'category': 'lpga',
                    'keywords_matched': ['LPGA'],
                    'summary': '',
                })
            except Exception as e:
                logger.debug(f"Error parsing LPGA news: {e}")

    # Try tournaments page
    soup = fetch_page(f"{URLS['lpga_com']}/tournaments")
    if soup:
        tournament_items = soup.select('[class*="tournament"], [class*="event"], article')

        for item in tournament_items[:10]:
            try:
                name_elem = item.select_one('h2, h3, .title, [class*="name"]')
                date_elem = item.select_one('[class*="date"], time')
                location_elem = item.select_one('[class*="location"], [class*="venue"]')

                name = name_elem.get_text(strip=True) if name_elem else ''
                if not name:
                    continue

                tournaments.append({
                    'name': clean_text(name),
                    'tour': 'LPGA',
                    'dates': clean_text(date_elem.get_text() if date_elem else ''),
                    'location': clean_text(location_elem.get_text() if location_elem else ''),
                    'status': 'upcoming',
                    'winner': None,
                    'leaderboard_url': '',
                })
            except Exception as e:
                logger.debug(f"Error parsing LPGA tournament: {e}")

    if not articles and not tournaments:
        logger.warning("LPGA.com: No data found - site likely requires JavaScript (Selenium needed)")
    else:
        logger.info(f"LPGA.com: Found {len(articles)} articles, {len(tournaments)} tournaments")

    return articles, tournaments


def scrape_epson_tour() -> tuple[list[dict], list[dict]]:
    """
    Scrape Epson Tour (developmental tour) for news and tournaments.

    NOTE: May require JavaScript for some content.
    """
    articles = []
    tournaments = []

    # Try main page / news
    soup = fetch_page(URLS['epson_tour'])
    if soup:
        # Look for news items
        news_items = soup.select('article, .news-card, [class*="news"], [class*="article"]')

        for item in news_items[:10]:
            try:
                title_elem = item.select_one('h2, h3, .title, a')
                link_elem = item.select_one('a[href]')

                title = title_elem.get_text(strip=True) if title_elem else ''
                if not title:
                    continue

                href = ''
                if link_elem:
                    href = link_elem.get('href', '')
                    if not href.startswith('http'):
                        href = urljoin(URLS['epson_tour'], href)

                articles.append({
                    'title': clean_text(title),
                    'source': 'Epson Tour',
                    'url': href,
                    'published_date': '',
                    'category': 'epson',
                    'keywords_matched': ['Epson Tour'],
                    'summary': '',
                })
            except Exception as e:
                logger.debug(f"Error parsing Epson Tour news: {e}")

        # Look for tournament info
        tournament_items = soup.select('[class*="tournament"], [class*="schedule"], [class*="event"]')

        for item in tournament_items[:10]:
            try:
                name_elem = item.select_one('h2, h3, .title, [class*="name"]')
                name = name_elem.get_text(strip=True) if name_elem else ''
                if not name:
                    continue

                tournaments.append({
                    'name': clean_text(name),
                    'tour': 'Epson Tour',
                    'dates': '',
                    'location': '',
                    'status': 'upcoming',
                    'winner': None,
                    'leaderboard_url': '',
                })
            except Exception as e:
                logger.debug(f"Error parsing Epson tournament: {e}")

    if not articles and not tournaments:
        logger.warning("Epson Tour: No data found - site may require JavaScript")
    else:
        logger.info(f"Epson Tour: Found {len(articles)} articles, {len(tournaments)} tournaments")

    return articles, tournaments


def scrape_ncaa_golf() -> tuple[list[dict], list[dict]]:
    """
    Scrape NCAA women's golf news and tournaments.

    NOTE: NCAA.com uses JavaScript heavily. Limited results expected.
    """
    articles = []
    tournaments = []

    soup = fetch_page(URLS['ncaa'])
    if soup:
        # Look for news/articles
        news_items = soup.select('article, .content-card, [class*="story"], [class*="news"]')

        for item in news_items[:10]:
            try:
                title_elem = item.select_one('h2, h3, h4, .title, a')
                link_elem = item.select_one('a[href]')

                title = title_elem.get_text(strip=True) if title_elem else ''
                if not title:
                    continue

                href = ''
                if link_elem:
                    href = link_elem.get('href', '')
                    if not href.startswith('http'):
                        href = urljoin('https://www.ncaa.com', href)

                articles.append({
                    'title': clean_text(title),
                    'source': 'NCAA',
                    'url': href,
                    'published_date': '',
                    'category': 'college',
                    'keywords_matched': ['NCAA women golf', 'college golf'],
                    'summary': '',
                })
            except Exception as e:
                logger.debug(f"Error parsing NCAA news: {e}")

    if not articles:
        logger.warning("NCAA: No data found - site requires JavaScript (Selenium needed)")
    else:
        logger.info(f"NCAA: Found {len(articles)} articles")

    return articles, tournaments


def scrape_golf_channel() -> list[dict]:
    """
    Scrape Golf Channel LPGA section.

    NOTE: Often requires JavaScript.
    """
    articles = []

    soup = fetch_page(URLS['golf_channel'])
    if soup:
        news_items = soup.select('article, .story-card, [class*="article"], [class*="story"]')

        for item in news_items[:10]:
            try:
                title_elem = item.select_one('h2, h3, .headline, .title, a')
                link_elem = item.select_one('a[href]')

                title = title_elem.get_text(strip=True) if title_elem else ''
                if not title:
                    continue

                href = ''
                if link_elem:
                    href = link_elem.get('href', '')
                    if not href.startswith('http'):
                        href = urljoin('https://www.golfchannel.com', href)

                articles.append({
                    'title': clean_text(title),
                    'source': 'Golf Channel',
                    'url': href,
                    'published_date': '',
                    'category': categorize_article(title),
                    'keywords_matched': match_keywords(title) or ['LPGA'],
                    'summary': '',
                })
            except Exception as e:
                logger.debug(f"Error parsing Golf Channel: {e}")

    if not articles:
        logger.warning("Golf Channel: No data found - site may require JavaScript")
    else:
        logger.info(f"Golf Channel: Found {len(articles)} articles")

    return articles


def scrape_golfweek() -> list[dict]:
    """
    Scrape Golfweek LPGA section.
    """
    articles = []

    soup = fetch_page(URLS['golfweek'])
    if soup:
        news_items = soup.select('article, .gnt_m_flm_a, [class*="article"], [class*="story"]')

        for item in news_items[:10]:
            try:
                title_elem = item.select_one('h2, h3, .gnt_m_flm_hl, .title, a')
                link_elem = item.select_one('a[href]')

                title = title_elem.get_text(strip=True) if title_elem else ''
                if not title:
                    continue

                href = ''
                if link_elem:
                    href = link_elem.get('href', '')
                    if not href.startswith('http'):
                        href = urljoin('https://golfweek.usatoday.com', href)

                articles.append({
                    'title': clean_text(title),
                    'source': 'Golfweek',
                    'url': href,
                    'published_date': '',
                    'category': categorize_article(title),
                    'keywords_matched': match_keywords(title) or ['LPGA'],
                    'summary': '',
                })
            except Exception as e:
                logger.debug(f"Error parsing Golfweek: {e}")

    if not articles:
        logger.warning("Golfweek: No data found - site may require JavaScript")
    else:
        logger.info(f"Golfweek: Found {len(articles)} articles")

    return articles


# =============================================================================
# DATA PROCESSING
# =============================================================================

def extract_player_mentions(articles: list[dict]) -> list[dict]:
    """
    Extract player mentions from article titles and summaries.

    Looks for common LPGA player name patterns.
    """
    # Top LPGA players to track (expandable)
    top_players = [
        'Nelly Korda', 'Jin Young Ko', 'Lydia Ko', 'Lexi Thompson',
        'Brooke Henderson', 'Minjee Lee', 'Atthaya Thitikul', 'Celine Boutier',
        'Lilia Vu', 'Rose Zhang', 'Charley Hull', 'Hannah Green',
        'Ayaka Furue', 'Nasa Hataoka', 'Danielle Kang', 'Jessica Korda',
    ]

    player_data = defaultdict(lambda: {'mentions': 0, 'contexts': []})

    for article in articles:
        text = f"{article.get('title', '')} {article.get('summary', '')}"

        for player in top_players:
            if player.lower() in text.lower():
                player_data[player]['mentions'] += 1
                # Extract context (first 50 chars around mention)
                idx = text.lower().find(player.lower())
                context = text[max(0, idx - 20):idx + len(player) + 30].strip()
                if context and context not in player_data[player]['contexts']:
                    player_data[player]['contexts'].append(context[:80])

    # Convert to list format
    mentions = []
    for player, data in player_data.items():
        if data['mentions'] > 0:
            mentions.append({
                'player': player,
                'mentions': data['mentions'],
                'contexts': data['contexts'][:3],  # Limit to 3 contexts
            })

    # Sort by mention count
    mentions.sort(key=lambda x: x['mentions'], reverse=True)
    return mentions


def deduplicate_articles(articles: list[dict]) -> list[dict]:
    """Remove duplicate articles based on URL and title similarity."""
    seen_urls = set()
    seen_titles = set()
    unique = []

    for article in articles:
        url = article.get('url', '')
        title = article.get('title', '').lower()[:50]

        if url and url in seen_urls:
            continue
        if title and title in seen_titles:
            continue

        if url:
            seen_urls.add(url)
        if title:
            seen_titles.add(title)
        unique.append(article)

    return unique


# =============================================================================
# MAIN
# =============================================================================

def save_results(data: dict) -> Path:
    """Save scan results to JSON file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now().strftime('%Y-%m-%d')
    filename = f"lpga-{date_str}.json"
    filepath = OUTPUT_DIR / filename

    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    logger.info(f"Results saved to: {filepath}")
    return filepath


def main():
    """Main entry point for enhanced golf news monitor."""
    logger.info("=" * 60)
    logger.info("Enhanced Golf News Monitor (v2)")
    logger.info("=" * 60)

    all_articles = []
    all_tournaments = []
    sources_scraped = []

    # 1. Google News (Primary - most reliable)
    if SOURCES.get('google_news'):
        try:
            # Multiple queries for broader coverage
            for query in ['LPGA golf news', 'Epson Tour golf', 'NCAA women golf']:
                articles = scrape_google_news(query)
                all_articles.extend(articles)
            sources_scraped.append('google_news')
        except Exception as e:
            logger.error(f"Google News error: {e}")

    # 2. DuckDuckGo (Fallback)
    if SOURCES.get('duckduckgo'):
        try:
            articles = scrape_duckduckgo('LPGA women golf news 2026')
            all_articles.extend(articles)
            sources_scraped.append('duckduckgo')
        except Exception as e:
            logger.error(f"DuckDuckGo error: {e}")

    # 3. LPGA.com
    if SOURCES.get('lpga_com'):
        try:
            articles, tournaments = scrape_lpga_com()
            all_articles.extend(articles)
            all_tournaments.extend(tournaments)
            sources_scraped.append('lpga_com')
        except Exception as e:
            logger.error(f"LPGA.com error: {e}")

    # 4. Epson Tour
    if SOURCES.get('epson_tour'):
        try:
            articles, tournaments = scrape_epson_tour()
            all_articles.extend(articles)
            all_tournaments.extend(tournaments)
            sources_scraped.append('epson_tour')
        except Exception as e:
            logger.error(f"Epson Tour error: {e}")

    # 5. NCAA
    if SOURCES.get('ncaa'):
        try:
            articles, tournaments = scrape_ncaa_golf()
            all_articles.extend(articles)
            all_tournaments.extend(tournaments)
            sources_scraped.append('ncaa')
        except Exception as e:
            logger.error(f"NCAA error: {e}")

    # 6. Golf Channel
    if SOURCES.get('golf_channel'):
        try:
            articles = scrape_golf_channel()
            all_articles.extend(articles)
            sources_scraped.append('golf_channel')
        except Exception as e:
            logger.error(f"Golf Channel error: {e}")

    # 7. Golfweek
    if SOURCES.get('golfweek'):
        try:
            articles = scrape_golfweek()
            all_articles.extend(articles)
            sources_scraped.append('golfweek')
        except Exception as e:
            logger.error(f"Golfweek error: {e}")

    # Process results
    all_articles = deduplicate_articles(all_articles)
    player_mentions = extract_player_mentions(all_articles)

    # Build output
    data = {
        'scan_date': datetime.now().isoformat(),
        'sources_scraped': sources_scraped,
        'articles': all_articles,
        'tournaments': all_tournaments,
        'player_mentions': player_mentions,
        'stats': {
            'total_articles': len(all_articles),
            'total_tournaments': len(all_tournaments),
            'sources_attempted': sum(1 for v in SOURCES.values() if v),
            'sources_successful': len(sources_scraped),
        },
        'notes': [],
    }

    # Add notes for failures
    if len(all_articles) == 0:
        data['notes'].append(
            "WARNING: No articles found. Sites may require JavaScript (Selenium) or be blocking requests."
        )

    # Save results
    filepath = save_results(data)

    # Print summary
    print("\n" + "=" * 60)
    print("GOLF NEWS SCAN SUMMARY")
    print("=" * 60)
    print(f"Sources scraped: {', '.join(sources_scraped)}")
    print(f"Total articles: {len(all_articles)}")
    print(f"Total tournaments: {len(all_tournaments)}")
    print(f"Player mentions tracked: {len(player_mentions)}")

    if all_articles:
        print("\nTop 5 articles:")
        for article in all_articles[:5]:
            print(f"  [{article['category']}] {article['title'][:50]}...")
            print(f"    Source: {article['source']}")

    if player_mentions:
        print("\nTop mentioned players:")
        for pm in player_mentions[:5]:
            print(f"  {pm['player']}: {pm['mentions']} mentions")

    print(f"\nOutput: {filepath}")


if __name__ == '__main__':
    main()
