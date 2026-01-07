# CRM Module

> Network Intelligence for Datacore

Track entities (people, companies, projects, events), relationships, and industry landscape. Capture from journals, calendar, research, and email. Surface strategic insights in workflows.

## Quick Start

```bash
# Main entry point - conversational CRM
/crm

# Or with specific intent:
/crm John Smith          # View contact
/crm trip to Dubai       # Trip preparation
/crm scan                # Scan journals/calendar
/crm status              # Network dashboard
/crm new                 # Create contact
/crm import              # Import vCard
/crm enrich              # Enrich from email
```

## Features

### Contact Management
- **Entity types**: People, companies, projects, events
- **Lifecycle tracking**: discovered → lead → contacted → active → dormant
- **Relationship scoring**: Health scores based on recency, frequency, depth
- **Cross-space**: Personal contacts can be promoted to team spaces

### Capture Sources
- **Journals**: Auto-extract `[[Contact Name]]` wiki-link mentions
- **Calendar**: Extract attendees from meetings
- **Research**: Entity extraction from literature notes
- **Email**: Gmail history enrichment with interaction stats

### Industry Landscape
- Build competitive landscape
- Track industry relationships
- Identify coverage gaps

## Commands

| Command | Purpose |
|---------|---------|
| `/crm` | Main conversational entry point |
| `/crm [name]` | View/edit specific contact |
| `/crm status` | Network dashboard with health metrics |
| `/crm scan` | Scan journals/calendar for interactions |
| `/crm new` | Create new contact |
| `/crm import [file]` | Import from vCard (Apple/Gmail) |
| `/crm enrich` | Enrich with email history |
| `/crm maintenance` | Run dedup/validation checks |
| `/crm landscape` | Generate industry landscape |

## Agents

| Agent | Purpose | Trigger |
|-------|---------|---------|
| `crm-interaction-extractor` | Scan journals/calendar for mentions | `/crm scan`, nightshift |
| `crm-relationship-scorer` | Calculate relationship health (0-1) | On contact view, reports |
| `crm-entity-extractor` | Extract entities from research | After research, `/crm extract` |
| `crm-contact-maintainer` | Dedup, validate, merge | Weekly nightshift, `/crm maintenance` |

## Workflows

### Daily: Interaction Scanning

```
/today triggers → today-hook
         ↓
    Scan recent journals for [[Contact]] mentions
         ↓
    Scan calendar for meeting attendees
         ↓
    Log interactions to contact files
         ↓
    Surface follow-ups in briefing
```

### Import from Apple Contacts / Gmail

```bash
# Step 1: Export from source
# Apple: Contacts.app → File → Export → Export vCard
# Gmail: contacts.google.com → Export → vCard format

# Step 2: Run import (preview first)
python crm_cli.py import ~/Downloads/contacts.vcf --dry-run

# Step 3: Import to space
python crm_cli.py import ~/Downloads/contacts.vcf --space 0-personal

# Step 4: Review draft contacts
# All imports have status: draft
# Change to status: active after review
```

### Email Enrichment from Gmail

```bash
# Step 1: Setup Gmail OAuth (one-time)
python email_enricher.py setup --account you@gmail.com

# Step 2: Enrich all draft contacts
python crm_cli.py enrich --gmail you@gmail.com --all-drafts

# Or enrich specific contact
python crm_cli.py enrich --gmail you@gmail.com --email contact@example.com
```

**What gets enriched:**
- First/last contact dates
- Email counts (sent/received)
- Frequency (emails/month)
- Topics extracted from subjects
- Key conversation threads
- Relationship status (active/warming/cooling/dormant)

### Trip Preparation

```
/crm trip to Dubai, Dec 11-13
         ↓
    Search contacts in region (UAE/Middle East)
         ↓
    Find relevant contacts (by topic/industry)
         ↓
    Identify dormant worth reconnecting
         ↓
    Generate briefing with suggested actions
         ↓
    Optional: Add tasks to next_actions.org
```

## CLI Tools

### crm_cli.py - Main CLI

