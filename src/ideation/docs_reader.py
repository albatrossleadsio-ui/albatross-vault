#!/usr/bin/env python3
"""
Google Docs Reader for Albatross Ideation Engine
Part of Albatross Phase 4 - Ideation

Read and write Google Docs for ideation workflow.
MVP: Uses local JSON file fallback if Google API not configured.
"""

import os
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass, asdict

# For Google Docs API (optional)
try:
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google_auth_oauthlib.flow import InstalledAppFlow
    HAS_GOOGLE = True
except ImportError:
    HAS_GOOGLE = False


@dataclass
class BookmarkEntry:
    """Single bookmark entry from Section 1."""
    id: str
    timestamp: str
    source: str  # twitter, article, manual
    content: str
    url: Optional[str]
    user_notes: str
    status: str  # pending, analyzing, analyzed, approved, rejected


@dataclass
class AnalysisEntry:
    """Analysis for a bookmark (Section 2)."""
    bookmark_id: str
    domain: str  # web_scraping, automation, etc.
    market_research: str
    opportunity_score: int  # 1-10
    proposal: str
    estimated_cost: float
    estimated_iterations: int


@dataclass
class DecisionEntry:
    """User decision (Section 3)."""
    bookmark_id: str
    decision: str  # APPROVED, REJECTED, RESEARCH_MORE
    feedback: str
    decided_at: str


