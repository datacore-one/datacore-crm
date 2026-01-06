---
type: contact
entity_type: person
name: "{{NAME}}"
status: draft                     # draft | active | dormant | archived
relationship_status: discovered   # discovered | lead | contacted | in_discussion | active | partner | dormant | archived
relationship_type: ""             # partner | investor | customer | vendor | advisor | peer | competitor | target_*
relevance: 2                      # 1-5 (minimal to critical)
privacy: personal                 # personal | team
space: {{SPACE}}
organization: ""
role: ""
industries: []                    # Kept for machine queries (kebab-case)
channels:
  email: ""
  telegram: ""
  linkedin: ""
  phone: ""
location: ""
introduced_by: ""
met_at: ""
discovered_in: ""                 # Source: "[[Literature Note]]" | "research" | "journal"
# Import metadata (set by /crm import)
import_source: ""                 # gmail | apple | manual
import_date: ""                   # When imported
photo: ""                         # Path to photo: .photos/Name.jpg
# Email history (set by /crm enrich)
email_history:
  first_contact: ""               # Earliest email exchange
  last_contact: ""                # Most recent email
  total_messages: 0               # Total email count
  sent_count: 0                   # Emails sent to contact
  received_count: 0               # Emails received from contact
  frequency: ""                   # e.g., "3.2/month"
  topics: []                      # Keywords from subject lines
  relationship_status: ""         # active | warming | cooling | dormant
created: {{DATE}}
updated: {{DATE}}
last_interaction: {{DATE}}
---

# {{NAME}}

## Overview

<!-- Role, organization, how you met -->

**Relevance:** <!-- Why this person matters to you/your work -->

## Goals

**What I want:**
-

**What they want:**
-

## Notes

<!-- Freeform notes, personality observations, conversation highlights -->

## Email History

<!-- Auto-populated by /crm enrich command -->

## Interaction Log

<!-- Auto-populated by CRM adapters -->

| Date | Channel | Type | Summary |
|------|---------|------|---------|
| {{DATE}} | journal | mention | Initial contact created |

## Next Actions

<!-- Embedded from next_actions.org with :CRM: tag and :CONTACT: property -->

## Related

<!-- Wiki-links to company, other contacts, projects -->
-

#industry-tag, #relationship-type
