---
summary: "Network intelligence — track entities, relationships, and industry landscape"
triggers: ["CRM dashboard", "look up contact", "dormant contacts", "who do I know at", "prepare for trip", "scan interactions"]
context: on_match
---

# CRM Module

## Purpose

Central hub for network intelligence. Tracks four entity types (people, companies, projects, events) with relationship lifecycle management. Captures from journals, calendar, research, and mail. Surfaces follow-ups, dormant contacts, and landscape insights in `/today` and weekly reviews.

## Quick Start
> Say "CRM dashboard" to see network status, follow-ups, and dormant relationships.

## How It Works

### Entity & Relationship Model
Four entity types with shared lifecycle: `discovered -> lead -> contacted -> active/partner -> dormant -> archived`. Relationship types span collaborative (partner, investor, customer), neutral (peer, acquaintance), competitive, and potential (target_*). Relevance scored 1-5. Industries are discovered dynamically, not hardcoded.

### Capture Sources
Journals (`[[Contact]]` mentions), calendar attendees, research outputs (entity extraction), mail module, and manual entry via `/crm`.

### Surfacing
Hooks into `/today` (follow-ups, dormant alerts), weekly review (relationship health), and post-research (entity extraction).

## Agents & Commands

| Name | Type | When to use |
|------|------|-------------|
| `/crm` | command | Single entry point: status, scan, create, maintain, landscape |
| `crm-interaction-extractor` | agent | Extract contact mentions from journals/calendar |
| `crm-relationship-scorer` | agent | Calculate health scores (recency, frequency, depth, reciprocity) |
| `crm-entity-extractor` | agent | Extract entities from research and literature notes |
| `crm-contact-maintainer` | agent | Weekly: dedupe, validate, merge suggestions |

## Key Paths

| Path | Purpose |
|------|---------|
| `[space]/contacts/people/` | Person contact notes |
| `[space]/contacts/companies/` | Company contact notes |
| `[space]/contacts/projects/` | Project/protocol notes |
| `[space]/contacts/events/` | Conference/event notes |
| `[space]/contacts/landscape/` | Industry overview, competitors, ecosystem |
| `.datacore/state/crm/industries.yaml` | Dynamic industry registry |

## Boundaries

- Does NOT auto-create contacts from research unless `entity_extraction.auto_create_drafts` is enabled (default: off)
- Contact notes use frontmatter schema (entity_type, status, relevance, industries) -- see DIP-0012
- GTD integration via `:CRM:` tag in `next_actions.org`

---

*This file covers structure, capability, and stable configuration. Learned behavior, user corrections, and operational preferences live as engrams -- call `plur_recall_hybrid` for those.*
