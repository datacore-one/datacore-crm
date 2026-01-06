#!/usr/bin/env python3
"""
Mbox Parser - Parse Thunderbird mbox files with privacy-aware enrichment.

Parses local email archives for relationship database indexing.
- Full enrichment for normal domains (headers + subject + body snippet)
- Sensitive domains get headers + subject only (no body content)
- Newsletter/automated emails are filtered out

Usage:
    from mbox_parser import MboxParser

    parser = MboxParser(
        mbox_path="~/Library/Thunderbird/.../All Mail",
        rules_path=".datacore/modules/mail/rules.base.yaml",
        sensitive_domains=["*-law.eu", "*.health"],
        excluded_domains=["spam.example.com"]
    )

    for email in parser.parse_all():
        print(f"{email.from_email}: {email.subject}")
"""

import mailbox
import re
import yaml
from dataclasses import dataclass, field
from datetime import datetime
from email.utils import parseaddr, parsedate_to_datetime, getaddresses
from fnmatch import fnmatch
from pathlib import Path
from typing import Generator, List, Optional, Set, Dict, Any
from html.parser import HTMLParser


@dataclass
class EmailMetadata:
    """Parsed email metadata for relationship tracking."""
    from_email: str
    from_name: str
    to_emails: List[str]
    cc_emails: List[str]
    date: datetime
    subject: str
    snippet: Optional[str]  # None for sensitive domains
    keywords: Optional[List[str]]  # None for sensitive domains
    message_id: str
    thread_id: str
    is_sensitive: bool = False


class HTMLStripper(HTMLParser):
    """Strip HTML tags from content."""

    def __init__(self):
        super().__init__()
        self.reset()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)

    def get_text(self):
        return ''.join(self.text)


def strip_html(html: str) -> str:
    """Remove HTML tags and return plain text."""
    stripper = HTMLStripper()
    try:
        stripper.feed(html)
        return stripper.get_text()
    except:
        return html


def parse_email_address(addr_string: str) -> str:
    """Extract email address from 'Name <email>' format."""
    if not addr_string:
        return ''
    name, email = parseaddr(addr_string)
    return email.lower().strip()


def parse_name_from_address(addr_string: str) -> str:
    """Extract name from 'Name <email>' format."""
    if not addr_string:
        return ''
    name, email = parseaddr(addr_string)
    return name.strip() or email.split('@')[0]


def parse_recipients(addr_string: str) -> List[str]:
    """Parse multiple recipients from header."""
    if not addr_string:
        return []
    addresses = getaddresses([addr_string])
    return [email.lower().strip() for name, email in addresses if email]


def parse_date_safe(date_str: str) -> datetime:
    """Parse date string safely, return epoch on failure."""
    if not date_str:
        return datetime(1970, 1, 1)
    try:
        return parsedate_to_datetime(date_str)
    except:
        return datetime(1970, 1, 1)


def extract_keywords(text: str) -> List[str]:
    """Extract keywords from subject/text for topic detection."""
    if not text:
        return []

    # Common stop words to filter
    stop_words = {
        're', 'fwd', 'fw', 'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on',
        'at', 'to', 'for', 'of', 'with', 'by', 'from', 'is', 'are', 'was',
        'were', 'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does',
        'did', 'will', 'would', 'could', 'should', 'may', 'might', 'must',
        'this', 'that', 'these', 'those', 'i', 'you', 'he', 'she', 'it',
        'we', 'they', 'my', 'your', 'his', 'her', 'its', 'our', 'their',
        'what', 'which', 'who', 'whom', 'whose', 'when', 'where', 'why', 'how',
        'all', 'each', 'every', 'both', 'few', 'more', 'most', 'other', 'some',
        'such', 'no', 'nor', 'not', 'only', 'own', 'same', 'so', 'than', 'too',
        'very', 'just', 'about', 'up', 'down', 'out', 'off', 'over', 'under'
    }

    # Extract words, filter stop words, keep meaningful ones
    words = re.findall(r'\b[a-zA-Z]{3,}\b', text.lower())
    keywords = [w for w in words if w not in stop_words]

    # Return unique keywords
    return list(dict.fromkeys(keywords))[:10]


