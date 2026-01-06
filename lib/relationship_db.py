#!/usr/bin/env python3
"""
Relationship Database - SQLCipher encrypted storage with NetworkX graph analysis.

Stores personal email contacts with relationship metrics and graph centrality.
Privacy-aware: sensitive domains have metadata only (no body content).

Usage:
    from relationship_db import RelationshipDB

    db = RelationshipDB("~/.datacore/state/relationships.db")
    db.index_mbox(
        mbox_path="~/Library/Thunderbird/.../All Mail",
        my_email="user@example.com",
        rules_path=".datacore/modules/mail/rules.base.yaml",
        sensitive_domains=["*-law.eu"],
        excluded_domains=[]
    )
    db.compute_scores()
    db.compute_graph_metrics()
"""

import json
import os
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple

try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False
    print("Warning: NetworkX not installed. Graph analysis disabled.")

try:
    from pysqlcipher3 import dbapi2 as sqlcipher
    HAS_SQLCIPHER = True
except ImportError:
    HAS_SQLCIPHER = False
    # Fall back to regular sqlite3

from mbox_parser import MboxParser, EmailMetadata


# Database schema
SCHEMA = """
-- Core contacts table
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    domain TEXT,
    first_seen DATE,
    last_seen DATE,
    sent_count INTEGER DEFAULT 0,
    received_count INTEGER DEFAULT 0,
    thread_count INTEGER DEFAULT 0,
    -- Classification
    is_personal BOOLEAN DEFAULT TRUE,
    is_sensitive BOOLEAN DEFAULT FALSE,
    tags TEXT,  -- JSON array
    topics TEXT,  -- JSON array (extracted from subjects)
    -- Relationship metrics (computed)
    frequency_score REAL,
    reciprocity_score REAL,
    recency_score REAL,
    -- NetworkX graph metrics (computed)
    degree_centrality REAL,
    betweenness_centrality REAL,
    community_id INTEGER
);

-- Email interactions
CREATE TABLE IF NOT EXISTS interactions (
    id INTEGER PRIMARY KEY,
    contact_id INTEGER REFERENCES contacts(id),
    date DATETIME,
    direction TEXT,  -- 'sent' or 'received'
    subject TEXT,
    snippet TEXT,  -- NULL for sensitive contacts
    thread_id TEXT,
    message_id TEXT UNIQUE,
    keywords TEXT  -- JSON array, NULL for sensitive
);

-- Thread tracking
CREATE TABLE IF NOT EXISTS threads (
    id INTEGER PRIMARY KEY,
    thread_id TEXT UNIQUE,
    subject TEXT,
    first_date DATE,
    last_date DATE,
    message_count INTEGER DEFAULT 0,
    participants TEXT  -- JSON array of emails
);

-- Sensitive domain exclusions
CREATE TABLE IF NOT EXISTS excluded_domains (
    id INTEGER PRIMARY KEY,
    domain TEXT UNIQUE,
    reason TEXT,
    added_date DATE
);

-- Insights for PKM export
CREATE TABLE IF NOT EXISTS insights (
    id INTEGER PRIMARY KEY,
    contact_id INTEGER REFERENCES contacts(id),
    insight_type TEXT,
    content TEXT,
    created_date DATE,
    exported_to TEXT,
    exported_date DATE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_contacts_domain ON contacts(domain);
CREATE INDEX IF NOT EXISTS idx_contacts_last_seen ON contacts(last_seen);
CREATE INDEX IF NOT EXISTS idx_contacts_community ON contacts(community_id);
CREATE INDEX IF NOT EXISTS idx_interactions_date ON interactions(date);
CREATE INDEX IF NOT EXISTS idx_interactions_contact ON interactions(contact_id);
CREATE INDEX IF NOT EXISTS idx_interactions_thread ON interactions(thread_id);
CREATE INDEX IF NOT EXISTS idx_threads_participants ON threads(participants);
"""


