# /crm

## Command Context

### When to Reference CRM Module

**Always reference when:**
- User mentions contacts, relationships, or networking
- Preparing for trips, events, or meetings
- Need to track who you've talked to or when
- Building or maintaining professional networks
- User asks about "who do I know in [location/industry]"

**Key decisions the module informs:**
- Who to reconnect with before dormancy
- Which relationships need attention
- Meeting preparation with contact context
- Network growth and maintenance strategy

### Quick Reference

| Question | Answer |
|----------|--------|
| How does CRM track interactions? | Automatically scans journals and calendar for wiki-link mentions |
| Where are contacts stored? | [space]/contacts/ folders (people, companies, projects, events) |
| Can it auto-create contacts? | Only with confirmation or auto_create flag |
| What's the primary entry point? | /crm command with intent detection |

### Agents This Command Invokes

| Agent | Purpose |
|-------|---------|
| crm-interaction-extractor | Scan journals/calendar for interactions |
| crm-relationship-scorer | Calculate relationship health scores |
| crm-entity-extractor | Extract entities from research (via manual trigger) |
| crm-contact-maintainer | Database quality and maintenance (via /crm maintenance) |

### Integration Points

- **/today** - Shows meeting context and CRM follow-ups (via today-hook)
- **/gtd-weekly-review** - Includes relationship health overview (via weekly-hook)
- **gtd-research-processor** - Extracts entities from research (via research-hook)
- **Nightshift** - Daily scans and index updates (via nightshift-hook)

---

Contact Relationship Management - single entry point for all CRM operations.

## Intent Detection

If the user provides context with the command, infer intent:

| User Input | Intent | Action |
|------------|--------|--------|
| `/crm John Smith` | View contact | Show contact details |
| `/crm trip to Dubai` | Trip prep | Run trip preparation workflow |
| `/crm scan` | Scan interactions | Run journal/calendar scan |
| `/crm status` | Network status | Show dashboard |
| `/crm new` or `/crm add` | Create contact | Run create workflow |
| `/crm import` or `/crm import [file]` | Import contacts | Run vCard import workflow |
| `/crm enrich` | Enrich with email | Run email enrichment workflow |

If no context or unclear intent, present the menu.

## Menu

```
CRM - Contact Relationship Management

What would you like to do?

1. **View network status** - Dashboard of contacts and relationship health
2. **Prepare for trip/event** - Pre-meeting briefing with relevant contacts
3. **Scan for interactions** - Update from journals and calendar
4. **Create or update contact** - Add new or edit existing contact
5. **Import contacts** - Import from Apple Contacts or Gmail (vCard)
6. **Enrich with email history** - Add interaction data from Gmail
```

## Workflows

### 1. Network Status

Display CRM dashboard:

```
CRM STATUS
──────────

Overview
────────
Total contacts: 78 (47 personal, 31 team)
Active: 34 | Dormant: 29 | New: 15

Recent Activity (7 days)
────────────────────────
Interactions logged: 12
New contacts: 3
Contacts engaged: 8

Attention Needed
────────────────
Dormant >30 days (high value):
- [[John Smith]] - Last: Nov 10 - Investor lead
- [[Jane Doe]] - Last: Nov 5 - Partner contact

Follow-ups overdue:
- Email [[Acme Corp]] - Due Dec 10 (8 days overdue)

This Week
─────────
Scheduled meetings: 3
Follow-ups due: 5
```

**Data sources:**
- Cross-space index at `.datacore/state/crm/contacts-index.yaml`
- Tasks with `:CRM:` tag from `next_actions.org`
- Calendar entries from `calendar.org`

### 2. Trip Preparation

**Step 1: Gather trip info**

```
Where are you going?
> [Event name, location, dates]

Example: "Solana Breakpoint, Abu Dhabi, Dec 11-13"
```

**Step 2: Search contacts**

Search by:
- Location field matching trip location
- Tags matching event topic
- Companies relevant to event
- Dormant contacts worth reconnecting

**Step 3: Generate briefing**

