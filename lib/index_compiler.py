#!/usr/bin/env python3
"""
CRM Index Compiler (DIP-0012)

Compiles contact data across all spaces into a unified index.
Follows DIP-0002 layered context pattern for cross-space aggregation.

Index location: .datacore/state/crm/contacts-index.yaml

Usage:
    python index_compiler.py --compile
    python index_compiler.py --status
    python index_compiler.py --contact "John Smith"
"""

import re
import sys
import yaml
import math
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any

# Add parent lib to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'lib'))

from adapters import Interaction, get_adapters, aggregate_by_contact


@dataclass
class ContactScore:
    """Relationship health score for a contact."""
    score: float              # 0-1 overall score
    status: str               # active, warming, cooling, dormant
    recency: float            # Recency component (0-1)
    frequency: float          # Frequency component (0-1)
    depth: float              # Depth component (0-1)
    reciprocity: float        # Reciprocity component (0-1)
    trend: str                # improving, stable, declining
    last_interaction: str     # ISO date


@dataclass
class ContactEntry:
    """A contact in the cross-space index."""
    name: str
    contact_type: str         # person, company
    status: str               # active, dormant, draft
    space: str                # Primary space
    source_file: str          # Path to contact note
    organization: Optional[str] = None
    role: Optional[str] = None
    tags: List[str] = None
    last_interaction: Optional[str] = None
    interaction_count: int = 0
    score: Optional[ContactScore] = None
    updated: Optional[str] = None


