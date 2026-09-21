#!/usr/bin/env python3
"""
CRM Adapters (DIP-0012)

Base adapter interface and built-in adapters for extracting contact
interactions from various channels.

Built-in adapters:
- JournalAdapter: Extracts [[Contact]] wiki-links from daily journals
- CalendarAdapter: Extracts meeting attendees from calendar.org

External modules can implement CRMAdapter to feed interactions into CRM.

Usage:
    python adapters.py --scan --days 7
    python adapters.py --scan --since 2025-12-01
"""

import re
import sys
from abc import ABC, abstractmethod
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any

# Add parent lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'lib'))


@dataclass
class Interaction:
    """A contact interaction extracted from a channel."""
    contact: str              # Contact name (as appears in wiki-link)
    date: str                 # ISO date YYYY-MM-DD
    channel: str              # Source channel (journal, calendar, mail, etc.)
    interaction_type: str     # meeting, email, mention, call, message
    summary: str              # Brief description of interaction
    source: str               # File path and line number
    context: str = ""         # Surrounding text for context
    metadata: Dict[str, Any] = field(default_factory=dict)


class CRMAdapter(ABC):
    """Base interface for CRM interaction adapters.

    Other modules implement this interface to feed interactions
    into the CRM hub.
    """

    @property
    @abstractmethod
    def adapter_type(self) -> str:
        """Unique identifier (e.g., 'journal', 'mail', 'telegram')."""
        pass

    @abstractmethod
    def extract_interactions(self, since: datetime, until: datetime = None) -> List[Interaction]:
        """Extract contact interactions from this channel.

        Args:
            since: Start of date range
            until: End of date range (default: now)

        Returns:
            List of Interaction objects
        """
        pass

    def resolve_contact(self, identifier: str) -> Optional[str]:
        """Resolve channel-specific ID to contact name.

        Override in subclasses for channels with non-wiki-link identifiers
        (e.g., email addresses, telegram handles).

        Args:
            identifier: Channel-specific contact identifier

        Returns:
            Contact name or None if not resolved
        """
        return identifier


class JournalAdapter(CRMAdapter):
    """Extracts [[Contact Name]] wiki-links from daily journals."""

    # Wiki-link pattern: [[Name]] or [[Name|alias]]
    WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')

    # Context extraction: sentence or paragraph containing the link
    SENTENCE_PATTERN = re.compile(r'[^.!?\n]*\[\[[^\]]+\]\][^.!?\n]*[.!?\n]?')

    def __init__(self, data_root: Path, spaces: Dict[str, Dict]):
        """Initialize with data root and space configuration.

        Args:
            data_root: Path to ~/Data
            spaces: Space configuration dict from zettel_db.SPACES
        """
        self.data_root = data_root
        self.spaces = spaces

    @property
    def adapter_type(self) -> str:
        return "journal"

    def extract_interactions(self, since: datetime, until: datetime = None) -> List[Interaction]:
        """Scan journals for wiki-links in date range."""
        if until is None:
            until = datetime.now()

        interactions = []

        for space_name, space_config in self.spaces.items():
            journal_path = space_config.get('journal_path')
            if not journal_path or not journal_path.exists():
                continue

            # Scan journal files in date range
            for journal_file in sorted(journal_path.glob('*.md')):
                # Parse date from filename (YYYY-MM-DD.md)
                date_match = re.match(r'^(\d{4}-\d{2}-\d{2})\.md$', journal_file.name)
                if not date_match:
                    continue

                file_date = datetime.strptime(date_match.group(1), '%Y-%m-%d')
                if file_date < since or file_date > until:
                    continue

                # Extract interactions from this file
                file_interactions = self._extract_from_file(journal_file, date_match.group(1))
                interactions.extend(file_interactions)

        return interactions

    def _extract_from_file(self, file_path: Path, date_str: str) -> List[Interaction]:
        """Extract wiki-link interactions from a single journal file."""
        interactions = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return interactions

        lines = content.split('\n')

        for line_num, line in enumerate(lines, 1):
            # Find all wiki-links in this line
            for match in self.WIKI_LINK_PATTERN.finditer(line):
                contact_name = match.group(1).strip()

                # Skip non-contact wiki-links (files, pages, etc.)
                if self._is_likely_contact(contact_name):
                    # Determine interaction type from context
                    interaction_type = self._detect_interaction_type(line)

                    # Extract surrounding context
                    context = self._extract_context(content, match.start(), line_num)

                    interactions.append(Interaction(
                        contact=contact_name,
                        date=date_str,
                        channel='journal',
                        interaction_type=interaction_type,
                        summary=self._generate_summary(line, contact_name),
                        source=f"{file_path}:{line_num}",
                        context=context,
                    ))

        return interactions

    def _is_likely_contact(self, name: str) -> bool:
        """Heuristic to determine if wiki-link is likely a contact name."""
        # Skip common non-contact patterns
        skip_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',  # Dates
            r'\.md$',                 # File references
            r'^#',                    # Tags
            r'^[a-z_]+$',             # Likely internal links (all lowercase)
        ]

        for pattern in skip_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return False

        # Contacts typically have:
        # - Capital letters (names)
        # - Multiple words (first + last name)
        # - Or company names (PascalCase or with Inc/Corp/etc)
        if re.search(r'[A-Z]', name):
            return True

        return False

    def _detect_interaction_type(self, line: str) -> str:
        """Detect interaction type from line context."""
        line_lower = line.lower()

        if any(w in line_lower for w in ['met', 'meeting', 'met with', 'call with', 'spoke']):
            return 'meeting'
        elif any(w in line_lower for w in ['email', 'sent', 'received', 'replied']):
            return 'email'
        elif any(w in line_lower for w in ['message', 'dm', 'chat']):
            return 'message'
        elif any(w in line_lower for w in ['called', 'phone', 'rang']):
            return 'call'
        else:
            return 'mention'

    def _extract_context(self, content: str, match_pos: int, line_num: int) -> str:
        """Extract surrounding context for the interaction."""
        lines = content.split('\n')

        # Get 1 line before and after
        start = max(0, line_num - 2)
        end = min(len(lines), line_num + 1)

        context_lines = lines[start:end]
        return '\n'.join(context_lines).strip()[:500]  # Limit length

    def _generate_summary(self, line: str, contact_name: str) -> str:
        """Generate a brief summary from the line."""
        # Remove wiki-link markup and clean up
        summary = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', line)
        summary = summary.strip().strip('-*').strip()

        # Truncate if too long
        if len(summary) > 100:
            summary = summary[:97] + '...'

        return summary


