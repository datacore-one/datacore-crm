#!/usr/bin/env python3
"""
Analyze Telegram contacts for follow-up gaps.
Identify contacts left hanging after conferences or in conversations.
"""

import json
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict

# Conference dates (2024 focus - still relevant for follow-up)
CONFERENCES_2024 = {
    'DevCon Bangkok': datetime(2024, 11, 12),
    'Token2049 Singapore': datetime(2024, 9, 18),
    'Token2049 Dubai': datetime(2024, 4, 17),
    'EthCC Paris': datetime(2024, 7, 8),
}

def parse_date(date_str):
    """Parse Telegram date format."""
    if not date_str:
        return None
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except:
        return None

def analyze_conversation_ending(messages, now):
    """Analyze if conversation was left hanging."""
    if not messages or len(messages) < 2:
        return None

    last_msg = messages[-1]
    second_last = messages[-2] if len(messages) > 1 else None

    last_from = last_msg.get('from', '')
    last_date = parse_date(last_msg.get('date'))

    if not last_date:
        return None

    days_since = (now - last_date).days

    # Pattern 1: They messaged last, no reply from me
    if last_from != os.environ.get('DATACORE_USER', 'User'):
        return {
            'type': 'unanswered_by_me',
            'last_message_from': last_from,
            'days_ago': days_since,
            'last_message_date': last_date.strftime('%Y-%m-%d'),
            'last_message_text': get_message_text(last_msg)[:200]
        }

    # Pattern 2: I messaged last, no reply from them (if it's a question or requires response)
    if last_from == os.environ.get('DATACORE_USER', 'User'):
        text = get_message_text(last_msg).lower()
        # Check if it looks like a question or request
        if any(marker in text for marker in ['?', 'let me know', 'thoughts', 'what do you think', 'when', 'how about']):
            # Check if it's been a while
            if days_since > 14:
                return {
                    'type': 'no_response_to_my_message',
                    'last_message_from': f'{os.environ.get("DATACORE_USER", "User")} (you)',
                    'days_ago': days_since,
                    'last_message_date': last_date.strftime('%Y-%m-%d'),
                    'last_message_text': text[:200]
                }

    return None

def get_message_text(msg):
    """Extract text from message (handle arrays)."""
    text = msg.get('text', '')
    if isinstance(text, list):
        text = ''.join([
            item.get('text', '') if isinstance(item, dict) else str(item)
            for item in text
        ])
    return text

def find_post_conference_gaps(messages, contact_name, now):
    """Find if there was conference interaction but no follow-up."""
    gaps = []

    for conf_name, conf_date in CONFERENCES_2024.items():
        # Find messages during conference window (± 5 days)
        conf_start = conf_date - timedelta(days=3)
        conf_end = conf_date + timedelta(days=5)

        conference_messages = []
        for msg in messages:
            msg_date = parse_date(msg.get('date'))
            if msg_date and conf_start <= msg_date <= conf_end:
                conference_messages.append(msg)

        if conference_messages:
            # Check if there was follow-up after conference
            last_conf_msg = conference_messages[-1]
            last_conf_date = parse_date(last_conf_msg.get('date'))

            # Find messages after conference
            post_conf_messages = [
                msg for msg in messages
                if parse_date(msg.get('date')) and parse_date(msg.get('date')) > conf_end
            ]

            days_since_conf = (now - last_conf_date).days if last_conf_date else 999

            if not post_conf_messages and days_since_conf > 30:
                gaps.append({
                    'conference': conf_name,
                    'conference_date': conf_date.strftime('%Y-%m-%d'),
                    'messages_during': len(conference_messages),
                    'days_since': days_since_conf,
                    'last_conference_message': get_message_text(last_conf_msg)[:200],
                    'follow_up_sent': False
                })
            elif post_conf_messages and len(post_conf_messages) < 3:
                # Minimal follow-up
                first_followup = post_conf_messages[0]
                followup_date = parse_date(first_followup.get('date'))
                days_between = (followup_date - last_conf_date).days if followup_date and last_conf_date else 0

                gaps.append({
                    'conference': conf_name,
                    'conference_date': conf_date.strftime('%Y-%m-%d'),
                    'messages_during': len(conference_messages),
                    'days_since': days_since_conf,
                    'follow_up_sent': True,
                    'follow_up_weak': True,
                    'days_to_followup': days_between,
                    'followup_messages': len(post_conf_messages)
                })

    return gaps

