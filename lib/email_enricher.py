#!/usr/bin/env python3
"""
Email Enricher for CRM module.

Extracts interaction history from Gmail for CRM contacts.
Calculates first/last contact dates, frequency, topics, and threads.

Usage:
    python email_enricher.py enrich --email john@example.com
    python email_enricher.py enrich --all-drafts --space 0-personal
"""

import re
import sys
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from collections import Counter, defaultdict
from typing import List, Dict, Optional, Any, Tuple
import yaml

# Add mail module to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / 'mail' / 'adapters'))

# English stopwords for topic extraction
STOPWORDS = {
    'a', 'an', 'the', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of',
    'with', 'by', 'from', 'as', 'is', 'was', 'are', 'were', 'be', 'been',
    'being', 'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would',
    'could', 'should', 'may', 'might', 'must', 'shall', 'can', 'need',
    'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it', 'we',
    'they', 'me', 'him', 'her', 'us', 'them', 'my', 'your', 'his', 'its',
    'our', 'their', 'what', 'which', 'who', 'whom', 'when', 'where', 'why',
    'how', 'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other',
    'some', 'such', 'no', 'not', 'only', 'same', 'so', 'than', 'too', 'very',
    'just', 'about', 'into', 'over', 'after', 'before', 'between', 'under',
    'again', 'then', 'once', 'here', 'there', 'any', 'if', 'because', 'until',
    'while', 'during', 'through', 'above', 'below', 'up', 'down', 'out',
    're', 'fwd', 'fw', 'subject', 'please', 'thanks', 'thank', 'hi', 'hello',
    'dear', 'best', 'regards', 'sincerely', 'cheers'
}


@dataclass
class EmailThread:
    """Represents an email conversation thread."""
    thread_id: str
    subject: str
    message_count: int
    first_date: datetime
    last_date: datetime
    participants: List[str] = field(default_factory=list)
    snippet: str = ""


@dataclass
class InteractionHistory:
    """Email interaction history for a contact."""
    contact_email: str
    contact_name: str = ""

    # Dates
    first_contact: Optional[datetime] = None
    last_contact: Optional[datetime] = None

    # Counts
    total_messages: int = 0
    sent_count: int = 0           # Emails I sent to them
    received_count: int = 0       # Emails I received from them

    # Frequency
    frequency_per_month: float = 0.0
    active_months: int = 0

    # Topics
    topics: List[str] = field(default_factory=list)
    subject_samples: List[str] = field(default_factory=list)

    # Threads
    key_threads: List[EmailThread] = field(default_factory=list)
    thread_count: int = 0

    # Relationship status based on recency
    relationship_status: str = ""  # active | warming | cooling | dormant

    # Monthly breakdown
    monthly_counts: Dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        """Convert to dictionary for YAML serialization."""
        return {
            'first_contact': self.first_contact.strftime('%Y-%m-%d') if self.first_contact else None,
            'last_contact': self.last_contact.strftime('%Y-%m-%d') if self.last_contact else None,
            'total_messages': self.total_messages,
            'sent_count': self.sent_count,
            'received_count': self.received_count,
            'frequency': f"{self.frequency_per_month:.1f}/month",
            'topics': self.topics[:5],
            'relationship_status': self.relationship_status,
        }