class RelationshipDB:
    """
    Encrypted relationship database with graph analysis.

    Uses SQLCipher for encryption if available, falls back to SQLite.
    NetworkX for community detection and centrality metrics.
    """

    def __init__(self, db_path: str, passphrase: str = None):
        """
        Initialize database connection.

        Args:
            db_path: Path to database file
            passphrase: Encryption passphrase (required for SQLCipher)
        """
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.passphrase = passphrase
        self.encrypted = False

        # Try SQLCipher first, fall back to SQLite
        if HAS_SQLCIPHER and passphrase:
            self.conn = sqlcipher.connect(str(self.db_path))
            self.conn.execute(f"PRAGMA key = '{passphrase}'")
            self.encrypted = True
        else:
            if passphrase and not HAS_SQLCIPHER:
                print("Warning: pysqlcipher3 not installed. Using unencrypted SQLite.")
            self.conn = sqlite3.connect(str(self.db_path))

        self.conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        """Initialize database schema."""
        self.conn.executescript(SCHEMA)
        self.conn.commit()

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    # =========================================================================
    # INDEXING
    # =========================================================================

    def index_mbox(
        self,
        mbox_path: str,
        my_email: str,
        rules_path: str,
        sensitive_domains: List[str] = None,
        excluded_domains: List[str] = None,
        progress_callback=None,
        max_messages: int = 0
    ) -> Dict[str, int]:
        """
        Index all personal contacts from mbox file.

        Args:
            mbox_path: Path to Thunderbird mbox file
            my_email: Your email address (to determine direction)
            rules_path: Path to mail rules YAML
            sensitive_domains: Patterns for domains to index without body
            excluded_domains: Patterns for domains to skip entirely
            progress_callback: Optional function(current, total)
            max_messages: Max messages to process (0 = all)

        Returns:
            Stats dict with counts
        """
        parser = MboxParser(
            mbox_path=mbox_path,
            rules_path=rules_path,
            sensitive_domains=sensitive_domains or [],
            excluded_domains=excluded_domains or []
        )

        my_email_lower = my_email.lower()
        stats = {
            'processed': 0,
            'contacts_created': 0,
            'contacts_updated': 0,
            'interactions_added': 0,
            'threads_tracked': 0,
            'skipped': 0
        }

        # Thread participant tracking
        thread_participants = defaultdict(set)
        thread_first_date = {}
        thread_last_date = {}
        thread_subjects = {}
        thread_counts = defaultdict(int)

        for email in parser.parse_all(progress_callback, max_messages):
            stats['processed'] += 1

            try:
                # Determine direction and contact emails
                if email.from_email.lower() == my_email_lower:
                    direction = 'sent'
                    contact_emails = email.to_emails + email.cc_emails
                else:
                    direction = 'received'
                    contact_emails = [email.from_email]

                # Skip if no valid contacts
                if not contact_emails:
                    stats['skipped'] += 1
                    continue

                # Track thread participants
                if email.thread_id:
                    all_participants = [email.from_email] + email.to_emails + email.cc_emails
                    thread_participants[email.thread_id].update(all_participants)
                    thread_counts[email.thread_id] += 1

                    email_date = email.date.isoformat() if email.date else None
                    if email_date:
                        if email.thread_id not in thread_first_date:
                            thread_first_date[email.thread_id] = email_date
                        thread_first_date[email.thread_id] = min(
                            thread_first_date[email.thread_id], email_date
                        )
                        thread_last_date[email.thread_id] = max(
                            thread_last_date.get(email.thread_id, ''), email_date
                        )

                    if email.subject and email.thread_id not in thread_subjects:
                        thread_subjects[email.thread_id] = email.subject

                # Process each contact
                for contact_email in contact_emails:
                    if not contact_email or '@' not in contact_email:
                        continue

                    contact_email = contact_email.lower()
                    if contact_email == my_email_lower:
                        continue  # Don't track yourself

                    # Upsert contact
                    created = self._upsert_contact(
                        email=contact_email,
                        name=email.from_name if direction == 'received' else '',
                        date=email.date,
                        direction=direction,
                        is_sensitive=email.is_sensitive,
                        keywords=email.keywords
                    )

                    if created:
                        stats['contacts_created'] += 1
                    else:
                        stats['contacts_updated'] += 1

                    # Add interaction
                    added = self._add_interaction(
                        contact_email=contact_email,
                        email=email,
                        direction=direction
                    )
                    if added:
                        stats['interactions_added'] += 1

            except Exception as e:
                stats['skipped'] += 1
                continue

        # Store threads
        for thread_id, participants in thread_participants.items():
            self._upsert_thread(
                thread_id=thread_id,
                subject=thread_subjects.get(thread_id, ''),
                first_date=thread_first_date.get(thread_id),
                last_date=thread_last_date.get(thread_id),
                message_count=thread_counts[thread_id],
                participants=list(participants)
            )
            stats['threads_tracked'] += 1

        self.conn.commit()
        return stats

    def _upsert_contact(
        self,
        email: str,
        name: str,
        date: datetime,
        direction: str,
        is_sensitive: bool,
        keywords: List[str] = None
    ) -> bool:
        """
        Insert or update contact.

        Returns True if created, False if updated.
        """
        cursor = self.conn.cursor()

        # Check if exists
        cursor.execute("SELECT id, topics FROM contacts WHERE email = ?", (email,))
        row = cursor.fetchone()

        domain = email.split('@')[-1] if '@' in email else ''
        date_str = date.strftime('%Y-%m-%d') if date else None

        if row:
            # Update existing
            contact_id = row['id']
            existing_topics = json.loads(row['topics']) if row['topics'] else []

            # Merge keywords into topics
            if keywords:
                for kw in keywords:
                    if kw not in existing_topics:
                        existing_topics.append(kw)
                existing_topics = existing_topics[:50]  # Limit

            # Update counts and dates
            if direction == 'sent':
                cursor.execute("""
                    UPDATE contacts SET
                        sent_count = sent_count + 1,
                        last_seen = MAX(COALESCE(last_seen, ''), ?),
                        first_seen = MIN(COALESCE(first_seen, '9999'), ?),
                        topics = ?,
                        is_sensitive = is_sensitive OR ?
                    WHERE id = ?
                """, (date_str, date_str, json.dumps(existing_topics), is_sensitive, contact_id))
            else:
                cursor.execute("""
                    UPDATE contacts SET
                        received_count = received_count + 1,
                        last_seen = MAX(COALESCE(last_seen, ''), ?),
                        first_seen = MIN(COALESCE(first_seen, '9999'), ?),
                        name = COALESCE(NULLIF(?, ''), name),
                        topics = ?,
                        is_sensitive = is_sensitive OR ?
                    WHERE id = ?
                """, (date_str, date_str, name, json.dumps(existing_topics), is_sensitive, contact_id))

            return False
        else:
            # Insert new
            cursor.execute("""
                INSERT INTO contacts (
                    email, name, domain, first_seen, last_seen,
                    sent_count, received_count, is_sensitive, topics
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                email, name, domain, date_str, date_str,
                1 if direction == 'sent' else 0,
                1 if direction == 'received' else 0,
                is_sensitive,
                json.dumps(keywords or [])
            ))
            return True

    def _add_interaction(
        self,
        contact_email: str,
        email: EmailMetadata,
        direction: str
    ) -> bool:
        """Add interaction record. Returns True if added."""
        cursor = self.conn.cursor()

        # Get contact ID
        cursor.execute("SELECT id FROM contacts WHERE email = ?", (contact_email,))
        row = cursor.fetchone()
        if not row:
            return False

        contact_id = row['id']

        # Check for duplicate
        if email.message_id:
            cursor.execute(
                "SELECT id FROM interactions WHERE message_id = ?",
                (email.message_id,)
            )
            if cursor.fetchone():
                return False

        try:
            cursor.execute("""
                INSERT INTO interactions (
                    contact_id, date, direction, subject, snippet,
                    thread_id, message_id, keywords
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                contact_id,
                email.date.isoformat() if email.date else None,
                direction,
                email.subject,
                email.snippet,  # None for sensitive
                email.thread_id,
                email.message_id,
                json.dumps(email.keywords) if email.keywords else None
            ))
            return True
        except sqlite3.IntegrityError:
            return False

    def _upsert_thread(
        self,
        thread_id: str,
        subject: str,
        first_date: str,
        last_date: str,
        message_count: int,
        participants: List[str]
    ):
        """Insert or update thread record."""
        cursor = self.conn.cursor()

        cursor.execute("""
            INSERT INTO threads (thread_id, subject, first_date, last_date, message_count, participants)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(thread_id) DO UPDATE SET
                last_date = MAX(excluded.last_date, threads.last_date),
                message_count = excluded.message_count,
                participants = excluded.participants
        """, (
            thread_id, subject, first_date, last_date,
            message_count, json.dumps(participants)
        ))

    # =========================================================================
    # SCORING
    # =========================================================================

    def compute_scores(self):
        """Compute relationship scores for all contacts."""
        cursor = self.conn.cursor()
        now = datetime.now()

        # Get all contacts with their interaction data
        cursor.execute("""
            SELECT
                c.id, c.email, c.first_seen, c.last_seen,
                c.sent_count, c.received_count
            FROM contacts c
        """)

        for row in cursor.fetchall():
            contact_id = row['id']
            sent = row['sent_count'] or 0
            received = row['received_count'] or 0
            total = sent + received

            # Skip contacts with no interactions
            if total == 0:
                continue

            # Parse dates
            first_seen = datetime.fromisoformat(row['first_seen']) if row['first_seen'] else now
            last_seen = datetime.fromisoformat(row['last_seen']) if row['last_seen'] else now

            # Frequency: emails per month
            relationship_days = max((now - first_seen).days, 1)
            relationship_months = relationship_days / 30.0
            frequency_score = total / relationship_months if relationship_months > 0 else 0

            # Reciprocity: 1.0 = perfectly balanced, 0.0 = completely one-way
            # Formula: 1 - |sent_ratio - 0.5| * 2
            sent_ratio = sent / total
            reciprocity_score = 1.0 - abs(sent_ratio - 0.5) * 2

            # Recency: exponential decay from last contact
            # Score = exp(-days_since / 90) → 1.0 at 0 days, 0.37 at 90 days
            days_since = (now - last_seen).days
            recency_score = 2.718 ** (-days_since / 90.0)

            cursor.execute("""
                UPDATE contacts SET
                    frequency_score = ?,
                    reciprocity_score = ?,
                    recency_score = ?
                WHERE id = ?
            """, (frequency_score, reciprocity_score, recency_score, contact_id))

        self.conn.commit()

    # =========================================================================
    # GRAPH ANALYSIS
    # =========================================================================

    def build_graph(self) -> 'nx.Graph':
        """
        Build NetworkX graph from thread co-participation.

        Nodes: contact emails
        Edges: weighted by number of shared threads
        """
        if not HAS_NETWORKX:
            raise ImportError("NetworkX not installed")

        G = nx.Graph()
        cursor = self.conn.cursor()

        # Get all threads with participants
        cursor.execute("SELECT thread_id, participants FROM threads")

        for row in cursor.fetchall():
            participants = json.loads(row['participants']) if row['participants'] else []
            participants = [p.lower() for p in participants if p and '@' in p]

            if len(participants) < 2:
                continue

            # Add edges between all co-participants
            for p1, p2 in combinations(participants, 2):
                if G.has_edge(p1, p2):
                    G[p1][p2]['weight'] += 1
                else:
                    G.add_edge(p1, p2, weight=1)

        return G

    def compute_graph_metrics(self):
        """Compute and store NetworkX metrics for all contacts."""
        if not HAS_NETWORKX:
            print("Warning: NetworkX not installed. Skipping graph metrics.")
            return

        G = self.build_graph()

        if len(G.nodes) == 0:
            print("No graph nodes to analyze.")
            return

        print(f"Computing metrics for graph with {len(G.nodes)} nodes, {len(G.edges)} edges...")

        # Centrality metrics
        degree = nx.degree_centrality(G)
        betweenness = nx.betweenness_centrality(G)

        # Community detection (Louvain)
        try:
            communities = nx.community.louvain_communities(G)
            community_map = {}
            for i, community in enumerate(communities):
                for node in community:
                    community_map[node] = i
            print(f"Detected {len(communities)} communities.")
        except Exception as e:
            print(f"Community detection failed: {e}")
            community_map = {}

        # Update database
        cursor = self.conn.cursor()
        for email in degree:
            cursor.execute("""
                UPDATE contacts SET
                    degree_centrality = ?,
                    betweenness_centrality = ?,
                    community_id = ?
                WHERE email = ?
            """, (
                degree[email],
                betweenness.get(email, 0),
                community_map.get(email),
                email
            ))

        self.conn.commit()

    # =========================================================================
    # QUERIES
    # =========================================================================

    def get_contact(self, email: str) -> Optional[Dict]:
        """Get contact by email."""
        cursor = self.conn.cursor()
        cursor.execute("SELECT * FROM contacts WHERE email = ?", (email.lower(),))
        row = cursor.fetchone()
        return dict(row) if row else None

    def get_all_contacts(
        self,
        min_interactions: int = 0,
        domain: str = None,
        community_id: int = None,
        limit: int = 0
    ) -> List[Dict]:
        """Get contacts with optional filters."""
        cursor = self.conn.cursor()

        query = "SELECT * FROM contacts WHERE 1=1"
        params = []

        if min_interactions > 0:
            query += " AND (sent_count + received_count) >= ?"
            params.append(min_interactions)

        if domain:
            query += " AND domain = ?"
            params.append(domain.lower())

        if community_id is not None:
            query += " AND community_id = ?"
            params.append(community_id)

        query += " ORDER BY (sent_count + received_count) DESC"

        if limit > 0:
            query += f" LIMIT {limit}"

        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

    def get_top_contacts(
        self,
        by: str = 'frequency',
        limit: int = 50
    ) -> List[Dict]:
        """
        Get top contacts by metric.

        Args:
            by: 'frequency', 'recency', 'centrality', 'total'
            limit: Number of results
        """
        order_map = {
            'frequency': 'frequency_score DESC',
            'recency': 'recency_score DESC',
            'centrality': 'degree_centrality DESC',
            'total': '(sent_count + received_count) DESC'
        }

        order = order_map.get(by, 'frequency_score DESC')

        cursor = self.conn.cursor()
        cursor.execute(f"""
            SELECT * FROM contacts
            WHERE (sent_count + received_count) > 0
            ORDER BY {order}
            LIMIT ?
        """, (limit,))

        return [dict(row) for row in cursor.fetchall()]

    def get_reconnection_candidates(
        self,
        silence_days: int = 90,
        min_past_frequency: float = 0.5,
        limit: int = 20
    ) -> List[Dict]:
        """
        Get contacts to reconnect with.

        Criteria: High past frequency but haven't contacted in silence_days.
        """
        cursor = self.conn.cursor()
        cutoff = (datetime.now() - timedelta(days=silence_days)).strftime('%Y-%m-%d')

        cursor.execute("""
            SELECT * FROM contacts
            WHERE last_seen < ?
              AND frequency_score >= ?
              AND reciprocity_score > 0.3
            ORDER BY frequency_score DESC
            LIMIT ?
        """, (cutoff, min_past_frequency, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_one_way_contacts(
        self,
        direction: str = 'sent',
        min_interactions: int = 3,
        limit: int = 50
    ) -> List[Dict]:
        """
        Get contacts with one-way communication.

        Args:
            direction: 'sent' (I send, they don't reply) or 'received' (they send, I don't reply)
        """
        cursor = self.conn.cursor()

        if direction == 'sent':
            # I send more than receive
            cursor.execute("""
                SELECT * FROM contacts
                WHERE sent_count > received_count * 3
                  AND sent_count >= ?
                ORDER BY sent_count DESC
                LIMIT ?
            """, (min_interactions, limit))
        else:
            # They send more than I reply
            cursor.execute("""
                SELECT * FROM contacts
                WHERE received_count > sent_count * 3
                  AND received_count >= ?
                ORDER BY received_count DESC
                LIMIT ?
            """, (min_interactions, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_communities(self) -> List[Dict]:
        """Get communities with member counts and top contacts."""
        cursor = self.conn.cursor()

        cursor.execute("""
            SELECT
                community_id,
                COUNT(*) as member_count,
                GROUP_CONCAT(domain) as domains,
                GROUP_CONCAT(email) as emails
            FROM contacts
            WHERE community_id IS NOT NULL
            GROUP BY community_id
            ORDER BY member_count DESC
        """)

        communities = []
        for row in cursor.fetchall():
            # Get top domains in community
            domains = row['domains'].split(',') if row['domains'] else []
            domain_counts = defaultdict(int)
            for d in domains:
                domain_counts[d] += 1
            top_domains = sorted(domain_counts.items(), key=lambda x: x[1], reverse=True)[:5]

            communities.append({
                'community_id': row['community_id'],
                'member_count': row['member_count'],
                'top_domains': [d[0] for d in top_domains],
                'sample_emails': row['emails'].split(',')[:10] if row['emails'] else []
            })

        return communities

    def search(
        self,
        query: str,
        limit: int = 50
    ) -> List[Dict]:
        """Search contacts by email, name, domain, or topics."""
        cursor = self.conn.cursor()
        pattern = f"%{query.lower()}%"

        cursor.execute("""
            SELECT * FROM contacts
            WHERE email LIKE ?
               OR LOWER(name) LIKE ?
               OR domain LIKE ?
               OR topics LIKE ?
            ORDER BY (sent_count + received_count) DESC
            LIMIT ?
        """, (pattern, pattern, pattern, pattern, limit))

        return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, Any]:
        """Get database statistics."""
        cursor = self.conn.cursor()

        cursor.execute("SELECT COUNT(*) as count FROM contacts")
        total_contacts = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM interactions")
        total_interactions = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM threads")
        total_threads = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(DISTINCT community_id) as count FROM contacts WHERE community_id IS NOT NULL")
        total_communities = cursor.fetchone()['count']

        cursor.execute("SELECT COUNT(*) as count FROM contacts WHERE is_sensitive = 1")
        sensitive_contacts = cursor.fetchone()['count']

        cursor.execute("""
            SELECT
                SUM(sent_count) as total_sent,
                SUM(received_count) as total_received
            FROM contacts
        """)
        row = cursor.fetchone()
        total_sent = row['total_sent'] or 0
        total_received = row['total_received'] or 0

        return {
            'total_contacts': total_contacts,
            'total_interactions': total_interactions,
            'total_threads': total_threads,
            'total_communities': total_communities,
            'sensitive_contacts': sensitive_contacts,
            'total_sent': total_sent,
            'total_received': total_received,
            'encrypted': self.encrypted
        }


def main():
    """Test the relationship database."""
    import sys

    print("RelationshipDB Test")
    print("=" * 60)

    # Test with temporary database
    db_path = "/tmp/test_relationships.db"

    with RelationshipDB(db_path) as db:
        print(f"Database: {db_path}")
        print(f"Encrypted: {db.encrypted}")

        stats = db.get_stats()
        print(f"Stats: {stats}")


if __name__ == "__main__":
    main()