def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_followup_gaps.py <result.json>")
        sys.exit(1)

    result_file = Path(sys.argv[1])
    if not result_file.exists():
        print(f"Error: {result_file} not found")
        sys.exit(1)

    print("Analyzing follow-up gaps...")
    with open(result_file) as f:
        data = json.load(f)

    chats = data.get('chats', {}).get('list', [])
    personal_chats = [c for c in chats if c.get('type') == 'personal_chat']

    print(f"Analyzing {len(personal_chats)} personal chats...")

    now = datetime.now()

    # Collect results
    unanswered_by_me = []
    no_response_from_them = []
    post_conference_gaps = []

    for i, chat in enumerate(personal_chats):
        name = chat.get('name') or f"Unknown_{chat.get('id', '')}"
        name = str(name)
        messages = chat.get('messages', [])

        if not messages:
            continue

        # Check conversation ending
        ending = analyze_conversation_ending(messages, now)
        if ending:
            contact_info = {
                'name': name,
                'message_count': len(messages),
                **ending
            }

            if ending['type'] == 'unanswered_by_me':
                unanswered_by_me.append(contact_info)
            elif ending['type'] == 'no_response_to_my_message':
                no_response_from_them.append(contact_info)

        # Check post-conference gaps
        conf_gaps = find_post_conference_gaps(messages, name, now)
        if conf_gaps:
            for gap in conf_gaps:
                post_conference_gaps.append({
                    'name': name,
                    'message_count': len(messages),
                    **gap
                })

        if (i + 1) % 100 == 0:
            print(f"  Analyzed {i + 1}/{len(personal_chats)}...")

    print(f"\n✓ Analysis complete!")
    print(f"  Unanswered by me: {len(unanswered_by_me)}")
    print(f"  No response from them: {len(no_response_from_them)}")
    print(f"  Post-conference gaps: {len(post_conference_gaps)}")

    # Generate report
    output_file = result_file.parent / 'followup_gaps_analysis.md'

    report = f"""# Follow-Up Gaps Analysis

Generated: {now.strftime('%Y-%m-%d %H:%M')}

This analysis identifies contacts where follow-up is needed:
1. **Unanswered by me** - They sent the last message, no response from you
2. **Waiting for their response** - You sent a question/request, they didn't respond
3. **Post-conference gaps** - Met at conference, but no/weak follow-up

---

## 1. Unanswered by Me ({len(unanswered_by_me)} contacts)

These contacts sent you a message and you haven't replied yet.

**Priority: HIGH** - They're waiting for your response.

"""

    # Sort by days ago (most recent first, but only show those > 7 days)
    unanswered_filtered = [c for c in unanswered_by_me if c['days_ago'] > 7]
    unanswered_sorted = sorted(unanswered_filtered, key=lambda x: (-x['message_count'], x['days_ago']))

    if unanswered_sorted:
        report += "| Contact | Messages | Days Ago | Last Message | Preview |\n"
        report += "|---------|----------|----------|--------------|----------|\n"

        for c in unanswered_sorted[:30]:  # Top 30
            name = c['name']
            msg_count = c['message_count']
            days = c['days_ago']
            date = c['last_message_date']
            preview = c['last_message_text'].replace('\n', ' ')[:100]

            report += f"| [[{name}]] | {msg_count} | {days} | {date} | {preview}... |\n"
    else:
        report += "*No significant unanswered messages (>7 days old)*\n"

    report += f"""

---

## 2. Waiting for Their Response ({len(no_response_from_them)} contacts)

You sent a question or request, and they haven't responded.

**Priority: MEDIUM** - May need gentle follow-up or consider conversation closed.

"""

    waiting_sorted = sorted(no_response_from_them, key=lambda x: x['days_ago'])[:20]

    if waiting_sorted:
        report += "| Contact | Messages | Days Ago | Your Message | Preview |\n"
        report += "|---------|----------|----------|--------------|----------|\n"

        for c in waiting_sorted:
            name = c['name']
            msg_count = c['message_count']
            days = c['days_ago']
            date = c['last_message_date']
            preview = c['last_message_text'].replace('\n', ' ')[:100]

            report += f"| [[{name}]] | {msg_count} | {days} | {date} | {preview}... |\n"
    else:
        report += "*No pending responses*\n"

    report += f"""

---

## 3. Post-Conference Follow-Up Gaps ({len(post_conference_gaps)} contacts)

Contacts you met at conferences in 2024 but didn't follow up with (or weak follow-up).

**Priority: HIGH** - These are warm intros from conferences that need nurturing.

"""

    # Group by conference
    by_conference = defaultdict(list)
    for gap in post_conference_gaps:
        by_conference[gap['conference']].append(gap)

    # Sort conferences by date (most recent first)
    sorted_conferences = sorted(
        by_conference.items(),
        key=lambda x: CONFERENCES_2024[x[0]],
        reverse=True
    )

    for conf_name, gaps in sorted_conferences:
        conf_date = CONFERENCES_2024[conf_name].strftime('%Y-%m-%d')
        report += f"\n### {conf_name} ({conf_date})\n\n"
        report += f"**Contacts with gaps:** {len(gaps)}\n\n"

        # Separate no follow-up vs weak follow-up
        no_followup = [g for g in gaps if not g.get('follow_up_sent')]
        weak_followup = [g for g in gaps if g.get('follow_up_weak')]

        if no_followup:
            report += f"**No follow-up sent ({len(no_followup)} contacts):**\n\n"
            report += "| Contact | Messages at Conf | Days Since | Last Conference Message |\n"
            report += "|---------|------------------|------------|-------------------------|\n"

            # Sort by message count during conference (most engaged first)
            no_followup_sorted = sorted(no_followup, key=lambda x: -x['messages_during'])

            for g in no_followup_sorted[:15]:  # Top 15
                name = g['name']
                msgs = g['messages_during']
                days = g['days_since']
                preview = g.get('last_conference_message', '')[:80]

                report += f"| [[{name}]] | {msgs} | {days} | {preview}... |\n"

        if weak_followup:
            report += f"\n**Weak follow-up ({len(weak_followup)} contacts):**\n\n"
            report += "| Contact | Messages at Conf | Follow-up Msgs | Days to Follow-up |\n"
            report += "|---------|------------------|----------------|-------------------|\n"

            weak_sorted = sorted(weak_followup, key=lambda x: -x['messages_during'])

            for g in weak_sorted[:10]:  # Top 10
                name = g['name']
                msgs = g['messages_during']
                followup_count = g.get('followup_messages', 0)
                days_to = g.get('days_to_followup', 0)

                report += f"| [[{name}]] | {msgs} | {followup_count} | {days_to} |\n"

    report += """

---

## Recommendations

### Immediate Actions (This Week)

1. **Reply to unanswered messages** - Prioritize contacts with high message counts (existing relationships)
2. **Conference follow-ups** - Focus on DevCon Bangkok (most recent, Nov 2024)
   - Template: "Great meeting you at DevCon! [specific memory]. Let's [specific next step]."

### Short-term (Next 2 Weeks)

3. **Token2049 Singapore follow-ups** - Still relevant (Sep 2024)
4. **Gentle nudges** - For contacts waiting >30 days for your response to questions
   - Template: "Circling back on this - [original question]. Thoughts?"

### Strategy

- **Prioritize by conference recency** - DevCon Bangkok > Token2049 Singapore > older
- **High message count = high value** - Focus on contacts with 3+ messages during conference
- **No follow-up > weak follow-up** - Better to follow up late than never
- **Be specific** - Reference what you discussed at conference

---

## Next Steps

- [ ] Add top 10 unanswered contacts to `org/next_actions.org` with :CRM: tag
- [ ] Create conference-specific follow-up templates
- [ ] Schedule 30 min for "conference follow-up sprint"
- [ ] Track follow-up success rate in CRM

---

*Analysis based on Telegram export (DataExport_2025-12-21)*
"""

    with open(output_file, 'w') as f:
        f.write(report)

    print(f"\n✓ Report saved: {output_file}")

    # Save detailed JSON
    json_output = result_file.parent / 'followup_gaps_detailed.json'
    with open(json_output, 'w') as f:
        json.dump({
            'generated': now.isoformat(),
            'unanswered_by_me': unanswered_by_me,
            'no_response_from_them': no_response_from_them,
            'post_conference_gaps': post_conference_gaps,
        }, f, indent=2)

    print(f"✓ Detailed data: {json_output}")
    print("\n" + "="*60)
    print("Follow-up gaps analysis complete!")
    print("="*60)

if __name__ == '__main__':
    main()
