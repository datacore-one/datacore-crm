#!/usr/bin/env python3
"""
Contact maintainer for CRM module.

Handles deduplication, validation, merging, and industry registry management.
"""

import re
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Set
from datetime import datetime, date
import yaml


@dataclass
class DuplicatePair:
    """A pair of potentially duplicate contacts."""
    contact1: str
    contact2: str
    similarity: float
    same_org: bool
    shared_channels: List[str]
    spaces: List[str]
    recommendation: str  # likely_duplicate | possible_duplicate | review


@dataclass
class ValidationIssue:
    """A validation issue with a contact."""
    contact: str
    issue_type: str  # broken_link | incomplete | stale | invalid
    field: Optional[str]
    details: str


@dataclass
class MergePreview:
    """Preview of a contact merge operation."""
    keep: str
    merge_from: str
    merged_fields: Dict[str, any]
    conflicts: Dict[str, List[str]]
    action_required: bool


@dataclass
class MaintenanceResult:
    """Result of maintenance operation."""
    contacts_scanned: int
    duplicates: List[DuplicatePair]
    validation_issues: List[ValidationIssue]
    merge_previews: List[MergePreview]
    industry_registry_updates: Dict
    actions_taken: List[str]


class IndustryRegistry:
    """Manages the canonical industry registry."""

    def __init__(self, registry_path: Path):
        self.registry_path = registry_path
        self.registry = self._load_registry()

    def _load_registry(self) -> Dict:
        """Load registry from file."""
        if self.registry_path.exists():
            return yaml.safe_load(self.registry_path.read_text()) or {'industries': {}}
        return {'industries': {}}

    def save(self):
        """Save registry to file."""
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.registry_path.write_text(yaml.dump(self.registry, default_flow_style=False))

    def normalize(self, tag: str) -> str:
        """Normalize industry tag to canonical form."""
        normalized = tag.lower().strip()
        normalized = re.sub(r'[\s-]+', '_', normalized)
        return normalized

    def register(self, tag: str) -> Tuple[str, bool]:
        """
        Register an industry tag.

        Returns (canonical_tag, is_new).
        """
        normalized = self.normalize(tag)
        industries = self.registry.get('industries', {})

        # Check exact match
        if normalized in industries:
            industries[normalized]['count'] = industries[normalized].get('count', 0) + 1
            return normalized, False

        # Check aliases
        for canonical, data in industries.items():
            if normalized in data.get('aliases', []):
                data['count'] = data.get('count', 0) + 1
                return canonical, False

        # Check similarity
        similar = self.find_similar(normalized)
        if similar:
            # Don't auto-merge, but add as alias candidate
            return similar, False

        # New industry
        industries[normalized] = {
            'label': tag.replace('_', ' ').title(),
            'aliases': [],
            'count': 1,
            'first_seen': date.today().isoformat()
        }
        self.registry['industries'] = industries
        return normalized, True

    def find_similar(self, tag: str, threshold: int = 3) -> Optional[str]:
        """Find similar industry tag using Levenshtein distance."""
        industries = self.registry.get('industries', {})
        for canonical in industries:
            if levenshtein_distance(tag, canonical) < threshold:
                return canonical
        return None

    def get_potential_merges(self) -> List[Tuple[str, str]]:
        """Find industries that might be duplicates."""
        industries = list(self.registry.get('industries', {}).keys())
        merges = []

        for i, ind1 in enumerate(industries):
            for ind2 in industries[i + 1:]:
                dist = levenshtein_distance(ind1, ind2)
                if dist < 4:  # Slightly higher threshold for suggestions
                    merges.append((ind1, ind2))

        return merges

    def update_counts(self, contacts: List[Dict]) -> Dict[str, int]:
        """Update industry counts from contacts."""
        counts = {}
        for contact in contacts:
            for industry in contact.get('industries', []):
                normalized = self.normalize(industry)
                counts[normalized] = counts.get(normalized, 0) + 1

        # Update registry
        industries = self.registry.get('industries', {})
        for ind, count in counts.items():
            if ind in industries:
                industries[ind]['count'] = count

        return counts