class EmailEnricher:
    """Enriches CRM contacts with email interaction history."""

    def __init__(self, gmail_address: str, data_root: Path = None):
        """
        Initialize enricher.

        Args:
            gmail_address: Gmail account to query
            data_root: Path to ~/Data (auto-detected if None)
        """
        self.gmail_address = gmail_address
        self.data_root = data_root or Path.home() / 'Data'
        self._gmail_adapter = None

    @property
    def gmail_adapter(self):
        """Lazy-load Gmail adapter."""
        if self._gmail_adapter is None:
            try:
                from gmail import GmailAdapter
                self._gmail_adapter = GmailAdapter({'address': self.gmail_address})

                if not self._gmail_adapter.is_configured():
                    print(f"Gmail not configured for {self.gmail_address}")
                    print(f"Run: python gmail.py setup --account {self.gmail_address}")
                    return None

            except ImportError as e:
                print(f"Could not import Gmail adapter: {e}")
                return None

        return self._gmail_adapter

    def enrich_contact(
        self,
        contact_email: str,
        max_messages: int = 500,
        lookback_days: int = 365 * 3
    ) -> Optional[InteractionHistory]:
        """
        Extract email interaction history for a contact.

        Args:
            contact_email: Email address to look up
            max_messages: Maximum messages to analyze
            lookback_days: How far back to look

        Returns:
            InteractionHistory or None if no data
        """
        if not self.gmail_adapter:
            return None

        contact_email = contact_email.lower().strip()
        history = InteractionHistory(contact_email=contact_email)

        # Query emails FROM this contact
        received_emails = self._query_emails(
            f"from:{contact_email}",
            max_messages // 2,
            lookback_days
        )

        # Query emails TO this contact
        sent_emails = self._query_emails(
            f"to:{contact_email}",
            max_messages // 2,
            lookback_days
        )

        if not received_emails and not sent_emails:
            return None

        # Combine and dedupe by message ID
        all_emails = {}
        for email in received_emails:
            all_emails[email.id] = ('received', email)
        for email in sent_emails:
            if email.id not in all_emails:
                all_emails[email.id] = ('sent', email)

        # Process emails
        history.received_count = len(received_emails)
        history.sent_count = len([e for e in sent_emails if e.id not in {r.id for r in received_emails}])
        history.total_messages = len(all_emails)

        if not all_emails:
            return None

        # Extract contact name from received emails
        for _, email in all_emails.values():
            if email.sender.lower() == contact_email:
                if email.sender_name:
                    history.contact_name = email.sender_name
                    break

        # Sort by date
        sorted_emails = sorted(
            [(direction, email) for _, (direction, email) in all_emails.items()],
            key=lambda x: x[1].date
        )

        # First and last contact
        history.first_contact = sorted_emails[0][1].date
        history.last_contact = sorted_emails[-1][1].date

        # Calculate frequency
        if history.first_contact and history.last_contact:
            days_span = max(1, (history.last_contact - history.first_contact).days)
            months_span = max(1, days_span / 30)
            history.frequency_per_month = history.total_messages / months_span

        # Monthly breakdown
        history.monthly_counts = self._calculate_monthly_counts(sorted_emails)
        history.active_months = len(history.monthly_counts)

        # Extract topics from subjects
        subjects = [email.subject for _, email in sorted_emails]
        history.topics = self._extract_topics(subjects)
        history.subject_samples = self._get_subject_samples(subjects)

        # Group by threads
        history.key_threads = self._extract_threads(sorted_emails)
        history.thread_count = len(history.key_threads)

        # Determine relationship status
        history.relationship_status = self._calculate_relationship_status(history.last_contact)

        return history

    def _query_emails(self, query: str, max_results: int, days: int) -> List:
        """Query Gmail API."""
        try:
            emails = self.gmail_adapter.pull_emails(
                query=query,
                days=days,
                max_results=max_results
            )
            return emails
        except Exception as e:
            print(f"Error querying emails: {e}")
            return []

    def _calculate_monthly_counts(self, sorted_emails: List) -> Dict[str, int]:
        """Calculate message counts by month."""
        counts = defaultdict(int)
        for _, email in sorted_emails:
            month_key = email.date.strftime('%Y-%m')
            counts[month_key] += 1
        return dict(counts)

    def _extract_topics(self, subjects: List[str], top_n: int = 5) -> List[str]:
        """Extract topic keywords from subject lines."""
        words = []

        for subject in subjects:
            # Clean subject
            subject = subject.lower()
            # Remove Re:/Fwd: prefixes
            subject = re.sub(r'^(re:|fwd?:|fw:)\s*', '', subject, flags=re.IGNORECASE)

            # Tokenize
            tokens = re.findall(r'\b[a-z]{3,}\b', subject)

            # Filter stopwords and short words
            tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 2]
            words.extend(tokens)

        # Count frequencies
        counter = Counter(words)

        # Return top N
        return [word for word, _ in counter.most_common(top_n)]

    def _get_subject_samples(self, subjects: List[str], max_samples: int = 5) -> List[str]:
        """Get sample subject lines (deduplicated)."""
        seen = set()
        samples = []

        for subject in subjects:
            # Normalize for dedup
            normalized = re.sub(r'^(re:|fwd?:|fw:)\s*', '', subject, flags=re.IGNORECASE).strip()
            if normalized.lower() not in seen and normalized:
                seen.add(normalized.lower())
                samples.append(normalized[:80])
                if len(samples) >= max_samples:
                    break

        return samples

    def _extract_threads(self, sorted_emails: List, top_n: int = 5) -> List[EmailThread]:
        """Extract key conversation threads."""
        threads = defaultdict(list)

        for direction, email in sorted_emails:
            threads[email.thread_id].append((direction, email))

        # Build thread objects
        thread_objects = []
        for thread_id, messages in threads.items():
            if len(messages) < 2:
                continue

            messages.sort(key=lambda x: x[1].date)
            first_msg = messages[0][1]
            last_msg = messages[-1][1]

            # Get normalized subject
            subject = re.sub(r'^(re:|fwd?:|fw:)\s*', '', first_msg.subject, flags=re.IGNORECASE).strip()

            # Get participants
            participants = set()
            for _, msg in messages:
                participants.add(msg.sender)
                participants.update(msg.recipients)

            thread_objects.append(EmailThread(
                thread_id=thread_id,
                subject=subject[:60],
                message_count=len(messages),
                first_date=first_msg.date,
                last_date=last_msg.date,
                participants=list(participants)[:5],
                snippet=last_msg.snippet[:100] if last_msg.snippet else ""
            ))

        # Sort by message count and recency
        thread_objects.sort(key=lambda t: (t.message_count, t.last_date), reverse=True)

        return thread_objects[:top_n]

    def _calculate_relationship_status(self, last_contact: datetime) -> str:
        """Calculate relationship status based on recency."""
        if not last_contact:
            return 'unknown'

        days_since = (datetime.now(last_contact.tzinfo) - last_contact).days

        if days_since <= 14:
            return 'active'
        elif days_since <= 30:
            return 'warming'
        elif days_since <= 60:
            return 'cooling'
        else:
            return 'dormant'


