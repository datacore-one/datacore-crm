#!/usr/bin/env python3
"""
Inbox Cleanup - Delete emails by category.

Usage:
    python inbox_cleanup.py delete --account user@organization.example.com --category github
    python inbox_cleanup.py delete --account user@organization.example.com --category newsletters
    python inbox_cleanup.py delete --account user@organization.example.com --category automated
"""

import sys
from pathlib import Path
from typing import List, Dict, Any

# Add mail module to path
MODULES_DIR = Path(__file__).parent.parent.parent
sys.path.insert(0, str(MODULES_DIR))

from mail.adapters.gmail import GmailAdapter


# Category definitions - senders/patterns for each category
CATEGORIES = {
    'github': {
        'description': 'GitHub notifications',
        'senders': ['notifications@github.com'],
        'query': 'from:notifications@github.com'
    },
    'newsletters': {
        'description': 'Newsletter emails',
        'patterns': [
            'newsletter', 'substack.com', 'beehiiv.com', 'getrevue.co',
            'mailchimp.com', 'sendgrid.net', 'constantcontact.com',
            'news@', 'digest@', 'weekly@', 'daily@', 'updates@',
            'marketing@', 'info@organization.example.com'
        ],
        # Will build query dynamically
    },
    'automated': {
        'description': 'Automated/System emails',
        'patterns': [
            'noreply', 'no-reply', 'donotreply', 'notifications@',
            'alert@', 'alerts@', 'system@', 'mailer@', 'daemon@',
            'postmaster@', 'bounce@', 'auto@', 'automated@',
            'comments-noreply@docs.google.com', 'drive-shares-noreply@google.com',
            'noreply@kraken.com', 'no-reply@hackmd.io', 'noreply@beehive.infra.example.org',
            'noreply@notify.cloudflare.com', 'no-reply@docsend.com',
            'do-not-reply@trello.com', 'notify@mail.notion.so'
        ],
        # Will build query dynamically
    },
    'transactional': {
        'description': 'Transactional emails (receipts, invoices)',
        'patterns': [
            'receipt', 'invoice', 'order', 'confirmation', 'booking',
            'support@', 'help@', 'service@', 'billing@'
        ],
    }
}


def build_newsletter_query():
    """Build Gmail query for newsletters."""
    # Common newsletter domains and patterns
    domains = [
        'substack.com', 'beehiiv.com', 'getrevue.co', 'mailchimp.com',
        'e.economist.com', 'mail.hotels.com', 'coinlist.co',
        'farnamstreetblog.com', 'theblockcrypto.com', 'mydata.org'
    ]

    # Known newsletter senders from the analysis
    newsletter_senders = [
        'newsletter@techcrunch.com',
        'weekinethereum@substack.com',
        'veradiverdict@substack.com',
        'info@infra.example.org',
        'thedailygwei@substack.com',
        'platformer@substack.com',
        'notboring@substack.com',
        'team@coinlist.co',
        'therundownai@mail.beehiiv.com',
        'info@organization.example.com',
        'info@mail.hotels.com',
        'newsletter@farnamstreetblog.com',
        'hello@mydata.org',
        'newsletter@theblockcrypto.com',
        'newsletters@e.economist.com',
        'news@daily.therundown.ai',
        'emailteam@emails.hbr.org',
        'hello@betoken.fund',
        'thedefiant@substack.com',
        'coinmetrics@substack.com',
        'superhuman@mail.joinsuperhuman.ai',
        'noreply-analytics@google.com',
        'news@send.zapier.com',
        'mailings@aiforgood.itu.int',
        'newsletters@coindesk.com',
        'info@mail.fiscal.ai',
        'hello@walrus.xyz',
        'no-reply@mail.thedefiant.io'
    ]

    # Build OR query
    parts = [f'from:{sender}' for sender in newsletter_senders]
    return ' OR '.join(parts)


def build_automated_query():
    """Build Gmail query for automated emails."""
    # Known automated senders from the analysis
    automated_senders = [
        'notifications@github.com',  # This overlaps but we handle github separately
        'noreply@kraken.com',
        'comments-noreply@docs.google.com',
        'no-reply@hackmd.io',
        'drive-shares-noreply@google.com',
        'noreply@beehive.infra.example.org',
        'noreply@notify.cloudflare.com',
        'no-reply@docsend.com',
        'do-not-reply@trello.com',
        'notify@mail.notion.so',
        'noreply@md.getharvest.com',
        'noreply@github.com',
        'git@github.com',
        'notifications@circleci.com',
        'noreply@google.com',
        'calendar-notification@google.com',
        'no-reply@accounts.google.com',
        'noreply-local-guides@google.com',
        'noreply-drivesharing@google.com',
        'noreply-surveys@google.com'
    ]

    # Exclude github since we handle it separately
    automated_senders = [s for s in automated_senders if 'github.com' not in s]

    parts = [f'from:{sender}' for sender in automated_senders]
    return ' OR '.join(parts)


