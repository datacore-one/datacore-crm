#!/usr/bin/env python3
"""
Domain categorizer for CRM module - Domain-based contact categorization.

Auto-categorizes contacts based on email domain patterns:
- Investor (VC firms, investment funds)
- Crypto/Web3 (blockchain projects, protocols)
- Enterprise (large corporations)
- Startup (early-stage companies)
"""

import re
from typing import List, Optional, Dict
from dataclasses import dataclass
import tldextract


@dataclass
class DomainCategory:
    """Category assigned to a domain."""
    primary: str
    secondary: List[str]
    confidence: float
    indicators: List[str]  # What triggered the categorization


class DomainCategorizer:
    """Categorize contacts based on email domain patterns."""

    # Investor/VC patterns
    INVESTOR_PATTERNS = {
        'domains': {
            'a16z.com', 'andreessen.com', 'sequoiacap.com', 'accel.com',
            'greylock.com', 'kleinerperkins.com', 'nea.com', 'bessemervp.com',
            'lightspeedvp.com', 'indexventures.com', 'gv.com', 'spark.co',
            'benchmarkvc.com', 'foundersfund.com', 'thrive.com',
            'paradigm.xyz', 'multicoin.capital', 'variant.fund',
            'electriccapital.com', 'a16zcrypto.com', 'panteracapital.com',
            'dcg.co', 'coinbase.ventures', 'binancelabs.co',
        },
        'keywords': [
            'ventures', 'venture', 'capital', 'partners', 'fund', 'funds',
            'investment', 'investments', 'investor', 'investors',
            'equity', 'growth', 'seed',
        ],
        'suffixes': [
            'vc', 'ventures', 'capital', 'partners', 'fund',
        ]
    }

    # Crypto/Web3 patterns
    CRYPTO_PATTERNS = {
        'domains': {
            'ethereum.org', 'protocol.ai', 'filecoin.io', 'ipfs.io',
            'consensys.net', 'metamask.io', 'polygon.technology',
            'avalabs.org', 'solana.com', 'near.org', 'cosmos.network',
            'polkadot.network', 'chainlink.com', 'uniswap.org',
            'compound.finance', 'aave.com', 'makerdao.com',
            'alchemy.com', 'infura.io', 'quicknode.com',
            'coinbase.com', 'kraken.com', 'binance.com', 'gemini.com',
        },
        'keywords': [
            'blockchain', 'crypto', 'web3', 'defi', 'nft', 'dao',
            'protocol', 'chain', 'network', 'token', 'coin',
            'decentralized', 'dapp', 'smart contract',
        ],
        'tlds': [
            'xyz', 'crypto', 'blockchain', 'eth', 'btc',
        ]
    }

    # Enterprise patterns
    ENTERPRISE_PATTERNS = {
        'domains': {
            'google.com', 'apple.com', 'microsoft.com', 'amazon.com',
            'meta.com', 'facebook.com', 'netflix.com', 'salesforce.com',
            'oracle.com', 'ibm.com', 'intel.com', 'cisco.com',
            'adobe.com', 'vmware.com', 'sap.com', 'dell.com',
            'hp.com', 'accenture.com', 'deloitte.com', 'pwc.com',
            'ey.com', 'kpmg.com', 'mckinsey.com', 'bcg.com', 'bain.com',
        },
        'indicators': [
            'fortune500', 'public_company', 'large_corp',
        ]
    }

    # Startup patterns (heuristic-based)
    STARTUP_INDICATORS = {
        'tlds': ['io', 'ai', 'xyz', 'app', 'tech'],
        'domain_length': (4, 12),  # Typically short, memorable
        'exclude_keywords': ['mail', 'email', 'webmail'],
    }

    def __init__(self):
        """Initialize domain categorizer."""
        pass

    def categorize(self, email: str, context: Optional[Dict] = None) -> DomainCategory:
        """
        Categorize a contact based on email domain.

        Args:
            email: Email address
            context: Optional additional context (title, bio, etc.)

        Returns:
            DomainCategory with primary and secondary categories
        """
        if not email or '@' not in email:
            return DomainCategory(
                primary='unknown',
                secondary=[],
                confidence=0.0,
                indicators=['invalid_email']
            )

        local_part, domain = email.rsplit('@', 1)
        domain_lower = domain.lower()
        extracted = tldextract.extract(domain)

        categories = []
        indicators = []
        confidence_scores = {}

        # Check investor patterns
        investor_result = self._check_investor(domain_lower, extracted, context)
        if investor_result['match']:
            categories.append('investor')
            confidence_scores['investor'] = investor_result['confidence']
            indicators.extend(investor_result['indicators'])

        # Check crypto patterns
        crypto_result = self._check_crypto(domain_lower, extracted, context)
        if crypto_result['match']:
            categories.append('crypto')
            confidence_scores['crypto'] = crypto_result['confidence']
            indicators.extend(crypto_result['indicators'])

        # Check enterprise patterns
        enterprise_result = self._check_enterprise(domain_lower, extracted, context)
        if enterprise_result['match']:
            categories.append('enterprise')
            confidence_scores['enterprise'] = enterprise_result['confidence']
            indicators.extend(enterprise_result['indicators'])

        # Check startup patterns (only if no other category matched)
        if not categories:
            startup_result = self._check_startup(domain_lower, extracted, context)
            if startup_result['match']:
                categories.append('startup')
                confidence_scores['startup'] = startup_result['confidence']
                indicators.extend(startup_result['indicators'])

        # Determine primary and secondary
        if categories:
            # Sort by confidence
            sorted_cats = sorted(categories, key=lambda c: confidence_scores[c], reverse=True)
            primary = sorted_cats[0]
            secondary = sorted_cats[1:]
            confidence = confidence_scores[primary]
        else:
            primary = 'unknown'
            secondary = []
            confidence = 0.0
            indicators = ['no_pattern_match']

        return DomainCategory(
            primary=primary,
            secondary=secondary,
            confidence=confidence,
            indicators=indicators
        )

    def _check_investor(self, domain: str, extracted, context: Optional[Dict]) -> Dict:
        """Check if domain matches investor patterns."""
        indicators = []
        confidence = 0.0

        # Exact domain match
        if domain in self.INVESTOR_PATTERNS['domains']:
            indicators.append(f'known_vc_domain:{domain}')
            confidence = 0.95
            return {'match': True, 'confidence': confidence, 'indicators': indicators}

        # Keyword match
        domain_parts = extracted.domain.lower()
        for keyword in self.INVESTOR_PATTERNS['keywords']:
            if keyword in domain_parts:
                indicators.append(f'investor_keyword:{keyword}')
                confidence = max(confidence, 0.75)

        # Suffix match
        for suffix in self.INVESTOR_PATTERNS['suffixes']:
            if domain_parts.endswith(suffix):
                indicators.append(f'investor_suffix:{suffix}')
                confidence = max(confidence, 0.8)

        # Context check (title/bio)
        if context:
            title = context.get('title', '').lower()
            bio = context.get('bio', '').lower()
            combined = f"{title} {bio}"

            investor_titles = ['investor', 'venture capital', 'vc', 'partner', 'managing director']
            for term in investor_titles:
                if term in combined:
                    indicators.append(f'investor_title:{term}')
                    confidence = max(confidence, 0.7)

        return {
            'match': confidence > 0.0,
            'confidence': confidence,
            'indicators': indicators
        }

    def _check_crypto(self, domain: str, extracted, context: Optional[Dict]) -> Dict:
        """Check if domain matches crypto/web3 patterns."""
        indicators = []
        confidence = 0.0

        # Exact domain match
        if domain in self.CRYPTO_PATTERNS['domains']:
            indicators.append(f'known_crypto_domain:{domain}')
            confidence = 0.95
            return {'match': True, 'confidence': confidence, 'indicators': indicators}

        # TLD match
        if extracted.suffix in self.CRYPTO_PATTERNS['tlds']:
            indicators.append(f'crypto_tld:{extracted.suffix}')
            confidence = max(confidence, 0.6)

        # Keyword match
        domain_parts = extracted.domain.lower()
        for keyword in self.CRYPTO_PATTERNS['keywords']:
            if keyword in domain_parts:
                indicators.append(f'crypto_keyword:{keyword}')
                confidence = max(confidence, 0.8)

        # Context check
        if context:
            title = context.get('title', '').lower()
            bio = context.get('bio', '').lower()
            combined = f"{title} {bio}"

            crypto_terms = ['blockchain', 'crypto', 'web3', 'defi', 'protocol', 'dao']
            for term in crypto_terms:
                if term in combined:
                    indicators.append(f'crypto_context:{term}')
                    confidence = max(confidence, 0.75)

        return {
            'match': confidence > 0.0,
            'confidence': confidence,
            'indicators': indicators
        }

    def _check_enterprise(self, domain: str, extracted, context: Optional[Dict]) -> Dict:
        """Check if domain matches enterprise patterns."""
        indicators = []
        confidence = 0.0

        # Exact domain match
        if domain in self.ENTERPRISE_PATTERNS['domains']:
            indicators.append(f'known_enterprise_domain:{domain}')
            confidence = 0.95
            return {'match': True, 'confidence': confidence, 'indicators': indicators}

        # Heuristic: very short domains often belong to established companies
        if len(extracted.domain) <= 6 and extracted.suffix == 'com':
            indicators.append('short_com_domain')
            confidence = max(confidence, 0.5)

        # Context check
        if context:
            title = context.get('title', '').lower()
            enterprise_titles = ['vp', 'vice president', 'svp', 'evp', 'chief', 'director']
            for term in enterprise_titles:
                if term in title:
                    indicators.append(f'enterprise_title:{term}')
                    confidence = max(confidence, 0.6)

        return {
            'match': confidence > 0.0,
            'confidence': confidence,
            'indicators': indicators
        }

    def _check_startup(self, domain: str, extracted, context: Optional[Dict]) -> Dict:
        """Check if domain matches startup patterns."""
        indicators = []
        confidence = 0.0

        # TLD check
        if extracted.suffix in self.STARTUP_INDICATORS['tlds']:
            indicators.append(f'startup_tld:{extracted.suffix}')
            confidence = max(confidence, 0.5)

        # Domain length check (short, memorable)
        min_len, max_len = self.STARTUP_INDICATORS['domain_length']
        domain_len = len(extracted.domain)
        if min_len <= domain_len <= max_len:
            indicators.append(f'startup_domain_length:{domain_len}')
            confidence = max(confidence, 0.4)

        # Exclude generic keywords
        domain_parts = extracted.domain.lower()
        for keyword in self.STARTUP_INDICATORS['exclude_keywords']:
            if keyword in domain_parts:
                # Not a startup if it's a mail service
                return {'match': False, 'confidence': 0.0, 'indicators': []}

        # Context check
        if context:
            title = context.get('title', '').lower()
            startup_titles = ['founder', 'co-founder', 'ceo', 'cto']
            for term in startup_titles:
                if term in title:
                    indicators.append(f'startup_title:{term}')
                    confidence = max(confidence, 0.7)

        return {
            'match': confidence > 0.0,
            'confidence': confidence,
            'indicators': indicators
        }

    def bulk_categorize(self, contacts: List[Dict]) -> Dict[str, DomainCategory]:
        """
        Categorize multiple contacts.

        Args:
            contacts: List of contact dicts with 'email', optionally 'title', 'bio'

        Returns:
            Dict mapping email to DomainCategory
        """
        results = {}

        for contact in contacts:
            email = contact.get('email')
            if not email:
                continue

            context = {
                'title': contact.get('title', ''),
                'bio': contact.get('bio', ''),
            }

            category = self.categorize(email, context)
            results[email] = category

        return results


def main():
    """CLI entry point for domain categorization."""
    import sys
    import json

    if len(sys.argv) < 2:
        print("Usage: domain_categorizer.py <email> [--title='...' --bio='...']")
        print("\nCategorizes email domain as investor/crypto/enterprise/startup.")
        sys.exit(1)

    email = sys.argv[1]
    context = {}

    # Parse optional context
    for arg in sys.argv[2:]:
        if arg.startswith('--'):
            key, val = arg[2:].split('=', 1)
            context[key] = val

    categorizer = DomainCategorizer()
    category = categorizer.categorize(email, context if context else None)

    print(json.dumps({
        'email': email,
        'primary': category.primary,
        'secondary': category.secondary,
        'confidence': round(category.confidence, 2),
        'indicators': category.indicators
    }, indent=2))


if __name__ == '__main__':
    main()
