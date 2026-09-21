#!/usr/bin/env python3
"""
Extract individual people (group members) from partnership Telegram groups.
This gets the actual contacts who participated in partnership discussions.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime
from collections import defaultdict, Counter

def load_telegram_export(json_path):
    """Load raw Telegram export."""
    with open(json_path) as f:
        return json.load(f)

def load_kept_groups():
    """Load the groups that were kept (have names)."""
    groups_file = Path(os.environ.get('DATACORE_ROOT', os.path.expanduser('~/Data'))) / '0-personal/1-active/crm-analysis/partnership-groups.md'

    kept_group_names = []

    with open(groups_file, 'r') as f:
        lines = f.readlines()

    in_table = False
    for line in lines:
        if line.startswith('| Group Name'):
            in_table = True
            continue

        if not in_table or not line.strip().startswith('|'):
            continue

        if '---' in line:
            continue

        parts = [p.strip() for p in line.split('|')]
        if len(parts) < 2:
            continue

        group_name = parts[1].strip()

        # Skip if name is empty (deleted by user)
        if not group_name:
            continue

        kept_group_names.append(group_name)

    return kept_group_names

def extract_members_from_groups(data, kept_group_names):
    """Extract unique members from the kept partnership groups."""
    chats = data.get('chats', {}).get('list', [])

    # Filter to group chats
    group_chats = [
        c for c in chats
        if c.get('type') in ['private_group', 'private_supergroup']
    ]

    print(f"Found {len(group_chats)} group chats in export")
    print(f"Keeping {len(kept_group_names)} groups based on your edits")

    # Find matching groups by name
    members_by_person = defaultdict(lambda: {
        'groups': [],
        'message_count': 0,
        'first_seen': None,
        'last_seen': None
    })

    matched_groups = 0

    for chat in group_chats:
        chat_name = chat.get('name', '')

        # Check if this group is in our kept list
        if chat_name not in kept_group_names:
            continue

        matched_groups += 1
        messages = chat.get('messages', [])

        # Extract unique participants from messages
        participants = set()
        for msg in messages:
            from_user = msg.get('from')
            if from_user and from_user != os.environ.get('DATACORE_USER', 'User'):  # Exclude yourself
                participants.add(from_user)

        # Count messages per participant
        for participant in participants:
            participant_msgs = [m for m in messages if m.get('from') == participant]

            if participant_msgs:
                first_date = participant_msgs[0].get('date')
                last_date = participant_msgs[-1].get('date')

                members_by_person[participant]['groups'].append({
                    'group': chat_name,
                    'messages': len(participant_msgs),
                    'first': first_date,
                    'last': last_date
                })

                members_by_person[participant]['message_count'] += len(participant_msgs)

                # Track overall first/last seen
                if not members_by_person[participant]['first_seen']:
                    members_by_person[participant]['first_seen'] = first_date
                if not members_by_person[participant]['last_seen']:
                    members_by_person[participant]['last_seen'] = last_date
                else:
                    # Update if this is later
                    if last_date and last_date > members_by_person[participant]['last_seen']:
                        members_by_person[participant]['last_seen'] = last_date

    print(f"Matched {matched_groups} groups from your kept list")
    print(f"Extracted {len(members_by_person)} unique people from these groups")

    return dict(members_by_person)

def main():
    if len(sys.argv) < 2:
        print("Usage: python extract_group_members.py <result.json>")
        sys.exit(1)

    result_file = Path(sys.argv[1])
    if not result_file.exists():
        print(f"Error: {result_file} not found")
        sys.exit(1)

    print("Loading Telegram export...")
    data = load_telegram_export(result_file)

    print("\nLoading kept groups from your edits...")
    kept_groups = load_kept_groups()

    print(f"\nExtracting members from {len(kept_groups)} partnership groups...")
    members = extract_members_from_groups(data, kept_groups)

    # Sort by message count
    sorted_members = sorted(members.items(), key=lambda x: x[1]['message_count'], reverse=True)

    # Generate report
    report = f"""# Partnership Group Members

Extracted from Telegram partnership groups (kept after your review)
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}

Total partnership groups analyzed: {len(kept_groups)}
Unique people extracted: {len(members)}

## People by Activity Level

Sorted by total message count across all partnership groups.

