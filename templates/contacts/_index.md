---
type: index
title: Contacts
space: {{SPACE}}
created: {{DATE}}
updated: {{DATE}}
---

# Contacts

Contact Relationship Management for {{SPACE_NAME}}.

## Overview

| Metric | Count |
|--------|-------|
| Total contacts | - |
| People | - |
| Companies | - |
| Active | - |
| Dormant | - |

## Quick Access

### By Status

- **Active**: Contacts with recent interactions
- **Dormant**: No interaction in 60+ days
- **Draft**: New, needs completion

### By Category

- **Investors**: Potential and current investors
- **Partners**: Strategic and technical partners
- **Customers**: Current and prospective customers
- **Vendors**: Service providers and suppliers

## Recent Interactions

<!-- Auto-updated by CRM scan -->

| Date | Contact | Type | Summary |
|------|---------|------|---------|
| | | | |

## Follow-ups Due

<!-- Embedded from next_actions.org :CRM: tasks -->

## Structure

```
contacts/
├── _index.md          # This file
├── people/            # Person contacts
│   └── [Name].md
└── companies/         # Company contacts
    └── [Name].md
```

## Usage

### Create Contact

```
/crm new
```

Or create file directly in `people/` or `companies/`.

### Log Interaction

Mention contacts in daily journal:
```markdown
Met with [[John Smith]] to discuss partnership.
```

Or use `/crm` → "Log interaction"

### Scan for Interactions

```
/crm scan
```

Extracts `[[Contact]]` mentions from journals and calendar.

## Related

- [[next_actions.org]] - Tasks with `:CRM:` tag
- [[calendar.org]] - Meeting attendees