class GoogleDocsReader:
    """
    Interface to Google Docs for ideation workflow.

    MVP: Can use simple text file fallback if Google API not configured
    """

    # If Google API not available, use local file
    FALLBACK_FILE = Path.home() / "albatross" / "data" / "ideation_queue.json"

    # Google Docs API scopes
    SCOPES = ['https://www.googleapis.com/auth/documents.readonly']

    def __init__(self, doc_id: Optional[str] = None, use_fallback: bool = True):
        """
        Initialize Google Docs reader.

        Args:
            doc_id: Google Doc ID (from URL)
            use_fallback: Use local file if Google API not available
        """
        self.doc_id = doc_id or os.environ.get('GOOGLE_DOC_ID', '')
        self.use_fallback = use_fallback
        self.service = None

        # Ensure data directory exists
        self.FALLBACK_FILE.parent.mkdir(parents=True, exist_ok=True)

        if HAS_GOOGLE and self.doc_id:
            self._init_google_api()

    def _init_google_api(self):
        """Initialize Google Docs API (MVP: can skip if complex)."""
        # MVP: Just set up basic auth structure
        # Full implementation requires OAuth flow
        pass

    def _use_fallback(self) -> bool:
        """Check if we should use fallback mode."""
        return not HAS_GOOGLE or not self.service or not self.doc_id

    def _ensure_file_exists(self):
        """Ensure fallback file exists with proper structure."""
        if not self.FALLBACK_FILE.exists():
            with open(self.FALLBACK_FILE, 'w') as f:
                json.dump({
                    'section_1': [],
                    'section_2': [],
                    'section_3': []
                }, f, indent=2)

    def read_section_1(self) -> List[BookmarkEntry]:
        """
        Read raw bookmarks from Section 1.

        Returns:
            List of BookmarkEntry objects

        MVP Implementation (Fallback):
        - Read from local JSON file
        - Return pending bookmarks
        """
        if self._use_fallback():
            return self._read_fallback_section_1()

        # Full Google Docs API implementation would go here
        # For MVP, always use fallback
        return self._read_fallback_section_1()

    def _read_fallback_section_1(self) -> List[BookmarkEntry]:
        """Read from local JSON file."""
        self._ensure_file_exists()

        with open(self.FALLBACK_FILE, 'r') as f:
            data = json.load(f)

        bookmarks = []
        for item in data.get('section_1', []):
            bookmarks.append(BookmarkEntry(
                id=item.get('id', ''),
                timestamp=item.get('timestamp', ''),
                source=item.get('source', 'manual'),
                content=item.get('content', ''),
                url=item.get('url'),
                user_notes=item.get('user_notes', ''),
                status=item.get('status', 'pending')
            ))

        # Return only pending bookmarks
        return [b for b in bookmarks if b.status == 'pending']

    def read_all_bookmarks(self) -> List[BookmarkEntry]:
        """Read all bookmarks regardless of status."""
        self._ensure_file_exists()

        with open(self.FALLBACK_FILE, 'r') as f:
            data = json.load(f)

        bookmarks = []
        for item in data.get('section_1', []):
            bookmarks.append(BookmarkEntry(
                id=item.get('id', ''),
                timestamp=item.get('timestamp', ''),
                source=item.get('source', 'manual'),
                content=item.get('content', ''),
                url=item.get('url'),
                user_notes=item.get('user_notes', ''),
                status=item.get('status', 'pending')
            ))

        return bookmarks

    def write_section_2(self, analysis: AnalysisEntry):
        """
        Write analysis to Section 2.

        MVP: Append to local JSON
        """
        if self._use_fallback():
            self._write_fallback_section_2(analysis)

    def _write_fallback_section_2(self, analysis: AnalysisEntry):
        """Write analysis to local file."""
        self._ensure_file_exists()

        with open(self.FALLBACK_FILE, 'r') as f:
            data = json.load(f)

        # Add or update analysis
        section_2 = data.get('section_2', [])
        section_2 = [a for a in section_2 if a.get('bookmark_id') != analysis.bookmark_id]
        section_2.append({
            'bookmark_id': analysis.bookmark_id,
            'domain': analysis.domain,
            'market_research': analysis.market_research,
            'opportunity_score': analysis.opportunity_score,
            'proposal': analysis.proposal,
            'estimated_cost': analysis.estimated_cost,
            'estimated_iterations': analysis.estimated_iterations
        })

        data['section_2'] = section_2

        with open(self.FALLBACK_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def read_section_3(self) -> List[DecisionEntry]:
        """
        Read user decisions from Section 3.

        Returns APPROVED items that need to trigger Ralph-Lite.
        """
        if self._use_fallback():
            return self._read_fallback_section_3()

        return []

    def _read_fallback_section_3(self) -> List[DecisionEntry]:
        """Read decisions from local file."""
        self._ensure_file_exists()

        with open(self.FALLBACK_FILE, 'r') as f:
            data = json.load(f)

        decisions = []
        for item in data.get('section_3', []):
            decisions.append(DecisionEntry(
                bookmark_id=item.get('bookmark_id', ''),
                decision=item.get('decision', ''),
                feedback=item.get('feedback', ''),
                decided_at=item.get('decided_at', '')
            ))

        # Return APPROVED decisions that haven't been processed
        return [d for d in decisions if d.decision == 'APPROVED']

    def add_decision(self, bookmark_id: str, decision: str, feedback: str = ""):
        """Add a decision to Section 3."""
        self._ensure_file_exists()

        with open(self.FALLBACK_FILE, 'r') as f:
            data = json.load(f)

        section_3 = data.get('section_3', [])
        section_3.append({
            'bookmark_id': bookmark_id,
            'decision': decision,
            'feedback': feedback,
            'decided_at': datetime.now().isoformat()
        })

        data['section_3'] = section_3

        with open(self.FALLBACK_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def update_bookmark_status(self, bookmark_id: str, status: str):
        """Update bookmark status (e.g., pending -> analyzed)."""
        self._ensure_file_exists()

        with open(self.FALLBACK_FILE, 'r') as f:
            data = json.load(f)

        for item in data.get('section_1', []):
            if item['id'] == bookmark_id:
                item['status'] = status
                break

        with open(self.FALLBACK_FILE, 'w') as f:
            json.dump(data, f, indent=2)

    def add_bookmark(self, content: str, source: str = "manual",
                    url: Optional[str] = None, notes: str = "") -> str:
        """
        Add new bookmark to Section 1.

        Can be called from Telegram bot when user sends /bookmark.
        """
        bookmark = BookmarkEntry(
            id=f"bm_{int(time.time())}",
            timestamp=datetime.now().isoformat(),
            source=source,
            content=content,
            url=url,
            user_notes=notes,
            status='pending'
        )

        self._ensure_file_exists()

        with open(self.FALLBACK_FILE, 'r') as f:
            data = json.load(f)

        data['section_1'].append({
            'id': bookmark.id,
            'timestamp': bookmark.timestamp,
            'source': bookmark.source,
            'content': bookmark.content,
            'url': bookmark.url,
            'user_notes': bookmark.user_notes,
            'status': bookmark.status
        })

        with open(self.FALLBACK_FILE, 'w') as f:
            json.dump(data, f, indent=2)

        return bookmark.id

    def get_bookmark_by_id(self, bookmark_id: str) -> Optional[BookmarkEntry]:
        """Get a specific bookmark by ID."""
        all_bookmarks = self.read_all_bookmarks()
        for bookmark in all_bookmarks:
            if bookmark.id == bookmark_id:
                return bookmark
        return None


# Convenience functions
def get_docs_reader() -> GoogleDocsReader:
    """Factory function."""
    return GoogleDocsReader()


def add_bookmark_manual(content: str, notes: str = "") -> str:
    """
    Quick function to add bookmark manually.

    Usage:
        from src.ideation.docs_reader import add_bookmark_manual
        bookmark_id = add_bookmark_manual("Tweet text here", "Research this")
    """
    reader = get_docs_reader()
    return reader.add_bookmark(content, "manual", notes=notes)


if __name__ == "__main__":
    # Test
    reader = GoogleDocsReader()

    # Add a test bookmark
    bid = reader.add_bookmark(
        "Made $50K scraping county assessor data for real estate investors",
        source="twitter",
        notes="Research this opportunity"
    )
    print(f"Added bookmark: {bid}")

    # Read pending
    pending = reader.read_section_1()
    print(f"Pending bookmarks: {len(pending)}")
