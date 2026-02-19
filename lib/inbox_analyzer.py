#!/usr/bin/env python3
"""
Inbox Analyzer - Extract sender statistics from Gmail for CRM and cleanup.

Usage:
    python inbox_analyzer.py analyze --account user@organization.example.com
    python inbox_analyzer.py analyze --account user@organization.example.com --output /tmp/senders.txt
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
from collections import defaultdict

# Add mail module to path
MODULES_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(MODULES_DIR))

from mail.adapters.gmail import GmailAdapter


def classify_sender(email: str, name: str) -> str:
    """Classify sender type based on email/name patterns."""
    email_lower = email.lower()
    name_lower = name.lower() if name else ''

    # Automated/System emails
    automated_patterns = [
        'noreply', 'no-reply', 'donotreply', 'notifications@',
        'alert@', 'alerts@', 'system@', 'mailer@', 'daemon@',
        'postmaster@', 'bounce@', 'auto@', 'automated@'
    ]
    if any(p in email_lower for p in automated_patterns):
        return 'automated'

    # Newsletter patterns
    newsletter_patterns = [
        'newsletter', 'news@', 'digest@', 'weekly@', 'daily@',
        'updates@', 'marketing@', 'info@', 'hello@', 'team@',
        'mail.beehiiv.com', 'substack.com', 'mailchimp.com',
        'sendgrid.net', 'constantcontact.com'
    ]
    if any(p in email_lower for p in newsletter_patterns):
        return 'newsletter'

    # Transaction/Service emails
    service_patterns = [
        'receipt', 'invoice', 'order', 'confirmation', 'booking',
        'support@', 'help@', 'service@', 'billing@'
    ]
    if any(p in email_lower for p in service_patterns):
        return 'transactional'

    # Social/Platform notifications
    social_patterns = [
        'linkedin.com', 'twitter.com', 'facebook.com', 'github.com',
        'slack.com', 'discord.com', 'telegram.org', 'zoom.us'
    ]
    if any(p in email_lower for p in social_patterns):
        return 'social'

    # Via forwarding (Zapier, etc)
    if 'via zapier' in name_lower or '@organization.example.com' in email_lower and 'via' in name_lower:
        return 'forwarded'

    # Default: personal/human
    return 'personal'


def analyze_inbox(
    account: str,
    max_results: int = 0,
    output_file: str = None
) -> Dict[str, Any]:
    """
    Analyze Gmail inbox and extract sender statistics.

    Args:
        account: Gmail account to analyze
        max_results: Max emails to scan (0 = unlimited)
        output_file: Optional file to write results

    Returns:
        Analysis results dict
    """
    adapter = GmailAdapter({"address": account})

    if not adapter.is_configured():
        print(f"ERROR: Account {account} not configured.")
        print(f"Run: python gmail.py setup --account {account}")
        return {}

    print(f"Analyzing inbox for {account}...")
    print("This may take a while for large mailboxes.\n")

    # Progress callback
    def progress(current, total):
        pct = (current / total * 100) if total else 0
        print(f"\r  Processed {current:,}/{total:,} emails ({pct:.1f}%)...", end='', flush=True)

    # Get all senders from "All Mail"
    senders = adapter.get_all_senders(
        query="in:all",
        labels=[],  # No label filter - get all mail
        max_results=max_results,
        progress_callback=progress
    )

    print(f"\n\nFound {len(senders)} unique senders.\n")

    # Calculate totals
    total_emails = sum(s['count'] for s in senders.values())

    # Classify senders
    by_type = defaultdict(list)
    for email, stats in senders.items():
        sender_type = classify_sender(email, stats['name'])
        by_type[sender_type].append({
            'email': email,
            'name': stats['name'],
            'count': stats['count'],
            'last_date': stats['last_date'],
            'sample_subjects': stats['sample_subjects']
        })

    # Sort each category by count
    for category in by_type:
        by_type[category].sort(key=lambda x: x['count'], reverse=True)

    # Build report
    report_lines = []
    report_lines.append(f"Inbox Analysis for {account}")
    report_lines.append("=" * 80)
    report_lines.append(f"Total emails: {total_emails:,}")
    report_lines.append(f"Unique senders: {len(senders)}")
    report_lines.append(f"Analysis date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    report_lines.append("")

    # Summary by type
    report_lines.append("BY SENDER TYPE:")
    for sender_type in ['personal', 'newsletter', 'social', 'automated', 'transactional', 'forwarded']:
        senders_list = by_type.get(sender_type, [])
        count = sum(s['count'] for s in senders_list)
        pct = (count / total_emails * 100) if total_emails else 0
        report_lines.append(f"  {sender_type.capitalize():15} {count:>6,} ({pct:>5.1f}%) - {len(senders_list)} unique senders")
    report_lines.append("")

    # Top senders overall
    report_lines.append("TOP 30 SENDERS (by email count):")
    all_senders_sorted = sorted(senders.items(), key=lambda x: x[1]['count'], reverse=True)
    for i, (email, stats) in enumerate(all_senders_sorted[:30], 1):
        sender_type = classify_sender(email, stats['name'])
        name_display = stats['name'][:30] if stats['name'] else ''
        report_lines.append(f"  {i:>2}. {stats['count']:>5} | {email[:50]:<50} | {name_display:<30} | [{sender_type}]")
    report_lines.append("")

    # Personal contacts (for CRM)
    report_lines.append("PERSONAL CONTACTS FOR CRM:")
    personal = by_type.get('personal', [])
    for sender in personal[:50]:
        name_display = sender['name'] or '(no name)'
        report_lines.append(f"  {sender['count']:>4} | {sender['email']:<50} | {name_display}")
    if len(personal) > 50:
        report_lines.append(f"  ... and {len(personal) - 50} more")
    report_lines.append("")

    # Newsletter cleanup candidates
    report_lines.append("NEWSLETTER CLEANUP CANDIDATES (high volume):")
    newsletters = by_type.get('newsletter', [])
    for sender in newsletters[:20]:
        name_display = sender['name'] or '(no name)'
        report_lines.append(f"  {sender['count']:>4} | {sender['email']:<50} | {name_display}")
    report_lines.append("")

    # Social notifications
    report_lines.append("SOCIAL PLATFORM NOTIFICATIONS:")
    social = by_type.get('social', [])
    for sender in social[:15]:
        name_display = sender['name'] or '(no name)'
        report_lines.append(f"  {sender['count']:>4} | {sender['email']:<50} | {name_display}")
    report_lines.append("")

    # Output
    report = '\n'.join(report_lines)

    if output_file:
        Path(output_file).write_text(report)
        print(f"Report saved to: {output_file}")
    else:
        print(report)

    return {
        'total_emails': total_emails,
        'unique_senders': len(senders),
        'by_type': {k: len(v) for k, v in by_type.items()},
        'senders': senders
    }


def get_contacts_for_crm(account: str, max_results: int = 0) -> Dict[str, Dict[str, Any]]:
    """
    Get all email contacts with sent/received counts for CRM.

    Returns contacts with bidirectional email counts.
    """
    adapter = GmailAdapter({"address": account})

    if not adapter.is_configured():
        print(f"ERROR: Account {account} not configured.")
        return {}

    print(f"Extracting contacts from {account}...")

    def progress(current, total):
        pct = (current / total * 100) if total else 0
        print(f"\r  Processed {current:,}/{total:,} emails ({pct:.1f}%)...", end='', flush=True)

    contacts = adapter.get_all_contacts(
        query="in:all",
        labels=[],
        max_results=max_results,
        progress_callback=progress
    )

    print(f"\n\nFound {len(contacts)} unique contacts.")
    return contacts


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inbox Analyzer for CRM")
    parser.add_argument("command", choices=["analyze", "contacts"],
                       help="Command to run")
    parser.add_argument("--account", required=True,
                       help="Gmail account to analyze")
    parser.add_argument("--max", type=int, default=0,
                       help="Max emails to scan (0 = unlimited)")
    parser.add_argument("--output", "-o",
                       help="Output file path")

    args = parser.parse_args()

    if args.command == "analyze":
        analyze_inbox(
            account=args.account,
            max_results=args.max,
            output_file=args.output
        )

    elif args.command == "contacts":
        contacts = get_contacts_for_crm(
            account=args.account,
            max_results=args.max
        )

        # Sort by total interaction
        sorted_contacts = sorted(
            contacts.items(),
            key=lambda x: x[1]['sent_count'] + x[1]['received_count'],
            reverse=True
        )

        print("\nTop contacts by interaction:")
        print(f"{'Email':<50} | {'Name':<25} | {'Sent':>5} | {'Recv':>5}")
        print("-" * 95)
        for email, stats in sorted_contacts[:50]:
            name = stats['name'][:25] if stats['name'] else ''
            print(f"{email:<50} | {name:<25} | {stats['sent_count']:>5} | {stats['received_count']:>5}")

        if args.output:
            with open(args.output, 'w') as f:
                f.write(f"{'Email'}|{'Name'}|{'Sent'}|{'Recv'}\n")
                for email, stats in sorted_contacts:
                    name = stats['name'] or ''
                    f.write(f"{email}|{name}|{stats['sent_count']}|{stats['received_count']}\n")
            print(f"\nFull list saved to: {args.output}")
