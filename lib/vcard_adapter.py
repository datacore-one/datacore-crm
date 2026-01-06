#!/usr/bin/env python3
"""
vCard Import Adapter for CRM module.

Parses vCard (.vcf) files from Gmail and Apple Contacts exports
and converts to CRM contact format.

Usage:
    python vcard_adapter.py import contacts.vcf --space 0-personal
    python vcard_adapter.py import ~/Downloads/*.vcf --dry-run
"""

import re
import base64
from pathlib import Path
from dataclasses import dataclass, field
from datetime import datetime, date
from typing import List, Dict, Optional, Tuple, Any
import yaml

# Import from sibling module
from contact_maintainer import levenshtein_distance


@dataclass
class VCardContact:
    """Parsed vCard contact data."""
    # Identity
    name: str                          # FN field (formatted name)
    first_name: str = ""               # N field, given name
    last_name: str = ""                # N field, family name

    # Channels
    emails: List[Dict[str, str]] = field(default_factory=list)  # [{type, value}]
    phones: List[Dict[str, str]] = field(default_factory=list)  # [{type, value}]

    # Organization
    organization: str = ""             # ORG field
    role: str = ""                     # TITLE field

    # Additional
    addresses: List[Dict[str, str]] = field(default_factory=list)
    urls: List[str] = field(default_factory=list)
    notes: str = ""
    photo_data: Optional[bytes] = None  # Binary photo data
    photo_type: str = ""               # JPEG, PNG, etc.

    # Metadata
    source: str = ""                   # 'gmail' or 'apple'
    source_uid: str = ""               # UID field for dedup
    source_file: str = ""              # Original file path

    # Import tracking
    duplicate_of: str = ""             # Name of duplicate contact if detected
    duplicate_confidence: float = 0.0

    @property
    def primary_email(self) -> str:
        """Get primary email address."""
        if self.emails:
            # Prefer WORK or first
            for e in self.emails:
                if e.get('type', '').upper() in ['WORK', 'PREF']:
                    return e['value']
            return self.emails[0]['value']
        return ""

    @property
    def primary_phone(self) -> str:
        """Get primary phone number."""
        if self.phones:
            for p in self.phones:
                if p.get('type', '').upper() in ['CELL', 'MOBILE', 'PREF']:
                    return p['value']
            return self.phones[0]['value']
        return ""