@dataclass
class DiscoveredEmail:
    """Result of email discovery for a contact."""
    contact_name: str
    discovered_email: Optional[str] = None
    confidence: float = 0.0
    match_count: int = 0
    sample_subjects: List[str] = field(default_factory=list)
    error: str = ""


class EmailDiscovery:
    """Discovers email addresses for contacts by searching Gmail by name."""

    def __init__(self, gmail_address: str, data_root: Path = None):
        self.gmail_address = gmail_address
        self.data_root = data_root or Path.home() / 'Data'
        self._gmail_adapter = None

    @property
    def gmail_adapter(self):
        """Lazy-load Gmail adapter."""
        if self._gmail_adapter is None:
            try:
                from gmail import GmailAdapter
                self._gmail_adapter = GmailAdapter({'address': self.gmail_address})
                if not self._gmail_adapter.is_configured():
                    print(f"Gmail not configured for {self.gmail_address}")
                    return None
            except ImportError as e:
                print(f"Could not import Gmail adapter: {e}")
                return None
        return self._gmail_adapter

    def discover_email(self, name: str, max_results: int = 20) -> DiscoveredEmail:
        """
        Search Gmail for emails from/to a person by name.

        Args:
            name: Contact name to search for
            max_results: Maximum messages to analyze

        Returns:
            DiscoveredEmail with results
        """
        result = DiscoveredEmail(contact_name=name)

        if not self.gmail_adapter:
            result.error = "Gmail adapter not available"
            return result

        # Clean name for search (remove emojis, special chars, handle suffixes)
        clean_name = self._clean_name_for_search(name)
        if not clean_name or len(clean_name) < 3:
            result.error = f"Name too short after cleaning: '{clean_name}'"
            return result

        # Search for emails FROM this person
        try:
            query = f'from:"{clean_name}"'
            emails = self.gmail_adapter.pull_emails(
                query=query,
                days=365 * 5,  # Look back 5 years
                max_results=max_results
            )
        except Exception as e:
            result.error = f"Query error: {e}"
            return result

        if not emails:
            # Try TO query as fallback
            try:
                query = f'to:"{clean_name}"'
                emails = self.gmail_adapter.pull_emails(
                    query=query,
                    days=365 * 5,
                    max_results=max_results
                )
            except Exception as e:
                result.error = f"Query error: {e}"
                return result

        if not emails:
            result.error = "No emails found"
            return result

        # Extract email addresses from results
        email_counts = Counter()
        subjects = []

        for email in emails:
            # Check sender
            if email.sender and self._name_matches(clean_name, email.sender_name or ""):
                email_counts[email.sender.lower()] += 1
                if len(subjects) < 3:
                    subjects.append(email.subject[:50])

            # Check recipients
            for recipient in email.recipients:
                # We can't easily get recipient names, so just collect emails
                # that aren't our own
                if recipient.lower() != self.gmail_address.lower():
                    email_counts[recipient.lower()] += 1

        if not email_counts:
            result.error = "No matching email addresses found"
            return result

        # Get most common email
        most_common = email_counts.most_common(1)[0]
        result.discovered_email = most_common[0]
        result.match_count = most_common[1]
        result.sample_subjects = subjects
        result.confidence = min(1.0, most_common[1] / 5)  # 5+ matches = full confidence

        return result

    def _clean_name_for_search(self, name: str) -> str:
        """Clean contact name for Gmail search."""
        # Remove emojis and special Unicode
        clean = re.sub(r'[^\w\s\-\']', '', name, flags=re.UNICODE)
        # Remove common suffixes like "(1)", "- NTC Kranj"
        clean = re.sub(r'\s*\([^)]*\)\s*', ' ', clean)
        clean = re.sub(r'\s*-\s*[^-]+$', '', clean)
        clean = re.sub(r'\s*\|.*$', '', clean)
        # Normalize whitespace
        clean = ' '.join(clean.split())
        return clean.strip()

    def _name_matches(self, search_name: str, found_name: str) -> bool:
        """Check if found name reasonably matches search name."""
        if not found_name:
            return False

        search_lower = search_name.lower()
        found_lower = found_name.lower()

        # Exact match
        if search_lower == found_lower:
            return True

        # First name match
        search_parts = search_lower.split()
        found_parts = found_lower.split()

        if search_parts and found_parts:
            # First name matches
            if search_parts[0] == found_parts[0]:
                return True
            # Last name matches (if both have 2+ parts)
            if len(search_parts) > 1 and len(found_parts) > 1:
                if search_parts[-1] == found_parts[-1]:
                    return True

        return False


