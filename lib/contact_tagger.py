#!/usr/bin/env python3
"""
Contact Tagger - Auto-tag contacts based on domain patterns and rules.

Tags are detected from:
- Domain patterns (e.g., @team-a.example.com → "team-a")
- Email patterns (e.g., newsletter@* → "newsletter")
- User-defined rules in rules.local.yaml

Usage:
    from contact_tagger import ContactTagger

    tagger = ContactTagger(rules_path="mail/rules.local.yaml")
    tags = tagger.get_tags("fred@usv.com")
    # Returns: ["investor", "vc"]
"""

import yaml
from fnmatch import fnmatch
from pathlib import Path
from typing import List, Dict, Set, Optional


# Built-in domain → tag mappings
DOMAIN_TAGS = {
    # Internal teams
    'team-a.example.com': [\'team-a\', 'internal'],
    'team-a.example.com': [\'team-a\', 'internal'],
    'team-b.example.com': [\'team-b\', 'internal'],

    # Known investor domains
    'usv.com': ['investor', 'vc'],
    'a16z.com': ['investor', 'vc'],
    'pantera.capital': ['investor', 'vc'],
    'sequoiacap.com': ['investor', 'vc'],
    'paradigm.xyz': ['investor', 'vc', 'crypto'],
    'polychain.capital': ['investor', 'vc', 'crypto'],
    'dragonfly.xyz': ['investor', 'vc', 'crypto'],

    # Legal
    'novak-law.eu': ['legal'],

    # Tech companies
    'google.com': ['tech', 'bigtech'],
    'microsoft.com': ['tech', 'bigtech'],
    'apple.com': ['tech', 'bigtech'],
    'amazon.com': ['tech', 'bigtech'],
    'meta.com': ['tech', 'bigtech'],

    # Crypto/Web3
    'ethereum.org': ['crypto', 'ethereum'],
    'consensys.net': ['crypto', 'ethereum'],
    'protocol.ai': ['crypto', 'filecoin'],

    # Academic
    'edu': ['academic'],
    'ac.uk': ['academic'],
    'uni-*.de': ['academic'],

    # Government
    'gov': ['government'],
    'europa.eu': ['government', 'eu'],
}

# Domain patterns (wildcards)
DOMAIN_PATTERNS = {
    '*-law.*': ['legal'],
    '*.legal.*': ['legal'],
    '*law.eu': ['legal'],
    '*law.si': ['legal'],
    '*.health': ['medical'],
    'clinic*': ['medical'],
    'doctor*': ['medical'],
    '*.vc': ['investor', 'vc'],
    '*capital.*': ['investor'],
    '*ventures.*': ['investor', 'vc'],
    '*.edu': ['academic'],
    '*.ac.*': ['academic'],
    '*.gov': ['government'],
    '*.gov.*': ['government'],
}

# Email patterns (for local part)
EMAIL_PATTERNS = {
    'newsletter@*': ['newsletter'],
    'news@*': ['newsletter'],
    'digest@*': ['newsletter'],
    'weekly@*': ['newsletter'],
    'daily@*': ['newsletter'],
    'updates@*': ['newsletter'],
    'noreply@*': ['automated'],
    'no-reply@*': ['automated'],
    'notifications@*': ['automated'],
    'support@*': ['support'],
    'help@*': ['support'],
    'sales@*': ['sales'],
    'info@*': ['generic'],
    'hello@*': ['generic'],
    'team@*': ['generic'],
    'marketing@*': ['marketing'],
    'pr@*': ['marketing', 'pr'],
}


class ContactTagger:
    """
    Auto-tag contacts based on domain patterns and rules.

    Uses built-in patterns plus optional user rules from YAML.
    """

    def __init__(self, rules_path: str = None):
        """
        Initialize tagger.

        Args:
            rules_path: Optional path to rules YAML with contact_tags section
        """
        self.domain_tags = dict(DOMAIN_TAGS)
        self.domain_patterns = dict(DOMAIN_PATTERNS)
        self.email_patterns = dict(EMAIL_PATTERNS)
        self.custom_patterns = {}

        if rules_path:
            self._load_custom_rules(rules_path)

    def _load_custom_rules(self, rules_path: str):
        """Load custom tagging rules from YAML."""
        path = Path(rules_path).expanduser()
        if not path.exists():
            return

        try:
            with open(path) as f:
                rules = yaml.safe_load(f) or {}

            # Load contact_tags section
            contact_tags = rules.get('contact_tags', {})
            for tag, patterns in contact_tags.items():
                for pattern_def in patterns:
                    if isinstance(pattern_def, dict):
                        pattern = pattern_def.get('pattern', '')
                    else:
                        pattern = str(pattern_def)

                    if pattern:
                        if tag not in self.custom_patterns:
                            self.custom_patterns[tag] = []
                        self.custom_patterns[tag].append(pattern.lower())

        except Exception as e:
            print(f"Warning: Failed to load custom rules from {path}: {e}")

    def get_tags(self, email: str, name: str = None) -> List[str]:
        """
        Get tags for an email address.

        Args:
            email: Email address
            name: Optional display name

        Returns:
            List of tags (deduplicated)
        """
        if not email or '@' not in email:
            return []

        email = email.lower()
        local_part, domain = email.split('@', 1)
        tags: Set[str] = set()

        # 1. Exact domain match
        if domain in self.domain_tags:
            tags.update(self.domain_tags[domain])

        # 2. Domain patterns (wildcards)
        for pattern, pattern_tags in self.domain_patterns.items():
            if fnmatch(domain, pattern):
                tags.update(pattern_tags)

        # 3. Email patterns (local part)
        for pattern, pattern_tags in self.email_patterns.items():
            # Pattern is like "newsletter@*" - we check local_part
            if '@' in pattern:
                local_pattern = pattern.split('@')[0]
                if fnmatch(local_part, local_pattern):
                    tags.update(pattern_tags)

        # 4. Custom patterns (match against full email or name)
        for tag, patterns in self.custom_patterns.items():
            for pattern in patterns:
                if pattern in email:
                    tags.add(tag)
                elif name and pattern in name.lower():
                    tags.add(tag)

        # 5. Top-level domain tags
        tld = domain.split('.')[-1]
        if tld == 'edu':
            tags.add('academic')
        elif tld == 'gov':
            tags.add('government')
        elif tld in ['io', 'xyz', 'eth']:
            tags.add('tech')

        return sorted(tags)

    def get_tag_from_domain(self, domain: str) -> List[str]:
        """Get tags for a domain only."""
        return self.get_tags(f"user@{domain}")

    def is_internal(self, email: str) -> bool:
        """Check if email is from internal team."""
        tags = self.get_tags(email)
        return 'internal' in tags

    def is_investor(self, email: str) -> bool:
        """Check if email is from investor/VC."""
        tags = self.get_tags(email)
        return 'investor' in tags or 'vc' in tags


class BulkTagger:
    """
    Apply tags to contacts in the relationship database.
    """

    def __init__(self, db, tagger: ContactTagger):
        """
        Initialize bulk tagger.

        Args:
            db: RelationshipDB instance
            tagger: ContactTagger instance
        """
        self.db = db
        self.tagger = tagger

    def auto_tag_all(self, overwrite: bool = False) -> Dict[str, int]:
        """
        Auto-tag all contacts in database.

        Args:
            overwrite: If True, replace existing tags. If False, merge.

        Returns:
            Stats dict with tag counts
        """
        import json
        cursor = self.db.conn.cursor()

        cursor.execute("SELECT id, email, name, tags FROM contacts")
        contacts = cursor.fetchall()

        stats = {
            'total': 0,
            'tagged': 0,
            'already_tagged': 0,
            'tag_counts': {}
        }

        for row in contacts:
            stats['total'] += 1
            contact_id = row['id']
            email = row['email']
            name = row['name']
            existing_tags = json.loads(row['tags']) if row['tags'] else []

            # Get auto-detected tags
            new_tags = self.tagger.get_tags(email, name)

            if not new_tags and not existing_tags:
                continue

            # Merge or overwrite
            if overwrite:
                final_tags = new_tags
            else:
                final_tags = list(set(existing_tags + new_tags))

            if final_tags:
                stats['tagged'] += 1
                for tag in final_tags:
                    stats['tag_counts'][tag] = stats['tag_counts'].get(tag, 0) + 1

                cursor.execute(
                    "UPDATE contacts SET tags = ? WHERE id = ?",
                    (json.dumps(sorted(final_tags)), contact_id)
                )
            elif existing_tags:
                stats['already_tagged'] += 1

        self.db.conn.commit()
        return stats


def main():
    """Test the contact tagger."""
    tagger = ContactTagger()

    test_emails = [
        'user@example.com',
        'fred@usv.com',
        'nejc.novak@novak-law.eu',
        'newsletter@techcrunch.com',
        'noreply@github.com',
        'researcher@stanford.edu',
        'someone@random.com',
        'contributor@example.com',
    ]

    print("Contact Tagger Test")
    print("=" * 60)

    for email in test_emails:
        tags = tagger.get_tags(email)
        print(f"{email:<40} → {tags}")


if __name__ == "__main__":
    main()
