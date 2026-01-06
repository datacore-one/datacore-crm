#!/usr/bin/env python3
"""
Relationship CLI - Index and query the personal relationship database.

Usage:
    # Index Thunderbird mbox
    python relationship_cli.py index --account team-a

    # Search and filter
    python relationship_cli.py search "investor"
    python relationship_cli.py search --domain team-b.example.com

    # Relationship analysis
    python relationship_cli.py top --by frequency --limit 50
    python relationship_cli.py reconnect --silence-days 90
    python relationship_cli.py one-way --direction sent

    # Graph analysis
    python relationship_cli.py graph stats
    python relationship_cli.py graph communities

    # Database stats
    python relationship_cli.py stats
"""

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional

from relationship_db import RelationshipDB

# Configuration
DATA_DIR = Path.home() / "Data"
DB_PATH = DATA_DIR / ".datacore" / "state" / "relationships.db"
RULES_PATH = DATA_DIR / ".datacore" / "modules" / "mail" / "rules.base.yaml"
KEY_PATH = DATA_DIR / ".datacore" / "env" / "relationships.key"

# Thunderbird profile locations
THUNDERBIRD_BASE = Path.home() / "Library" / "Thunderbird" / "Profiles"

# Account configurations
ACCOUNTS = {
    \'team-a\': {
        'email': 'user@example.com',
        'imap_server': 'imap.gmail-1.com',
        'mbox_path': '[Gmail].sbd/All Mail'
    },
    \'team-b\': {
        'email': 'user@example.com',
        'imap_server': 'imap.gmail-4.com',  # Adjust as needed
        'mbox_path': '[Gmail].sbd/All Mail'
    }
}

# Default sensitive domains (legal, medical)
DEFAULT_SENSITIVE_DOMAINS = [
    "*-law.eu",
    "*-law.si",
    "*.legal.ch",
    "novak-law.eu",
    "*.health",
    "doctor*",
    "clinic*"
]


def get_passphrase() -> Optional[str]:
    """Get database passphrase from file or environment."""
    # Try environment variable first
    passphrase = os.environ.get('RELATIONSHIP_DB_KEY')
    if passphrase:
        return passphrase

    # Try key file
    if KEY_PATH.exists():
        return KEY_PATH.read_text().strip()

    # Generate new key
    import secrets
    passphrase = secrets.token_urlsafe(32)
    KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    KEY_PATH.write_text(passphrase)
    KEY_PATH.chmod(0o600)
    print(f"Generated new passphrase at {KEY_PATH}")

    return passphrase


def find_thunderbird_profile() -> Optional[Path]:
    """Find the default Thunderbird profile."""
    if not THUNDERBIRD_BASE.exists():
        return None

    profiles = list(THUNDERBIRD_BASE.glob("*.default*"))
    if profiles:
        return profiles[0]

    # Try any profile
    profiles = list(THUNDERBIRD_BASE.iterdir())
    if profiles:
        return profiles[0]

    return None


def get_mbox_path(account: str) -> Optional[Path]:
    """Get mbox path for account."""
    if account not in ACCOUNTS:
        print(f"Unknown account: {account}")
        print(f"Available accounts: {', '.join(ACCOUNTS.keys())}")
        return None

    config = ACCOUNTS[account]
    profile = find_thunderbird_profile()

    if not profile:
        print("Could not find Thunderbird profile")
        return None

    mbox_path = profile / "ImapMail" / config['imap_server'] / config['mbox_path']

    if not mbox_path.exists():
        print(f"Mbox file not found: {mbox_path}")
        # Try to list available mbox files
        imap_dir = profile / "ImapMail" / config['imap_server']
        if imap_dir.exists():
            print(f"\nAvailable in {imap_dir}:")
            for f in imap_dir.rglob("*"):
                if f.is_file() and not f.suffix:
                    print(f"  {f.relative_to(imap_dir)}")
        return None

    return mbox_path


