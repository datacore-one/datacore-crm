#!/usr/bin/env python3
"""
Name normalizer for CRM module - Contact deduplication by normalized name.

Handles same person with multiple email addresses through fuzzy name matching.
"""

import re
import unicodedata
from typing import Optional, List, Tuple
from dataclasses import dataclass


@dataclass
class NameMatch:
    """Result of name matching."""
    normalized: str
    original: str
    similarity: float
    is_duplicate: bool
    matched_name: Optional[str] = None


class NameNormalizer:
    """Normalize and deduplicate contact names."""

    # Common suffixes to ignore in matching
    SUFFIXES = {
        'jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv',
        'phd', 'ph.d.', 'md', 'm.d.', 'esq', 'esq.',
        'cpa', 'dds', 'dvm',
    }

    # Title prefixes to ignore
    PREFIXES = {
        'mr', 'mr.', 'mrs', 'mrs.', 'ms', 'ms.', 'miss',
        'dr', 'dr.', 'prof', 'prof.', 'rev', 'rev.',
    }

    def __init__(self, similarity_threshold: float = 0.85):
        """
        Initialize name normalizer.

        Args:
            similarity_threshold: Minimum similarity score (0-1) to consider duplicate
        """
        self.similarity_threshold = similarity_threshold

    def normalize(self, name: str) -> str:
        """
        Normalize a name to canonical form for matching.

        Steps:
        1. Unicode normalization (NFKD)
        2. Lowercase
        3. Remove accents/diacritics
        4. Remove titles and suffixes
        5. Collapse whitespace
        6. Remove punctuation except hyphens in compound names

        Args:
            name: Original name

        Returns:
            Normalized name
        """
        if not name:
            return ""

        # Unicode normalization
        normalized = unicodedata.normalize('NFKD', name)
        normalized = normalized.encode('ASCII', 'ignore').decode('ASCII')

        # Lowercase
        normalized = normalized.lower()

        # Split into parts
        parts = normalized.split()

        # Remove prefixes
        while parts and parts[0].rstrip('.') in self.PREFIXES:
            parts = parts[1:]

        # Remove suffixes
        while parts and parts[-1].rstrip('.') in self.SUFFIXES:
            parts = parts[:-1]

        # Remove special characters except hyphens in compound names
        cleaned_parts = []
        for part in parts:
            # Keep hyphens, remove other punctuation
            cleaned = re.sub(r'[^\w\s-]', '', part)
            if cleaned:
                cleaned_parts.append(cleaned)

        # Rejoin
        normalized = ' '.join(cleaned_parts)

        # Collapse multiple spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()

        return normalized

    def extract_initials(self, name: str) -> str:
        """
        Extract initials from a name.

        Used for fuzzy matching names with different formatting:
        - "John Smith" vs "J. Smith"
        - "Mary Jane Watson" vs "M.J. Watson"
        """
        normalized = self.normalize(name)
        parts = normalized.split()
        return ''.join(p[0] for p in parts if p)

    def similarity(self, name1: str, name2: str) -> float:
        """
        Calculate similarity score between two names.

        Uses multiple strategies:
        1. Exact normalized match → 1.0
        2. Levenshtein distance on normalized names
        3. Initial matching (J. Smith vs John Smith)
        4. Reversed names (First Last vs Last First)

        Args:
            name1: First name
            name2: Second name

        Returns:
            Similarity score (0.0 - 1.0)
        """
        norm1 = self.normalize(name1)
        norm2 = self.normalize(name2)

        # Exact match
        if norm1 == norm2:
            return 1.0

        # Empty check
        if not norm1 or not norm2:
            return 0.0

        # Levenshtein distance
        max_len = max(len(norm1), len(norm2))
        lev_dist = self._levenshtein_distance(norm1, norm2)
        lev_similarity = 1.0 - (lev_dist / max_len)

        # Initial matching
        parts1 = norm1.split()
        parts2 = norm2.split()

        # Check if one has initials
        if len(parts1) == len(parts2):
            initial_matches = 0
            total_parts = len(parts1)

            for p1, p2 in zip(parts1, parts2):
                if p1 == p2:
                    initial_matches += 1
                elif len(p1) == 1 and p2.startswith(p1):
                    # "j" matches "john"
                    initial_matches += 0.9
                elif len(p2) == 1 and p1.startswith(p2):
                    # "john" matches "j"
                    initial_matches += 0.9

            if initial_matches / total_parts >= 0.8:
                return 0.95  # High confidence for initial match

        # Reversed names (First Last vs Last, First)
        if len(parts1) == 2 and len(parts2) == 2:
            if parts1[0] == parts2[1] and parts1[1] == parts2[0]:
                return 0.98  # High confidence for reversed names

        return lev_similarity

    def find_duplicates(self, names: List[str]) -> List[Tuple[str, str, float]]:
        """
        Find duplicate names in a list.

        Args:
            names: List of names to check

        Returns:
            List of (name1, name2, similarity) tuples for likely duplicates
        """
        duplicates = []

        for i, name1 in enumerate(names):
            for name2 in names[i + 1:]:
                sim = self.similarity(name1, name2)
                if sim >= self.similarity_threshold:
                    duplicates.append((name1, name2, sim))

        return duplicates

    def match_name(self, name: str, existing_names: List[str]) -> NameMatch:
        """
        Match a name against a list of existing names.

        Args:
            name: Name to check
            existing_names: List of known names

        Returns:
            NameMatch with duplicate detection result
        """
        normalized = self.normalize(name)
        best_match = None
        best_similarity = 0.0

        for existing in existing_names:
            sim = self.similarity(name, existing)
            if sim > best_similarity:
                best_similarity = sim
                best_match = existing

        is_duplicate = best_similarity >= self.similarity_threshold

        return NameMatch(
            normalized=normalized,
            original=name,
            similarity=best_similarity,
            is_duplicate=is_duplicate,
            matched_name=best_match if is_duplicate else None
        )

    def merge_contact_info(self, contact1: dict, contact2: dict) -> dict:
        """
        Merge two contact records, combining unique information.

        Strategy:
        - Keep most complete record as base
        - Add missing fields from other record
        - Merge list fields (emails, tags, industries)
        - Track source of merge

        Args:
            contact1: First contact dict
            contact2: Second contact dict

        Returns:
            Merged contact dict
        """
        # Determine which is more complete
        count1 = sum(1 for v in contact1.values() if v)
        count2 = sum(1 for v in contact2.values() if v)

        if count1 >= count2:
            base, other = contact1.copy(), contact2
        else:
            base, other = contact2.copy(), contact1

        # Merge fields
        for key, value in other.items():
            if key not in base or not base[key]:
                # Add missing field
                base[key] = value
            elif isinstance(base[key], list) and isinstance(value, list):
                # Merge lists, removing duplicates
                base[key] = list(set(base[key] + value))
            elif base[key] != value and key not in ['name', 'created', 'updated']:
                # Conflict - store both (for manual review)
                if not isinstance(base[key], list):
                    base[key] = [base[key]]
                if value not in base[key]:
                    base[key].append(value)

        # Track merge
        if 'merged_from' not in base:
            base['merged_from'] = []
        merged_name = other.get('name', 'Unknown')
        if merged_name not in base['merged_from']:
            base['merged_from'].append(merged_name)

        return base

    @staticmethod
    def _levenshtein_distance(s1: str, s2: str) -> int:
        """Calculate Levenshtein distance between two strings."""
        if len(s1) < len(s2):
            return NameNormalizer._levenshtein_distance(s2, s1)

        if len(s2) == 0:
            return len(s1)

        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row

        return previous_row[-1]