class ContactMaintainer:
    """Maintains contact database quality."""

    REQUIRED_FIELDS = ['name', 'entity_type', 'status']
    ENUM_FIELDS = {
        'entity_type': ['person', 'company', 'project', 'event'],
        'status': ['draft', 'active', 'dormant', 'archived', 'completed'],
        'relationship_status': [
            'discovered', 'lead', 'contacted', 'in_discussion',
            'negotiating', 'active', 'partner', 'customer', 'investor',
            'dormant', 'churned', 'archived'
        ],
    }

    def __init__(self, data_root: Path, registry: IndustryRegistry):
        self.data_root = data_root
        self.registry = registry
        self.contacts = []

    def load_contacts(self, spaces: List[str] = None) -> List[Dict]:
        """Load all contacts from specified spaces."""
        contacts = []

        # Find all contact files
        if spaces:
            space_paths = [self.data_root / s / 'contacts' for s in spaces]
        else:
            space_paths = list(self.data_root.glob('*/contacts'))

        for space_path in space_paths:
            if not space_path.exists():
                continue

            for contact_file in space_path.rglob('*.md'):
                # Skip index files
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

    def find_duplicates(self) -> List[DuplicatePair]:
        """Find potential duplicate contacts."""
        duplicates = []

        for i, c1 in enumerate(self.contacts):
            for c2 in self.contacts[i + 1:]:
                pair = self._check_duplicate(c1, c2)
                if pair:
                    duplicates.append(pair)

        return duplicates

    def _check_duplicate(self, c1: Dict, c2: Dict) -> Optional[DuplicatePair]:
        """Check if two contacts are duplicates."""
        name1 = c1.get('name', '')
        name2 = c2.get('name', '')

        # Skip if different entity types
        if c1.get('entity_type') != c2.get('entity_type'):
            return None

        # Check name similarity
        similarity = 1.0 - (levenshtein_distance(name1.lower(), name2.lower()) /
                           max(len(name1), len(name2), 1))

        if similarity < 0.7:
            return None

        # Check same organization
        same_org = (c1.get('organization') == c2.get('organization') and
                    c1.get('organization') is not None)

        # Check shared channels
        shared = []
        channels1 = c1.get('channels', {})
        channels2 = c2.get('channels', {})
        for channel in ['email', 'linkedin', 'telegram']:
            if (channels1.get(channel) and
                    channels1.get(channel) == channels2.get(channel)):
                shared.append(channel)

        # Determine recommendation
        if similarity > 0.95 or shared:
            recommendation = 'likely_duplicate'
        elif similarity > 0.85 or same_org:
            recommendation = 'possible_duplicate'
        else:
            recommendation = 'review'

        return DuplicatePair(
            contact1=name1,
            contact2=name2,
            similarity=round(similarity, 2),
            same_org=same_org,
            shared_channels=shared,
            spaces=[c1.get('_space', ''), c2.get('_space', '')],
            recommendation=recommendation
        )

    def validate_contacts(self) -> List[ValidationIssue]:
        """Validate all contacts for data quality issues."""
        issues = []

        for contact in self.contacts:
            name = contact.get('name', 'Unknown')

            # Check required fields
            for field in self.REQUIRED_FIELDS:
                if not contact.get(field):
                    issues.append(ValidationIssue(
                        contact=name,
                        issue_type='incomplete',
                        field=field,
                        details=f"Missing required field: {field}"
                    ))

            # Check enum fields
            for field, valid_values in self.ENUM_FIELDS.items():
                value = contact.get(field)
                if value and value not in valid_values:
                    issues.append(ValidationIssue(
                        contact=name,
                        issue_type='invalid',
                        field=field,
                        details=f"Invalid value '{value}' for {field}"
                    ))

            # Check stale contacts
            last_interaction = contact.get('last_interaction')
            if last_interaction:
                try:
                    if isinstance(last_interaction, str):
                        last_date = datetime.strptime(last_interaction, '%Y-%m-%d').date()
                    else:
                        last_date = last_interaction
                    days_since = (date.today() - last_date).days
                    if days_since > 180:
                        issues.append(ValidationIssue(
                            contact=name,
                            issue_type='stale',
                            field='last_interaction',
                            details=f"{days_since} days since last interaction"
                        ))
                except (ValueError, TypeError):
                    pass

            # Check wiki-links (basic check)
            org = contact.get('organization', '')
            if org and '[[' in org:
                # Extract link target
                match = re.search(r'\[\[([^\]]+)\]\]', org)
                if match:
                    link_target = match.group(1)
                    # Check if target exists (simplified)
                    # In production, would check actual file existence
                    pass

        return issues

    def generate_merge_preview(self, dup: DuplicatePair) -> MergePreview:
        """Generate a merge preview for a duplicate pair."""
        # Find the actual contact data
        c1 = next((c for c in self.contacts if c.get('name') == dup.contact1), {})
        c2 = next((c for c in self.contacts if c.get('name') == dup.contact2), {})

        # Determine which to keep (newer updated date)
        updated1 = c1.get('updated', '')
        updated2 = c2.get('updated', '')
        if updated1 >= updated2:
            keep, merge_from = c1, c2
            keep_name, merge_name = dup.contact1, dup.contact2
        else:
            keep, merge_from = c2, c1
            keep_name, merge_name = dup.contact2, dup.contact1

        merged_fields = {}
        conflicts = {}

        # Process each field
        for field in set(list(keep.keys()) + list(merge_from.keys())):
            if field.startswith('_'):
                continue

            val_keep = keep.get(field)
            val_merge = merge_from.get(field)

            # Skip if both empty or same
            if val_keep == val_merge:
                continue

            # Non-empty wins over empty
            if not val_keep and val_merge:
                merged_fields[field] = val_merge
            elif val_keep and not val_merge:
                pass  # Keep already has it
            # Both have values - conflict
            elif val_keep != val_merge:
                if isinstance(val_keep, list) and isinstance(val_merge, list):
                    # Merge lists
                    merged = list(set(val_keep + val_merge))
                    if merged != val_keep:
                        merged_fields[field] = merged
                else:
                    conflicts[field] = [val_keep, val_merge]

        return MergePreview(
            keep=keep_name,
            merge_from=merge_name,
            merged_fields=merged_fields,
            conflicts=conflicts,
            action_required=len(conflicts) > 0
        )

    def update_industry_registry(self) -> Dict:
        """Update industry registry from all contacts."""
        new_industries = []
        all_industries = set()

        for contact in self.contacts:
            for industry in contact.get('industries', []):
                all_industries.add(industry)
                canonical, is_new = self.registry.register(industry)
                if is_new:
                    new_industries.append(industry)

        # Update counts
        counts = self.registry.update_counts(self.contacts)

        # Find potential merges
        potential_merges = self.registry.get_potential_merges()

        return {
            'new_industries': new_industries,
            'potential_merges': potential_merges,
            'updated_counts': counts
        }


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


