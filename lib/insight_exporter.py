#!/usr/bin/env python3
"""
Insight Exporter - Generate and export relationship insights to PKM.

Creates zettels from relationship database analysis:
- Community discoveries (groups of related contacts)
- Reconnection suggestions
- Relationship patterns
- Network bridge contacts (high betweenness)

Usage:
    from insight_exporter import InsightExporter

    exporter = InsightExporter(db, pkm_path="~/Data/0-personal/notes")
    insights = exporter.generate_all()
    exporter.export_to_pkm(insights)
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any

from relationship_db import RelationshipDB


@dataclass
class Insight:
    """A relationship insight ready for PKM export."""
    id: str
    insight_type: str  # 'community', 'reconnect', 'bridge', 'pattern'
    title: str
    content: str
    related_contacts: List[str]
    tags: List[str]
    created: datetime = None
    exported_to: str = None

    def __post_init__(self):
        if self.created is None:
            self.created = datetime.now()


class InsightExporter:
    """
    Generate and export relationship insights to PKM.
    """

    def __init__(self, db: RelationshipDB, pkm_path: str):
        """
        Initialize exporter.

        Args:
            db: RelationshipDB instance
            pkm_path: Path to PKM notes directory
        """
        self.db = db
        self.pkm_path = Path(pkm_path).expanduser()
        self.zettel_dir = self.pkm_path / "2-knowledge" / "zettel"

    def generate_all(self) -> List[Insight]:
        """Generate all types of insights."""
        insights = []

        insights.extend(self.generate_community_insights())
        insights.extend(self.generate_reconnection_insights())
        insights.extend(self.generate_bridge_insights())
        insights.extend(self.generate_pattern_insights())

        return insights

    def generate_community_insights(self) -> List[Insight]:
        """
        Generate insights about contact communities.

        Identifies meaningful groups based on graph communities.
        """
        insights = []
        communities = self.db.get_communities()

        for comm in communities:
            if comm['member_count'] < 3:
                continue

            # Infer community theme from top domains
            top_domains = comm['top_domains']
            theme = self._infer_theme(top_domains)

            # Get sample contacts
            sample_contacts = self.db.get_all_contacts(
                community_id=comm['community_id'],
                limit=10
            )

            # Build content
            contact_list = "\n".join([
                f"- {c['name'] or c['email']} ({c['email']})"
                for c in sample_contacts
            ])

            content = f"""This community contains {comm['member_count']} contacts who frequently appear together in email threads.

## Top Domains
{', '.join(top_domains[:5])}

## Theme
{theme}

## Key Contacts
{contact_list}

## Analysis
These contacts form a natural cluster in the communication network. Consider:
- Are there untapped collaboration opportunities within this group?
- Should these contacts be introduced to each other?
- Are there key connectors who bridge to other communities?
"""

            insights.append(Insight(
                id=f"community-{comm['community_id']}",
                insight_type='community',
                title=f"Contact Community: {theme}",
                content=content,
                related_contacts=[c['email'] for c in sample_contacts],
                tags=['relationship', 'network', 'community', theme.lower().replace(' ', '-')]
            ))

        return insights

    def generate_reconnection_insights(self) -> List[Insight]:
        """
        Generate insights about contacts to reconnect with.
        """
        insights = []

        # Get reconnection candidates
        candidates = self.db.get_reconnection_candidates(
            silence_days=90,
            min_past_frequency=0.5,
            limit=20
        )

        if not candidates:
            return insights

        # Group by domain/theme
        grouped = {}
        for c in candidates:
            domain = c['domain']
            if domain not in grouped:
                grouped[domain] = []
            grouped[domain].append(c)

        # Create single insight with all candidates
        contact_list = []
        for c in candidates[:15]:
            topics = json.loads(c['topics']) if c['topics'] else []
            topic_str = f" - Topics: {', '.join(topics[:3])}" if topics else ""
            contact_list.append(
                f"- **{c['name'] or c['email']}** ({c['email']})\n"
                f"  Last contact: {c['last_seen']} | Past frequency: {c['frequency_score']:.1f}/month{topic_str}"
            )

        content = f"""These contacts were previously active correspondents but haven't been contacted in 90+ days.

## Reconnection Candidates
{chr(10).join(contact_list)}

## Suggested Actions
1. Review each contact and their last conversation topics
2. Consider reaching out with a genuine update or question
3. Some may no longer be relevant - that's okay to acknowledge
4. Prioritize based on current goals and projects
"""

        insights.append(Insight(
            id="reconnection-batch",
            insight_type='reconnect',
            title="Contacts to Reconnect With",
            content=content,
            related_contacts=[c['email'] for c in candidates[:15]],
            tags=['relationship', 'reconnection', 'action-needed']
        ))

        return insights

    def generate_bridge_insights(self) -> List[Insight]:
        """
        Generate insights about network bridge contacts.

        These are contacts with high betweenness centrality - they connect
        different parts of your network.
        """
        insights = []

        # Get top centrality contacts
        bridges = self.db.get_top_contacts(by='centrality', limit=10)
        bridges = [b for b in bridges if b['betweenness_centrality'] and b['betweenness_centrality'] > 0.01]

        if not bridges:
            return insights

        contact_list = []
        for b in bridges:
            tags = json.loads(b['tags']) if b['tags'] else []
            tag_str = f" [{', '.join(tags)}]" if tags else ""
            contact_list.append(
                f"- **{b['name'] or b['email']}**{tag_str}\n"
                f"  Centrality: {b['betweenness_centrality']:.4f} | Community: {b['community_id']}"
            )

        content = f"""These contacts serve as bridges between different parts of your network.
They connect communities that might otherwise be isolated.

## Bridge Contacts
{chr(10).join(contact_list)}