"""

    for name, data in sorted_members[:200]:  # Top 200
        msg_count = data['message_count']
        num_groups = len(data['groups'])
        first = data['first_seen'][:10] if data['first_seen'] else 'Unknown'
        last = data['last_seen'][:10] if data['last_seen'] else 'Unknown'

        report += f"\n### {name}\n\n"
        report += f"**Total messages:** {msg_count} across {num_groups} group(s)\n"
        report += f"**Active period:** {first} to {last}\n\n"

        report += "**Partnership groups:**\n"
        for group_data in sorted(data['groups'], key=lambda x: x['messages'], reverse=True):
            report += f"- {group_data['group']} ({group_data['messages']} messages)\n"

        # Check if contact exists
        data_root = os.environ.get('DATACORE_ROOT', os.path.expanduser('~/Data'))
        contact_file = Path(f"{data_root}/0-personal/contacts/people/{name}.md")
        if contact_file.exists():
            report += f"\n**Status:** Exists in CRM\n"
        else:
            report += f"\n**Status:** NEW - Create contact\n"

    # Summary stats
    report += f"""

---

## Statistics

- Total unique people: {len(members)}
- People in 1 group: {len([m for m in members.values() if len(m['groups']) == 1])}
- People in 2+ groups: {len([m for m in members.values() if len(m['groups']) > 1])}
- People in 5+ groups: {len([m for m in members.values() if len(m['groups']) >= 5])}

## Top Multi-Group Participants

People active in 5+ partnership groups (key connectors):

"""

    multi_group = [(name, data) for name, data in sorted_members if len(data['groups']) >= 5]
    for name, data in multi_group[:20]:
        report += f"- **{name}**: {len(data['groups'])} groups, {data['message_count']} total messages\n"

    report += """

## Next Steps

1. [ ] Review top 50 people by message count
2. [ ] Create CRM contacts for key participants
3. [ ] Link people to their organizations (from group names)
4. [ ] Identify decision makers and key contacts
5. [ ] Cross-reference with 1-1 Telegram contacts

---

*Note: Excludes the configured user from extraction*
"""

    # Save report
    output_file = Path(os.environ.get('DATACORE_ROOT', os.path.expanduser('~/Data'))) / '0-personal/1-active/crm-analysis/partnership-group-members.md'
    with open(output_file, 'w') as f:
        f.write(report)

    print(f"\n✓ Report saved: {output_file}")

    # Generate contact creation list
    new_members = []
    existing_members = []

    for name, data in sorted_members:
        data_root = os.environ.get('DATACORE_ROOT', os.path.expanduser('~/Data'))
        contact_file = Path(f"{data_root}/0-personal/contacts/people/{name}.md")

        if contact_file.exists():
            existing_members.append(name)
        else:
            new_members.append({
                'name': name,
                'message_count': data['message_count'],
                'groups': data['groups']
            })

    print(f"\n✓ Existing contacts: {len(existing_members)}")
    print(f"✓ New people to create: {len(new_members)}")

    # Save new members list (top 100 by activity)
    if new_members:
        creation_report = f"""# New Partnership Group Members to Create

Found {len(new_members)} new people from partnership groups.
Showing top 100 by message activity.

"""

        for i, member in enumerate(new_members[:100], 1):
            creation_report += f"\n## {i}. {member['name']}\n\n"
            creation_report += f"**Total messages:** {member['message_count']}\n"
            creation_report += f"**Groups ({len(member['groups'])}):**\n"

            for group in sorted(member['groups'], key=lambda x: x['messages'], reverse=True)[:5]:
                creation_report += f"- {group['group']} ({group['messages']} messages)\n"

            if len(member['groups']) > 5:
                creation_report += f"- ...and {len(member['groups']) - 5} more groups\n"

            creation_report += "\n"

        creation_file = Path(os.environ.get('DATACORE_ROOT', os.path.expanduser('~/Data'))) / '0-personal/1-active/crm-analysis/new-group-members-to-create.md'
        with open(creation_file, 'w') as f:
            f.write(creation_report)

        print(f"✓ Top 100 new members list: {creation_file}")

    print("\n" + "="*60)
    print("Group member extraction complete!")
    print("="*60)

if __name__ == '__main__':
    main()
