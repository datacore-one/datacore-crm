# Agent: crm-interaction-extractor

Extracts contact interactions from journals and calendar for CRM module.

## Trigger

Called by:
- `/crm` scan workflow
- Nightshift scheduled scans
- `/today` auto-scan (if `auto_scan_enabled: true`)

## Input

```yaml
date_range:
  start: YYYY-MM-DD
  end: YYYY-MM-DD
space: all | [space-name]
```

## Process

### 1. Scan Journals

Search `notes/journals/` for wiki-links matching contact patterns:

```
Pattern: \[\[([^\]]+)\]\]
```

For each match:
1. Check if contact exists in `contacts/people/` or `contacts/companies/`
2. Extract surrounding context (sentence or paragraph)
3. Determine interaction type from context keywords

**Context keywords:**
- `met`, `meeting`, `call` → meeting
- `email`, `sent`, `received` → email
- `mentioned`, `discussed` → mention

### 2. Scan Calendar

Parse `calendar.org` for events in date range:

```org
* Meeting with [[John Smith]]
  <2025-12-18 Thu 10:00-11:00>
```

Extract:
- Attendees (wiki-links)
- Event title
- Date/time

### 3. Detect New Contacts

For wiki-links that don't match existing contacts:
- Flag as potential new contact
- Include context for user review
- Count occurrences

## Output

```yaml
interactions:
  - contact: "John Smith"
    date: 2025-12-18
    channel: journal
    type: meeting
    summary: "Discussed partnership proposal"
    source: "notes/journals/2025-12-18.md:45"

  - contact: "Jane Doe"
    date: 2025-12-17
    channel: calendar
    type: meeting
    summary: "Quarterly sync"
    source: "org/calendar.org:123"

new_contacts_detected:
  - name: "Dr. Sarah Chen"
    occurrences: 2
    context: "Met at conference, AI researcher"
    sources:
      - "notes/journals/2025-12-15.md:23"
      - "notes/journals/2025-12-16.md:45"

summary:
  interactions_found: 12
  contacts_updated: 5
  new_contacts_detected: 2
  date_range: "2025-12-11 to 2025-12-18"
```

## Actions

After extraction:
1. Update `last_interaction` in contact frontmatter
2. Append to interaction log in contact note
3. Update cross-space index at `.datacore/state/crm/contacts-index.yaml`
4. Report new contacts for user review

## Boundaries

**CAN:**
- Read journals and calendar
- Update contact notes (interaction log, last_interaction)
- Create new contact drafts (with user confirmation)

**CANNOT:**
- Delete contacts
- Modify contact content beyond interaction log
- Access external services

## Related

- [crm-relationship-scorer](crm-relationship-scorer.md) - Scores relationships after extraction
- [/crm](../commands/crm.md) - Command that invokes this agent