## What This Means
- These contacts appear in threads with diverse groups of people
- They may be good for introductions across domains
- Losing touch with them could fragment network access
- Consider nurturing these relationships strategically

## Strategic Value
Bridge contacts are often:
- Cross-functional leaders
- Industry connectors
- Partnership facilitators
- Information brokers
"""

        insights.append(Insight(
            id="network-bridges",
            insight_type='bridge',
            title="Network Bridge Contacts",
            content=content,
            related_contacts=[b['email'] for b in bridges],
            tags=['relationship', 'network', 'strategic', 'bridges']
        ))

        return insights

    def generate_pattern_insights(self) -> List[Insight]:
        """
        Generate insights about communication patterns.
        """
        insights = []
        stats = self.db.get_stats()

        # Get one-way contacts
        one_way_sent = self.db.get_one_way_contacts(direction='sent', min_interactions=5, limit=10)
        one_way_received = self.db.get_one_way_contacts(direction='received', min_interactions=10, limit=10)

        # Communication balance insight
        total_sent = stats['total_sent']
        total_received = stats['total_received']
        total = total_sent + total_received

        if total > 0:
            ratio = total_sent / total
            if ratio > 0.6:
                pattern = "You send more than you receive - you're primarily an initiator."
            elif ratio < 0.4:
                pattern = "You receive more than you send - many people reach out to you."
            else:
                pattern = "Your communication is balanced between sending and receiving."

            content = f"""## Overall Communication Pattern
{pattern}

- Total sent: {total_sent:,}
- Total received: {total_received:,}
- Ratio: {ratio:.1%} sent

## One-Way Sent (You initiate, they don't reply much)
"""
            for c in one_way_sent[:5]:
                content += f"- {c['email']}: {c['sent_count']} sent / {c['received_count']} received\n"

            content += "\n## One-Way Received (They send, you don't reply much)\n"
            for c in one_way_received[:5]:
                content += f"- {c['email']}: {c['received_count']} received / {c['sent_count']} sent\n"

            content += """
## Interpretation
- **One-way sent**: May need follow-up, or relationship has cooled
- **One-way received**: Could be newsletters, or opportunities for deeper engagement
"""

            insights.append(Insight(
                id="communication-patterns",
                insight_type='pattern',
                title="Communication Patterns Analysis",
                content=content,
                related_contacts=[],
                tags=['relationship', 'patterns', 'analysis']
            ))

        return insights

    def _infer_theme(self, domains: List[str]) -> str:
        """Infer community theme from domains."""
        # Check for common patterns
        domain_str = ' '.join(domains)

        if 'organization.example.com' in domain_str:
            return "Organization Team"
        elif 'infra.example.org' in domain_str:
            return "Infrastructure Team"
        elif any(x in domain_str for x in ['law', 'legal']):
            return "Legal Contacts"
        elif any(x in domain_str for x in ['.vc', 'capital', 'ventures', 'usv']):
            return "Investors & VCs"
        elif any(x in domain_str for x in ['.edu', 'university', 'research']):
            return "Academic Network"
        elif any(x in domain_str for x in ['gmail', 'yahoo', 'outlook']):
            return "Personal Contacts"
        else:
            # Use first domain as theme
            return f"{domains[0].split('.')[0].title()} Network"

    def export_to_pkm(self, insights: List[Insight], dry_run: bool = False) -> List[str]:
        """
        Export insights as PKM zettels.

        Args:
            insights: List of insights to export
            dry_run: If True, don't write files

        Returns:
            List of created file paths
        """
        created_files = []

        self.zettel_dir.mkdir(parents=True, exist_ok=True)

        for insight in insights:
            # Generate filename
            date_str = insight.created.strftime('%Y%m%d')
            slug = insight.title.lower().replace(' ', '-').replace(':', '')[:50]
            filename = f"{date_str}-{slug}.md"
            filepath = self.zettel_dir / filename

            # Build frontmatter
            frontmatter = f"""---
type: zettel
source: relationship-db
created: {insight.created.strftime('%Y-%m-%d')}
insight_type: {insight.insight_type}
---"""

            # Build content
            content = f"""{frontmatter}

# {insight.title}

{insight.content}

#{"  #".join(insight.tags)}
"""

            if dry_run:
                print(f"Would create: {filepath}")
                print("-" * 40)
                print(content[:500])
                print("..." if len(content) > 500 else "")
            else:
                filepath.write_text(content)
                created_files.append(str(filepath))

                # Update insight in database
                insight.exported_to = str(filepath)

        return created_files


def main():
    """Test insight generation."""
    import argparse

    parser = argparse.ArgumentParser(description="Insight Exporter")
    parser.add_argument('--db', default="~/.datacore/state/relationships.db",
                        help="Database path")
    parser.add_argument('--pkm', default="~/Data/0-personal/notes",
                        help="PKM path")
    parser.add_argument('--dry-run', action='store_true',
                        help="Don't write files")

    args = parser.parse_args()

    db_path = Path(args.db).expanduser()
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        return

    with RelationshipDB(str(db_path)) as db:
        exporter = InsightExporter(db, args.pkm)
        insights = exporter.generate_all()

        print(f"Generated {len(insights)} insights")

        for insight in insights:
            print(f"\n{'=' * 60}")
            print(f"Type: {insight.insight_type}")
            print(f"Title: {insight.title}")
            print(f"Tags: {insight.tags}")
            print(f"Contacts: {len(insight.related_contacts)}")
            print("-" * 60)
            print(insight.content[:300] + "..." if len(insight.content) > 300 else insight.content)

        if not args.dry_run:
            created = exporter.export_to_pkm(insights)
            print(f"\nExported {len(created)} zettels")
            for f in created:
                print(f"  {f}")


if __name__ == "__main__":
    main()
