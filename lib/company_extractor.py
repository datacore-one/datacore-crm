#!/usr/bin/env python3
"""
Company extractor for CRM module - Multi-source company entity extraction.

Extracts company entities from:
- Person title/bio fields (e.g., "CEO at Acme Corp")
- Email domains (e.g., dave@example.com → Acme Corp)
- Conversation mentions in context
"""

import re
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass
import tldextract


@dataclass
class CompanyMention:
    """A company mention extracted from text."""
    name: str
    source: str  # 'title' | 'bio' | 'email' | 'conversation'
    confidence: float  # 0.0 - 1.0
    context: Optional[str] = None
    domain: Optional[str] = None


class CompanyExtractor:
    """Extract company entities from multiple sources."""

    # Company suffixes (stronger signals)
    COMPANY_SUFFIXES = {
        'inc', 'incorporated', 'corp', 'corporation', 'co',
        'ltd', 'limited', 'llc', 'lp', 'plc',
        'gmbh', 'ag', 'sa', 'bv', 'nv',
        'labs', 'laboratory', 'laboratories',
        'foundation', 'institute',
        'ventures', 'capital', 'partners',
        'technologies', 'technology', 'tech',
        'systems', 'solutions', 'services',
        'group', 'holdings', 'enterprises',
    }

    # Web3-specific suffixes
    WEB3_SUFFIXES = {
        'protocol', 'network', 'chain', 'blockchain',
        'dao', 'collective',
        'finance', 'defi',
        'labs', 'studio', 'studios',
    }

    # Title/bio patterns indicating company
    TITLE_PATTERNS = [
        r'(?:CEO|CTO|CFO|COO|CMO|CPO|CRO)\s+(?:at|@|of)\s+([A-Z][a-zA-Z0-9\s&.-]{2,30})',
        r'(?:Founder|Co-founder|Co-Founder)\s+(?:at|@|of)\s+([A-Z][a-zA-Z0-9\s&.-]{2,30})',
        r'(?:Director|VP|Vice President|President)\s+(?:at|@|of)\s+([A-Z][a-zA-Z0-9\s&.-]{2,30})',
        r'(?:Head of|Lead|Manager|Partner)\s+.*?(?:at|@)\s+([A-Z][a-zA-Z0-9\s&.-]{2,30})',
        r'(?:works?|working)\s+(?:at|@|for)\s+([A-Z][a-zA-Z0-9\s&.-]{2,30})',
        r'(?:employed|employee)\s+(?:at|@|by)\s+([A-Z][a-zA-Z0-9\s&.-]{2,30})',
        r'([A-Z][a-zA-Z0-9\s&.-]{2,30})\s+(?:' + '|'.join(COMPANY_SUFFIXES) + r')\b',
    ]

    # Common TLDs to ignore when extracting from domains
    COMMON_TLDS = {'com', 'net', 'org', 'io', 'co', 'ai', 'xyz', 'app'}

    # Generic/consumer domains to skip
    GENERIC_DOMAINS = {
        'gmail.com', 'googlemail.com', 'yahoo.com', 'hotmail.com',
        'outlook.com', 'live.com', 'msn.com', 'icloud.com',
        'me.com', 'mac.com', 'aol.com', 'protonmail.com',
        'proton.me', 'tutanota.com', 'fastmail.com',
        'hey.com', 'mail.com', 'zoho.com', 'yandex.com',
    }

    def __init__(self):
        """Initialize company extractor."""
        self.compiled_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.TITLE_PATTERNS
        ]

    def extract_from_title(self, title: str) -> List[CompanyMention]:
        """
        Extract company from person's title field.

        Examples:
        - "CEO at Acme Corp" → Acme Corp
        - "Founder @ Protocol Labs" → Protocol Labs
        - "Head of Engineering at Blockchain Inc" → Blockchain Inc
        """
        if not title:
            return []

        companies = []
        for pattern in self.compiled_patterns:
            matches = pattern.finditer(title)
            for match in matches:
                company_name = match.group(1).strip()

                # Clean up trailing punctuation
                company_name = re.sub(r'[,;.]+$', '', company_name)

                # Skip if too short or looks like noise
                if len(company_name) < 3 or company_name.lower() in {'the', 'a', 'an'}:
                    continue

                # Check if it has company suffix → high confidence
                confidence = 0.7
                name_lower = company_name.lower()
                for suffix in self.COMPANY_SUFFIXES | self.WEB3_SUFFIXES:
                    if name_lower.endswith(suffix):
                        confidence = 0.95
                        break

                companies.append(CompanyMention(
                    name=company_name,
                    source='title',
                    confidence=confidence,
                    context=title
                ))

        return self._deduplicate_mentions(companies)

    def extract_from_bio(self, bio: str) -> List[CompanyMention]:
        """
        Extract companies from person's bio field.

        Similar to title extraction but with lower confidence.
        """
        if not bio:
            return []

        companies = []
        for pattern in self.compiled_patterns:
            matches = pattern.finditer(bio)
            for match in matches:
                company_name = match.group(1).strip()
                company_name = re.sub(r'[,;.]+$', '', company_name)

                if len(company_name) < 3:
                    continue

                # Lower confidence for bio vs title
                confidence = 0.6
                name_lower = company_name.lower()
                for suffix in self.COMPANY_SUFFIXES | self.WEB3_SUFFIXES:
                    if name_lower.endswith(suffix):
                        confidence = 0.85
                        break

                # Extract context window
                start = max(0, match.start() - 50)
                end = min(len(bio), match.end() + 50)
                context = bio[start:end].strip()

                companies.append(CompanyMention(
                    name=company_name,
                    source='bio',
                    confidence=confidence,
                    context=context
                ))

        return self._deduplicate_mentions(companies)

    def extract_from_email(self, email: str) -> Optional[CompanyMention]:
        """
        Extract company from email domain.

        Examples:
        - dave@example.com → Acme Corp
        - ivan@example.com → Protocol Labs
        - alice@example.com → Blockchain

        Skips generic consumer domains (gmail, yahoo, etc.)
        """
        if not email or '@' not in email:
            return None

        local_part, domain = email.rsplit('@', 1)
        domain_lower = domain.lower()

        # Skip generic domains
        if domain_lower in self.GENERIC_DOMAINS:
            return None

        # Extract using tldextract for proper parsing
        extracted = tldextract.extract(domain)

        # Skip if no subdomain and domain is too generic
        if not extracted.subdomain and extracted.domain.lower() in {'mail', 'email', 'webmail'}:
            return None

        # Build company name from domain
        company_name = self._domain_to_company_name(extracted)

        # Confidence based on domain characteristics
        confidence = 0.65

        # Higher confidence for known company TLDs
        if extracted.suffix in {'com', 'co', 'io', 'ai', 'xyz'}:
            confidence = 0.7

        # Higher confidence if domain has obvious company suffix
        domain_parts = extracted.domain.lower()
        for suffix in self.COMPANY_SUFFIXES | self.WEB3_SUFFIXES:
            if suffix in domain_parts:
                confidence = 0.8
                break

        return CompanyMention(
            name=company_name,
            source='email',
            confidence=confidence,
            domain=domain_lower
        )

    def extract_from_conversation(self, text: str, context_window: int = 100) -> List[CompanyMention]:
        """
        Extract company mentions from conversation text.

        Looks for patterns like:
        - "talked to the team at Acme Corp"
        - "partnership with Protocol Labs"
        - "Blockchain Inc is building..."
        """
        if not text:
            return []

        companies = []

        # Pattern: "at/with/from [Company]"
        pattern = r'\b(?:at|with|from|by)\s+([A-Z][a-zA-Z0-9\s&.-]{2,30}?)(?:\s|$|,|;|\.)'
        for match in re.finditer(pattern, text):
            company_name = match.group(1).strip()
            company_name = re.sub(r'[,;.]+$', '', company_name)

            if len(company_name) < 3:
                continue

            # Extract context
            start = max(0, match.start() - context_window // 2)
            end = min(len(text), match.end() + context_window // 2)
            context = text[start:end].strip()

            # Base confidence
            confidence = 0.5

            # Boost if has company suffix
            name_lower = company_name.lower()
            for suffix in self.COMPANY_SUFFIXES | self.WEB3_SUFFIXES:
                if name_lower.endswith(suffix):
                    confidence = 0.75
                    break

            companies.append(CompanyMention(
                name=company_name,
                source='conversation',
                confidence=confidence,
                context=context
            ))

        return self._deduplicate_mentions(companies)

    def extract_all_sources(
        self,
        title: Optional[str] = None,
        bio: Optional[str] = None,
        email: Optional[str] = None,
        conversation: Optional[str] = None
    ) -> List[CompanyMention]:
        """
        Extract companies from all available sources and merge results.

        Returns deduplicated list sorted by confidence.
        """
        all_mentions = []

        if title:
            all_mentions.extend(self.extract_from_title(title))

        if bio:
            all_mentions.extend(self.extract_from_bio(bio))

        if email:
            email_mention = self.extract_from_email(email)
            if email_mention:
                all_mentions.append(email_mention)

        if conversation:
            all_mentions.extend(self.extract_from_conversation(conversation))

        # Merge mentions of same company from different sources
        merged = self._merge_mentions(all_mentions)

        # Sort by confidence descending
        merged.sort(key=lambda m: m.confidence, reverse=True)

        return merged

    def _deduplicate_mentions(self, mentions: List[CompanyMention]) -> List[CompanyMention]:
        """Remove duplicate mentions from same source."""
        seen = {}
        for mention in mentions:
            key = mention.name.lower()
            if key not in seen or mention.confidence > seen[key].confidence:
                seen[key] = mention
        return list(seen.values())

    def _merge_mentions(self, mentions: List[CompanyMention]) -> List[CompanyMention]:
        """
        Merge mentions of the same company from different sources.

        Takes highest confidence and combines sources.
        """
        grouped = {}

        for mention in mentions:
            key = mention.name.lower()

            if key not in grouped:
                grouped[key] = mention
            else:
                existing = grouped[key]

                # Use highest confidence
                if mention.confidence > existing.confidence:
                    grouped[key] = mention

                # Combine sources
                if mention.source not in existing.source:
                    existing.source = f"{existing.source},{mention.source}"

                # Keep domain if available
                if mention.domain and not existing.domain:
                    existing.domain = mention.domain

        return list(grouped.values())

    def _domain_to_company_name(self, extracted) -> str:
        """
        Convert domain parts to company name.

        Examples:
        - acmecorp.com → Acme Corp
        - protocol.labs → Protocol Labs
        - blockchain.io → Blockchain
        """
        domain = extracted.domain

        # Split on common separators
        parts = re.split(r'[-_]', domain)

        # Capitalize each part
        capitalized = [p.capitalize() for p in parts]

        # Join with space
        company_name = ' '.join(capitalized)

        return company_name


def main():
    """CLI entry point for company extraction."""
    import sys
    import json

    if len(sys.argv) < 3:
        print("Usage: company_extractor.py <source> <text>")
        print("\nSources:")
        print("  title <title>         - Extract from title")
        print("  bio <bio>             - Extract from bio")
        print("  email <email>         - Extract from email")
        print("  conversation <text>   - Extract from conversation")
        print("  all --title='...' --bio='...' --email='...' --conversation='...'")
        sys.exit(1)

    source = sys.argv[1]
    extractor = CompanyExtractor()

    if source == 'title':
        title = ' '.join(sys.argv[2:])
        mentions = extractor.extract_from_title(title)
    elif source == 'bio':
        bio = ' '.join(sys.argv[2:])
        mentions = extractor.extract_from_bio(bio)
    elif source == 'email':
        email = sys.argv[2]
        mention = extractor.extract_from_email(email)
        mentions = [mention] if mention else []
    elif source == 'conversation':
        text = ' '.join(sys.argv[2:])
        mentions = extractor.extract_from_conversation(text)
    elif source == 'all':
        # Parse named arguments
        args = {}
        for arg in sys.argv[2:]:
            if arg.startswith('--'):
                key, val = arg[2:].split('=', 1)
                args[key] = val

        mentions = extractor.extract_all_sources(
            title=args.get('title'),
            bio=args.get('bio'),
            email=args.get('email'),
            conversation=args.get('conversation')
        )
    else:
        print(f"Unknown source: {source}")
        sys.exit(1)

    # Output as JSON
    print(json.dumps([
        {
            'name': m.name,
            'source': m.source,
            'confidence': round(m.confidence, 2),
            'context': m.context,
            'domain': m.domain
        }
        for m in mentions
    ], indent=2))


if __name__ == '__main__':
    main()