class ContactDiscovery:
    """Discovers emails for phone-only contacts in a space."""

    def __init__(self, data_root: Path, gmail_address: str, space: str = '0-personal'):
        self.data_root = data_root
        self.space = space
        self.contacts_dir = data_root / space / 'contacts' / 'people'
        self.discovery = EmailDiscovery(gmail_address, data_root)

    def get_phone_only_contacts(self) -> List[Tuple[Path, str]]:
        """Get list of contacts with phone but no email."""
        results = []

        for contact_file in self.contacts_dir.glob('*.md'):
            if contact_file.name.startswith('_'):
                continue

            try:
                content = contact_file.read_text()
                if not content.startswith('---'):
                    continue

                parts = content.split('---', 2)
                if len(parts) < 3:
                    continue

                frontmatter = yaml.safe_load(parts[1])
                if not frontmatter:
                    continue

                channels = frontmatter.get('channels', {})
                email = channels.get('email', '')
                phone = channels.get('phone', '')

                if phone and not email:
                    name = frontmatter.get('name', contact_file.stem)
                    results.append((contact_file, name))

            except Exception:
                continue

        return results

    def discover_all(self, update_contacts: bool = False) -> List[DiscoveredEmail]:
        """
        Discover emails for all phone-only contacts.

        Args:
            update_contacts: If True, update contact files with discovered emails

        Returns:
            List of DiscoveredEmail results
        """
        phone_only = self.get_phone_only_contacts()
        results = []

        print(f"\nDiscovering emails for {len(phone_only)} phone-only contacts...")

        for contact_path, name in phone_only:
            print(f"  {name}...", end=" ", flush=True)

            result = self.discovery.discover_email(name)
            results.append(result)

            if result.discovered_email:
                print(f"→ {result.discovered_email} (confidence: {result.confidence:.0%})")

                if update_contacts:
                    self._update_contact_email(contact_path, result.discovered_email)
            else:
                print(f"✗ {result.error}")

        return results

    def _update_contact_email(self, contact_path: Path, email: str):
        """Update contact file with discovered email."""
        content = contact_path.read_text()
        parts = content.split('---', 2)

        if len(parts) < 3:
            return

        try:
            frontmatter = yaml.safe_load(parts[1])
            if not frontmatter:
                return

            # Update email
            if 'channels' not in frontmatter:
                frontmatter['channels'] = {}
            frontmatter['channels']['email'] = email
            frontmatter['updated'] = date.today().isoformat()

            # Rebuild content
            new_content = "---\n"
            new_content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
            new_content += "---\n"
            new_content += parts[2]

            contact_path.write_text(new_content)

        except Exception as e:
            print(f"    Error updating: {e}")