def delete_by_query(adapter: GmailAdapter, query: str, description: str, dry_run: bool = False) -> int:
    """
    Delete all emails matching a query.

    Args:
        adapter: Gmail adapter
        query: Gmail search query
        description: What we're deleting (for logging)
        dry_run: If True, only count without deleting

    Returns:
        Number of emails deleted
    """
    print(f"\nSearching for: {description}")
    print(f"Query: {query[:100]}..." if len(query) > 100 else f"Query: {query}")

    # Get all message IDs matching query
    message_ids = adapter.list_message_ids(query=query, labels=[])
    total = len(message_ids)

    print(f"Found {total:,} emails to delete")

    if total == 0:
        return 0

    if dry_run:
        print("DRY RUN - no emails deleted")
        return total

    # Delete in batches
    deleted = 0
    batch_size = 100

    service = adapter._get_service()
    if not service:
        print("ERROR: Could not get Gmail service")
        return 0

    for i in range(0, total, batch_size):
        batch = message_ids[i:i+batch_size]

        for msg_id in batch:
            try:
                service.users().messages().delete(userId='me', id=msg_id).execute()
                deleted += 1
            except Exception as e:
                print(f"  Error deleting {msg_id}: {e}")

        pct = (deleted / total * 100)
        print(f"  Deleted {deleted:,}/{total:,} ({pct:.1f}%)", end='\r')

    print(f"\n  Completed: {deleted:,} emails permanently deleted")
    return deleted


def cleanup_inbox(account: str, categories: List[str], dry_run: bool = False) -> Dict[str, int]:
    """
    Clean up inbox by deleting emails in specified categories.

    Args:
        account: Gmail account
        categories: List of category names to delete
        dry_run: If True, only count without deleting

    Returns:
        Dict of category -> count deleted
    """
    adapter = GmailAdapter({"address": account})

    if not adapter.is_configured():
        print(f"ERROR: Account {account} not configured.")
        return {}

    results = {}

    for category in categories:
        if category == 'github':
            query = 'from:notifications@github.com'
            deleted = delete_by_query(adapter, query, 'GitHub notifications', dry_run)
            results['github'] = deleted

        elif category == 'newsletters':
            query = build_newsletter_query()
            deleted = delete_by_query(adapter, query, 'Newsletter emails', dry_run)
            results['newsletters'] = deleted

        elif category == 'automated':
            query = build_automated_query()
            deleted = delete_by_query(adapter, query, 'Automated emails', dry_run)
            results['automated'] = deleted

    # Summary
    print("\n" + "=" * 60)
    print("CLEANUP SUMMARY")
    print("=" * 60)
    total_deleted = 0
    for cat, count in results.items():
        print(f"  {cat}: {count:,} emails {'would be' if dry_run else ''} deleted")
        total_deleted += count
    print(f"  TOTAL: {total_deleted:,} emails")

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Inbox Cleanup")
    parser.add_argument("command", choices=["delete", "count"],
                       help="Command: delete or count (dry run)")
    parser.add_argument("--account", required=True,
                       help="Gmail account")
    parser.add_argument("--categories", nargs='+',
                       choices=['github', 'newsletters', 'automated', 'all'],
                       default=['all'],
                       help="Categories to delete")

    args = parser.parse_args()

    # Expand 'all'
    if 'all' in args.categories:
        categories = ['github', 'newsletters', 'automated']
    else:
        categories = args.categories

    dry_run = args.command == 'count'

    if not dry_run:
        print("=" * 60)
        print("WARNING: PERMANENT DELETION")
        print("=" * 60)
        print(f"This will PERMANENTLY delete emails from: {account}")
        print(f"Categories: {', '.join(categories)}")
        print("\nThis action CANNOT be undone!")
        confirm = input("Type 'DELETE' to confirm: ")
        if confirm != 'DELETE':
            print("Aborted.")
            sys.exit(1)

    cleanup_inbox(args.account, categories, dry_run=dry_run)