```
TRIP PREPARATION: Solana Breakpoint
───────────────────────────────────
Event: Dec 11-13, 2025 | Abu Dhabi, UAE

CONTACTS IN REGION (UAE/Middle East)
────────────────────────────────────
- [[Alaa El Rabah]] (DMCC) - Last: Nov 15
  Role: Partnership lead
  Goal: Finalize company setup

RELEVANT CONTACTS (Solana/Crypto)
─────────────────────────────────
- [[Chainlink Team]] - Last: Sep 20 (dormant)
  Note: Explore BUILD program integration

DORMANT WORTH RECONNECTING
──────────────────────────
- [[Investor X]] - Last: Aug 15 (125 days)
  Was interested in data infrastructure

SUGGESTED PRE-TRIP ACTIONS
──────────────────────────
1. TODO Email [[Alaa El Rabah]] to schedule meeting    :CRM:
2. TODO Research Chainlink updates before event        :CRM:
3. TODO Prepare [[Investor X]] update one-pager       :CRM:

Add these tasks to next_actions.org? (y/n)
```

### 3. Scan for Interactions

**Step 1: Confirm scan range**

```
Scan journals and calendar for interactions.

Date range: Last 7 days (default)
Change range? (Enter days or date range, or press Enter for default)
>
```

**Step 2: Run adapters**

- Journal adapter: Scan `notes/journals/` for `[[Contact Name]]` wiki-links
- Calendar adapter: Scan `calendar.org` for meeting attendees

**Step 3: Report results**

```
CRM SCAN RESULTS
────────────────
Scanned: Dec 11-18, 2025 (7 days)

KNOWN CONTACTS MENTIONED
────────────────────────
- [[John Smith]] - 3 mentions
  Dec 18: Meeting about partnership (calendar)
  Dec 15: Mentioned in journal - follow-up needed
  Dec 12: Email exchange noted

- [[Jane Doe]] - 1 mention
  Dec 14: Coffee meeting (calendar)

NEW NAMES DETECTED
──────────────────
- [[Dr. Sarah Chen]] - 2 mentions
  Context: "Met at conference, AI researcher"
  Create contact? (y/n/skip all)

- [[Bob Wilson]] - 1 mention
  Context: "Intro from John Smith"
  Create contact? (y/n/skip all)

SUMMARY
───────
Updated 2 contact interaction logs
Detected 2 potential new contacts
```

### 4. Create or Update Contact

**Step 1: Person or Company?**

```
Create new contact:

1. Person
2. Company

>
```

**Step 2: Gather info (Person)**

```
Name: [Full name]
Organization: [Company, optional]
Role: [Title, optional]
Email: [optional]
How did you meet?: [optional]
Tags: [comma-separated, optional]
```

**Step 3: Create contact file**

Create file at `[space]/contacts/people/[Name].md` using template.

**Step 4: Confirm**

```
Created contact: [[John Smith]]
Location: 0-personal/contacts/people/John Smith.md

Next steps:
- Add notes and goals
- Log first interaction with /crm log
- Mention as [[John Smith]] in journals
```

### 5. Import Contacts (vCard)

Import contacts from Apple Contacts or Gmail exports.

**Step 1: Export from source**

| Source | How to Export |
|--------|---------------|
| Apple Contacts | Contacts.app -> File -> Export -> Export vCard |
| Gmail | contacts.google.com -> Export -> vCard format |

**Step 2: Run import**

```bash
# Via CLI
python crm_cli.py import ~/Downloads/contacts.vcf --space 0-personal

# Preview first (dry run)
python crm_cli.py import contacts.vcf --dry-run
```

**Step 3: Review output**

```
Import Results:
  Total parsed: 245
  New contacts: 231
  Duplicates skipped: 14
  Photos: 89

  By source:
    apple: 150
    gmail: 95

  Merge candidates (5):
    - John Smith + Jon Smith (fuzzy name match)

  Report saved to: 0-personal/content/reports/2025-12-22-contact-import.md
```

**Step 4: Review drafts**

All imported contacts have `status: draft`. Review and activate:

```bash
# List draft contacts
python crm_cli.py status

# Or manually review in contacts/people/
# Change status: draft to status: active after review
```

### 6. Enrich with Email History

Extract interaction history from Gmail for each contact.