class ContactEnricher:
    """Enriches CRM contact files with email history."""

    def __init__(self, data_root: Path, gmail_address: str, space: str = '0-personal'):
        self.data_root = data_root
        self.space = space
        self.contacts_dir = data_root / space / 'contacts' / 'people'
        self.enricher = EmailEnricher(gmail_address, data_root)

    def enrich_contact_file(self, contact_path: Path) -> Optional[InteractionHistory]:
        """
        Enrich a single contact file with email history.

        Args:
            contact_path: Path to contact markdown file

        Returns:
            InteractionHistory if enriched, None otherwise
        """
        # Read contact file
        content = contact_path.read_text()
        if not content.startswith('---'):
            return None

        parts = content.split('---', 2)
        if len(parts) < 3:
            return None

        try:
            frontmatter = yaml.safe_load(parts[1])
        except yaml.YAMLError:
            return None

        if not frontmatter:
            return None

        # Get email address
        channels = frontmatter.get('channels', {})
        email = channels.get('email', '')

        if not email:
            print(f"  No email for {frontmatter.get('name', contact_path.name)}")
            return None

        # Enrich
        print(f"  Enriching {frontmatter.get('name', '')} ({email})...")
        history = self.enricher.enrich_contact(email)

        if not history or history.total_messages == 0:
            print(f"    No email history found")
            return None

        print(f"    Found {history.total_messages} emails, {history.first_contact} to {history.last_contact}")

        # Update frontmatter
        frontmatter['email_history'] = history.to_dict()
        frontmatter['updated'] = date.today().isoformat()

        if history.last_contact:
            frontmatter['last_interaction'] = history.last_contact.strftime('%Y-%m-%d')

        # Update relationship_status if dormant
        if history.relationship_status == 'dormant' and frontmatter.get('relationship_status') == 'active':
            frontmatter['relationship_status'] = 'dormant'

        # Rebuild content
        new_content = "---\n"
        new_content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        new_content += "---\n"

        # Update body with email history section
        body = parts[2]
        body = self._update_email_history_section(body, history)

        new_content += body

        # Write back
        contact_path.write_text(new_content)

        return history

    def _update_email_history_section(self, body: str, history: InteractionHistory) -> str:
        """Update or add Email History section in contact body."""
        section = self._generate_email_history_section(history)

        # Check if section exists
        if '## Email History' in body:
            # Replace existing section
            pattern = r'## Email History\n.*?(?=\n## |\n#[^#]|\Z)'
            body = re.sub(pattern, section.rstrip() + '\n\n', body, flags=re.DOTALL)
        else:
            # Add before Notes or at end
            if '## Notes' in body:
                body = body.replace('## Notes', f'{section}\n## Notes')
            else:
                body = body.rstrip() + '\n\n' + section

        return body

    def _generate_email_history_section(self, history: InteractionHistory) -> str:
        """Generate Email History markdown section."""
        section = "## Email History\n\n"

        section += "| Metric | Value |\n"
        section += "|--------|-------|\n"
        section += f"| First contact | {history.first_contact.strftime('%Y-%m-%d') if history.first_contact else 'N/A'} |\n"
        section += f"| Last contact | {history.last_contact.strftime('%Y-%m-%d') if history.last_contact else 'N/A'} |\n"
        section += f"| Total emails | {history.total_messages} |\n"
        section += f"| Sent | {history.sent_count} |\n"
        section += f"| Received | {history.received_count} |\n"
        section += f"| Frequency | {history.frequency_per_month:.1f}/month |\n"
        section += f"| Status | {history.relationship_status} |\n"
        section += "\n"

        if history.topics:
            section += f"**Topics:** {', '.join(history.topics)}\n\n"

        if history.key_threads:
            section += "### Key Threads\n\n"
            for thread in history.key_threads[:5]:
                date_str = thread.last_date.strftime('%b %Y')
                section += f"- [{date_str}] {thread.subject} ({thread.message_count} emails)\n"
            section += "\n"

        return section

    def enrich_all_drafts(self) -> Dict[str, Any]:
        """Enrich all draft contacts with email history."""
        results = {
            'total': 0,
            'enriched': 0,
            'no_email': 0,
            'no_history': 0,
            'errors': []
        }

        if not self.contacts_dir.exists():
            print(f"Contacts directory not found: {self.contacts_dir}")
            return results

        for contact_file in self.contacts_dir.rglob('*.md'):
            if contact_file.name.startswith('_'):
                continue

            # Check if draft
            content = contact_file.read_text()
            if 'status: draft' not in content:
                continue

            results['total'] += 1

            try:
                history = self.enrich_contact_file(contact_file)
                if history:
                    results['enriched'] += 1
                elif 'No email' in str(history):
                    results['no_email'] += 1
                else:
                    results['no_history'] += 1
            except Exception as e:
                results['errors'].append(f"{contact_file.name}: {e}")

        return results

    def enrich_by_email(self, email: str) -> Optional[InteractionHistory]:
        """Find and enrich contact by email address."""
        if not self.contacts_dir.exists():
            return None

        for contact_file in self.contacts_dir.rglob('*.md'):
            if contact_file.name.startswith('_'):
                continue

            content = contact_file.read_text()
            if f'email: {email}' in content or f'email: "{email}"' in content:
                return self.enrich_contact_file(contact_file)

        print(f"No contact found with email: {email}")
        return None


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """CLI entry point for email enrichment."""
    import argparse

    parser = argparse.ArgumentParser(description="Email Enricher for CRM")
    parser.add_argument('command', choices=['enrich', 'test', 'analyze', 'discover'],
                        help='Command to run')
    parser.add_argument('--email', help='Contact email to enrich')
    parser.add_argument('--name', help='Contact name to discover email for')
    parser.add_argument('--all-drafts', action='store_true',
                        help='Enrich all draft contacts')
    parser.add_argument('--all-phone-only', action='store_true',
                        help='Discover emails for all phone-only contacts')
    parser.add_argument('--update', action='store_true',
                        help='Update contact files with discovered emails')
    parser.add_argument('--space', default='0-personal',
                        help='Target space (default: 0-personal)')
    parser.add_argument('--gmail-account', required=True,
                        help='Gmail account to query')
    parser.add_argument('--data-root', default=str(Path.home() / 'Data'),
                        help='Data root path')
    parser.add_argument('--max-messages', type=int, default=500,
                        help='Max messages to analyze per contact')

    args = parser.parse_args()

    data_root = Path(args.data_root)

    if args.command == 'test':
        # Test Gmail connection
        enricher = EmailEnricher(args.gmail_account, data_root)
        if enricher.gmail_adapter:
            success, msg = enricher.gmail_adapter.test_connection()
            print(f"{'OK' if success else 'FAILED'}: {msg}")
        else:
            print("Gmail adapter not available")

    elif args.command == 'analyze':
        # Analyze single email without updating files
        if not args.email:
            print("--email required for analyze command")
            return 1

        enricher = EmailEnricher(args.gmail_account, data_root)
        history = enricher.enrich_contact(args.email, max_messages=args.max_messages)

        if history:
            print(f"\nInteraction History for {args.email}")
            print(f"  Contact name: {history.contact_name}")
            print(f"  First contact: {history.first_contact}")
            print(f"  Last contact: {history.last_contact}")
            print(f"  Total messages: {history.total_messages}")
            print(f"  Sent: {history.sent_count}, Received: {history.received_count}")
            print(f"  Frequency: {history.frequency_per_month:.1f}/month")
            print(f"  Status: {history.relationship_status}")
            print(f"  Topics: {', '.join(history.topics)}")
            print(f"  Threads: {history.thread_count}")

            if history.key_threads:
                print(f"\n  Key threads:")
                for thread in history.key_threads[:5]:
                    print(f"    - {thread.subject} ({thread.message_count} emails)")
        else:
            print(f"No email history found for {args.email}")

    elif args.command == 'enrich':
        contact_enricher = ContactEnricher(data_root, args.gmail_account, args.space)

        if args.all_drafts:
            print(f"\nEnriching all draft contacts in {args.space}...")
            results = contact_enricher.enrich_all_drafts()

            print(f"\nResults:")
            print(f"  Total drafts: {results['total']}")
            print(f"  Enriched: {results['enriched']}")
            print(f"  No email: {results['no_email']}")
            print(f"  No history: {results['no_history']}")

            if results['errors']:
                print(f"\n  Errors:")
                for error in results['errors']:
                    print(f"    - {error}")

        elif args.email:
            history = contact_enricher.enrich_by_email(args.email)
            if history:
                print(f"\nEnriched contact with {history.total_messages} emails")
            else:
                print(f"Could not enrich contact")
        else:
            print("Specify --email or --all-drafts")
            return 1

    elif args.command == 'discover':
        if args.all_phone_only:
            # Discover emails for all phone-only contacts
            discovery = ContactDiscovery(data_root, args.gmail_account, args.space)
            results = discovery.discover_all(update_contacts=args.update)

            # Summary
            found = [r for r in results if r.discovered_email]
            not_found = [r for r in results if not r.discovered_email]

            print(f"\n{'='*60}")
            print(f"Discovery Summary:")
            print(f"  Total searched: {len(results)}")
            print(f"  Emails found: {len(found)}")
            print(f"  Not found: {len(not_found)}")

            if found:
                print(f"\n  Found emails:")
                for r in found:
                    conf = f"({r.confidence:.0%})" if r.confidence < 1.0 else ""
                    print(f"    {r.contact_name} → {r.discovered_email} {conf}")

            if args.update:
                print(f"\n  Contact files updated with discovered emails.")
                print(f"  Run 'enrich --all-drafts' to fetch email history.")

        elif args.name:
            # Discover email for single contact by name
            discovery = EmailDiscovery(args.gmail_account, data_root)
            result = discovery.discover_email(args.name)

            if result.discovered_email:
                print(f"\nDiscovered email for '{args.name}':")
                print(f"  Email: {result.discovered_email}")
                print(f"  Confidence: {result.confidence:.0%}")
                print(f"  Match count: {result.match_count}")
                if result.sample_subjects:
                    print(f"  Sample subjects:")
                    for subj in result.sample_subjects:
                        print(f"    - {subj}")
            else:
                print(f"\nNo email found for '{args.name}': {result.error}")

        else:
            print("Specify --name or --all-phone-only")
            return 1

    return 0


if __name__ == '__main__':
    exit(main())