class IndexCompiler:
    """Compiles cross-space contact index."""

    # Scoring weights (from DIP-0012)
    WEIGHT_RECENCY = 0.4
    WEIGHT_FREQUENCY = 0.3
    WEIGHT_DEPTH = 0.2
    WEIGHT_RECIPROCITY = 0.1

    # Decay constant for recency (half-life ~21 days)
    RECENCY_DECAY = 30

    # Target frequency (weekly = max score)
    TARGET_FREQUENCY = 4

    # Interaction type weights
    DEPTH_WEIGHTS = {
        'meeting': 1.0,
        'call': 0.8,
        'email': 0.5,
        'message': 0.4,
        'mention': 0.2,
    }

    # Score thresholds
    THRESHOLD_ACTIVE = 0.7
    THRESHOLD_WARMING = 0.5
    THRESHOLD_COOLING = 0.4

    def __init__(self, data_root: Path = None):
        """Initialize compiler.

        Args:
            data_root: Path to ~/Data (auto-detected if None)
        """
        self.data_root = data_root or Path.home() / 'Data'
        self.state_dir = self.data_root / '.datacore' / 'state' / 'crm'
        self.index_path = self.state_dir / 'contacts-index.yaml'

        # Discover spaces
        self.spaces = self._discover_spaces()

    def _discover_spaces(self) -> Dict[str, Path]:
        """Discover all spaces with contacts folders."""
        spaces = {}

        for item in self.data_root.iterdir():
            if item.is_dir() and re.match(r'^\d+-', item.name):
                contacts_dir = item / 'contacts'
                if contacts_dir.exists():
                    spaces[item.name] = contacts_dir

        return spaces

    def scan_contacts(self) -> List[ContactEntry]:
        """Scan all spaces for contact notes."""
        contacts = []

        for space_name, contacts_dir in self.spaces.items():
            # Scan people
            people_dir = contacts_dir / 'people'
            if people_dir.exists():
                for contact_file in people_dir.glob('*.md'):
                    entry = self._parse_contact_file(contact_file, space_name, 'person')
                    if entry:
                        contacts.append(entry)

            # Scan companies
            companies_dir = contacts_dir / 'companies'
            if companies_dir.exists():
                for contact_file in companies_dir.glob('*.md'):
                    entry = self._parse_contact_file(contact_file, space_name, 'company')
                    if entry:
                        contacts.append(entry)

        return contacts

    def _parse_contact_file(self, file_path: Path, space: str, contact_type: str) -> Optional[ContactEntry]:
        """Parse a contact file and extract metadata."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except Exception:
            return None

        # Parse YAML frontmatter
        frontmatter = {}
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                try:
                    frontmatter = yaml.safe_load(parts[1]) or {}
                except yaml.YAMLError:
                    pass

        # Extract name from frontmatter or filename
        name = frontmatter.get('name', file_path.stem)

        return ContactEntry(
            name=name,
            contact_type=frontmatter.get('contact_type', contact_type),
            status=frontmatter.get('status', 'draft'),
            space=space,
            source_file=str(file_path),
            organization=frontmatter.get('organization'),
            role=frontmatter.get('role'),
            tags=frontmatter.get('tags', []),
            last_interaction=frontmatter.get('last_interaction'),
            updated=frontmatter.get('updated'),
        )

    def calculate_score(self, contact: ContactEntry, interactions: List[Interaction]) -> ContactScore:
        """Calculate relationship health score for a contact."""
        now = datetime.now()

        # Recency score
        if contact.last_interaction:
            try:
                last_date = datetime.strptime(contact.last_interaction, '%Y-%m-%d')
                days_since = (now - last_date).days
                recency = math.exp(-days_since / self.RECENCY_DECAY)
            except ValueError:
                recency = 0.0
        elif interactions:
            # Use most recent interaction
            latest = max(interactions, key=lambda x: x.date)
            try:
                last_date = datetime.strptime(latest.date, '%Y-%m-%d')
                days_since = (now - last_date).days
                recency = math.exp(-days_since / self.RECENCY_DECAY)
            except ValueError:
                recency = 0.0
        else:
            recency = 0.0

        # Frequency score (interactions per month)
        if interactions:
            # Count interactions in last 30 days
            cutoff = now - timedelta(days=30)
            recent_count = sum(
                1 for i in interactions
                if datetime.strptime(i.date, '%Y-%m-%d') >= cutoff
            )
            frequency = min(recent_count / self.TARGET_FREQUENCY, 1.0)
        else:
            frequency = 0.0

        # Depth score (weighted by interaction type)
        if interactions:
            type_weights = [
                self.DEPTH_WEIGHTS.get(i.interaction_type, 0.2)
                for i in interactions
            ]
            depth = sum(type_weights) / len(type_weights) if type_weights else 0.0
        else:
            depth = 0.0

        # Reciprocity (placeholder - would need bidirectional tracking)
        reciprocity = 0.5  # Neutral assumption

        # Calculate final score
        score = (
            recency * self.WEIGHT_RECENCY +
            frequency * self.WEIGHT_FREQUENCY +
            depth * self.WEIGHT_DEPTH +
            reciprocity * self.WEIGHT_RECIPROCITY
        )

        # Determine status
        if score > self.THRESHOLD_ACTIVE:
            status = 'active'
        elif score > self.THRESHOLD_WARMING:
            status = 'warming'
        elif score > self.THRESHOLD_COOLING:
            status = 'cooling'
        else:
            status = 'dormant'

        # Determine trend (placeholder - would compare with previous score)
        trend = 'stable'

        # Get last interaction date
        if interactions:
            last_interaction = max(i.date for i in interactions)
        else:
            last_interaction = contact.last_interaction or ''

        return ContactScore(
            score=round(score, 2),
            status=status,
            recency=round(recency, 2),
            frequency=round(frequency, 2),
            depth=round(depth, 2),
            reciprocity=round(reciprocity, 2),
            trend=trend,
            last_interaction=last_interaction,
        )

    def compile_index(self, scan_days: int = 90) -> Dict[str, Any]:
        """Compile the full cross-space index.

        Args:
            scan_days: Days of interactions to scan for scoring

        Returns:
            Index dict ready for YAML serialization
        """
        # Scan all contacts
        contacts = self.scan_contacts()

        # Scan interactions
        since = datetime.now() - timedelta(days=scan_days)
        all_interactions = []
        for adapter in get_adapters(self.data_root):
            all_interactions.extend(adapter.extract_interactions(since))

        # Group interactions by contact
        interactions_by_contact = aggregate_by_contact(all_interactions)

        # Calculate scores and update contacts
        for contact in contacts:
            contact_interactions = interactions_by_contact.get(contact.name, [])
            contact.interaction_count = len(contact_interactions)
            contact.score = self.calculate_score(contact, contact_interactions)

        # Build index structure
        index = {
            'version': '1.0',
            'compiled_at': datetime.now().isoformat(),
            'scan_days': scan_days,
            'summary': {
                'total': len(contacts),
                'people': sum(1 for c in contacts if c.contact_type == 'person'),
                'companies': sum(1 for c in contacts if c.contact_type == 'company'),
                'by_status': {},
                'by_space': {},
            },
            'contacts': [],
        }

        # Calculate summary stats
        for contact in contacts:
            status = contact.score.status if contact.score else 'unknown'
            index['summary']['by_status'][status] = index['summary']['by_status'].get(status, 0) + 1
            index['summary']['by_space'][contact.space] = index['summary']['by_space'].get(contact.space, 0) + 1

        # Serialize contacts
        for contact in sorted(contacts, key=lambda c: c.name):
            entry = {
                'name': contact.name,
                'type': contact.contact_type,
                'status': contact.status,
                'space': contact.space,
                'source': contact.source_file,
                'interaction_count': contact.interaction_count,
            }

            if contact.organization:
                entry['organization'] = contact.organization
            if contact.role:
                entry['role'] = contact.role
            if contact.tags:
                entry['tags'] = contact.tags

            if contact.score:
                entry['score'] = {
                    'value': contact.score.score,
                    'status': contact.score.status,
                    'trend': contact.score.trend,
                    'last_interaction': contact.score.last_interaction,
                    'components': {
                        'recency': contact.score.recency,
                        'frequency': contact.score.frequency,
                        'depth': contact.score.depth,
                        'reciprocity': contact.score.reciprocity,
                    }
                }

            index['contacts'].append(entry)

        return index

    def save_index(self, index: Dict[str, Any]) -> Path:
        """Save index to state directory.

        Args:
            index: Compiled index dict

        Returns:
            Path to saved index file
        """
        # Ensure state directory exists
        self.state_dir.mkdir(parents=True, exist_ok=True)

        # Write index
        with open(self.index_path, 'w', encoding='utf-8') as f:
            yaml.dump(index, f, default_flow_style=False, allow_unicode=True)

        return self.index_path

    def load_index(self) -> Optional[Dict[str, Any]]:
        """Load existing index from state directory."""
        if not self.index_path.exists():
            return None

        try:
            with open(self.index_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        except Exception:
            return None

    def get_contact(self, name: str) -> Optional[Dict[str, Any]]:
        """Get a specific contact from the index.

        Args:
            name: Contact name (case-insensitive search)

        Returns:
            Contact entry or None
        """
        index = self.load_index()
        if not index:
            return None

        name_lower = name.lower()
        for contact in index.get('contacts', []):
            if contact['name'].lower() == name_lower:
                return contact

        # Partial match fallback
        for contact in index.get('contacts', []):
            if name_lower in contact['name'].lower():
                return contact

        return None

    def get_attention_needed(self, threshold_days: int = 30) -> List[Dict[str, Any]]:
        """Get contacts that need attention.

        Args:
            threshold_days: Days without interaction to flag

        Returns:
            List of contacts needing attention
        """
        index = self.load_index()
        if not index:
            return []

        attention = []
        cutoff = datetime.now() - timedelta(days=threshold_days)

        for contact in index.get('contacts', []):
            score = contact.get('score', {})

            # Flag dormant contacts
            if score.get('status') == 'dormant':
                last = score.get('last_interaction', '')
                if last:
                    try:
                        last_date = datetime.strptime(last, '%Y-%m-%d')
                        days_since = (datetime.now() - last_date).days
                    except ValueError:
                        days_since = 999
                else:
                    days_since = 999

                attention.append({
                    **contact,
                    'days_since': days_since,
                    'reason': f'Dormant {days_since} days',
                })

        # Sort by days since interaction
        attention.sort(key=lambda x: x.get('days_since', 999), reverse=True)

        return attention


def print_status(index: Dict[str, Any]):
    """Print index status summary."""
    summary = index.get('summary', {})

    print(f"\n{'='*50}")
    print("CRM INDEX STATUS")
    print(f"{'='*50}")
    print(f"Compiled: {index.get('compiled_at', 'Unknown')}")
    print(f"Scan range: {index.get('scan_days', 0)} days")
    print()

    print(f"Total contacts: {summary.get('total', 0)}")
    print(f"  People: {summary.get('people', 0)}")
    print(f"  Companies: {summary.get('companies', 0)}")
    print()

    print("By status:")
    for status, count in sorted(summary.get('by_status', {}).items()):
        print(f"  {status}: {count}")
    print()

    print("By space:")
    for space, count in sorted(summary.get('by_space', {}).items()):
        print(f"  {space}: {count}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="CRM Index Compiler")
    parser.add_argument('--compile', action='store_true', help='Compile index')
    parser.add_argument('--status', action='store_true', help='Show index status')
    parser.add_argument('--contact', help='Look up specific contact')
    parser.add_argument('--attention', action='store_true', help='Show contacts needing attention')
    parser.add_argument('--days', type=int, default=90, help='Days to scan for scoring')

    args = parser.parse_args()

    compiler = IndexCompiler()

    if args.compile:
        print("Compiling CRM index...")
        index = compiler.compile_index(scan_days=args.days)
        path = compiler.save_index(index)
        print(f"Index saved to: {path}")
        print_status(index)

    elif args.status:
        index = compiler.load_index()
        if index:
            print_status(index)
        else:
            print("No index found. Run with --compile first.")

    elif args.contact:
        contact = compiler.get_contact(args.contact)
        if contact:
            print(f"\n{contact['name']}")
            print(f"  Type: {contact.get('type', 'unknown')}")
            print(f"  Space: {contact.get('space', 'unknown')}")
            if contact.get('organization'):
                print(f"  Organization: {contact['organization']}")
            if contact.get('role'):
                print(f"  Role: {contact['role']}")

            score = contact.get('score', {})
            if score:
                print(f"\n  Score: {score.get('value', 0)} ({score.get('status', 'unknown')})")
                print(f"  Last interaction: {score.get('last_interaction', 'Never')}")
                print(f"  Trend: {score.get('trend', 'unknown')}")
        else:
            print(f"Contact not found: {args.contact}")

    elif args.attention:
        attention = compiler.get_attention_needed()
        if attention:
            print(f"\n=== Contacts Needing Attention ({len(attention)}) ===")
            for contact in attention[:10]:  # Show top 10
                print(f"\n  {contact['name']} ({contact.get('type', '')})")
                print(f"    {contact.get('reason', '')}")
                print(f"    Space: {contact.get('space', '')}")
        else:
            print("No contacts need attention.")

    else:
        parser.print_help()