class MboxParser:
    """
    Parse Thunderbird mbox files with privacy-aware enrichment.

    - Full enrichment for normal domains
    - Headers + subject only for sensitive domains
    - Newsletters/automated emails filtered out
    """

    def __init__(
        self,
        mbox_path: str,
        rules_path: str,
        sensitive_domains: List[str] = None,
        excluded_domains: List[str] = None
    ):
        """
        Initialize parser.

        Args:
            mbox_path: Path to Thunderbird mbox file
            rules_path: Path to mail rules YAML (for newsletter detection)
            sensitive_domains: Patterns for domains to index without body
            excluded_domains: Patterns for domains to skip entirely
        """
        self.mbox_path = Path(mbox_path).expanduser()
        self.rules = self._load_rules(rules_path)
        self.sensitive = set(sensitive_domains or [])
        self.excluded = set(excluded_domains or [])

        # Build pattern lists from rules
        self._newsletter_patterns = self._build_newsletter_patterns()
        self._automated_patterns = self._build_automated_patterns()

    def _load_rules(self, rules_path: str) -> Dict[str, Any]:
        """Load mail classification rules from YAML."""
        path = Path(rules_path).expanduser()
        if not path.exists():
            return {}
        try:
            with open(path) as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            print(f"Warning: Failed to load rules from {path}: {e}")
            return {}

    def _build_newsletter_patterns(self) -> Set[str]:
        """Build set of newsletter sender patterns from rules."""
        patterns = set()

        # From senders.newsletter
        newsletter_rules = self.rules.get('senders', {}).get('newsletter', [])
        for rule in newsletter_rules:
            if isinstance(rule, dict):
                pattern = rule.get('pattern', '').lower()
            else:
                pattern = str(rule).lower()
            if pattern:
                patterns.add(pattern)

        # Newsletter domains
        domains = self.rules.get('domains', {}).get('newsletter', [])
        patterns.update(d.lower() for d in domains)

        # Common newsletter patterns
        patterns.update([
            'substack.com', 'beehiiv.com', 'mailchimp.com', 'sendgrid.net',
            'constantcontact.com', 'getrevue.co', 'convertkit.com',
            'newsletter', 'news@', 'digest@', 'weekly@', 'daily@',
            'updates@', 'info@', 'hello@', 'team@', 'marketing@'
        ])

        return patterns

    def _build_automated_patterns(self) -> Set[str]:
        """Build set of automated sender patterns."""
        return {
            'noreply', 'no-reply', 'donotreply', 'notifications@',
            'alert@', 'alerts@', 'system@', 'mailer@', 'daemon@',
            'postmaster@', 'bounce@', 'auto@', 'automated@',
            'notifications@github.com', 'noreply@github.com',
            'calendar-notification@google.com', 'drive-shares-noreply@google.com',
            'linkedin.com', 'facebook.com', 'twitter.com'
        }

    def _matches_pattern(self, text: str, patterns: Set[str]) -> bool:
        """Check if text matches any pattern."""
        text_lower = text.lower()
        return any(p in text_lower for p in patterns)

    def _is_excluded(self, email: str) -> bool:
        """Check if email domain is fully excluded."""
        if not email or '@' not in email:
            return True
        domain = email.split('@')[-1].lower()
        return any(fnmatch(domain, pattern) for pattern in self.excluded)

    def _is_sensitive(self, email: str) -> bool:
        """Check if email domain is sensitive (no body storage)."""
        if not email or '@' not in email:
            return False
        domain = email.split('@')[-1].lower()
        return any(fnmatch(domain, pattern) for pattern in self.sensitive)

    def _is_personal(self, email: str, from_header: str) -> bool:
        """Check if sender is personal (not newsletter/automated)."""
        # Check for newsletter patterns
        if self._matches_pattern(from_header, self._newsletter_patterns):
            return False
        if self._matches_pattern(email, self._newsletter_patterns):
            return False

        # Check for automated patterns
        if self._matches_pattern(from_header, self._automated_patterns):
            return False
        if self._matches_pattern(email, self._automated_patterns):
            return False

        return True

    def _extract_body_snippet(self, message, max_chars: int = 500) -> Optional[str]:
        """
        Extract first N chars of body content.

        Handles multipart messages, prefers text/plain over HTML.
        Strips signatures, quotes, and forwarded content.
        """
        try:
            body = None

            if message.is_multipart():
                # Find text/plain or text/html part
                for part in message.walk():
                    content_type = part.get_content_type()
                    if content_type == 'text/plain':
                        payload = part.get_payload(decode=True)
                        if payload:
                            body = payload.decode('utf-8', errors='ignore')
                            break
                    elif content_type == 'text/html' and body is None:
                        payload = part.get_payload(decode=True)
                        if payload:
                            html = payload.decode('utf-8', errors='ignore')
                            body = strip_html(html)
            else:
                payload = message.get_payload(decode=True)
                if payload:
                    body = payload.decode('utf-8', errors='ignore')
                    content_type = message.get_content_type()
                    if content_type == 'text/html':
                        body = strip_html(body)

            if not body:
                return None

            # Clean up the body
            # Remove quoted content (lines starting with >)
            lines = body.split('\n')
            cleaned_lines = []
            for line in lines:
                stripped = line.strip()
                # Skip quoted lines
                if stripped.startswith('>'):
                    continue
                # Stop at signature markers
                if stripped in ['--', '---', '- --', '___']:
                    break
                # Stop at forwarded content
                if 'Forwarded message' in line or 'Original Message' in line:
                    break
                cleaned_lines.append(line)

            body = '\n'.join(cleaned_lines)

            # Normalize whitespace
            body = re.sub(r'\s+', ' ', body).strip()

            return body[:max_chars] if body else None

        except Exception as e:
            return None

    def _derive_thread_id(self, message) -> str:
        """Derive thread ID from References or In-Reply-To headers."""
        # Try Gmail thread ID first
        gmail_thread = message.get('X-GM-THRID')
        if gmail_thread:
            return gmail_thread

        # Fall back to first reference or In-Reply-To
        references = message.get('References', '')
        if references:
            # First message-id in references is usually the thread root
            match = re.search(r'<([^>]+)>', references)
            if match:
                return match.group(1)

        in_reply_to = message.get('In-Reply-To', '')
        if in_reply_to:
            match = re.search(r'<([^>]+)>', in_reply_to)
            if match:
                return match.group(1)

        # No thread info, use message-id as thread
        message_id = message.get('Message-ID', '')
        match = re.search(r'<([^>]+)>', message_id)
        return match.group(1) if match else ''

    def count_messages(self) -> int:
        """Count total messages in mbox (for progress)."""
        try:
            mbox = mailbox.mbox(str(self.mbox_path))
            count = len(mbox)
            mbox.close()
            return count
        except:
            return 0

    def parse_all(
        self,
        progress_callback=None,
        max_messages: int = 0
    ) -> Generator[EmailMetadata, None, None]:
        """
        Parse all emails with privacy-aware enrichment.

        Args:
            progress_callback: Optional function(current, total) for progress
            max_messages: Max messages to parse (0 = all)

        Yields:
            EmailMetadata for each personal email
        """
        mbox = mailbox.mbox(str(self.mbox_path))
        total = len(mbox)
        processed = 0
        yielded = 0

        try:
            i = 0
            for key in mbox.keys():
                try:
                    message = mbox.get(key)
                except (UnicodeDecodeError, KeyError) as e:
                    # Skip messages with encoding issues
                    i += 1
                    continue

                if progress_callback and i % 1000 == 0:
                    progress_callback(i, total)

                if max_messages and yielded >= max_messages:
                    break

                i += 1

                try:
                    # Parse from address
                    from_header = message.get('From', '')
                    from_email = parse_email_address(from_header)

                    if not from_email:
                        continue

                    # Skip fully excluded domains
                    if self._is_excluded(from_email):
                        continue

                    # Skip newsletters/automated
                    if not self._is_personal(from_email, from_header):
                        continue

                    # Parse recipients
                    to_emails = parse_recipients(message.get('To', ''))
                    cc_emails = parse_recipients(message.get('Cc', ''))

                    # Check if ANY participant is sensitive → no body
                    all_participants = [from_email] + to_emails + cc_emails
                    is_sensitive = any(self._is_sensitive(e) for e in all_participants)

                    # Parse subject
                    subject = message.get('Subject', '') or ''

                    # Extract message ID
                    message_id_raw = message.get('Message-ID', '')
                    match = re.search(r'<([^>]+)>', message_id_raw)
                    message_id = match.group(1) if match else message_id_raw

                    # Build metadata
                    yield EmailMetadata(
                        from_email=from_email,
                        from_name=parse_name_from_address(from_header),
                        to_emails=to_emails,
                        cc_emails=cc_emails,
                        date=parse_date_safe(message.get('Date')),
                        subject=subject,
                        # NO body/keywords for sensitive domains
                        snippet=None if is_sensitive else self._extract_body_snippet(message),
                        keywords=None if is_sensitive else extract_keywords(subject),
                        message_id=message_id,
                        thread_id=self._derive_thread_id(message),
                        is_sensitive=is_sensitive
                    )

                    yielded += 1

                except Exception as e:
                    # Skip malformed messages
                    continue

        finally:
            mbox.close()

        if progress_callback:
            progress_callback(total, total)


def main():
    """Test parser on sample mbox."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: python mbox_parser.py <mbox_path>")
        print("Example: python mbox_parser.py ~/Library/Thunderbird/.../All\\ Mail")
        sys.exit(1)

    mbox_path = sys.argv[1]
    rules_path = Path(__file__).parent.parent.parent / "mail" / "rules.base.yaml"

    parser = MboxParser(
        mbox_path=mbox_path,
        rules_path=str(rules_path),
        sensitive_domains=["*-law.eu", "*-law.si", "*.legal.ch"],
        excluded_domains=[]
    )

    print(f"Parsing: {mbox_path}")
    total = parser.count_messages()
    print(f"Total messages: {total:,}")

    def progress(current, total):
        pct = (current / total * 100) if total else 0
        print(f"\r  Processed {current:,}/{total:,} ({pct:.1f}%)...", end='', flush=True)

    personal_count = 0
    sensitive_count = 0

    for email in parser.parse_all(progress_callback=progress, max_messages=1000):
        personal_count += 1
        if email.is_sensitive:
            sensitive_count += 1

    print(f"\n\nPersonal emails: {personal_count:,}")
    print(f"Sensitive (no body): {sensitive_count:,}")


if __name__ == "__main__":
    main()