def cmd_index(args):
    """Index mbox files into relationship database."""
    accounts = args.accounts if args.accounts else [\'team-a\']

    passphrase = get_passphrase() if not args.no_encrypt else None

    with RelationshipDB(str(DB_PATH), passphrase) as db:
        for account in accounts:
            mbox_path = get_mbox_path(account)
            if not mbox_path:
                continue

            config = ACCOUNTS[account]
            print(f"\nIndexing {account} ({config['email']})")
            print(f"Mbox: {mbox_path}")
            print(f"Size: {mbox_path.stat().st_size / 1024 / 1024:.1f} MB")

            def progress(current, total):
                pct = (current / total * 100) if total else 0
                print(f"\r  Processed {current:,}/{total:,} ({pct:.1f}%)...", end='', flush=True)

            stats = db.index_mbox(
                mbox_path=str(mbox_path),
                my_email=config['email'],
                rules_path=str(RULES_PATH),
                sensitive_domains=DEFAULT_SENSITIVE_DOMAINS,
                excluded_domains=[],
                progress_callback=progress,
                max_messages=args.max if args.max else 0
            )

            print(f"\n\nIndexing complete:")
            print(f"  Processed: {stats['processed']:,}")
            print(f"  Contacts created: {stats['contacts_created']:,}")
            print(f"  Contacts updated: {stats['contacts_updated']:,}")
            print(f"  Interactions: {stats['interactions_added']:,}")
            print(f"  Threads: {stats['threads_tracked']:,}")
            print(f"  Skipped: {stats['skipped']:,}")

        # Compute scores
        print("\nComputing relationship scores...")
        db.compute_scores()

        # Compute graph metrics
        print("Computing graph metrics...")
        db.compute_graph_metrics()

        print("\nDone!")


def cmd_stats(args):
    """Show database statistics."""
    passphrase = get_passphrase() if not args.no_encrypt else None

    with RelationshipDB(str(DB_PATH), passphrase) as db:
        stats = db.get_stats()

        print("Relationship Database Statistics")
        print("=" * 50)
        print(f"Database: {DB_PATH}")
        print(f"Encrypted: {stats['encrypted']}")
        print()
        print(f"Contacts: {stats['total_contacts']:,}")
        print(f"  - Sensitive: {stats['sensitive_contacts']:,}")
        print(f"Interactions: {stats['total_interactions']:,}")
        print(f"  - Sent: {stats['total_sent']:,}")
        print(f"  - Received: {stats['total_received']:,}")
        print(f"Threads: {stats['total_threads']:,}")
        print(f"Communities: {stats['total_communities']}")


def cmd_search(args):
    """Search contacts."""
    passphrase = get_passphrase() if not args.no_encrypt else None

    with RelationshipDB(str(DB_PATH), passphrase) as db:
        if args.domain:
            results = db.get_all_contacts(domain=args.domain, limit=args.limit)
            print(f"Contacts in domain: {args.domain}")
        elif args.community:
            results = db.get_all_contacts(community_id=args.community, limit=args.limit)
            print(f"Contacts in community: {args.community}")
        else:
            results = db.search(args.query, limit=args.limit)
            print(f"Search results for: {args.query}")

        print("=" * 80)

        for c in results:
            total = (c['sent_count'] or 0) + (c['received_count'] or 0)
            direction = get_direction_indicator(c)
            sensitive = " [SENSITIVE]" if c['is_sensitive'] else ""

            print(f"{total:>5} {direction} {c['email']:<45} {(c['name'] or '')[:25]}{sensitive}")

        print(f"\nTotal: {len(results)} contacts")


def cmd_top(args):
    """Show top contacts by metric."""
    passphrase = get_passphrase() if not args.no_encrypt else None

    with RelationshipDB(str(DB_PATH), passphrase) as db:
        results = db.get_top_contacts(by=args.by, limit=args.limit)

        print(f"Top {args.limit} contacts by {args.by}")
        print("=" * 80)

        for c in results:
            total = (c['sent_count'] or 0) + (c['received_count'] or 0)
            direction = get_direction_indicator(c)

            # Show relevant score
            if args.by == 'frequency':
                score = f"freq={c['frequency_score']:.2f}/mo" if c['frequency_score'] else ""
            elif args.by == 'recency':
                score = f"recency={c['recency_score']:.2f}" if c['recency_score'] else ""
            elif args.by == 'centrality':
                score = f"centrality={c['degree_centrality']:.4f}" if c['degree_centrality'] else ""
            else:
                score = ""

            print(f"{total:>5} {direction} {c['email']:<40} {score}")


def cmd_reconnect(args):
    """Show contacts to reconnect with."""
    passphrase = get_passphrase() if not args.no_encrypt else None

    with RelationshipDB(str(DB_PATH), passphrase) as db:
        results = db.get_reconnection_candidates(
            silence_days=args.silence_days,
            min_past_frequency=args.min_frequency,
            limit=args.limit
        )

        print(f"Reconnection candidates (no contact in {args.silence_days}+ days)")
        print("=" * 80)

        for c in results:
            total = (c['sent_count'] or 0) + (c['received_count'] or 0)
            topics = json.loads(c['topics']) if c['topics'] else []

            print(f"{total:>5} emails | last: {c['last_seen']}")
            print(f"      {c['email']} ({c['name'] or 'no name'})")
            if topics:
                print(f"      Topics: {', '.join(topics[:5])}")
            print()


def cmd_oneway(args):
    """Show one-way contacts."""
    passphrase = get_passphrase() if not args.no_encrypt else None

    with RelationshipDB(str(DB_PATH), passphrase) as db:
        results = db.get_one_way_contacts(
            direction=args.direction,
            min_interactions=args.min,
            limit=args.limit
        )

        if args.direction == 'sent':
            print("Contacts I send to but rarely reply (potential follow-up needed)")
        else:
            print("Contacts who send to me but I rarely reply (newsletters or missed emails)")

        print("=" * 80)

        for c in results:
            sent = c['sent_count'] or 0
            received = c['received_count'] or 0

            print(f"  {sent:>4} sent / {received:>4} received | {c['email']} ({c['name'] or ''})")


def cmd_graph(args):
    """Graph analysis commands."""
    passphrase = get_passphrase() if not args.no_encrypt else None

    with RelationshipDB(str(DB_PATH), passphrase) as db:
        if args.subcommand == 'stats':
            try:
                G = db.build_graph()
                print("Graph Statistics")
                print("=" * 50)
                print(f"Nodes: {len(G.nodes):,}")
                print(f"Edges: {len(G.edges):,}")

                if len(G.nodes) > 0:
                    import networkx as nx
                    print(f"Density: {nx.density(G):.4f}")
                    if nx.is_connected(G):
                        print(f"Diameter: {nx.diameter(G)}")
                    else:
                        print(f"Connected components: {nx.number_connected_components(G)}")

            except ImportError:
                print("NetworkX not installed. Cannot compute graph stats.")

        elif args.subcommand == 'communities':
            communities = db.get_communities()

            print("Contact Communities")
            print("=" * 80)

            for comm in communities:
                print(f"\nCommunity {comm['community_id']}: {comm['member_count']} members")
                print(f"  Top domains: {', '.join(comm['top_domains'])}")
                print(f"  Sample: {', '.join(comm['sample_emails'][:5])}")

        elif args.subcommand == 'compute':
            print("Computing graph metrics...")
            db.compute_graph_metrics()
            print("Done!")


def get_direction_indicator(contact: Dict) -> str:
    """Get direction indicator for contact."""
    sent = contact.get('sent_count', 0) or 0
    received = contact.get('received_count', 0) or 0
    total = sent + received

    if total == 0:
        return "   "

    ratio = sent / total
    if ratio > 0.7:
        return " ->"  # I send more
    elif ratio < 0.3:
        return "<- "  # They send more
    else:
        return "<->"  # Balanced


def main():
    parser = argparse.ArgumentParser(
        description="Relationship Database CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument(
        '--no-encrypt', action='store_true',
        help='Use unencrypted database'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Index command
    index_parser = subparsers.add_parser('index', help='Index mbox files')
    index_parser.add_argument(
        '--accounts', nargs='+', choices=list(ACCOUNTS.keys()),
        help='Accounts to index (default: team-a)'
    )
    index_parser.add_argument(
        '--max', type=int, default=0,
        help='Max messages to process (0 = all)'
    )

    # Stats command
    subparsers.add_parser('stats', help='Show database statistics')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search contacts')
    search_parser.add_argument('query', nargs='?', default='', help='Search query')
    search_parser.add_argument('--domain', help='Filter by domain')
    search_parser.add_argument('--community', type=int, help='Filter by community ID')
    search_parser.add_argument('--limit', type=int, default=50, help='Max results')

    # Top command
    top_parser = subparsers.add_parser('top', help='Top contacts by metric')
    top_parser.add_argument(
        '--by', choices=['frequency', 'recency', 'centrality', 'total'],
        default='frequency', help='Metric to sort by'
    )
    top_parser.add_argument('--limit', type=int, default=50, help='Max results')

    # Reconnect command
    reconnect_parser = subparsers.add_parser('reconnect', help='Reconnection candidates')
    reconnect_parser.add_argument(
        '--silence-days', type=int, default=90,
        help='Days since last contact'
    )
    reconnect_parser.add_argument(
        '--min-frequency', type=float, default=0.5,
        help='Minimum past frequency (emails/month)'
    )
    reconnect_parser.add_argument('--limit', type=int, default=20, help='Max results')

    # One-way command
    oneway_parser = subparsers.add_parser('one-way', help='One-way contacts')
    oneway_parser.add_argument(
        '--direction', choices=['sent', 'received'],
        default='sent', help='Direction of one-way communication'
    )
    oneway_parser.add_argument('--min', type=int, default=3, help='Min interactions')
    oneway_parser.add_argument('--limit', type=int, default=50, help='Max results')

    # Graph command
    graph_parser = subparsers.add_parser('graph', help='Graph analysis')
    graph_parser.add_argument(
        'subcommand', choices=['stats', 'communities', 'compute'],
        help='Graph subcommand'
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Check if database exists for non-index commands
    if args.command != 'index' and not DB_PATH.exists():
        print(f"Database not found: {DB_PATH}")
        print("Run 'relationship_cli.py index' first to create it.")
        return

    if args.command == 'index':
        cmd_index(args)
    elif args.command == 'stats':
        cmd_stats(args)
    elif args.command == 'search':
        cmd_search(args)
    elif args.command == 'top':
        cmd_top(args)
    elif args.command == 'reconnect':
        cmd_reconnect(args)
    elif args.command == 'one-way':
        cmd_oneway(args)
    elif args.command == 'graph':
        cmd_graph(args)


if __name__ == "__main__":
    main()
