---
name: CRM for Datacore
description: "Network intelligence — contact management, relationship scoring, and entity extraction"
version: 0.3.0
author: datacore-one
license: MIT
tags: [crm, contacts, relationships, networking, entities]
x-datacore:
  module: crm
  tools: 3
  skills: 0
  agents: 4
  commands: 1
  workflows: 0
  engram_count: 0
  injection_policy: on_match
  match_terms: [crm, contact, relationship, networking, entity, landscape, people, company]
---

# CRM for Datacore

Network intelligence — track people, companies, projects, and events.
Auto-capture from journals, calendar, and research. Surface relationship insights.

## What This Module Provides

**Tools** (MCP):
- `datacore.crm.lookup` — Look up a contact or company by name
- `datacore.crm.recent_interactions` — List recent interactions with contacts
- `datacore.crm.dormant` — Find dormant relationships needing attention

**Agents** (4):
- `crm-interaction-extractor` — Extract interactions from journals/calendar
- `crm-relationship-scorer` — Calculate relationship health scores
- `crm-entity-extractor` — Extract entities from research/literature
- `crm-contact-maintainer` — Dedup, merge, validate contacts

**Commands**:
- `/crm` — Conversational CRM operations

## When to Use

Triggers: crm, contact, relationship, networking, entity, landscape, people, company.