class CalendarAdapter(CRMAdapter):
    """Extracts meeting attendees from calendar.org."""

    # Pattern for org-mode timestamps
    TIMESTAMP_PATTERN = re.compile(r'<(\d{4}-\d{2}-\d{2})(?: \w{3})?(?: (\d{2}:\d{2})(?:-(\d{2}:\d{2}))?)?\s*(?:\+\d+[dwmy])?>')

    # Wiki-link pattern for attendees
    WIKI_LINK_PATTERN = re.compile(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]')

    def __init__(self, data_root: Path, spaces: Dict[str, Dict]):
        self.data_root = data_root
        self.spaces = spaces

    @property
    def adapter_type(self) -> str:
        return "calendar"

    def extract_interactions(self, since: datetime, until: datetime = None) -> List[Interaction]:
        """Scan calendar.org for meetings in date range."""
        if until is None:
            until = datetime.now()

        interactions = []

        for space_name, space_config in self.spaces.items():
            org_paths = space_config.get('org_paths', [])

            for org_path in org_paths:
                calendar_file = org_path / 'calendar.org'
                if calendar_file.exists():
                    file_interactions = self._extract_from_calendar(
                        calendar_file, since, until
                    )
                    interactions.extend(file_interactions)

        return interactions

    def _extract_from_calendar(self, file_path: Path, since: datetime, until: datetime) -> List[Interaction]:
        """Extract interactions from calendar.org."""
        interactions = []

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return interactions

        lines = content.split('\n')
        current_heading = None
        current_line = 0

        for line_num, line in enumerate(lines, 1):
            # Track headings
            heading_match = re.match(r'^(\*+)\s+(.+)$', line)
            if heading_match:
                current_heading = heading_match.group(2).strip()
                current_line = line_num
                continue

            # Look for timestamps
            timestamp_match = self.TIMESTAMP_PATTERN.search(line)
            if timestamp_match and current_heading:
                event_date = timestamp_match.group(1)
                event_datetime = datetime.strptime(event_date, '%Y-%m-%d')

                if event_datetime < since or event_datetime > until:
                    continue

                # Extract attendees from heading
                attendees = self.WIKI_LINK_PATTERN.findall(current_heading)

                for attendee in attendees:
                    # Skip non-contact links
                    if self._is_likely_contact(attendee):
                        interactions.append(Interaction(
                            contact=attendee,
                            date=event_date,
                            channel='calendar',
                            interaction_type='meeting',
                            summary=self._clean_heading(current_heading),
                            source=f"{file_path}:{current_line}",
                            metadata={
                                'start_time': timestamp_match.group(2),
                                'end_time': timestamp_match.group(3),
                            }
                        ))

        return interactions

    def _is_likely_contact(self, name: str) -> bool:
        """Same heuristic as JournalAdapter."""
        skip_patterns = [
            r'^\d{4}-\d{2}-\d{2}$',
            r'\.md$',
            r'^#',
            r'^[a-z_]+$',
        ]

        for pattern in skip_patterns:
            if re.match(pattern, name, re.IGNORECASE):
                return False

        return bool(re.search(r'[A-Z]', name))

    def _clean_heading(self, heading: str) -> str:
        """Clean heading for summary."""
        # Remove TODO states
        heading = re.sub(r'^(TODO|DONE|NEXT|WAITING)\s+', '', heading)
        # Remove wiki-link markup
        heading = re.sub(r'\[\[([^\]|]+)(?:\|[^\]]+)?\]\]', r'\1', heading)
        # Remove tags
        heading = re.sub(r'\s*:[a-zA-Z0-9_:]+:\s*$', '', heading)
        return heading.strip()


