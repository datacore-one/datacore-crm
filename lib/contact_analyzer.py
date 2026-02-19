#!/usr/bin/env python3
"""
Contact Analyzer - Deep analysis of email contacts for CRM import decisions.

Analyzes:
- Interaction frequency (emails per month)
- Time span (how long the relationship has existed)
- Direction (mostly sent, received, or balanced)
- Domain grouping (company/organization)
- Recency (last contact date)

Usage:
    python contact_analyzer.py analyze --account user@organization.example.com
"""

import sys
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, Any, List, Tuple
from collections import defaultdict
from email.utils import parsedate_to_datetime

# Add mail module to path
MODULES_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(MODULES_DIR))

from mail.adapters.gmail import GmailAdapter


def parse_date_safe(date_str: str) -> datetime:
    """Parse date string safely, returning epoch on failure."""
    if not date_str:
        return datetime(1970, 1, 1)
    try:
        return parsedate_to_datetime(date_str)
    except:
        return datetime(1970, 1, 1)


def extract_domain(email: str) -> str:
    """Extract domain from email address."""
    if '@' in email:
        return email.split('@')[1].lower()
    return ''


def classify_contact(stats: Dict[str, Any], my_email: str) -> Dict[str, Any]:
    """Classify a contact based on interaction patterns."""
    sent = stats.get('sent_count', 0)
    received = stats.get('received_count', 0)
    total = sent + received

    # Direction ratio
    if total > 0:
        sent_ratio = sent / total
        if sent_ratio > 0.7:
            direction = 'mostly_sent'  # I mostly sent to them
        elif sent_ratio < 0.3:
            direction = 'mostly_received'  # They mostly sent to me
        else:
            direction = 'balanced'  # Mutual communication
    else:
        direction = 'unknown'

    # Frequency tier
    if total >= 50:
        frequency = 'high'
    elif total >= 10:
        frequency = 'medium'
    elif total >= 3:
        frequency = 'low'
    else:
        frequency = 'minimal'

    return {
        'sent_count': sent,
        'received_count': received,
        'total': total,
        'direction': direction,
        'frequency': frequency,
        'name': stats.get('name', ''),
        'last_date': stats.get('last_date', '')
    }


def analyze_contacts(account: str, max_results: int = 0) -> Dict[str, Any]:
    """
    Perform deep analysis of all email contacts.

    Returns comprehensive analysis with groupings.
    """
    adapter = GmailAdapter({"address": account})

    if not adapter.is_configured():
        print(f"ERROR: Account {account} not configured.")
        return {}

    print(f"Analyzing contacts for {account}...")
    print("This scans all emails for sender/recipient patterns.\n")

    def progress(current, total):
        pct = (current / total * 100) if total else 0
        print(f"\r  Processed {current:,}/{total:,} emails ({pct:.1f}%)...", end='', flush=True)

    # Get all contacts with bidirectional counts
    contacts = adapter.get_all_contacts(
        query="in:all",
        labels=[],
        max_results=max_results,
        progress_callback=progress
    )

    print(f"\n\nFound {len(contacts):,} unique email contacts.\n")

    # Classify each contact
    classified = {}
    for email, stats in contacts.items():
        classified[email] = classify_contact(stats, account)
        classified[email]['email'] = email
        classified[email]['domain'] = extract_domain(email)

    # Group by domain
    by_domain = defaultdict(list)
    for email, info in classified.items():
        by_domain[info['domain']].append(info)

    # Sort each domain's contacts by total interactions
    for domain in by_domain:
        by_domain[domain].sort(key=lambda x: x['total'], reverse=True)

    # Group by frequency tier
    by_frequency = defaultdict(list)
    for email, info in classified.items():
        by_frequency[info['frequency']].append(info)

    # Sort by total within each tier
    for tier in by_frequency:
        by_frequency[tier].sort(key=lambda x: x['total'], reverse=True)

    # Group by direction
    by_direction = defaultdict(list)
    for email, info in classified.items():
        by_direction[info['direction']].append(info)

    # Identify key domains (by total interactions)
    domain_totals = {}
    for domain, contacts_list in by_domain.items():
        domain_totals[domain] = sum(c['total'] for c in contacts_list)

    top_domains = sorted(domain_totals.items(), key=lambda x: x[1], reverse=True)[:30]

    return {
        'total_contacts': len(contacts),
        'classified': classified,
        'by_domain': dict(by_domain),
        'by_frequency': dict(by_frequency),
        'by_direction': dict(by_direction),
        'domain_totals': domain_totals,
        'top_domains': top_domains
    }