class VCardParser:
    """Parses vCard 3.0/4.0 files."""

    # vCard field patterns
    FIELD_PATTERN = re.compile(r'^([A-Z0-9-]+)(?:;([^:]*))?\s*:\s*(.*)$', re.IGNORECASE)
    CONTINUATION_PATTERN = re.compile(r'^\s+(.*)$')

    def parse_file(self, file_path: Path) -> List[VCardContact]:
        """Parse a .vcf file containing one or more vCards."""
        contacts = []

        try:
            content = file_path.read_text(encoding='utf-8', errors='replace')
        except Exception as e:
            print(f"Error reading {file_path}: {e}")
            return contacts

        # Split into individual vCards
        vcards = self._split_vcards(content)

        for vcard_text in vcards:
            contact = self._parse_single_vcard(vcard_text)
            if contact:
                contact.source_file = str(file_path)
                contacts.append(contact)

        return contacts

    def _split_vcards(self, content: str) -> List[str]:
        """Split file content into individual vCard blocks."""
        vcards = []
        current = []
        in_vcard = False

        for line in content.split('\n'):
            line = line.rstrip('\r')

            if line.upper().startswith('BEGIN:VCARD'):
                in_vcard = True
                current = [line]
            elif line.upper().startswith('END:VCARD'):
                if in_vcard:
                    current.append(line)
                    vcards.append('\n'.join(current))
                in_vcard = False
                current = []
            elif in_vcard:
                current.append(line)

        return vcards

    def _parse_single_vcard(self, vcard_text: str) -> Optional[VCardContact]:
        """Parse a single vCard block."""
        fields = self._parse_fields(vcard_text)

        # Get formatted name (required)
        fn = fields.get('FN', [])
        if not fn:
            # Try to construct from N field
            n = fields.get('N', [])
            if n:
                parts = n[0].get('value', '').split(';')
                if len(parts) >= 2:
                    fn = [{'value': f"{parts[1]} {parts[0]}".strip()}]

        if not fn:
            return None

        name = fn[0].get('value', '').strip()
        if not name:
            return None

        # Parse N field for first/last name
        first_name = ""
        last_name = ""
        n_field = fields.get('N', [])
        if n_field:
            parts = n_field[0].get('value', '').split(';')
            if len(parts) >= 2:
                last_name = parts[0].strip()
                first_name = parts[1].strip()

        # Parse emails
        emails = []
        for email_field in fields.get('EMAIL', []):
            email_type = self._extract_type(email_field.get('params', ''))
            emails.append({
                'type': email_type,
                'value': email_field.get('value', '').strip()
            })

        # Parse phones
        phones = []
        for tel_field in fields.get('TEL', []):
            tel_type = self._extract_type(tel_field.get('params', ''))
            phones.append({
                'type': tel_type,
                'value': self._normalize_phone(tel_field.get('value', ''))
            })

        # Parse organization
        org = ""
        org_field = fields.get('ORG', [])
        if org_field:
            org = org_field[0].get('value', '').split(';')[0].strip()

        # Parse role/title
        role = ""
        title_field = fields.get('TITLE', [])
        if title_field:
            role = title_field[0].get('value', '').strip()

        # Parse addresses
        addresses = []
        for adr_field in fields.get('ADR', []):
            adr_type = self._extract_type(adr_field.get('params', ''))
            parts = adr_field.get('value', '').split(';')
            if len(parts) >= 6:
                addresses.append({
                    'type': adr_type,
                    'street': parts[2].strip() if len(parts) > 2 else '',
                    'city': parts[3].strip() if len(parts) > 3 else '',
                    'region': parts[4].strip() if len(parts) > 4 else '',
                    'postal': parts[5].strip() if len(parts) > 5 else '',
                    'country': parts[6].strip() if len(parts) > 6 else '',
                })

        # Parse URLs
        urls = []
        for url_field in fields.get('URL', []):
            url = url_field.get('value', '').strip()
            if url:
                urls.append(url)

        # Parse notes
        notes = ""
        note_field = fields.get('NOTE', [])
        if note_field:
            notes = note_field[0].get('value', '').replace('\\n', '\n').strip()

        # Parse photo
        photo_data = None
        photo_type = ""
        photo_field = fields.get('PHOTO', [])
        if photo_field:
            photo_data, photo_type = self._extract_photo(photo_field[0])

        # Parse UID
        uid = ""
        uid_field = fields.get('UID', [])
        if uid_field:
            uid = uid_field[0].get('value', '').strip()

        # Detect source
        source = self._detect_source(fields)

        return VCardContact(
            name=name,
            first_name=first_name,
            last_name=last_name,
            emails=emails,
            phones=phones,
            organization=org,
            role=role,
            addresses=addresses,
            urls=urls,
            notes=notes,
            photo_data=photo_data,
            photo_type=photo_type,
            source=source,
            source_uid=uid,
        )

    def _parse_fields(self, vcard_text: str) -> Dict[str, List[Dict]]:
        """Parse vCard text into field dictionary."""
        fields = {}
        lines = vcard_text.split('\n')
        i = 0

        while i < len(lines):
            line = lines[i].rstrip('\r')

            # Handle line continuation (folded lines)
            while i + 1 < len(lines):
                next_line = lines[i + 1]
                if next_line.startswith(' ') or next_line.startswith('\t'):
                    line += next_line[1:]
                    i += 1
                else:
                    break

            # Parse field
            match = self.FIELD_PATTERN.match(line)
            if match:
                field_name = match.group(1).upper()
                params = match.group(2) or ''
                value = match.group(3)

                if field_name not in fields:
                    fields[field_name] = []

                fields[field_name].append({
                    'params': params,
                    'value': value
                })

            i += 1

        return fields

    def _extract_type(self, params: str) -> str:
        """Extract TYPE parameter from vCard params."""
        if not params:
            return ""

        # Handle TYPE=value format
        type_match = re.search(r'TYPE=([^;,]+)', params, re.IGNORECASE)
        if type_match:
            return type_match.group(1).upper()

        # Handle bare type values (e.g., WORK;VOICE)
        known_types = ['WORK', 'HOME', 'CELL', 'MOBILE', 'FAX', 'PREF', 'VOICE', 'INTERNET']
        for t in known_types:
            if t in params.upper():
                return t

        return ""

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone number for storage and comparison."""
        # Remove common formatting
        normalized = re.sub(r'[\s\-\.\(\)]', '', phone)
        return normalized

    def _extract_photo(self, photo_field: Dict) -> Tuple[Optional[bytes], str]:
        """Extract and decode photo data from PHOTO field."""
        params = photo_field.get('params', '')
        value = photo_field.get('value', '')

        if not value:
            return None, ""

        # Determine encoding and type
        photo_type = ""
        if 'JPEG' in params.upper() or 'JPG' in params.upper():
            photo_type = 'jpg'
        elif 'PNG' in params.upper():
            photo_type = 'png'
        elif 'GIF' in params.upper():
            photo_type = 'gif'
        else:
            photo_type = 'jpg'  # Default assumption

        # Handle base64 encoding
        if 'ENCODING=B' in params.upper() or 'BASE64' in params.upper() or 'ENCODING=BASE64' in params.upper():
            try:
                photo_data = base64.b64decode(value)
                return photo_data, photo_type
            except Exception:
                return None, ""

        # Handle URI reference (not supported for now)
        if value.startswith('http'):
            return None, ""

        return None, ""

    def _detect_source(self, fields: Dict) -> str:
        """Detect if vCard is from Gmail or Apple Contacts."""
        # Check PRODID
        prodid = fields.get('PRODID', [])
        if prodid:
            prodid_value = prodid[0].get('value', '').lower()
            if 'google' in prodid_value:
                return 'gmail'
            elif 'apple' in prodid_value or 'addressbook' in prodid_value:
                return 'apple'

        # Check X-ABLabel (Apple specific)
        if 'X-ABLABEL' in fields or 'X-ABADR' in fields:
            return 'apple'

        # Check for Google-specific fields
        if any(f.startswith('X-GOOGLE') for f in fields):
            return 'gmail'

        return 'unknown'


class VCardDeduplicator:
    """Handles deduplication across vCard sources and existing contacts."""

    def __init__(self, existing_contacts: List[Dict] = None):
        self.existing_contacts = existing_contacts or []
        self.email_index: Dict[str, str] = {}  # email -> contact name
        self.phone_index: Dict[str, str] = {}  # normalized phone -> contact name
        self.name_org_index: Dict[str, str] = {}  # "name|org" -> contact name
        self.all_names: List[str] = []

        # Build index from existing contacts
        self._build_existing_index()

    def _build_existing_index(self):
        """Build dedup index from existing contacts."""
        for contact in self.existing_contacts:
            name = contact.get('name', '')
            if not name:
                continue

            self.all_names.append(name)

            # Index emails
            channels = contact.get('channels', {})
            email = channels.get('email', '')
            if email:
                self.email_index[email.lower()] = name

            # Index phones
            phone = channels.get('phone', '')
            if phone:
                normalized = self._normalize_phone(phone)
                if normalized:
                    self.phone_index[normalized] = name

            # Index name + org
            org = contact.get('organization', '')
            if org:
                # Remove wiki-link markup
                org_clean = re.sub(r'\[\[([^\]]+)\]\]', r'\1', org)
                key = f"{name.lower()}|{org_clean.lower()}"
                self.name_org_index[key] = name

    def _normalize_phone(self, phone: str) -> str:
        """Normalize phone for comparison."""
        return re.sub(r'[\s\-\.\(\)+]', '', phone)

    def build_index(self, contacts: List[VCardContact]) -> None:
        """Build dedup index from vCard contact list."""
        for contact in contacts:
            self.all_names.append(contact.name)

            # Index emails
            for email in contact.emails:
                email_val = email.get('value', '').lower()
                if email_val and email_val not in self.email_index:
                    self.email_index[email_val] = contact.name

            # Index phones
            for phone in contact.phones:
                normalized = self._normalize_phone(phone.get('value', ''))
                if normalized and normalized not in self.phone_index:
                    self.phone_index[normalized] = contact.name

            # Index name + org
            if contact.organization:
                key = f"{contact.name.lower()}|{contact.organization.lower()}"
                if key not in self.name_org_index:
                    self.name_org_index[key] = contact.name

    def check_duplicate(self, contact: VCardContact) -> Optional[Tuple[str, float]]:
        """
        Check if contact is duplicate.

        Returns (match_name, confidence) or None.
        """
        # Stage 1: Exact email match (confidence: 1.0)
        for email in contact.emails:
            email_val = email.get('value', '').lower()
            if email_val in self.email_index:
                match_name = self.email_index[email_val]
                if match_name != contact.name:  # Don't match self
                    return (match_name, 1.0)

        # Stage 2: Phone number match (confidence: 0.95)
        for phone in contact.phones:
            normalized = self._normalize_phone(phone.get('value', ''))
            if normalized in self.phone_index:
                match_name = self.phone_index[normalized]
                if match_name != contact.name:
                    return (match_name, 0.95)

        # Stage 3: Name + organization match (confidence: 0.85)
        if contact.organization:
            key = f"{contact.name.lower()}|{contact.organization.lower()}"
            if key in self.name_org_index:
                match_name = self.name_org_index[key]
                if match_name != contact.name:
                    return (match_name, 0.85)

        # Stage 4: Fuzzy name match (confidence: 0.7)
        for existing_name in self.all_names:
            if existing_name == contact.name:
                continue

            # Calculate similarity
            max_len = max(len(contact.name), len(existing_name))
            if max_len == 0:
                continue

            distance = levenshtein_distance(contact.name.lower(), existing_name.lower())
            similarity = 1.0 - (distance / max_len)

            if similarity > 0.85:
                return (existing_name, 0.7 * similarity)

        return None

    def find_merge_candidates(self, contacts: List[VCardContact]) -> List[Dict]:
        """Find pairs that should be merged."""
        candidates = []
        seen_pairs = set()

        for i, c1 in enumerate(contacts):
            for c2 in contacts[i + 1:]:
                pair_key = tuple(sorted([c1.name, c2.name]))
                if pair_key in seen_pairs:
                    continue

                # Check if they're duplicates
                self.build_index([c1])
                dup = self.check_duplicate(c2)

                if dup and dup[0] == c1.name:
                    seen_pairs.add(pair_key)
                    candidates.append({
                        'contact1': c1.name,
                        'contact2': c2.name,
                        'source1': c1.source,
                        'source2': c2.source,
                        'confidence': dup[1],
                        'reason': self._get_match_reason(dup[1])
                    })

        return candidates

    def _get_match_reason(self, confidence: float) -> str:
        """Get human-readable match reason from confidence."""
        if confidence >= 1.0:
            return "email match"
        elif confidence >= 0.95:
            return "phone match"
        elif confidence >= 0.85:
            return "name + organization match"
        else:
            return "fuzzy name match"


@dataclass
class ImportReport:
    """Report from vCard import operation."""
    total_parsed: int = 0
    new_contacts: int = 0
    duplicates_skipped: int = 0
    duplicates_within_import: int = 0
    photos_imported: int = 0
    errors: List[str] = field(default_factory=list)
    created_files: List[str] = field(default_factory=list)
    duplicate_pairs: List[Dict] = field(default_factory=list)
    by_source: Dict[str, int] = field(default_factory=dict)


class VCardImporter:
    """Orchestrates vCard import to CRM."""

    def __init__(self, data_root: Path, space: str = '0-personal'):
        self.data_root = data_root
        self.space = space
        self.contacts_dir = data_root / space / 'contacts' / 'people'
        self.photos_dir = self.contacts_dir / '.photos'

    def import_vcards(
        self,
        files: List[Path],
        dry_run: bool = False,
        skip_existing: bool = True
    ) -> ImportReport:
        """
        Import vCard files to CRM.

        Args:
            files: List of vCard files to import
            dry_run: Preview without creating files
            skip_existing: Skip contacts that already exist

        Returns:
            ImportReport with counts and details
        """
        report = ImportReport()
        parser = VCardParser()

        # Load existing contacts for dedup
        existing = self._load_existing_contacts() if skip_existing else []
        deduplicator = VCardDeduplicator(existing)

        # Parse all vCards
        all_contacts = []
        for file_path in files:
            try:
                contacts = parser.parse_file(file_path)
                all_contacts.extend(contacts)
                report.total_parsed += len(contacts)
            except Exception as e:
                report.errors.append(f"Error parsing {file_path}: {e}")

        # Build index for cross-source dedup
        deduplicator.build_index(all_contacts)

        # Find duplicates within import
        merge_candidates = deduplicator.find_merge_candidates(all_contacts)
        report.duplicate_pairs = merge_candidates
        report.duplicates_within_import = len(merge_candidates)

        # Track what we've imported (by email/name)
        imported = set()

        for contact in all_contacts:
            # Count by source
            source = contact.source or 'unknown'
            report.by_source[source] = report.by_source.get(source, 0) + 1

            # Check for duplicate against existing
            dup = deduplicator.check_duplicate(contact)
            if dup and skip_existing:
                contact.duplicate_of = dup[0]
                contact.duplicate_confidence = dup[1]
                report.duplicates_skipped += 1
                continue

            # Check if already imported in this batch (by primary email or name)
            key = contact.primary_email.lower() if contact.primary_email else contact.name.lower()
            if key in imported:
                continue
            imported.add(key)

            if not dry_run:
                try:
                    file_path = self._save_contact(contact)
                    report.created_files.append(str(file_path))
                    report.new_contacts += 1

                    if contact.photo_data:
                        self._save_photo(contact)
                        report.photos_imported += 1

                except Exception as e:
                    report.errors.append(f"Error saving {contact.name}: {e}")
            else:
                report.new_contacts += 1
                if contact.photo_data:
                    report.photos_imported += 1

        return report

    def _load_existing_contacts(self) -> List[Dict]:
        """Load existing contacts for deduplication."""
        contacts = []

        if not self.contacts_dir.exists():
            return contacts

        for contact_file in self.contacts_dir.rglob('*.md'):
            if contact_file.name.startswith('_'):
                continue

            try:
                content = contact_file.read_text()
                if not content.startswith('---'):
                    continue

                parts = content.split('---', 2)
                if len(parts) >= 3:
                    frontmatter = yaml.safe_load(parts[1])
                    if frontmatter:
                        contacts.append(frontmatter)
            except Exception:
                pass

        return contacts

    def _save_contact(self, contact: VCardContact) -> Path:
        """Save contact to filesystem."""
        # Ensure directory exists
        self.contacts_dir.mkdir(parents=True, exist_ok=True)

        # Generate safe filename
        safe_name = re.sub(r'[^\w\s-]', '', contact.name)
        safe_name = re.sub(r'\s+', ' ', safe_name).strip()
        file_path = self.contacts_dir / f"{safe_name}.md"

        # Handle name collision
        counter = 1
        while file_path.exists():
            file_path = self.contacts_dir / f"{safe_name} ({counter}).md"
            counter += 1

        # Build frontmatter
        today = date.today().isoformat()

        frontmatter = {
            'type': 'contact',
            'entity_type': 'person',
            'name': contact.name,
            'status': 'draft',
            'relationship_status': 'discovered',
            'relationship_type': '',
            'relevance': 2,
            'privacy': 'personal',
            'space': self.space,
            'organization': f"[[{contact.organization}]]" if contact.organization else '',
            'role': contact.role,
            'industries': [],
            'channels': {
                'email': contact.primary_email,
                'telegram': '',
                'linkedin': self._extract_linkedin(contact.urls),
                'phone': contact.primary_phone,
            },
            'location': self._format_location(contact.addresses),
            'introduced_by': '',
            'met_at': '',
            'discovered_in': f"vCard import ({contact.source})",
            'import_source': contact.source,
            'import_date': today,
            'created': today,
            'updated': today,
            'last_interaction': '',
        }

        # Add photo reference if available
        if contact.photo_data:
            frontmatter['photo'] = f".photos/{safe_name}.{contact.photo_type}"

        # Build content
        content = "---\n"
        content += yaml.dump(frontmatter, default_flow_style=False, allow_unicode=True, sort_keys=False)
        content += "---\n\n"
        content += f"# {contact.name}\n\n"
        content += "## Overview\n\n"
        if contact.organization:
            content += f"{contact.role} at {contact.organization}\n\n" if contact.role else f"At {contact.organization}\n\n"
        content += "**Relevance:** <!-- Why this person matters to you/your work -->\n\n"
        content += "## Goals\n\n"
        content += "**What I want:**\n-\n\n"
        content += "**What they want:**\n-\n\n"
        content += "## Notes\n\n"
        if contact.notes:
            content += f"{contact.notes}\n\n"
        content += "## Interaction Log\n\n"
        content += "<!-- Auto-populated by CRM adapters -->\n\n"
        content += "| Date | Channel | Type | Summary |\n"
        content += "|------|---------|------|---------|"
        content += f"\n| {today} | import | - | Imported from {contact.source} vCard |\n\n"
        content += "## Next Actions\n\n"
        content += "<!-- Embedded from next_actions.org with :CRM: tag and :CONTACT: property -->\n\n"
        content += "## Related\n\n"
        if contact.organization:
            content += f"- [[{contact.organization}]]\n"
        content += "\n"

        file_path.write_text(content)
        return file_path

    def _save_photo(self, contact: VCardContact) -> Optional[Path]:
        """Save contact photo."""
        if not contact.photo_data:
            return None

        self.photos_dir.mkdir(parents=True, exist_ok=True)

        safe_name = re.sub(r'[^\w\s-]', '', contact.name)
        safe_name = re.sub(r'\s+', ' ', safe_name).strip()
        photo_path = self.photos_dir / f"{safe_name}.{contact.photo_type}"

        photo_path.write_bytes(contact.photo_data)
        return photo_path

    def _extract_linkedin(self, urls: List[str]) -> str:
        """Extract LinkedIn URL from URL list."""
        for url in urls:
            if 'linkedin.com' in url.lower():
                return url
        return ""

    def _format_location(self, addresses: List[Dict]) -> str:
        """Format location from addresses."""
        if not addresses:
            return ""

        # Prefer WORK or first
        addr = addresses[0]
        for a in addresses:
            if a.get('type', '').upper() == 'WORK':
                addr = a
                break

        parts = []
        if addr.get('city'):
            parts.append(addr['city'])
        if addr.get('country'):
            parts.append(addr['country'])

        return ', '.join(parts)

    def generate_report_markdown(self, report: ImportReport) -> str:
        """Generate Markdown import report."""
        today = datetime.now().strftime('%Y-%m-%d %H:%M')

        md = f"""---