def get_adapters(data_root: Path = None, spaces: Dict = None) -> List[CRMAdapter]:
    """Get all built-in CRM adapters.

    Args:
        data_root: Path to ~/Data (auto-detected if None)
        spaces: Space configuration (loaded from zettel_db if None)

    Returns:
        List of initialized adapters
    """
    if data_root is None:
        data_root = Path.home() / 'Data'

    if spaces is None:
        try:
            from zettel_db import SPACES
            spaces = SPACES
        except ImportError:
            # Fallback minimal config
            spaces = {
                'personal': {
                    'path': data_root / '0-personal',
                    'journal_path': data_root / '0-personal' / 'notes' / 'journals',
                    'org_paths': [data_root / '0-personal' / 'org'],
                }
            }

    return [
        JournalAdapter(data_root, spaces),
        CalendarAdapter(data_root, spaces),
    ]


def scan_all_adapters(days: int = 7, since: str = None) -> Dict[str, List[Interaction]]:
    """Run all adapters and aggregate interactions.

    Args:
        days: Number of days to scan (default 7)
        since: Override with specific date (YYYY-MM-DD)

    Returns:
        Dict mapping adapter type to list of interactions
    """
    if since:
        since_dt = datetime.strptime(since, '%Y-%m-%d')
    else:
        since_dt = datetime.now() - timedelta(days=days)

    until_dt = datetime.now()

    results = {}

    for adapter in get_adapters():
        interactions = adapter.extract_interactions(since_dt, until_dt)
        results[adapter.adapter_type] = interactions

    return results


def aggregate_by_contact(interactions: List[Interaction]) -> Dict[str, List[Interaction]]:
    """Group interactions by contact name.

    Args:
        interactions: Flat list of interactions

    Returns:
        Dict mapping contact name to their interactions
    """
    by_contact = {}

    for interaction in interactions:
        if interaction.contact not in by_contact:
            by_contact[interaction.contact] = []
        by_contact[interaction.contact].append(interaction)

    # Sort each contact's interactions by date
    for contact in by_contact:
        by_contact[contact].sort(key=lambda x: x.date, reverse=True)

    return by_contact


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CRM Adapters")
    parser.add_argument('--scan', action='store_true', help='Scan for interactions')
    parser.add_argument('--days', type=int, default=7, help='Days to scan')
    parser.add_argument('--since', help='Scan since date (YYYY-MM-DD)')
    parser.add_argument('--by-contact', action='store_true', help='Group by contact')

    args = parser.parse_args()

    if args.scan:
        print(f"\nScanning for interactions...")
        results = scan_all_adapters(days=args.days, since=args.since)

        total = sum(len(v) for v in results.values())
        print(f"Found {total} interactions\n")

        if args.by_contact:
            all_interactions = []
            for interactions in results.values():
                all_interactions.extend(interactions)

            by_contact = aggregate_by_contact(all_interactions)

            for contact, interactions in sorted(by_contact.items()):
                print(f"\n{contact} ({len(interactions)} interactions)")
                for i in interactions[:3]:  # Show max 3
                    print(f"  {i.date} | {i.channel} | {i.interaction_type} | {i.summary[:50]}")
        else:
            for adapter_type, interactions in results.items():
                print(f"\n=== {adapter_type.upper()} ({len(interactions)}) ===")
                for i in interactions[:5]:  # Show max 5
                    print(f"  {i.date} | {i.contact} | {i.interaction_type}")
                    print(f"    {i.summary[:60]}")
    else:
        parser.print_help()
