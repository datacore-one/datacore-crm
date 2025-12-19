#!/usr/bin/env python3
"""
Industry landscape compiler for CRM module.

Aggregates contacts into strategic landscape views for analysis.
"""

from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set
from datetime import datetime, date
from collections import defaultdict
import yaml


@dataclass
class IndustryStats:
    """Statistics for an industry."""
    name: str
    total_contacts: int = 0
    people: int = 0
    companies: int = 0
    projects: int = 0
    events: int = 0
    active_relationships: int = 0
    competitors: int = 0
    partners: int = 0


@dataclass
class RelationshipStats:
    """Statistics for relationship types."""
    partners: int = 0
    customers: int = 0
    investors: int = 0
    competitors: int = 0
    targets: int = 0
    dormant: int = 0


@dataclass
class LandscapeData:
    """Compiled landscape data."""
    generated: str
    industries: Dict[str, IndustryStats]
    relationships: RelationshipStats
    competitors: List[Dict]
    ecosystem: Dict
    coverage_gaps: List[str]
    entity_counts: Dict[str, int]


class LandscapeCompiler:
    """Compiles contact data into landscape views."""

    def __init__(self, data_root: Path):
        self.data_root = data_root
        self.contacts = []

    def load_contacts(self, spaces: List[str] = None) -> List[Dict]:
        """Load all contacts from specified spaces."""
        contacts = []

        if spaces:
            space_paths = [self.data_root / s / 'contacts' for s in spaces]
        else:
            space_paths = list(self.data_root.glob('*/contacts'))

        for space_path in space_paths:
            if not space_path.exists():
                continue

            for contact_file in space_path.rglob('*.md'):
                if contact_file.name.startswith('_'):
                    continue

                contact = self._load_contact(contact_file)
                if contact:
                    contact['_path'] = str(contact_file)
                    contact['_space'] = space_path.parent.name
                    contacts.append(contact)

        self.contacts = contacts
        return contacts

    def _load_contact(self, path: Path) -> Optional[Dict]:
        """Load contact frontmatter from file."""
        content = path.read_text()
        if not content.startswith('---'):
            return None

        parts = content.split('---', 2)
        if len(parts) < 3:
            return None

        try:
            return yaml.safe_load(parts[1])
        except yaml.YAMLError:
            return None

    def compile(self, spaces: List[str] = None) -> LandscapeData:
        """Compile landscape data from contacts."""
        if not self.contacts:
            self.load_contacts(spaces)

        return LandscapeData(
            generated=datetime.now().isoformat(),
            industries=self._aggregate_by_industry(),
            relationships=self._aggregate_relationships(),
            competitors=self._get_competitors(),
            ecosystem=self._build_ecosystem(),
            coverage_gaps=self._identify_gaps(),
            entity_counts=self._count_entities()
        )

    def _aggregate_by_industry(self) -> Dict[str, IndustryStats]:
        """Aggregate contacts by industry."""
        industries = defaultdict(lambda: IndustryStats(name=''))

        for contact in self.contacts:
            for industry in contact.get('industries', []):
                stats = industries[industry]
                stats.name = industry
                stats.total_contacts += 1

                # Count by entity type
                entity_type = contact.get('entity_type', 'person')
                if entity_type == 'person':
                    stats.people += 1
                elif entity_type == 'company':
                    stats.companies += 1
                elif entity_type == 'project':
                    stats.projects += 1
                elif entity_type == 'event':
                    stats.events += 1

                # Count by relationship
                rel_type = contact.get('relationship_type', '')
                rel_status = contact.get('relationship_status', '')

                if rel_status == 'active':
                    stats.active_relationships += 1
                if rel_type == 'competitor':
                    stats.competitors += 1
                if rel_type == 'partner':
                    stats.partners += 1

        return dict(industries)

    def _aggregate_relationships(self) -> RelationshipStats:
        """Aggregate relationship statistics."""
        stats = RelationshipStats()

        for contact in self.contacts:
            rel_type = contact.get('relationship_type', '')
            rel_status = contact.get('relationship_status', '')

            if rel_type == 'partner':
                stats.partners += 1
            elif rel_type == 'customer':
                stats.customers += 1
            elif rel_type == 'investor':
                stats.investors += 1
            elif rel_type == 'competitor':
                stats.competitors += 1
            elif rel_type and rel_type.startswith('target_'):
                stats.targets += 1

            if rel_status == 'dormant':
                stats.dormant += 1

        return stats

    def _get_competitors(self) -> List[Dict]:
        """Get competitor contacts with details."""
        competitors = []

        for contact in self.contacts:
            if contact.get('relationship_type') == 'competitor':
                competitors.append({
                    'name': contact.get('name'),
                    'entity_type': contact.get('entity_type'),
                    'industries': contact.get('industries', []),
                    'market_position': contact.get('market_position', ''),
                    'relevance': contact.get('relevance', 2),
                    'path': contact.get('_path')
                })

        # Sort by relevance
        competitors.sort(key=lambda x: x.get('relevance', 0), reverse=True)
        return competitors

    def _build_ecosystem(self) -> Dict:
        """Build ecosystem map of partners and vendors."""
        ecosystem = {
            'partners': [],
            'vendors': [],
            'customers': [],
            'investors': []
        }

        for contact in self.contacts:
            rel_type = contact.get('relationship_type', '')
            entry = {
                'name': contact.get('name'),
                'industries': contact.get('industries', []),
                'status': contact.get('relationship_status', '')
            }

            if rel_type == 'partner':
                ecosystem['partners'].append(entry)
            elif rel_type == 'vendor':
                ecosystem['vendors'].append(entry)
            elif rel_type == 'customer':
                ecosystem['customers'].append(entry)
            elif rel_type == 'investor':
                ecosystem['investors'].append(entry)

        return ecosystem

    def _identify_gaps(self) -> List[str]:
        """Identify coverage gaps in the network."""
        gaps = []

        # Check for industries with no partners
        industry_partners = defaultdict(int)
        for contact in self.contacts:
            if contact.get('relationship_type') == 'partner':
                for industry in contact.get('industries', []):
                    industry_partners[industry] += 1

        # Industries we're tracking but have no partners
        all_industries = set()
        for contact in self.contacts:
            all_industries.update(contact.get('industries', []))

        for industry in all_industries:
            if industry_partners.get(industry, 0) == 0:
                gaps.append(f"No partners in {industry}")

        # Check for high-relevance targets not yet contacted
        for contact in self.contacts:
            if (contact.get('relevance', 0) >= 4 and
                    contact.get('relationship_status') == 'discovered'):
                gaps.append(f"High-relevance target not contacted: {contact.get('name')}")

        return gaps[:10]  # Limit to top 10

    def _count_entities(self) -> Dict[str, int]:
        """Count entities by type."""
        counts = defaultdict(int)
        for contact in self.contacts:
            entity_type = contact.get('entity_type', 'unknown')
            counts[entity_type] += 1
        return dict(counts)

    def generate_overview_markdown(self, data: LandscapeData) -> str:
        """Generate markdown overview from landscape data."""
        lines = [
            "# Industry Landscape",
            "",
            f"*Auto-generated: {data.generated[:10]}*",
            "",
            "## Entity Summary",
            "",
            "| Type | Count |",
            "|------|-------|",
        ]

        for entity_type, count in sorted(data.entity_counts.items()):
            lines.append(f"| {entity_type.title()} | {count} |")

        lines.extend([
            "",
            "## Industries",
            "",
            "| Industry | Total | People | Companies | Projects | Competitors | Partners |",
            "|----------|-------|--------|-----------|----------|-------------|----------|",
        ])

        for name, stats in sorted(data.industries.items(), key=lambda x: x[1].total_contacts, reverse=True):
            lines.append(
                f"| {name} | {stats.total_contacts} | {stats.people} | "
                f"{stats.companies} | {stats.projects} | {stats.competitors} | {stats.partners} |"
            )

        lines.extend([
            "",
            "## Relationship Distribution",
            "",
            "| Type | Count |",
            "|------|-------|",
            f"| Partners | {data.relationships.partners} |",
            f"| Customers | {data.relationships.customers} |",
            f"| Investors | {data.relationships.investors} |",
            f"| Competitors | {data.relationships.competitors} |",
            f"| Targets | {data.relationships.targets} |",
            f"| Dormant | {data.relationships.dormant} |",
            "",
            "## Top Competitors",
            "",
            "| Name | Industries | Position | Relevance |",
            "|------|------------|----------|-----------|",
        ])

        for comp in data.competitors[:10]:
            industries = ', '.join(comp.get('industries', [])[:2])
            lines.append(
                f"| [[{comp['name']}]] | {industries} | "
                f"{comp.get('market_position', '-')} | {comp.get('relevance', '-')} |"
            )

        if data.coverage_gaps:
            lines.extend([
                "",
                "## Coverage Gaps",
                "",
            ])
            for gap in data.coverage_gaps:
                lines.append(f"- {gap}")

        lines.extend([
            "",
            "## Ecosystem",
            "",
            f"**Partners:** {len(data.ecosystem.get('partners', []))}",
            f"**Vendors:** {len(data.ecosystem.get('vendors', []))}",
            f"**Customers:** {len(data.ecosystem.get('customers', []))}",
            f"**Investors:** {len(data.ecosystem.get('investors', []))}",
            "",
        ])

        return '\n'.join(lines)


def main():
    """CLI entry point for landscape compilation."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: landscape_compiler.py <data_root> [--output file.md]")
        sys.exit(1)

    data_root = Path(sys.argv[1])
    if not data_root.exists():
        print(f"Data root not found: {data_root}")
        sys.exit(1)

    output_file = None
    if '--output' in sys.argv:
        idx = sys.argv.index('--output')
        if idx + 1 < len(sys.argv):
            output_file = Path(sys.argv[idx + 1])

    compiler = LandscapeCompiler(data_root)
    data = compiler.compile()

    # Generate markdown
    markdown = compiler.generate_overview_markdown(data)

    if output_file:
        output_file.write_text(markdown)
        print(f"Landscape overview written to {output_file}")
    else:
        print(markdown)

    # Print summary
    print(f"\n--- Summary ---")
    print(f"Contacts: {sum(data.entity_counts.values())}")
    print(f"Industries: {len(data.industries)}")
    print(f"Competitors: {len(data.competitors)}")
    print(f"Coverage gaps: {len(data.coverage_gaps)}")


if __name__ == '__main__':
    main()
