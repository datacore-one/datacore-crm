# Module: CRM

Contact Relationship Management for Datacore. Track relationships across spaces, extract interactions from multiple channels, and surface insights in daily workflows.

## Overview

The CRM module serves as a central hub for relationship management:

```
┌─────────────────────────────────────────────────────────────┐
│                  CAPTURE LAYER (Adapters)                    │
│  ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐ ┌───────────┐ │
│  │Journal │ │Calendar│ │Meeting │ │  Mail  │ │ Telegram/ │ │
│  │ (CRM)  │ │ (CRM)  │ │ Notes  │ │(module)│ │ LinkedIn  │ │
│  └───┬────┘ └───┬────┘ └───┬────┘ └───┬────┘ └─────┬─────┘ │
│      └──────────┴──────────┴──────────┴────────────┘       │
│                           │                                 │
│                           ▼                                 │
│            ┌──────────────────────────┐                    │
│            │     CRM MODULE (HUB)     │                    │
│            │  - Contact notes         │                    │
│            │  - Interaction log       │                    │
│            │  - Relationship scoring  │                    │
│            └────────────┬─────────────┘                    │
└─────────────────────────┼──────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     SURFACE LAYER                            │
│  /today          /gtd-weekly-review      Contact notes      │
│  - Follow-ups    - Relationship health   - Interaction log  │
│  - Dormant       - Follow-up queue       - Next actions     │
│  - Pre-meeting   - Contacts engaged                         │
└─────────────────────────────────────────────────────────────┘
```

## Commands

### /crm

Single conversational entry point for all CRM operations.

**When to use:**
- View network status and relationship health
- Prepare for trips/conferences
- Scan journals for new interactions
- Create or update contacts
- Promote contacts between spaces

**Menu options:**
1. View network status
2. Prepare for trip/event
3. Scan for new interactions
4. Create or update contact

## Agents

### crm-interaction-extractor

Extracts `[[Contact Name]]` mentions from journals and calendar attendees.

**Trigger:** Called by `/crm` scan or nightshift

**Input:** Date range to scan

**Output:** List of interactions with contact, channel, timestamp, summary

### crm-relationship-scorer

Calculates relationship health score (0-1) based on:
- Recency (40%): Exponential decay from last interaction
- Frequency (30%): Interactions per month
- Depth (20%): Meeting > email > mention
- Reciprocity (10%): Two-way vs one-way

**Score thresholds:**
- `> 0.7` Active
- `0.4 - 0.7` Warming/Cooling
- `< 0.4` Dormant

## Folder Structure

### Hybrid Approach

| Folder | Purpose | Updates |
|--------|---------|---------|
| `contacts/` | Active CRM - relationships with interaction tracking | Frequent, auto-populated |
| `reference/` | Static knowledge - people/companies as reference | Manual, occasional |

### Per-Space Structure

```
[space]/contacts/
├── _index.md              # Contacts index
├── people/
│   └── [Person Name].md
└── companies/
    └── [Company Name].md
```

## Contact Note Schema

### Person

```yaml
---
type: contact
contact_type: person
name: "[Full Name]"
status: active           # draft | active | dormant | archived
privacy: team            # personal | team
space: 1-teamspace
organization: "[[Company]]"
role: "Title"
channels:
  email: person@example.com
  telegram: "@username"
  linkedin: "/in/username"
tags: [investor, partner]
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_interaction: YYYY-MM-DD
---
```

### Sections

- **Overview**: Role, organization, relevance
- **Goals**: What I want, what they want
- **Notes**: Freeform observations
- **Interaction Log**: Auto-populated by adapters
- **Next Actions**: Embedded from `:CRM:` tasks
- **Related**: Wiki-links to company, contacts, projects

## GTD Integration

### Task Tagging

CRM tasks use `:CRM:` tag in `next_actions.org`:

```org
* TODO Follow up with [[John Smith]] on partnership   :CRM:
  SCHEDULED: <2025-12-20 Fri>
  :PROPERTIES:
  :CONTACT: John Smith
  :END:
```

### /today Integration

CRM surfaces in daily briefing:
- Today's meeting attendee context
- Follow-ups due today
- Dormant high-value relationships

### Weekly Review Integration

CRM section in weekly review:
- Interactions this week
- Relationship health distribution
- Follow-up queue

## Privacy Staging

Contacts can be promoted from personal to team space:

1. Contact starts in `0-personal/contacts/`
2. Relationship develops
3. User runs `/crm` → "Promote to team space"
4. Contact copied to team space
5. Personal notes stay private

## Adapter Interface

Other modules can implement `CRMAdapter` to feed interactions:

```python
class CRMAdapter(ABC):
    @property
    def adapter_type(self) -> str: ...

    def extract_interactions(self, since: datetime) -> List[Interaction]: ...

    def resolve_contact(self, identifier: str) -> Optional[str]: ...
```

**Built-in adapters:** journal, calendar

**External adapters:** meeting-notes, mail, telegram, linkedin (separate modules)

## Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `scan_days_default` | 7 | Journal scan range |
| `dormant_threshold_days` | 60 | Days until dormant |
| `auto_scan_enabled` | true | Scan on /today |

## Related DIPs

- [DIP-0002](../../dips/DIP-0002-layered-context-pattern.md) - Cross-space index
- [DIP-0009](../../dips/DIP-0009-gtd-specification.md) - GTD integration
- [DIP-0010](../../dips/DIP-0010-external-sync-architecture.md) - Adapter pattern
- [DIP-0012](../../dips/DIP-0012-crm-module.md) - CRM specification
