#!/usr/bin/env python3
"""
Entity extractor for CRM module.

Extracts people, companies, projects, and events from research documents
and literature notes.

Enhanced with:
- Multi-source company extraction (title, bio, email, conversation)
- Email filtering (non-person email detection)
- Domain-based categorization
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import yaml

# Import enrichment modules
try:
    from .company_extractor import CompanyExtractor
    from .email_filter import EmailFilter
    from .domain_categorizer import DomainCategorizer
except ImportError:
    # Fallback for direct execution
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from company_extractor import CompanyExtractor
    from email_filter import EmailFilter
    from domain_categorizer import DomainCategorizer


@dataclass
class ExtractedEntity:
    """An entity extracted from text."""
    name: str
    entity_type: str  # person | company | project | event
    confidence: float  # 0.0 - 1.0
    context: str
    source_line: int
    suggested_industries: List[str] = field(default_factory=list)
    suggested_organization: Optional[str] = None
    suggested_role: Optional[str] = None
    suggested_parent: Optional[str] = None
    existing_match: Optional[str] = None
    possible_match: Optional[str] = None
    # Enhanced fields
    email: Optional[str] = None
    domain_category: Optional[str] = None  # investor | crypto | enterprise | startup
    extracted_from_sources: List[str] = field(default_factory=list)  # title, bio, email, conversation


@dataclass
class ExtractionResult:
    """Result of entity extraction."""
    source_file: str
    entities: List[ExtractedEntity]
    total_extracted: int = 0
    high_confidence: int = 0
    medium_confidence: int = 0
    low_confidence: int = 0
    existing_matches: int = 0
    new_entities: int = 0
    created_drafts: int = 0


class EntityExtractor:
    """Extracts entities from text documents."""

    # Company suffixes
    COMPANY_SUFFIXES = [
        'Inc', 'Corp', 'Corporation', 'Ltd', 'Limited', 'GmbH',
        'Labs', 'Protocol', 'Foundation', 'Network', 'DAO',
        'Technologies', 'Ventures', 'Capital'
    ]

    # Role keywords for person detection
    ROLE_KEYWORDS = [
        'CEO', 'CTO', 'CFO', 'COO', 'CMO', 'CPO',
        'Founder', 'Co-founder', 'Co-Founder',
        'President', 'Director', 'VP', 'Vice President',
        'Head of', 'Lead', 'Manager', 'Partner'
    ]

    # Project type keywords
    PROJECT_KEYWORDS = [
        'protocol', 'platform', 'network', 'chain', 'token',
        'blockchain', 'mainnet', 'testnet', 'DAO', 'dApp'
    ]

    # Event keywords
    EVENT_KEYWORDS = [
        'conference', 'summit', 'meetup', 'hackathon',
        'workshop', 'symposium', 'expo', 'week'
    ]

    # Industry keyword mappings
    INDUSTRY_KEYWORDS = {
        'storage': ['storage', 'ipfs', 'filecoin', 'arweave', 'backup'],
        'defi': ['defi', 'swap', 'liquidity', 'lending', 'yield', 'amm'],
        'nft': ['nft', 'marketplace', 'collectible', 'art'],
        'web3': ['web3', 'decentralized', 'blockchain', 'crypto'],
        'ai_ml': ['ai', 'ml', 'machine learning', 'artificial intelligence', 'llm'],
        'identity': ['identity', 'did', 'credential', 'verification', 'ssi'],
        'privacy': ['privacy', 'zero knowledge', 'zk', 'encryption'],
        'rwa': ['rwa', 'real world asset', 'tokenization', 'real estate'],
        'data_infrastructure': ['data', 'infrastructure', 'api', 'indexing'],
    }

    def __init__(self, contacts_index: Optional[Dict] = None):
        """Initialize extractor with optional contacts index for dedup."""
        self.contacts_index = contacts_index or {}
        # Initialize enrichment modules
        self.company_extractor = CompanyExtractor()
        self.email_filter = EmailFilter()
        self.domain_categorizer = DomainCategorizer()

    def extract_person_with_context(
        self,
        name: str,
        email: Optional[str] = None,
        title: Optional[str] = None,
        bio: Optional[str] = None,
        context: Optional[str] = None
    ) -> ExtractedEntity:
        """
        Extract person entity with enhanced company extraction and categorization.

        This method uses the enrichment pipeline:
        1. Filter non-person emails
        2. Extract companies from title, bio, email domain
        3. Categorize domain (investor, crypto, enterprise, startup)
        4. Suggest industries based on all context
        """
        # Filter email
        if email and not self.email_filter.is_person_email(email):
            # Return None or raise exception for non-person email
            return None

        # Extract companies from multiple sources
        company_mentions = self.company_extractor.extract_all_sources(
            title=title,
            bio=bio,
            email=email,
            conversation=context
        )

        # Get organization (highest confidence company)
        suggested_org = None
        if company_mentions:
            top_company = company_mentions[0]  # Already sorted by confidence
            suggested_org = f"[[{top_company.name}]]"

        # Categorize domain
        domain_category = None
        if email:
            cat_context = {'title': title or '', 'bio': bio or ''}
            category = self.domain_categorizer.categorize(email, cat_context)
            domain_category = category.primary

        # Extract role from title
        suggested_role = None
        if title:
            for role_kw in self.ROLE_KEYWORDS:
                if role_kw.lower() in title.lower():
                    suggested_role = role_kw
                    break

        # Suggest industries from all context
        all_context = ' '.join(filter(None, [title or '', bio or '', context or '']))
        industries = self._suggest_industries(all_context)

        # Add domain category as industry if relevant
        if domain_category and domain_category != 'unknown':
            if domain_category not in industries:
                industries.insert(0, domain_category)

        return ExtractedEntity(
            name=name,
            entity_type='person',
            confidence=0.9,
            context=all_context[:200],  # Truncate for storage
            source_line=0,
            suggested_industries=industries,
            suggested_organization=suggested_org,
            suggested_role=suggested_role,
            email=email,
            domain_category=domain_category,
            extracted_from_sources=[s.source for s in company_mentions]
        )

    def extract_from_file(self, file_path: Path) -> ExtractionResult:
        """Extract entities from a file."""
        content = file_path.read_text()

        # Skip frontmatter
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                content = parts[2]

        lines = content.split('\n')
        entities = []

        for line_num, line in enumerate(lines, 1):
            # Skip empty lines and headers
            if not line.strip() or line.startswith('#'):
                continue

            # Extract entities from this line
            line_entities = self._extract_from_line(line, line_num)
            entities.extend(line_entities)

        # Deduplicate by name
        entities = self._deduplicate_entities(entities)

        # Check against existing contacts
        entities = self._check_existing(entities)

        # Calculate summary stats
        result = ExtractionResult(
            source_file=str(file_path),
            entities=entities,
            total_extracted=len(entities),
            high_confidence=len([e for e in entities if e.confidence > 0.8]),
            medium_confidence=len([e for e in entities if 0.5 <= e.confidence <= 0.8]),
            low_confidence=len([e for e in entities if e.confidence < 0.5]),
            existing_matches=len([e for e in entities if e.existing_match]),
            new_entities=len([e for e in entities if not e.existing_match])
        )

        return result

    def _extract_from_line(self, line: str, line_num: int) -> List[ExtractedEntity]:
        """Extract entities from a single line."""
        entities = []

        # Extract companies
        entities.extend(self._extract_companies(line, line_num))

        # Extract people
        entities.extend(self._extract_people(line, line_num))

        # Extract projects
        entities.extend(self._extract_projects(line, line_num))

        # Extract events
        entities.extend(self._extract_events(line, line_num))

        return entities

    def _extract_companies(self, line: str, line_num: int) -> List[ExtractedEntity]:
        """Extract company names from text using multi-source extraction."""
        entities = []

        # Use enhanced company extractor for conversation patterns
        company_mentions = self.company_extractor.extract_from_conversation(line)

        for mention in company_mentions:
            context = mention.context or self._extract_context(line, 0)
            industries = self._suggest_industries(context)

            entities.append(ExtractedEntity(
                name=mention.name,
                entity_type='company',
                confidence=mention.confidence,
                context=context,
                source_line=line_num,
                suggested_industries=industries,
                extracted_from_sources=['conversation']
            ))

        # Keep legacy suffix pattern for backward compatibility
        suffix_pattern = r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s+(' + '|'.join(self.COMPANY_SUFFIXES) + r')\b'
        for match in re.finditer(suffix_pattern, line):
            name = f"{match.group(1)} {match.group(2)}"
            # Check if already extracted
            if any(e.name.lower() == name.lower() for e in entities):
                continue

            context = self._extract_context(line, match.start())
            industries = self._suggest_industries(context)

            entities.append(ExtractedEntity(
                name=name,
                entity_type='company',
                confidence=0.9,
                context=context,
                source_line=line_num,
                suggested_industries=industries,
                extracted_from_sources=['pattern']
            ))

        return entities

    def _extract_people(self, line: str, line_num: int) -> List[ExtractedEntity]:
        """Extract person names from text."""
        entities = []

        # Pattern: Role + Name
        for role in self.ROLE_KEYWORDS:
            pattern = rf'\b{role}\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)'
            for match in re.finditer(pattern, line):
                name = match.group(1)
                context = self._extract_context(line, match.start())

                # Try to extract company
                company_match = re.search(r'(?:at|of|from)\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)', context)
                organization = f"[[{company_match.group(1)}]]" if company_match else None

                entities.append(ExtractedEntity(
                    name=name,
                    entity_type='person',
                    confidence=0.85,
                    context=context,
                    source_line=line_num,
                    suggested_role=role,
                    suggested_organization=organization
                ))

        # Pattern: Name, Role at Company
        name_role_pattern = r'\b([A-Z][a-z]+\s+[A-Z][a-z]+),\s+(\w+(?:\s+\w+)*)\s+(?:at|of)\s+([A-Z][a-zA-Z]*)'
        for match in re.finditer(name_role_pattern, line):
            name = match.group(1)
            role = match.group(2)
            company = match.group(3)
            context = self._extract_context(line, match.start())

            entities.append(ExtractedEntity(
                name=name,
                entity_type='person',
                confidence=0.9,
                context=context,
                source_line=line_num,
                suggested_role=role,
                suggested_organization=f"[[{company}]]"
            ))

        return entities

    def _extract_projects(self, line: str, line_num: int) -> List[ExtractedEntity]:
        """Extract project/protocol names from text."""
        entities = []

        # Pattern: Project keyword + Name
        for keyword in self.PROJECT_KEYWORDS:
            pattern = rf'\b([A-Z][a-zA-Z]*)\s+{keyword}\b'
            for match in re.finditer(pattern, line, re.IGNORECASE):
                name = match.group(1)
                context = self._extract_context(line, match.start())
                industries = self._suggest_industries(context)

                entities.append(ExtractedEntity(
                    name=name,
                    entity_type='project',
                    confidence=0.8,
                    context=context,
                    source_line=line_num,
                    suggested_industries=industries
                ))

        return entities

    def _extract_events(self, line: str, line_num: int) -> List[ExtractedEntity]:
        """Extract event names from text."""
        entities = []

        # Pattern: Event keyword + Name (+ Year)
        for keyword in self.EVENT_KEYWORDS:
            pattern = rf'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s+{keyword}(?:\s+(\d{{4}}))?\b'
            for match in re.finditer(pattern, line, re.IGNORECASE):
                name = match.group(1)
                year = match.group(2)
                if year:
                    name = f"{name} {keyword.title()} {year}"
                else:
                    name = f"{name} {keyword.title()}"

                context = self._extract_context(line, match.start())
                industries = self._suggest_industries(context)

                entities.append(ExtractedEntity(
                    name=name,
                    entity_type='event',
                    confidence=0.75,
                    context=context,
                    source_line=line_num,
                    suggested_industries=industries
                ))

        return entities

    def _extract_context(self, line: str, position: int, window: int = 100) -> str:
        """Extract surrounding context for an entity."""
        start = max(0, position - window // 2)
        end = min(len(line), position + window // 2)
        context = line[start:end].strip()

        # Clean up partial words at edges
        if start > 0 and not line[start - 1].isspace():
            context = '...' + context.split(' ', 1)[-1] if ' ' in context else context
        if end < len(line) and not line[end].isspace():
            context = context.rsplit(' ', 1)[0] + '...' if ' ' in context else context

        return context

    def _suggest_industries(self, context: str) -> List[str]:
        """Suggest industries based on context keywords."""
        context_lower = context.lower()
        industries = []

        for industry, keywords in self.INDUSTRY_KEYWORDS.items():
            if any(kw in context_lower for kw in keywords):
                industries.append(industry)

        return industries[:3]  # Limit to top 3

    def _deduplicate_entities(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        """Remove duplicate entities, keeping highest confidence."""
        seen = {}
        for entity in entities:
            key = (entity.name.lower(), entity.entity_type)
            if key not in seen or entity.confidence > seen[key].confidence:
                seen[key] = entity
        return list(seen.values())

    def _check_existing(self, entities: List[ExtractedEntity]) -> List[ExtractedEntity]:
        """Check entities against existing contacts."""
        for entity in entities:
            # Exact match
            if entity.name in self.contacts_index:
                entity.existing_match = self.contacts_index[entity.name]
            else:
                # Fuzzy match (simple contains check for now)
                for name, path in self.contacts_index.items():
                    if (entity.name.lower() in name.lower() or
                            name.lower() in entity.name.lower()):
                        entity.possible_match = path
                        break

        return entities


def levenshtein_distance(s1: str, s2: str) -> int:
    """Calculate Levenshtein distance between two strings."""
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def normalize_industry(tag: str) -> str:
    """Normalize industry tag to canonical form."""
    # Lowercase, replace spaces/hyphens with underscores
    normalized = tag.lower().strip()
    normalized = re.sub(r'[\s-]+', '_', normalized)
    return normalized


def main():
    """CLI entry point for entity extraction."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: entity_extractor.py <file_path>")
        sys.exit(1)

    file_path = Path(sys.argv[1])
    if not file_path.exists():
        print(f"File not found: {file_path}")
        sys.exit(1)

    extractor = EntityExtractor()
    result = extractor.extract_from_file(file_path)

    # Output as YAML
    output = {
        'source_file': result.source_file,
        'summary': {
            'total_extracted': result.total_extracted,
            'high_confidence': result.high_confidence,
            'medium_confidence': result.medium_confidence,
            'low_confidence': result.low_confidence,
            'existing_matches': result.existing_matches,
            'new_entities': result.new_entities
        },
        'entities': []
    }

    for entity in result.entities:
        entry = {
            'name': entity.name,
            'type': entity.entity_type,
            'confidence': entity.confidence,
            'context': entity.context,
            'source_line': entity.source_line
        }
        if entity.suggested_industries:
            entry['suggested_industries'] = entity.suggested_industries
        if entity.suggested_organization:
            entry['suggested_organization'] = entity.suggested_organization
        if entity.suggested_role:
            entry['suggested_role'] = entity.suggested_role
        if entity.existing_match:
            entry['existing_match'] = entity.existing_match
        if entity.possible_match:
            entry['possible_match'] = entity.possible_match

        output['entities'].append(entry)

    print(yaml.dump(output, default_flow_style=False, sort_keys=False))


if __name__ == '__main__':
    main()
