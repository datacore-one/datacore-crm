#!/usr/bin/env python3
"""
Entity extractor for CRM module.

Extracts people, companies, projects, and events from research documents
and literature notes.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from datetime import datetime
import yaml


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
        """Extract company names from text."""
        entities = []

        # Pattern: Name + company suffix
        suffix_pattern = r'\b([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*)*)\s+(' + '|'.join(self.COMPANY_SUFFIXES) + r')\b'
        for match in re.finditer(suffix_pattern, line):
            name = f"{match.group(1)} {match.group(2)}"
            context = self._extract_context(line, match.start())
            industries = self._suggest_industries(context)

            entities.append(ExtractedEntity(
                name=name,
                entity_type='company',
                confidence=0.9,
                context=context,
                source_line=line_num,
                suggested_industries=industries
            ))

        # Pattern: "at [Company]" or "from [Company]"
        at_pattern = r'\b(?:at|from|with|by)\s+([A-Z][a-zA-Z]*(?:\s+[A-Z][a-zA-Z]*){0,3})\b'
        for match in re.finditer(at_pattern, line):
            name = match.group(1)
            # Skip if it's a common word
            if name.lower() in ['the', 'this', 'that', 'their', 'there']:
                continue

            context = self._extract_context(line, match.start())
            industries = self._suggest_industries(context)

            entities.append(ExtractedEntity(
                name=name,
                entity_type='company',
                confidence=0.6,
                context=context,
                source_line=line_num,
                suggested_industries=industries
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
