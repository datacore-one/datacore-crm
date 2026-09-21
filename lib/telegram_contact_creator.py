#!/usr/bin/env python3
"""
Create CRM contact files for partnership contacts.
"""

import os
import re
from pathlib import Path
from datetime import datetime

# Load extracted contacts
def load_extracted_contacts():
    """Parse the extraction report to get contact details."""
    report_file = Path(os.environ.get('DATACORE_ROOT', os.path.expanduser('~/Data'))) / '0-personal/1-active/crm-analysis/partnership-contacts-extracted.md'

    contacts = []
    current_contact = None

    with open(report_file, 'r') as f:
        lines = f.readlines()

    for line in lines:
        # New contact section
        if line.startswith('### ') and '(' in line:
            # Parse: "### ContactName (type)"
            match = re.match(r'### (.+?) \((.+?)\)', line)
            if match:
                name = match.group(1)
                entity_type = match.group(2)

                if current_contact:
                    contacts.append(current_contact)

                current_contact = {
                    'name': name,
                    'entity_type': entity_type,
                    'groups': [],
                    'status': 'new'
                }

        # Group membership
        elif line.startswith('- ') and current_contact:
            # Parse: "- GroupName (N messages) - NOTE: xyz"
            group_line = line[2:].strip()

            # Extract note if present
            note = None
            if ' - NOTE: ' in group_line:
                group_part, note = group_line.split(' - NOTE: ', 1)
            else:
                group_part = group_line

            # Extract group name and message count
            match = re.match(r'(.+?) \((\d+) messages\)', group_part)
            if match:
                group_name = match.group(1)
                msg_count = match.group(2)

                current_contact['groups'].append({
                    'name': group_name,
                    'messages': msg_count,
                    'note': note
                })

        # Status line
        elif line.startswith('**Status:**') and current_contact:
            if 'exists in CRM' in line:
                current_contact['status'] = 'existing'
            else:
                current_contact['status'] = 'new'

    if current_contact:
        contacts.append(current_contact)

    return contacts

def determine_industries(groups):
    """Infer industries from group memberships."""
    industries = set()

    for group in groups:
        name = group['name'].lower()

        # Blockchain/Crypto
        if any(x in name for x in ['eth', 'bzz', 'defi', 'web3', 'crypto', 'chain', 'dao']):
            industries.add('web3')
            industries.add('blockchain')

        # Infrastructure
        if any(x in name for x in ['network', 'infrastructure', 'protocol', 'storage']):
            industries.add('infrastructure')

        # Finance/Trading
        if any(x in name for x in ['capital', 'ventures', 'fund', 'trading', 'exchange']):
            industries.add('finance')

        # AI
        if any(x in name for x in ['ai', 'gordon']):
            industries.add('ai')

        # Market Making
        if any(x in name for x in ['market', 'liquidity', 'maker']):
            industries.add('market_making')

    return list(industries)[:5]  # Limit to 5 industries

def determine_relationship_type(groups):
    """Infer relationship type from groups."""
    # Check for specific indicators
    for group in groups:
        name = group['name'].lower()

        if 'labs' in name or 'capital' in name or 'ventures' in name:
            return 'investor'

        if 'exchange' in name or '.com' in name or '.io' in name:
            return 'partner'

        if 'listing' in name or 'ama' in name:
            return 'partner'

    return 'partner'  # Default