**Prerequisites:**
- Gmail API OAuth configured (run `python gmail.py setup --account you@gmail.com` first)
- Contact must have an email address in `channels.email`

**Step 1: Run enrichment**

```bash
# Enrich all draft contacts
python crm_cli.py enrich --gmail you@gmail.com --all-drafts

# Or enrich specific contact by email
python crm_cli.py enrich --gmail you@gmail.com --email contact@example.com
```

**Step 2: Review results**

```
Enriching all draft contacts in 0-personal...
  Enriching John Smith (john@example.com)...
    Found 47 emails, 2023-05-15 to 2025-12-18

Results:
  Total drafts: 231
  Enriched: 189
  No email: 12
  No history: 30
```

**Step 3: Review enriched contacts**

Each contact now has an Email History section:

```markdown
## Email History

| Metric | Value |
|--------|-------|
| First contact | 2023-05-15 |
| Last contact | 2025-12-18 |
| Total emails | 47 |
| Sent | 22 |
| Received | 25 |
| Frequency | 3.2/month |
| Status | active |

**Topics:** partnership, proposal, funding, timeline

### Key Threads
- [Dec 2025] Partnership proposal follow-up (5 emails)
- [Nov 2025] Contract review (3 emails)
- [Oct 2025] Initial outreach (2 emails)
```

**Data extracted:**
- `first_contact` - Date of first email exchange
- `last_contact` - Most recent email
- `total_messages` - Total email count
- `sent_count` / `received_count` - Directional counts
- `frequency` - Emails per month average
- `topics` - Keywords extracted from subject lines
- `key_threads` - Most active conversation threads
- `relationship_status` - Calculated from recency (active/warming/cooling/dormant)

## Additional Operations

### View/Edit Contact

When user specifies a contact name:

```
/crm John Smith

JOHN SMITH
──────────
VP of Partnerships @ [[Acme Corp]]
Status: Active | Space: 1-teamspace

Contact
───────
Email: john@acme.com
LinkedIn: /in/johnsmith
Location: New York, USA

Relationship Score: 0.72 (Warming)
Last interaction: Dec 10, 2025 (8 days ago)

Recent Interactions
───────────────────
Dec 10 | meeting | Quarterly sync - discussed roadmap
Nov 28 | email   | Sent partnership proposal
Nov 15 | journal | Noted follow-up needed

Next Actions
────────────
- [ ] Follow up on partnership proposal (Dec 20)

What would you like to do?
1. Log new interaction
2. Edit contact
3. View full note
4. Promote to team space (if personal)
```

### Promote Contact

Move contact from personal to team space:

```
Promoting [[John Smith]] to team space...

Source: 0-personal/contacts/people/John Smith.md
Target: 1-teamspace/contacts/people/John Smith.md

What will happen:
- Contact copied to team space
- Personal notes section stays in personal space
- Original becomes reference link to team version

Proceed? (y/n)
```

## Error Handling

**Contact not found:**
```
No contact found matching '[name]'.

Solution:
  /crm new [name]   # Create new contact
  /crm              # Browse existing contacts
```

**No contacts folder:**
```
Contacts folder not found in [space].

Solution:
  Create structure? (y/n)
  This will create:
    [space]/contacts/
    ├── _index.md
    ├── people/
    ├── companies/
    ├── projects/
    ├── events/
    └── landscape/
```

**Duplicate contact:**
```
Contact [[Name]] already exists at [path].

Solution:
  /crm [name]           # View existing contact
  /crm maintenance      # Run dedup check
```

**Stale interaction data:**
```
Contact data may be outdated (last scan: [date]).

Solution:
  /crm scan             # Refresh from journals/calendar
```

## Your Boundaries

**YOU CAN:**
- Read and create contact notes in `contacts/` folders
- Scan journals and calendar for interactions
- Create tasks with `:CRM:` tag in `next_actions.org`
- Update cross-space index

**YOU CANNOT:**
- Delete contacts (archive only)
- Access external services directly (use adapters)
- Modify contacts in other users' personal spaces

**YOU MUST:**
- Respect privacy boundaries (personal vs team)
- Preserve existing interaction logs when updating
- Use wiki-links `[[Contact Name]]` for references
