# CRM Hook: /gtd-weekly-review Integration

This hook adds CRM analysis to the weekly GTD review.

## Trigger

Called by `/gtd-weekly-review` command when CRM module is installed.

## Sections to Add

### 1. Relationship Health Overview

```
RELATIONSHIP HEALTH
───────────────────
Total contacts: 78 (47 personal, 31 team)

Status Distribution:
  Active (>0.7):   12 ████████████
  Warming (0.5-0.7): 8 ████████
  Cooling (0.4-0.5): 10 ██████████
  Dormant (<0.4):  15 ███████████████

Trend vs Last Week:
  ↑ Improved: 5
  → Stable: 40
  ↓ Declined: 8
```

### 2. This Week's Activity

```
WEEKLY ACTIVITY
───────────────
Interactions logged: 12
  Meetings: 4
  Emails: 5
  Mentions: 3

Contacts engaged: 8
New contacts created: 3
```

### 3. Follow-up Queue

```
FOLLOW-UP QUEUE
───────────────
Overdue:
- [ ] Email [[Acme Corp]] - Due Dec 10 (8 days overdue)

This Week:
- [ ] Follow up [[John Smith]] on partnership - Dec 20
- [ ] Send deck to [[Investor X]] - Dec 22

Next Week:
- [ ] Quarterly check-in [[Jane Doe]] - Dec 28
```

### 4. Attention Needed

```
ATTENTION NEEDED
────────────────
High-value dormant (>30 days):
- [[Partner Contact]] - Last: Nov 10 (38 days)
  Was: Active partnership discussion
  Suggested: Schedule catch-up call

Declining relationships:
- [[Investor Y]] - Score dropped 0.65 → 0.45
  Reason: No contact in 3 weeks after active period
  Suggested: Send project update email
```

## Data Sources

- `.datacore/state/crm/contacts-index.yaml` - All contact data
- `next_actions.org` - Tasks with `:CRM:` tag
- Journal scans from past 7 days

## Output Format

Return markdown sections to be included in `/gtd-weekly-review` output.

## Actions

During weekly review, offer:
1. Run full CRM scan for the week
2. Update relationship scores
3. Create follow-up tasks for dormant contacts
4. Archive stale contacts

## Example Output

```markdown
## CRM Review

### Relationship Health

| Status | Count | Change |
|--------|-------|--------|
| Active | 12 | +2 |
| Warming | 8 | -1 |
| Cooling | 10 | +1 |
| Dormant | 15 | -2 |

### This Week

- **Interactions:** 12 (4 meetings, 5 emails, 3 mentions)
- **Contacts engaged:** 8
- **New contacts:** 3

### Follow-up Queue

**Overdue (1):**
- Email [[Acme Corp]] - 8 days overdue

**This week (2):**
- Follow up [[John Smith]] - Dec 20
- Send deck [[Investor X]] - Dec 22

### Attention Needed

**Dormant high-value:**
- [[Partner Contact]] - 38 days, suggest catch-up call
```