```bash
# Status and dashboard
python crm_cli.py status

# Import vCard
python crm_cli.py import [file.vcf] --space [space] [--dry-run]

# Enrich with email
python crm_cli.py enrich --gmail [account] --all-drafts

# Maintenance
python crm_cli.py maintenance --check-duplicates
python crm_cli.py maintenance --validate
```

### relationship_cli.py - Relationship Analysis

```bash
# Analyze relationship network
python relationship_cli.py analyze --space 0-personal

# Generate network graph
python relationship_cli.py graph --output network.png
```

### vcard_adapter.py - vCard Processing

```bash
# Parse and preview vCard
python vcard_adapter.py preview contacts.vcf

# Convert to markdown contacts
python vcard_adapter.py convert contacts.vcf --output ./contacts/people/
```

### email_enricher.py - Gmail Integration

```bash
# Setup OAuth
python email_enricher.py setup --account you@gmail.com

# Analyze email history for contact
python email_enricher.py analyze --email contact@example.com

# Batch enrich
python email_enricher.py batch --space 0-personal
```

## Folder Structure

```
[space]/contacts/
├── _index.md              # Contacts index
├── people/
│   └── [Person Name].md
├── companies/
│   └── [Company Name].md
├── projects/
│   └── [Project Name].md
├── events/
│   └── [Event Name].md
└── landscape/
    ├── _overview.md       # Industry landscape
    ├── competitors.md
    └── ecosystem.md
```

## Contact Schema

```yaml
---
type: contact
entity_type: person | company | project | event
name: "[Name]"
status: draft | active | dormant | archived
relationship_status: discovered | lead | contacted | active | partner | dormant
relationship_type: partner | investor | customer | competitor | target_*
relevance: 1-5
industries: [storage, web3, defi]

# Person-specific
organization: "[[Company]]"
role: "VP of Partnerships"
channels:
  email: john@example.com
  linkedin: /in/johnsmith
introduced_by: "[[Referrer]]"
met_at: "[[Event Name]]"

# Email history (from enrichment)
email_history:
  first_contact: 2023-05-15
  last_contact: 2025-12-18
  total_messages: 47
  sent_count: 22
  received_count: 25
  frequency: 3.2  # per month
  topics: [partnership, proposal, funding]
---
```

## Hooks

| Hook | Trigger | Action |
|------|---------|--------|
| `today-hook` | `/today` | Surface follow-ups, pre-meeting context |
| `weekly-hook` | `/gtd-weekly-review` | Relationship health overview |
| `nightshift-hook` | Daily nightshift | Auto-scan, index update |
| `research-hook` | Research complete | Entity extraction from new research |

## Configuration

In `settings.local.yaml`:

```yaml
crm:
  scan_days_default: 7         # Journal scan range
  dormant_threshold_days: 60   # Days until marked dormant
  auto_scan_enabled: true      # Scan on /today

  entity_extraction:
    auto_create_drafts: false  # Auto-create from research
    min_confidence: 0.7

  maintenance:
    weekly_maintenance: true
    stale_threshold_days: 180

  relationship_score_weights:
    recency: 0.4
    frequency: 0.3
    depth: 0.2
    reciprocity: 0.1
```

## GTD Integration

CRM tasks use `:CRM:` tag:

```org
* TODO Follow up with [[John Smith]] on partnership   :CRM:
  :PROPERTIES:
  :CONTACT: John Smith
  :END:
```

## Dependencies

- `core@>=1.0.0` (required)
- `gtd` (optional) - Enhanced task integration
- `nightshift` (optional) - Automated scans
- `mail` (optional) - Email interaction capture
- `meetings` (optional) - Meeting interaction capture

## Related DIPs

- [DIP-0012](../../dips/DIP-0012-crm-module.md) - CRM Module specification
- [DIP-0002](../../dips/DIP-0002-layered-context-pattern.md) - Cross-space index
- [DIP-0009](../../dips/DIP-0009-gtd-specification.md) - GTD integration
- [DIP-0010](../../dips/DIP-0010-external-sync-architecture.md) - Adapter pattern
- [DIP-0014](../../dips/DIP-0014-tag-taxonomy.md) - Tag taxonomy

## Version History

- **v0.2.0** - Gmail enrichment, vCard import, relationship scoring, automation CLI
- **v0.1.0** - Initial release: contacts, interactions, journal scanning
