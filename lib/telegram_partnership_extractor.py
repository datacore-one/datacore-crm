#!/usr/bin/env python3
"""
Extract contacts from partnership groups.
Groups with deleted names are ignored.
Groups with names have contacts extracted.
"""

import re
from pathlib import Path
from collections import defaultdict

# Parse the markdown table
def parse_partnership_groups(file_path):
    """Parse partnership groups file."""
    groups = []

    with open(file_path, 'r') as f:
        lines = f.readlines()

    # Find table start
    in_table = False
    for line in lines:
        # Skip until we find the table header
        if line.startswith('| Group Name'):
            in_table = True
            continue

        if not in_table or not line.strip().startswith('|'):
            continue

        # Parse table row
        parts = [p.strip() for p in line.split('|')]

        # Skip separator lines
        if '---' in line:
            continue

        # parts[0] is empty, parts[1] is group name, parts[2] is messages, etc.
        if len(parts) < 5:
            continue

        group_name = parts[1].strip()

        # Skip if name is empty (deleted)
        if not group_name:
            continue

        messages = parts[2].strip()
        group_type = parts[3].strip()
        last_activity = parts[4].strip()

        # Get any notes from remaining columns
        notes = ''
        if len(parts) > 5:
            notes = ' '.join(parts[5:]).strip()

        groups.append({
            'name': group_name,
            'messages': messages,
            'type': group_type,
            'last_activity': last_activity,
            'notes': notes
        })

    return groups

def extract_contacts_from_group_name(group_name):
    """Extract organization/contact names from group name."""
    contacts = []

    # Remove common prefixes/suffixes
    name = group_name
    name = re.sub(r'^\s*[📈💥👥🐳💥]\s*', '', name)  # Remove emoji
    name = re.sub(r'\s*\(.*?\)\s*', '', name)  # Remove parentheticals

    # Split on common separators
    separators = [' <> ', ' x ', ' X ', ' & ', ' <-> ', ' | ', ' / ']

    for sep in separators:
        if sep in name:
            parts = name.split(sep)
            for part in parts:
                part = part.strip()
                if part and len(part) > 1:
                    contacts.append(part)
            return contacts

    # If no separator, check for common patterns
    # "Swarm Foundation", "Gordon AI", etc.
    if 'Team A' in name or 'Swarm' in name or 'Gordon' in name or 'FDS' in name:
        # These are our own projects, skip
        return contacts

    # Single name group - might be a partner
    if len(name) > 2:
        contacts.append(name)

    return contacts

def categorize_contact(name):
    """Determine if contact is company, person, or project."""
    # Skip our own entities
    if any(x in name.lower() for x in [\'team-a\', 'swarm', 'gordon', 'fds', 'fair data']):
        return None

    # Companies/Exchanges
    company_indicators = [
        'labs', 'capital', 'ventures', 'fund', 'group', 'inc', 'ltd',
        'exchange', '.com', '.io', 'network', 'finance', 'global',
        'solutions', 'tech', 'dao', 'protocol', 'foundation'
    ]

    if any(ind in name.lower() for ind in company_indicators):
        return 'company'

    # Projects/Protocols
    project_indicators = [
        'chain', 'network', 'protocol'
    ]

    if any(ind in name.lower() for ind in project_indicators):
        return 'project'

    # Likely a company if multi-word and starts with capital
    if ' ' in name and name[0].isupper():
        return 'company'

    return 'company'  # Default to company for partnerships

def main():
    file_path = Path('/path/to/space/1-active/crm-analysis/partnership-groups.md')

    print("Parsing partnership groups...")
    groups = parse_partnership_groups(file_path)

    print(f"Found {len(groups)} active groups (with names)")

    # Extract contacts
    all_contacts = defaultdict(list)

    for group in groups:
        group_name = group['name']
        notes = group['notes']

        contacts = extract_contacts_from_group_name(group_name)

        for contact in contacts:
            entity_type = categorize_contact(contact)

            if not entity_type:
                continue

            all_contacts[contact].append({
                'group': group_name,
                'notes': notes,
                'messages': group['messages'],
                'entity_type': entity_type
            })

    print(f"\nExtracted {len(all_contacts)} unique contacts")

    # Generate report
    report = f"""# Partnership Contacts Extraction

Extracted from: partnership-groups.md
Generated: 2026-01-14

Total active groups: {len(groups)}
Unique contacts extracted: {len(all_contacts)}

## Contacts by Frequency

"""

    # Sort by frequency
    sorted_contacts = sorted(all_contacts.items(), key=lambda x: len(x[1]), reverse=True)

    for contact_name, occurrences in sorted_contacts:
        entity_type = occurrences[0]['entity_type']
        group_count = len(occurrences)

        report += f"\n### {contact_name} ({entity_type})\n\n"
        report += f"**Appears in {group_count} group(s)**\n\n"

        # List groups
        for occ in occurrences:
            notes_text = f" - NOTE: {occ['notes']}" if occ['notes'] and occ['notes'] != '✓' else ""
            report += f"- {occ['group']} ({occ['messages']} messages){notes_text}\n"

        # Check if contact exists in CRM
        contact_file = Path(f"/path/to/space/contacts/people/{contact_name}.md")
        if contact_file.exists():
            report += f"\n**Status:** Contact exists in CRM at `contacts/people/{contact_name}.md`\n"
        else:
            report += f"\n**Status:** NEW - Need to create contact\n"

    # Special notes section
    report += "\n\n---\n\n## Groups with Special Instructions\n\n"

    special_groups = [g for g in groups if g['notes'] and g['notes'] != '✓']

    if special_groups:
        for g in special_groups:
            report += f"- **{g['name']}**: {g['notes']}\n"
    else:
        report += "*No special instructions*\n"

    # Save report
    output_file = Path('/path/to/space/1-active/crm-analysis/partnership-contacts-extracted.md')
    with open(output_file, 'w') as f:
        f.write(report)

    print(f"\n✓ Report saved: {output_file}")

    # Generate contact creation tasks
    new_contacts = []
    existing_contacts = []

    for contact_name, occurrences in sorted_contacts:
        contact_file = Path(f"/path/to/space/contacts/people/{contact_name}.md")

        if contact_file.exists():
            existing_contacts.append(contact_name)
        else:
            new_contacts.append({
                'name': contact_name,
                'entity_type': occurrences[0]['entity_type'],
                'groups': [o['group'] for o in occurrences]
            })

    print(f"\n✓ Existing contacts: {len(existing_contacts)}")
    print(f"✓ New contacts to create: {len(new_contacts)}")

    # Save contact creation list
    if new_contacts:
        creation_report = f"""# New Contacts to Create

Found {len(new_contacts)} new contacts from partnership groups.

"""

        for nc in new_contacts:
            creation_report += f"\n## {nc['name']} ({nc['entity_type']})\n\n"
            creation_report += f"**From groups:**\n"
            for g in nc['groups']:
                creation_report += f"- {g}\n"
            creation_report += "\n"

        creation_file = Path('/path/to/space/1-active/crm-analysis/new-contacts-to-create.md')
        with open(creation_file, 'w') as f:
            f.write(creation_report)

        print(f"✓ New contacts list: {creation_file}")

    print("\n" + "="*60)
    print("Extraction complete!")
    print("="*60)

if __name__ == '__main__':
    main()