def main():
    """CLI entry point for contact maintenance."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: contact_maintainer.py <data_root> [--scope space1,space2]")
        sys.exit(1)

    data_root = Path(sys.argv[1])
    if not data_root.exists():
        print(f"Data root not found: {data_root}")
        sys.exit(1)

    # Parse scope
    spaces = None
    if '--scope' in sys.argv:
        idx = sys.argv.index('--scope')
        if idx + 1 < len(sys.argv):
            spaces = sys.argv[idx + 1].split(',')

    # Initialize
    registry_path = data_root / '.datacore' / 'state' / 'crm' / 'industries.yaml'
    registry = IndustryRegistry(registry_path)
    maintainer = ContactMaintainer(data_root, registry)

    # Load contacts
    contacts = maintainer.load_contacts(spaces)
    print(f"Loaded {len(contacts)} contacts")

    # Find duplicates
    duplicates = maintainer.find_duplicates()
    print(f"Found {len(duplicates)} potential duplicates")

    # Validate
    issues = maintainer.validate_contacts()
    print(f"Found {len(issues)} validation issues")

    # Update industry registry
    registry_updates = maintainer.update_industry_registry()
    print(f"New industries: {len(registry_updates['new_industries'])}")

    # Generate merge previews for likely duplicates
    merge_previews = []
    for dup in duplicates:
        if dup.recommendation == 'likely_duplicate':
            preview = maintainer.generate_merge_preview(dup)
            merge_previews.append(preview)

    # Output results
    output = {
        'summary': {
            'contacts_scanned': len(contacts),
            'duplicates_found': len(duplicates),
            'validation_issues': len(issues),
            'merge_candidates': len(merge_previews)
        },
        'duplicates': [
            {
                'pair': [d.contact1, d.contact2],
                'similarity': d.similarity,
                'recommendation': d.recommendation
            }
            for d in duplicates
        ],
        'validation_issues': [
            {
                'contact': i.contact,
                'type': i.issue_type,
                'field': i.field,
                'details': i.details
            }
            for i in issues[:20]  # Limit output
        ],
        'industry_registry': registry_updates
    }

    print("\n" + yaml.dump(output, default_flow_style=False, sort_keys=False))

    # Save registry
    registry.save()
    print(f"\nRegistry saved to {registry_path}")


if __name__ == '__main__':
    main()
