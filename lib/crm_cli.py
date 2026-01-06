#!/usr/bin/env python3
"""
CRM CLI - Command-line interface for CRM module.

Unified entry point for all CRM operations:
- status: Show network overview and relationship distribution
- scan: Run adapters to extract interactions
- contact: Look up specific contact details
- attention: List contacts needing follow-up
- trip: Prepare briefing for upcoming trip/event
- import: Import contacts from vCard files (Apple Contacts, Gmail)
- enrich: Enrich contacts with email interaction history

Usage:
    python crm_cli.py status
    python crm_cli.py scan --days 7
    python crm_cli.py contact "John Smith"
    python crm_cli.py attention
    python crm_cli.py trip "Dubai, Dec 15-20"
    python crm_cli.py import contacts.vcf --space 0-personal
    python crm_cli.py enrich --all-drafts --gmail your@gmail.com
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

# Add lib to path
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent / 'lib'))

from adapters import get_adapters, scan_all_adapters, aggregate_by_contact, Interaction
from index_compiler import IndexCompiler


def format_status_output(index: Dict[str, Any]) -> str:
    """Format index status for display."""
    lines = []
    summary = index.get('summary', {})

    lines.append("CRM STATUS")
    lines.append("=" * 50)
    lines.append("")

    # Overview
    lines.append("Overview")
    lines.append("-" * 40)
    total = summary.get('total', 0)
    people = summary.get('people', 0)
    companies = summary.get('companies', 0)
    lines.append(f"Total contacts: {total} ({people} people, {companies} companies)")
    lines.append("")

    # By status
    by_status = summary.get('by_status', {})
    if by_status:
        active = by_status.get('active', 0)
        warming = by_status.get('warming', 0)
        cooling = by_status.get('cooling', 0)
        dormant = by_status.get('dormant', 0)

        lines.append("Relationship Health")
        lines.append("-" * 40)
        lines.append(f"  Active (>0.7):    {active:3} {'█' * active}")
        lines.append(f"  Warming (0.5-0.7):{warming:3} {'▓' * warming}")
        lines.append(f"  Cooling (0.4-0.5):{cooling:3} {'▒' * cooling}")
        lines.append(f"  Dormant (<0.4):   {dormant:3} {'░' * dormant}")
        lines.append("")

    # By space
    by_space = summary.get('by_space', {})
    if by_space:
        lines.append("By Space")
        lines.append("-" * 40)
        for space, count in sorted(by_space.items()):
            lines.append(f"  {space}: {count}")
        lines.append("")

    # Compiled timestamp
    compiled = index.get('compiled_at', '')
    if compiled:
        lines.append(f"Last compiled: {compiled[:19]}")

    return '\n'.join(lines)


def format_contact_output(contact: Dict[str, Any]) -> str:
    """Format contact details for display."""
    lines = []

    name = contact.get('name', 'Unknown')
    lines.append(name.upper())
    lines.append("=" * len(name))
    lines.append("")

    # Basic info
    contact_type = contact.get('type', 'unknown')
    space = contact.get('space', 'unknown')
    status = contact.get('status', 'unknown')
    lines.append(f"Type: {contact_type} | Space: {space} | Status: {status}")

    if contact.get('organization'):
        lines.append(f"Organization: {contact['organization']}")
    if contact.get('role'):
        lines.append(f"Role: {contact['role']}")
    if contact.get('tags'):
        lines.append(f"Tags: {', '.join(contact['tags'])}")
    lines.append("")

    # Score
    score = contact.get('score', {})
    if score:
        lines.append("Relationship")
        lines.append("-" * 40)
        score_val = score.get('value', 0)
        score_status = score.get('status', 'unknown')
        trend = score.get('trend', 'stable')
        last = score.get('last_interaction', 'Never')

        lines.append(f"  Score: {score_val:.2f} ({score_status})")
        lines.append(f"  Trend: {trend}")
        lines.append(f"  Last interaction: {last}")

        components = score.get('components', {})
        if components:
            lines.append("")
            lines.append("  Components:")
            lines.append(f"    Recency:     {components.get('recency', 0):.2f}")
            lines.append(f"    Frequency:   {components.get('frequency', 0):.2f}")
            lines.append(f"    Depth:       {components.get('depth', 0):.2f}")
            lines.append(f"    Reciprocity: {components.get('reciprocity', 0):.2f}")

    lines.append("")
    lines.append(f"Source: {contact.get('source', 'unknown')}")

    return '\n'.join(lines)


def format_attention_output(contacts: List[Dict[str, Any]]) -> str:
    """Format attention-needed list for display."""
    lines = []

    lines.append("CONTACTS NEEDING ATTENTION")
    lines.append("=" * 50)
    lines.append("")

    if not contacts:
        lines.append("No contacts need immediate attention.")
        return '\n'.join(lines)

    for contact in contacts[:15]:  # Show top 15
        name = contact.get('name', 'Unknown')
        contact_type = contact.get('type', '')
        reason = contact.get('reason', '')
        space = contact.get('space', '')

        lines.append(f"• {name} ({contact_type})")
        lines.append(f"    {reason}")
        lines.append(f"    Space: {space}")
        lines.append("")

    if len(contacts) > 15:
        lines.append(f"... and {len(contacts) - 15} more")

    return '\n'.join(lines)


def format_scan_output(results: Dict[str, List[Interaction]], by_contact: Dict[str, List[Interaction]]) -> str:
    """Format scan results for display."""
    lines = []

    total = sum(len(v) for v in results.values())

    lines.append("CRM SCAN RESULTS")
    lines.append("=" * 50)
    lines.append("")

    # By channel
    lines.append("Interactions by Channel")
    lines.append("-" * 40)
    for channel, interactions in sorted(results.items()):
        lines.append(f"  {channel}: {len(interactions)}")
    lines.append(f"  Total: {total}")
    lines.append("")

    # By contact (top 10)
    if by_contact:
        lines.append("Top Contacts (by interaction count)")
        lines.append("-" * 40)
        sorted_contacts = sorted(by_contact.items(), key=lambda x: len(x[1]), reverse=True)
        for contact_name, interactions in sorted_contacts[:10]:
            lines.append(f"  {contact_name}: {len(interactions)}")
            # Show most recent interaction
            if interactions:
                latest = interactions[0]
                lines.append(f"      Last: {latest.date} | {latest.channel} | {latest.interaction_type}")
        lines.append("")

    return '\n'.join(lines)


def format_trip_output(destination: str, contacts: List[Dict[str, Any]], interactions: Dict[str, List[Interaction]]) -> str:
    """Format trip preparation briefing."""
    lines = []

    lines.append(f"TRIP PREPARATION: {destination}")
    lines.append("=" * 50)
    lines.append("")

    # Filter contacts by location/tags (basic matching)
    dest_lower = destination.lower()
    relevant = []
    dormant_reconnect = []

    for contact in contacts:
        score = contact.get('score', {})
        score_status = score.get('status', 'unknown')

        # Check if contact might be relevant to destination
        # (This is a simple heuristic - real implementation would use location field)
        tags = contact.get('tags', [])
        name = contact.get('name', '')

        if score_status == 'dormant':
            dormant_reconnect.append(contact)
        elif score_status in ['active', 'warming']:
            relevant.append(contact)

    # Show relevant contacts
    if relevant:
        lines.append("ACTIVE CONTACTS")
        lines.append("-" * 40)
        for contact in relevant[:5]:
            name = contact.get('name', '')
            org = contact.get('organization', '')
            score = contact.get('score', {})
            last = score.get('last_interaction', 'Unknown')
            lines.append(f"• [[{name}]] {f'({org})' if org else ''}")
            lines.append(f"    Last: {last} | Status: {score.get('status', '')}")
        lines.append("")

    # Show dormant worth reconnecting
    if dormant_reconnect:
        lines.append("DORMANT - WORTH RECONNECTING")
        lines.append("-" * 40)
        for contact in dormant_reconnect[:5]:
            name = contact.get('name', '')
            score = contact.get('score', {})
            last = score.get('last_interaction', 'Unknown')
            lines.append(f"• [[{name}]]")
            lines.append(f"    Last: {last}")
        lines.append("")

    # Suggested actions
    lines.append("SUGGESTED PRE-TRIP ACTIONS")
    lines.append("-" * 40)
    lines.append("1. TODO Review active contacts for meeting opportunities   :CRM:")
    lines.append("2. TODO Reach out to dormant contacts for reconnection     :CRM:")
    lines.append("3. TODO Prepare talking points for key relationships       :CRM:")
    lines.append("")
    lines.append("Add these tasks to next_actions.org? (manual step)")

    return '\n'.join(lines)


def cmd_status(args):
    """Show CRM status overview."""
    compiler = IndexCompiler()

    # Load or compile index
    index = compiler.load_index()
    if not index or args.refresh:
        print("Compiling index...")
        index = compiler.compile_index(scan_days=args.days)
        compiler.save_index(index)

    print(format_status_output(index))


def cmd_scan(args):
    """Scan for new interactions."""
    print(f"Scanning last {args.days} days for interactions...")
    print("")

    results = scan_all_adapters(days=args.days)
    all_interactions = []
    for interactions in results.values():
        all_interactions.extend(interactions)

    by_contact = aggregate_by_contact(all_interactions)

    print(format_scan_output(results, by_contact))

    # Update index after scan
    if args.update_index:
        print("Updating index...")
        compiler = IndexCompiler()
        index = compiler.compile_index(scan_days=90)
        compiler.save_index(index)
        print(f"Index saved to {compiler.index_path}")


def cmd_contact(args):
    """Look up specific contact."""
    compiler = IndexCompiler()
    contact = compiler.get_contact(args.name)

    if contact:
        print(format_contact_output(contact))
    else:
        print(f"Contact not found: {args.name}")
        print("")
        print("Try:")
        print("  python crm_cli.py status  # See all contacts")
        print("  python crm_cli.py scan    # Scan for new interactions")


def cmd_attention(args):
    """List contacts needing attention."""
    compiler = IndexCompiler()
    contacts = compiler.get_attention_needed(threshold_days=args.threshold)

    print(format_attention_output(contacts))


def cmd_trip(args):
    """Prepare trip briefing."""
    compiler = IndexCompiler()
    index = compiler.load_index()

    if not index:
        print("No index found. Running scan first...")
        index = compiler.compile_index(scan_days=90)
        compiler.save_index(index)

    contacts = index.get('contacts', [])

    # Get recent interactions for context
    results = scan_all_adapters(days=30)
    all_interactions = []
    for interactions in results.values():
        all_interactions.extend(interactions)
    by_contact = aggregate_by_contact(all_interactions)

    print(format_trip_output(args.destination, contacts, by_contact))


def cmd_import(args):
    """Import contacts from vCard files."""
    from vcard_adapter import VCardImporter

    data_root = Path(args.data_root)
    files = [Path(f) for f in args.files]

    # Validate files exist
    for f in files:
        if not f.exists():
            print(f"Error: File not found: {f}")
            return

    importer = VCardImporter(data_root, args.space)
    report = importer.import_vcards(
        files,
        dry_run=args.dry_run,
        skip_existing=not args.include_existing
    )

    print(f"\n{'Preview' if args.dry_run else 'Import'} Results:")
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

    if not args.dry_run and report.new_contacts > 0:
        from datetime import date
        # Save report
        report_dir = data_root / args.space / 'content' / 'reports'
        report_dir.mkdir(parents=True, exist_ok=True)
        report_file = report_dir / f"{date.today().isoformat()}-contact-import.md"
        report_file.write_text(importer.generate_report_markdown(report))
        print(f"\n  Report saved to: {report_file}")


def cmd_enrich(args):
    """Enrich contacts with email interaction history."""
    from email_enricher import ContactEnricher

    data_root = Path(args.data_root)

    if not args.gmail:
        print("Error: --gmail account required for email enrichment")
        print("Usage: python crm_cli.py enrich --gmail your@gmail.com --all-drafts")
        return

    enricher = ContactEnricher(data_root, args.gmail, args.space)

    if args.all_drafts:
        print(f"\nEnriching all draft contacts in {args.space}...")
        results = enricher.enrich_all_drafts()

        print(f"\nResults:")
        print(f"  Total drafts: {results['total']}")
        print(f"  Enriched: {results['enriched']}")
        print(f"  No email: {results['no_email']}")
        print(f"  No history: {results['no_history']}")

        if results['errors']:
            print(f"\n  Errors:")
            for error in results['errors']:
                print(f"    - {error}")

    elif args.email:
        history = enricher.enrich_by_email(args.email)
        if history:
            print(f"\nEnriched contact with {history.total_messages} emails")
            print(f"  First contact: {history.first_contact}")
            print(f"  Last contact: {history.last_contact}")
            print(f"  Topics: {', '.join(history.topics)}")
        else:
            print(f"Could not enrich contact with email: {args.email}")
    else:
        print("Specify --email or --all-drafts")
        print("Usage:")
        print("  python crm_cli.py enrich --gmail you@gmail.com --email contact@example.com")
        print("  python crm_cli.py enrich --gmail you@gmail.com --all-drafts")


def main():
    parser = argparse.ArgumentParser(
        description="CRM CLI - Contact Relationship Management",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python crm_cli.py status              Show network overview
  python crm_cli.py scan --days 7       Scan last 7 days
  python crm_cli.py contact "John"      Look up John
  python crm_cli.py attention           Show who needs follow-up
  python crm_cli.py trip "Dubai"        Prepare for Dubai trip
  python crm_cli.py import contacts.vcf Import vCard contacts
  python crm_cli.py enrich --gmail me@gmail.com --all-drafts
        """
    )

    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # status
    status_parser = subparsers.add_parser('status', help='Show network status')
    status_parser.add_argument('--refresh', action='store_true', help='Recompile index')
    status_parser.add_argument('--days', type=int, default=90, help='Days for scoring')
    status_parser.set_defaults(func=cmd_status)

    # scan
    scan_parser = subparsers.add_parser('scan', help='Scan for interactions')
    scan_parser.add_argument('--days', type=int, default=7, help='Days to scan')
    scan_parser.add_argument('--update-index', action='store_true', help='Update index after scan')
    scan_parser.set_defaults(func=cmd_scan)

    # contact
    contact_parser = subparsers.add_parser('contact', help='Look up contact')
    contact_parser.add_argument('name', help='Contact name to look up')
    contact_parser.set_defaults(func=cmd_contact)

    # attention
    attention_parser = subparsers.add_parser('attention', help='Contacts needing attention')
    attention_parser.add_argument('--threshold', type=int, default=30, help='Dormant threshold days')
    attention_parser.set_defaults(func=cmd_attention)

    # trip
    trip_parser = subparsers.add_parser('trip', help='Trip preparation')
    trip_parser.add_argument('destination', help='Trip destination/event')
    trip_parser.set_defaults(func=cmd_trip)

    # import
    import_parser = subparsers.add_parser('import', help='Import contacts from vCard')
    import_parser.add_argument('files', nargs='+', help='vCard files to import')
    import_parser.add_argument('--space', default='0-personal', help='Target space')
    import_parser.add_argument('--dry-run', action='store_true', help='Preview without creating')
    import_parser.add_argument('--include-existing', action='store_true', help='Import duplicates too')
    import_parser.add_argument('--data-root', default=str(Path.home() / 'Data'), help='Data root path')
    import_parser.set_defaults(func=cmd_import)

    # enrich
    enrich_parser = subparsers.add_parser('enrich', help='Enrich contacts with email history')
    enrich_parser.add_argument('--gmail', help='Gmail account to query')
    enrich_parser.add_argument('--email', help='Enrich specific contact by email')
    enrich_parser.add_argument('--all-drafts', action='store_true', help='Enrich all draft contacts')
    enrich_parser.add_argument('--space', default='0-personal', help='Target space')
    enrich_parser.add_argument('--data-root', default=str(Path.home() / 'Data'), help='Data root path')
    enrich_parser.set_defaults(func=cmd_enrich)

    args = parser.parse_args()

    if args.command:
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