type: report
title: Contact Import Report
date: {date.today().isoformat()}
---

# Contact Import Report

**Date:** {today}
**Space:** {self.space}

## Summary

| Metric | Count |
|--------|-------|
| Total parsed | {report.total_parsed} |
| New contacts created | {report.new_contacts} |
| Duplicates skipped | {report.duplicates_skipped} |
| Duplicates within import | {report.duplicates_within_import} |
| Photos imported | {report.photos_imported} |
| Errors | {len(report.errors)} |

## Contacts by Source

| Source | Count |
|--------|-------|
"""
        for source, count in report.by_source.items():
            md += f"| {source.title()} | {count} |\n"

        if report.duplicate_pairs:
            md += "\n## Merge Candidates\n\n"
            md += "These contacts appear in both sources and may need review:\n\n"
            for pair in report.duplicate_pairs:
                md += f"- **{pair['contact1']}** ({pair['source1']}) + **{pair['contact2']}** ({pair['source2']})\n"
                md += f"  - Confidence: {pair['confidence']:.0%} ({pair['reason']})\n"

        if report.errors:
            md += "\n## Errors\n\n"
            for error in report.errors:
                md += f"- {error}\n"

        md += f"\n## Created Contacts\n\n"
        md += f"All contacts created with `status: draft` in:\n"
        md += f"- `{self.space}/contacts/people/`\n\n"
        md += "Run `/crm maintenance --drafts` to review.\n"

        return md


# =============================================================================
# CLI Interface
# =============================================================================

def main():
    """CLI entry point for vCard import."""
    import argparse

    parser = argparse.ArgumentParser(description="vCard Import Adapter")
    parser.add_argument('command', choices=['import', 'parse', 'preview'],
                        help='Command to run')
    parser.add_argument('files', nargs='+', help='vCard files to process')
    parser.add_argument('--space', default='0-personal',
                        help='Target space (default: 0-personal)')
    parser.add_argument('--dry-run', action='store_true',
                        help='Preview without creating files')
    parser.add_argument('--include-existing', action='store_true',
                        help='Import even if contact exists')
    parser.add_argument('--data-root', default=str(Path.home() / 'Data'),
                        help='Data root path')

    args = parser.parse_args()

    data_root = Path(args.data_root)
    files = [Path(f) for f in args.files]

    # Validate files exist
    for f in files:
        if not f.exists():
            print(f"Error: File not found: {f}")
            return 1

    if args.command == 'parse':
        # Just parse and show what's in the files
        parser = VCardParser()
        for file_path in files:
            print(f"\n=== {file_path} ===\n")
            contacts = parser.parse_file(file_path)
            for contact in contacts:
                print(f"  {contact.name}")
                if contact.organization:
                    print(f"    Org: {contact.organization}")
                if contact.primary_email:
                    print(f"    Email: {contact.primary_email}")
                if contact.primary_phone:
                    print(f"    Phone: {contact.primary_phone}")
                print(f"    Source: {contact.source}")
                print()

    elif args.command in ['import', 'preview']:
        dry_run = args.dry_run or args.command == 'preview'

        importer = VCardImporter(data_root, args.space)
        report = importer.import_vcards(
            files,
            dry_run=dry_run,
            skip_existing=not args.include_existing
        )

        print(f"\n{'Preview' if dry_run else 'Import'} Results:")
        print(f"  Total parsed: {report.total_parsed}")
        print(f"  New contacts: {report.new_contacts}")
        print(f"  Duplicates skipped: {report.duplicates_skipped}")
        print(f"  Photos: {report.photos_imported}")

        if report.by_source:
            print(f"\n  By source:")
            for source, count in report.by_source.items():
                print(f"    {source}: {count}")

        if report.duplicate_pairs:
            print(f"\n  Merge candidates ({len(report.duplicate_pairs)}):")
            for pair in report.duplicate_pairs[:5]:
                print(f"    - {pair['contact1']} + {pair['contact2']} ({pair['reason']})")

        if report.errors:
            print(f"\n  Errors:")
            for error in report.errors:
                print(f"    - {error}")

        if not dry_run and report.new_contacts > 0:
            # Save report
            report_dir = data_root / args.space / 'content' / 'reports'
            report_dir.mkdir(parents=True, exist_ok=True)
            report_file = report_dir / f"{date.today().isoformat()}-contact-import.md"
            report_file.write_text(importer.generate_report_markdown(report))
            print(f"\n  Report saved to: {report_file}")

    return 0


if __name__ == '__main__':
    exit(main())