def generate_report(analysis: Dict[str, Any], account: str, output_file: str = None):
    """Generate a comprehensive contact analysis report."""

    lines = []
    lines.append(f"Contact Analysis Report for {account}")
    lines.append("=" * 80)
    lines.append(f"Analysis date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Total unique contacts: {analysis['total_contacts']:,}")
    lines.append("")

    # Summary by frequency
    by_freq = analysis['by_frequency']
    lines.append("BY INTERACTION FREQUENCY:")
    lines.append("-" * 40)
    for tier in ['high', 'medium', 'low', 'minimal']:
        contacts = by_freq.get(tier, [])
        total_emails = sum(c['total'] for c in contacts)
        lines.append(f"  {tier.upper():10} {len(contacts):>5} contacts | {total_emails:>6,} emails")
    lines.append("")

    # Summary by direction
    by_dir = analysis['by_direction']
    lines.append("BY COMMUNICATION DIRECTION:")
    lines.append("-" * 40)
    for direction, label in [('balanced', 'Mutual (balanced)'),
                              ('mostly_sent', 'I contact them more'),
                              ('mostly_received', 'They contact me more')]:
        contacts = by_dir.get(direction, [])
        lines.append(f"  {label:25} {len(contacts):>5} contacts")
    lines.append("")

    # Top domains
    lines.append("TOP 30 DOMAINS (by total interactions):")
    lines.append("-" * 60)
    for domain, total in analysis['top_domains']:
        contact_count = len(analysis['by_domain'].get(domain, []))
        lines.append(f"  {total:>6,} emails | {contact_count:>4} contacts | {domain}")
    lines.append("")

    # Key organizational groups
    lines.append("KEY ORGANIZATIONAL GROUPS:")
    lines.append("=" * 80)

    # Organization team
    org_contacts = analysis['by_domain'].get('organization.example.com', [])
    if org_contacts:
        lines.append("\n## ORGANIZATION TEAM (organization.example.com)")
        lines.append(f"   {len(org_contacts)} contacts, {sum(c['total'] for c in org_contacts):,} total emails")
        lines.append("-" * 60)
        for c in org_contacts[:20]:
            direction_icon = {'balanced': '<->', 'mostly_sent': ' ->', 'mostly_received': '<- '}[c['direction']]
            lines.append(f"  {c['total']:>5} {direction_icon} {c['email']:<40} {c['name'][:25]}")

    # Infrastructure team
    infra_contacts = analysis['by_domain'].get('infra.example.org', [])
    if infra_contacts:
        lines.append("\n## INFRASTRUCTURE TEAM (infra.example.org)")
        lines.append(f"   {len(infra_contacts)} contacts, {sum(c['total'] for c in infra_contacts):,} total emails")
        lines.append("-" * 60)
        for c in infra_contacts[:20]:
            direction_icon = {'balanced': '<->', 'mostly_sent': ' ->', 'mostly_received': '<- '}[c['direction']]
            lines.append(f"  {c['total']:>5} {direction_icon} {c['email']:<40} {c['name'][:25]}")

    # High frequency contacts (non-team)
    lines.append("\n## HIGH FREQUENCY CONTACTS (non-team, 50+ emails)")
    lines.append("-" * 60)
    high_freq = [c for c in analysis['by_frequency'].get('high', [])
                 if c['domain'] not in ['organization.example.com', 'infra.example.org', 'gmail.com', 'google.com']]
    for c in high_freq[:30]:
        direction_icon = {'balanced': '<->', 'mostly_sent': ' ->', 'mostly_received': '<- '}[c['direction']]
        lines.append(f"  {c['total']:>5} {direction_icon} {c['email']:<45} {c['name'][:25]}")

    # Medium frequency contacts (potential CRM candidates)
    lines.append("\n## MEDIUM FREQUENCY CONTACTS (10-49 emails, CRM candidates)")
    lines.append("-" * 60)
    medium_freq = [c for c in analysis['by_frequency'].get('medium', [])
                   if c['domain'] not in ['organization.example.com', 'infra.example.org', 'gmail.com', 'google.com']]
    for c in medium_freq[:40]:
        direction_icon = {'balanced': '<->', 'mostly_sent': ' ->', 'mostly_received': '<- '}[c['direction']]
        lines.append(f"  {c['total']:>5} {direction_icon} {c['email']:<45} {c['name'][:25]}")

    # Balanced communication (true relationships)
    lines.append("\n## BALANCED COMMUNICATION (likely real relationships)")
    lines.append("-" * 60)
    balanced = [c for c in analysis['by_direction'].get('balanced', [])
                if c['total'] >= 5 and c['domain'] not in ['organization.example.com', 'infra.example.org']]
    balanced.sort(key=lambda x: x['total'], reverse=True)
    for c in balanced[:40]:
        lines.append(f"  {c['total']:>5} <-> {c['email']:<45} {c['name'][:25]}")

    # Newsletter/automated senders (mostly received, many emails)
    lines.append("\n## LIKELY NEWSLETTERS/AUTOMATED (mostly receiving, high volume)")
    lines.append("-" * 60)
    newsletters = [c for c in analysis['by_direction'].get('mostly_received', [])
                   if c['total'] >= 10]
    newsletters.sort(key=lambda x: x['total'], reverse=True)
    for c in newsletters[:30]:
        lines.append(f"  {c['total']:>5} <- {c['email']:<45} {c['name'][:25]}")

    # Outreach contacts (mostly sending, potential leads)
    lines.append("\n## OUTREACH CONTACTS (I send more than receive)")
    lines.append("-" * 60)
    outreach = [c for c in analysis['by_direction'].get('mostly_sent', [])
                if c['total'] >= 3 and c['domain'] not in ['organization.example.com', 'infra.example.org']]
    outreach.sort(key=lambda x: x['total'], reverse=True)
    for c in outreach[:30]:
        lines.append(f"  {c['total']:>5} -> {c['email']:<45} {c['name'][:25]}")

    # Stats summary
    lines.append("\n" + "=" * 80)
    lines.append("SUMMARY & RECOMMENDATIONS")
    lines.append("=" * 80)

    high_count = len(analysis['by_frequency'].get('high', []))
    medium_count = len(analysis['by_frequency'].get('medium', []))
    balanced_count = len([c for c in analysis['by_direction'].get('balanced', []) if c['total'] >= 5])

    lines.append(f"""
Contacts worth importing to CRM:
- Organization team: {len(org_contacts)} (internal, auto-import)
- Infrastructure team: {len(infra_contacts)} (internal, auto-import)
- High frequency external: {high_count - len(org_contacts) - len(infra_contacts)} (auto-import)
- Medium frequency external: {medium_count} (review & import)
- Balanced communication: {balanced_count} (likely real relationships)

Suggested groups for CRM:
1. "Organization Team" - organization.example.com domain
2. "Infrastructure Team" - infra.example.org domain
3. "Business Contacts" - high/medium frequency, balanced direction
4. "Investors/VCs" - specific domains like usv.com, a16z.com, etc.
5. "Legal" - law firm domains
6. "Partners" - other company domains with balanced communication
7. "Newsletter Subscriptions" - mostly_received, high volume
""")

    report = '\n'.join(lines)

    if output_file:
        Path(output_file).write_text(report)
        print(f"Report saved to: {output_file}")
    else:
        print(report)

    return report


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Contact Analyzer")
    parser.add_argument("command", choices=["analyze"],
                       help="Command to run")
    parser.add_argument("--account", required=True,
                       help="Gmail account to analyze")
    parser.add_argument("--max", type=int, default=0,
                       help="Max emails to scan (0 = unlimited)")
    parser.add_argument("--output", "-o",
                       help="Output file path")

    args = parser.parse_args()

    if args.command == "analyze":
        analysis = analyze_contacts(args.account, args.max)
        if analysis:
            generate_report(analysis, args.account, args.output)
