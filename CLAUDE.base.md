# Module: CRM

Network Intelligence for Datacore. Track entities (people, companies, projects, events), relationships, and industry landscape. Capture from research, journals, and external channels. Surface strategic insights in workflows.

## Overview

The CRM module serves as a central hub for network intelligence:

```
┌─────────────────────────────────────────────────────────────┐
│                  CAPTURE LAYER                               │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐ │
│  │Journal │ │Calendar│ │Research│ │  Mail  │ │ External  │ │
│  │ (CRM)  │ │ (CRM)  │ │Extract │ │(module)│ │ Adapters  │ │
│  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └─────┬─────┘ │
│      └──────────┴──────────┴──────────┴────────────┘       │
│                           │                                 │
│                           ▼                                 │
│            ┌──────────────────────────┐                    │
│            │     CRM MODULE (HUB)     │                    │
│            │  - 4 Entity Types        │                    │
│            │  - Relationship Lifecycle│                    │
│            │  - Industry Landscape    │                    │
│            └────────────┬─────────────┘                    │
└─────────────────────────┼──────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     SURFACE LAYER                            │
│  /today          /gtd-weekly-review      Landscape          │
│  - Follow-ups    - Relationship health   - Industry view    │
│  - Dormant       - Follow-up queue       - Competitors      │
│  - Pre-meeting   - Contacts engaged      - Ecosystem        │
└─────────────────────────────────────────────────────────────┘
```

## Entity Types

| Type | Description | Examples |
|------|-------------|----------|
| `person` | Individual contact | John Smith, Juan Benet |
| `company` | Organization | Acme Corp, Protocol Labs |
| `project` | Product, protocol, initiative | Filecoin, IPFS |
| `event` | Conference, meetup | ETH Denver 2025 |

## Relationship Taxonomy

### Status (Lifecycle)

```
discovered → lead → contacted → in_discussion → negotiating → active/partner/customer
                                                               ↓
                                                        dormant → churned → archived
```

### Types

| Category | Types |
|----------|-------|
| Collaborative | partner, investor, customer, vendor, advisor, collaborator |
| Neutral | peer, acquaintance, press |
| Competitive | competitor, indirect_competitor |
| Potential | target_customer, target_partner, target_investor |

### Relevance (1-5)

| Score | Level | Description |
|-------|-------|-------------|
| 5 | Critical | Must-have relationship |
| 4 | High | Important for strategy |
| 3 | Medium | Useful connection |
| 2 | Low | Nice to have |
| 1 | Minimal | Peripheral |

### Industries (Dynamic)

Industries are **discovered, not hardcoded**. First use creates a canonical entry in the registry at `.datacore/state/crm/industries.yaml`. Similar tags are detected and suggested for merge.

## Commands

### /crm

Single conversational entry point for all CRM operations.

**Menu options:**
1. View network status
2. Prepare for trip/event
3. Scan for new interactions
4. Create or update contact
5. Run maintenance (dedupe, validate)
6. Generate landscape

## Agents

### crm-interaction-extractor

Extracts `[[Contact Name]]` mentions from journals and calendar attendees.

**Trigger:** Called by `/crm` scan or nightshift

### crm-relationship-scorer

Calculates relationship health score (0-1) based on recency, frequency, depth, reciprocity.

### crm-entity-extractor

**NEW:** Extracts entities from research outputs and literature notes.

**Trigger:** After research processor, or manual `/crm extract [file]`

**Process:**
- Detect person/company/project/event patterns
- Extract context and suggest industries
- Check against existing contacts
- Create draft contacts (with flag)

### crm-contact-maintainer

**NEW:** Maintains contact database quality.

**Trigger:** Weekly via nightshift, or manual `/crm maintenance`

**Process:**
- Duplicate detection (Levenshtein similarity)
- Validation (broken links, incomplete, stale)
- Merge preview generation
- Industry registry maintenance

## Folder Structure

```
[space]/contacts/
├── _index.md              # Contacts index
├── people/
│   └── [Person Name].md
├── companies/
│   └── [Company Name].md
├── projects/              # NEW
│   └── [Project Name].md
├── events/                # NEW
│   └── [Event Name].md
└── landscape/             # NEW
    ├── _overview.md       # Industry landscape
    ├── competitors.md
    └── ecosystem.md
```

## Contact Note Schema

### Common Fields

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
tags: []
discovered_in: "[[Source]]"    # Research source
created: YYYY-MM-DD
updated: YYYY-MM-DD
---
```

### Entity-Specific Fields

| Entity | Additional Fields |
|--------|-------------------|
| Person | organization, role, channels, introduced_by, met_at |
| Company | market_position, stage, website, linkedin |
| Project | project_type, stage, parent_company, github, docs |
| Event | event_type, date_start, date_end, location, website |

## Industry Landscape

The landscape provides strategic network intelligence:

- **Industry overview**: Contacts by industry with counts
- **Relationship distribution**: Partners, customers, competitors, targets
- **Competitor tracking**: Direct competitors with positioning
- **Coverage gaps**: Industries/areas lacking relationships

Generate with `/crm landscape` or via landscape compiler.

## GTD Integration

CRM tasks use `:CRM:` tag in `next_actions.org`:

```org
* TODO Follow up with [[John Smith]] on partnership   :CRM:
  :PROPERTIES:
  :CONTACT: John Smith
  :END:
```

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `scan_days_default` | 7 | Journal scan range |
| `dormant_threshold_days` | 60 | Days until dormant |
| `auto_scan_enabled` | true | Scan on /today |
| `entity_extraction.auto_create_drafts` | false | Auto-create from research |
| `entity_extraction.min_confidence` | 0.7 | Minimum confidence for extraction |
| `maintenance.weekly_maintenance` | true | Run weekly via nightshift |
| `maintenance.stale_threshold_days` | 180 | Days until stale warning |

## Related DIPs

- [DIP-0002](../../dips/DIP-0002-layered-context-pattern.md) - Cross-space index
- [DIP-0009](../../dips/DIP-0009-gtd-specification.md) - GTD integration
- [DIP-0010](../../dips/DIP-0010-external-sync-architecture.md) - Adapter pattern
- [DIP-0012](../../dips/DIP-0012-crm-module.md) - CRM specification
