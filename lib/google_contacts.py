#!/usr/bin/env python3
"""
Google Contacts fetcher for CRM module.

Fetches contacts from Google People API and exports as vCard or imports directly.
Requires OAuth re-authentication on first use to add contacts scope.

Usage:
    python google_contacts.py fetch --account user@organization.example.com --output contacts.vcf
    python google_contacts.py fetch --account user@organization.example.com --import --space 0-personal
"""

import os
import sys
import json
import pickle
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

# Google API
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Scopes for People API
SCOPES = [
    'https://www.googleapis.com/auth/contacts.readonly',
]

# Credentials paths (same as mail module)
DATA_ROOT = Path(os.environ.get('DATA_ROOT', Path.home() / 'Data'))
CREDS_DIR = DATA_ROOT / '.datacore' / 'env' / 'credentials'
CLIENT_SECRETS = CREDS_DIR / 'google_calendar_client_secret.json'


@dataclass
class GoogleContact:
    """Represents a Google Contact."""
    resource_name: str
    name: str = ""
    given_name: str = ""
    family_name: str = ""
    emails: List[str] = field(default_factory=list)
    phones: List[str] = field(default_factory=list)
    organization: str = ""
    title: str = ""
    photo_url: str = ""

    def to_vcard(self) -> str:
        """Convert to vCard 3.0 format."""
        lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"FN:{self.name}",
        ]

        if self.given_name or self.family_name:
            lines.append(f"N:{self.family_name};{self.given_name};;;")

        for email in self.emails:
            lines.append(f"EMAIL:{email}")

        for phone in self.phones:
            lines.append(f"TEL:{phone}")

        if self.organization:
            lines.append(f"ORG:{self.organization}")

        if self.title:
            lines.append(f"TITLE:{self.title}")

        lines.append("END:VCARD")
        return "\n".join(lines)


class GoogleContactsFetcher:
    """Fetches contacts from Google People API."""

    def __init__(self, account: str):
        self.account = account
        self.token_file = CREDS_DIR / f'contacts_token_{account.replace("@", "_at_")}.pickle'
        self._service = None

    def _get_credentials(self) -> Optional[Credentials]:
        """Get or refresh OAuth credentials."""
        creds = None

        # Load existing token
        if self.token_file.exists():
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)

        # Refresh if expired
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                print(f"Token refresh failed: {e}")
                creds = None

        # New authentication needed
        if not creds or not creds.valid:
            if not CLIENT_SECRETS.exists():
                print(f"Client secrets not found: {CLIENT_SECRETS}")
                print("Copy your Google OAuth client_secrets.json to this location.")
                return None

            print(f"\nAuthenticating for Google Contacts ({self.account})...")
            print("A browser window will open for OAuth consent.\n")

            flow = InstalledAppFlow.from_client_secrets_file(
                str(CLIENT_SECRETS), SCOPES)
            creds = flow.run_local_server(port=0)

            # Save token
            CREDS_DIR.mkdir(parents=True, exist_ok=True)
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)

            print("Authentication successful!")

        return creds

    @property
    def service(self):
        """Lazy-load People API service."""
        if self._service is None:
            creds = self._get_credentials()
            if creds:
                self._service = build('people', 'v1', credentials=creds)
        return self._service

    def fetch_all(self, max_results: int = 2000) -> List[GoogleContact]:
        """
        Fetch all contacts from Google.

        Args:
            max_results: Maximum contacts to fetch

        Returns:
            List of GoogleContact objects
        """
        if not self.service:
            return []

        contacts = []
        page_token = None

        print(f"Fetching contacts from {self.account}...")

        while len(contacts) < max_results:
            try:
                results = self.service.people().connections().list(
                    resourceName='people/me',
                    pageSize=min(1000, max_results - len(contacts)),
                    personFields='names,emailAddresses,phoneNumbers,organizations,photos',
                    pageToken=page_token
                ).execute()

                connections = results.get('connections', [])

                for person in connections:
                    contact = self._parse_person(person)
                    if contact.name or contact.emails:  # Skip empty contacts
                        contacts.append(contact)

                page_token = results.get('nextPageToken')
                if not page_token:
                    break

                print(f"  Fetched {len(contacts)} contacts...")

            except Exception as e:
                print(f"Error fetching contacts: {e}")
                break

        print(f"Total: {len(contacts)} contacts")
        return contacts

    def _parse_person(self, person: Dict[str, Any]) -> GoogleContact:
        """Parse a Person resource into GoogleContact."""
        contact = GoogleContact(resource_name=person.get('resourceName', ''))

        # Names
        names = person.get('names', [])
        if names:
            name = names[0]
            contact.name = name.get('displayName', '')
            contact.given_name = name.get('givenName', '')
            contact.family_name = name.get('familyName', '')

        # Emails
        emails = person.get('emailAddresses', [])
        contact.emails = [e.get('value', '') for e in emails if e.get('value')]

        # Phones
        phones = person.get('phoneNumbers', [])
        contact.phones = [p.get('value', '') for p in phones if p.get('value')]

        # Organization
        orgs = person.get('organizations', [])
        if orgs:
            org = orgs[0]
            contact.organization = org.get('name', '')
            contact.title = org.get('title', '')

        # Photo
        photos = person.get('photos', [])
        if photos:
            contact.photo_url = photos[0].get('url', '')

        return contact

    def export_vcf(self, contacts: List[GoogleContact], output_path: Path) -> int:
        """Export contacts to vCard file."""
        vcards = [c.to_vcard() for c in contacts]
        output_path.write_text("\n".join(vcards))
        return len(vcards)


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Google Contacts Fetcher")
    parser.add_argument('command', choices=['fetch', 'test'],
                        help='Command to run')
    parser.add_argument('--account', required=True,
                        help='Google account email')
    parser.add_argument('--output', type=Path,
                        help='Output vCard file path')
    parser.add_argument('--max', type=int, default=2000,
                        help='Maximum contacts to fetch')

    args = parser.parse_args()

    fetcher = GoogleContactsFetcher(args.account)

    if args.command == 'test':
        if fetcher.service:
            print("Connection successful!")
        else:
            print("Connection failed")
            return 1

    elif args.command == 'fetch':
        contacts = fetcher.fetch_all(max_results=args.max)

        if not contacts:
            print("No contacts found")
            return 1

        # Summary
        with_email = [c for c in contacts if c.emails]
        with_phone = [c for c in contacts if c.phones]
        print(f"\nSummary:")
        print(f"  Total contacts: {len(contacts)}")
        print(f"  With email: {len(with_email)}")
        print(f"  With phone: {len(with_phone)}")

        # Export
        if args.output:
            count = fetcher.export_vcf(contacts, args.output)
            print(f"\nExported {count} contacts to {args.output}")
        else:
            # Default output
            output = Path.cwd() / f'google_contacts_{args.account.split("@")[0]}.vcf'
            count = fetcher.export_vcf(contacts, output)
            print(f"\nExported {count} contacts to {output}")

    return 0


if __name__ == '__main__':
    exit(main())