def create_contact_file(contact, special_instructions):
    """Create a contact markdown file."""
    name = contact['name']
    entity_type = contact['entity_type']
    groups = contact['groups']

    # Determine metadata
    industries = determine_industries(groups)
    relationship_type = determine_relationship_type(groups)

    # Calculate total message volume
    total_messages = sum(int(g['messages']) for g in groups)

    # Determine relevance based on message volume
    if total_messages > 1000:
        relevance = 4
    elif total_messages > 300:
        relevance = 3
    elif total_messages > 100:
        relevance = 2
    else:
        relevance = 1

    # Get special instructions for this contact
    special_note = None
    for group in groups:
        if group['note']:
            special_note = group['note']
            break

    # Check if contact name appears in special instructions
    for instr_group, instr in special_instructions.items():
        if name.lower() in instr_group.lower():
            special_note = instr

    # Build groups list
    groups_text = '\n'.join([
        f"- {g['name']} ({g['messages']} messages)"
        for g in groups
    ])

    # Special instruction note
    instruction_section = ''
    if special_note:
        instruction_section = f"""

## Action Required

⚠️ **Special Instruction:** {special_note}
"""

    content = f"""---
type: contact
entity_type: {entity_type}
name: "{name}"
status: draft
relationship_status: partner
relationship_type: {relationship_type}
relevance: {relevance}
privacy: team
space: teamspace
industries: {industries}
source: telegram_partnership_groups
partnership_stats:
  total_groups: {len(groups)}
  total_messages: {total_messages}
created: {datetime.now().strftime('%Y-%m-%d')}
---

# {name}

## Overview

Partnership contact extracted from Telegram partnership groups.

**Groups:** {len(groups)} partnership group(s)
**Total messages:** {total_messages} across all groups
**Relationship:** {relationship_type.capitalize()}

## Partnership Groups

{groups_text}
{instruction_section}

## Notes

[Add partnership context, key contacts, relationship history]

**Key discussions:**
- [Topics discussed in partnership groups]

**Collaboration areas:**
- [Potential or active collaboration areas]

## Goals

**What we want:**
- [Partnership objectives]

**What they want:**
- [Their needs/interests]

## Next Steps

- [ ] Review partnership group history
- [ ] Identify key contacts at organization
- [ ] Define partnership scope
- [ ] Schedule alignment call

## Related

- Partnership groups: See above
- Related contacts: [Link to key people at this organization]
"""

    return content

def main():
    print("Loading extracted contacts...")
    contacts = load_extracted_contacts()

    print(f"Found {len(contacts)} total contacts")

    # Filter to new contacts only
    new_contacts = [c for c in contacts if c['status'] == 'new']
    print(f"Creating {len(new_contacts)} new contacts...")

    # Load special instructions
    special_instructions = {
        'Example Group': 'use for partner campaign',
        'Gnosis AI': 'reach out when Datacore is ready',
    }

    # Create contact files
    contacts_dir = Path(os.environ.get('DATACORE_ROOT', os.path.expanduser('~/Data'))) / '0-personal/contacts/people'
    contacts_dir.mkdir(parents=True, exist_ok=True)

    created = []
    skipped = []

    for contact in new_contacts:
        name = contact['name']

        # Sanitize filename
        filename = name.replace('/', '-').replace('\\', '-').replace(':', '-')
        filename = filename[:100] + '.md'

        contact_path = contacts_dir / filename

        # Skip if already exists (safety check)
        if contact_path.exists():
            skipped.append(name)
            continue

        # Create file
        content = create_contact_file(contact, special_instructions)

        with open(contact_path, 'w', encoding='utf-8') as f:
            f.write(content)

        created.append(name)

    print(f"\n✓ Created {len(created)} new contact files")
    if skipped:
        print(f"  Skipped {len(skipped)} existing contacts")

    # Generate summary
    summary = f"""# Partnership Contacts Created

Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

## Summary

- **Total contacts extracted:** {len(contacts)}
- **New contacts created:** {len(created)}
- **Existing contacts (skipped):** {len(skipped)}

## Created Contacts

"""

    for name in sorted(created):
        summary += f"- [[{name}]]\n"

    summary += f"""

## Special Instructions

The following contacts have special action items:

- **Gnosis AI**: reach out when Datacore is ready
- **Example Group**: use for partner campaign (Note: This is a group, not a contact)

## Next Steps

1. [ ] Review all partnership contacts in `contacts/people/`
2. [ ] Identify key people at each organization
3. [ ] Update relationship status from "draft" to appropriate status
4. [ ] Add specific contact people for each organization
5. [ ] Cross-reference with existing 1-1 Telegram contacts

## Notes

- All contacts marked as `entity_type: company` or `project`
- All have `privacy: team` (partnership level)
- `relevance` based on message volume in groups
- Source: Telegram partnership groups analysis
"""

    summary_file = Path(os.environ.get('DATACORE_ROOT', os.path.expanduser('~/Data'))) / '0-personal/1-active/crm-analysis/partnership-contacts-created-summary.md'
    with open(summary_file, 'w') as f:
        f.write(summary)

    print(f"✓ Summary saved: {summary_file}")

    print("\n" + "="*60)
    print("Partnership contacts created successfully!")
    print("="*60)

if __name__ == '__main__':
    main()
