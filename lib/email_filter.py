#!/usr/bin/env python3
"""
Email filter for CRM module - Non-person email detection.

Filters out system, bot, and automated emails during contact extraction.
"""

import re
from typing import Optional, Tuple
from dataclasses import dataclass


@dataclass
class EmailValidationResult:
    """Result of email validation."""
    is_person: bool
    rejection_reason: Optional[str] = None


class EmailFilter:
    """Filter non-person emails from contact extraction."""

    # Non-person email prefixes
    NON_PERSON_PREFIXES = {
        'noreply', 'no-reply', 'donotreply', 'do-not-reply',
        'notification', 'notifications', 'notify',
        'alert', 'alerts',
        'billing', 'invoice', 'invoices', 'payment', 'payments',
        'support', 'help', 'helpdesk',
        'info', 'hello', 'hi', 'contact',
        'sales', 'marketing',
        'admin', 'administrator', 'webmaster', 'postmaster',
        'system', 'daemon', 'mailer-daemon',
        'automated', 'auto', 'bot',
        'newsletter', 'news', 'updates',
        'security', 'bounce', 'bounces',
        'privacy', 'legal', 'compliance',
        'unsubscribe', 'abuse', 'spam',
        'team', 'all', 'everyone', 'group',
    }

    # Non-person email domains (known bot/system services)
    NON_PERSON_DOMAINS = {
        'notifications.github.com',
        'noreply.github.com',
        'reply.github.com',
        'calendly.com',
        'donotreply.slack.com',
        'notifications.slack.com',
        'notification.notion.so',
        'notify.notion.so',
        'updates.linkedin.com',
        'messages.linkedin.com',
        'notifications.google.com',
        'calendar-notification.google.com',
        'bounces.google.com',
        'mail-noreply.google.com',
        'facebookmail.com',
        'notification.facebook.com',
        'noreply.medium.com',
        'newsletters.medium.com',
        'update.grammarly.com',
        'newsletter.substack.com',
        'noreply.apple.com',
        'do_not_reply.apple.com',
        'email.apple.com',
    }

    # Generic notification patterns
    NON_PERSON_PATTERNS = [
        r'^[a-f0-9]{32}@',  # MD5/hex IDs
        r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}@',  # UUIDs
        r'^\d{5,}@',  # Numeric IDs
        r'^notifications?[-_]',
        r'^no[-_]?reply',
        r'^do[-_]?not[-_]?reply',
        r'@.*newsletter',
        r'@.*noreply',
        r'@.*notification',
    ]

    def __init__(self):
        """Initialize email filter."""
        self.compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.NON_PERSON_PATTERNS]

    def is_person_email(self, email: str) -> bool:
        """
        Check if email belongs to a real person.

        Returns True if email appears to be a person, False if system/bot.
        """
        result = self.validate_email(email)
        return result.is_person

    def validate_email(self, email: str) -> EmailValidationResult:
        """
        Validate email and return detailed result with rejection reason.

        Args:
            email: Email address to validate

        Returns:
            EmailValidationResult with is_person flag and optional rejection reason
        """
        if not email or '@' not in email:
            return EmailValidationResult(is_person=False, rejection_reason="Invalid format")

        # Normalize email
        email_lower = email.lower().strip()
        local_part, domain = email_lower.rsplit('@', 1)

        # Check full domain
        if email_lower in self.NON_PERSON_DOMAINS or domain in self.NON_PERSON_DOMAINS:
            return EmailValidationResult(
                is_person=False,
                rejection_reason=f"System domain: {domain}"
            )

        # Check prefix
        for prefix in self.NON_PERSON_PREFIXES:
            if local_part.startswith(prefix):
                return EmailValidationResult(
                    is_person=False,
                    rejection_reason=f"System prefix: {prefix}"
                )

        # Check patterns
        for pattern in self.compiled_patterns:
            if pattern.match(email_lower):
                return EmailValidationResult(
                    is_person=False,
                    rejection_reason=f"System pattern: {pattern.pattern}"
                )

        # Passed all checks - likely a person
        return EmailValidationResult(is_person=True)

    def get_rejection_reason(self, email: str) -> Optional[str]:
        """Get the reason why an email was rejected (if it was)."""
        result = self.validate_email(email)
        return result.rejection_reason

    def filter_emails(self, emails: list[str]) -> Tuple[list[str], list[str]]:
        """
        Filter a list of emails into person and non-person lists.

        Args:
            emails: List of email addresses

        Returns:
            Tuple of (person_emails, filtered_out_emails)
        """
        person_emails = []
        filtered_emails = []

        for email in emails:
            if self.is_person_email(email):
                person_emails.append(email)
            else:
                filtered_emails.append(email)

        return person_emails, filtered_emails


def main():
    """CLI entry point for email filtering."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: email_filter.py <email> [email2 email3 ...]")
        print("\nTests if emails belong to real people or are system/bot addresses.")
        sys.exit(1)

    filter = EmailFilter()

    print("Email Validation Results:\n")
    for email in sys.argv[1:]:
        result = filter.validate_email(email)
        status = "✓ PERSON" if result.is_person else "✗ FILTERED"
        reason = f" ({result.rejection_reason})" if result.rejection_reason else ""
        print(f"{status:15} {email:40} {reason}")


if __name__ == '__main__':
    main()