def main():
    """CLI entry point for name normalization."""
    import sys

    if len(sys.argv) < 2:
        print("Usage: name_normalizer.py <command> [args...]")
        print("\nCommands:")
        print("  normalize <name>              - Normalize a name")
        print("  compare <name1> <name2>       - Compare two names")
        print("  find-dupes <name1> <name2>... - Find duplicates in list")
        sys.exit(1)

    command = sys.argv[1]
    normalizer = NameNormalizer()

    if command == 'normalize':
        if len(sys.argv) < 3:
            print("Error: normalize requires a name argument")
            sys.exit(1)
        name = ' '.join(sys.argv[2:])
        normalized = normalizer.normalize(name)
        print(f"Original:   {name}")
        print(f"Normalized: {normalized}")

    elif command == 'compare':
        if len(sys.argv) < 4:
            print("Error: compare requires two name arguments")
            sys.exit(1)
        # Find where name2 starts (simple split at first occurrence of a likely name)
        args = sys.argv[2:]
        mid = len(args) // 2
        name1 = ' '.join(args[:mid])
        name2 = ' '.join(args[mid:])

        sim = normalizer.similarity(name1, name2)
        is_dup = sim >= normalizer.similarity_threshold

        print(f"Name 1:      {name1}")
        print(f"Name 2:      {name2}")
        print(f"Normalized1: {normalizer.normalize(name1)}")
        print(f"Normalized2: {normalizer.normalize(name2)}")
        print(f"Similarity:  {sim:.2f}")
        print(f"Duplicate:   {'YES' if is_dup else 'NO'}")

    elif command == 'find-dupes':
        if len(sys.argv) < 3:
            print("Error: find-dupes requires name arguments")
            sys.exit(1)

        names = sys.argv[2:]
        duplicates = normalizer.find_duplicates(names)

        if duplicates:
            print(f"Found {len(duplicates)} potential duplicates:\n")
            for name1, name2, sim in duplicates:
                print(f"  {sim:.2f} - {name1:30} ⟷  {name2}")
        else:
            print("No duplicates found.")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == '__main__':
    main()
