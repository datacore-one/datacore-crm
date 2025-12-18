# CRM Hook: /today Integration

This hook adds CRM context to the daily briefing.

## Trigger

Called by `/today` command when CRM module is installed.

## Sections to Add

### 1. Today's Meeting Context

If calendar has meetings today, show attendee context:

```
MEETING CONTEXT
───────────────
10:00 - Partnership Discussion
  Attendees:
  - [[John Smith]] (Acme Corp) - Last: Dec 15 - Active
    Goal: Finalize partnership terms
  - [[Jane Doe]] (Acme Corp) - Last: Nov 28 - Cooling
    Note: Decision maker, prefers data-driven proposals

14:00 - Investor Update
  Attendees:
  - [[Investor X]] - Last: Dec 10 - Active
    Goal: Seed round participation
```

### 2. Follow-ups Due Today

Show `:CRM:` tasks scheduled for today:

```
CRM FOLLOW-UPS DUE
──────────────────
- [ ] Email [[John Smith]] partnership proposal update
- [ ] Send deck to [[Investor X]]
```

### 3. Attention Needed (Optional)

If `auto_scan_enabled: true`, show high-value dormant contacts:

```
RELATIONSHIP ATTENTION
──────────────────────
Dormant >30 days (high value):
- [[Partner Contact]] - Last: Nov 10 (38 days)
  Was: Active partnership discussion
```

## Data Sources

- `calendar.org` - Today's meetings
- `next_actions.org` - Tasks with `:CRM:` tag scheduled today
- `.datacore/state/crm/contacts-index.yaml` - Contact scores and status

## Output Format

Return markdown sections to be included in `/today` output.

## Conditions

| Condition | Behavior |
|-----------|----------|
| No meetings today | Skip meeting context section |
| No CRM tasks due | Skip follow-ups section |
| No dormant contacts | Skip attention section |
| `auto_scan_enabled: false` | Skip attention section |

## Example Output

```markdown
## CRM

### Meeting Context

**10:00 - Partnership Discussion**
- [[John Smith]] (Acme Corp) - Active | Last: Dec 15
- [[Jane Doe]] (Acme Corp) - Cooling | Last: Nov 28

### Follow-ups Due

- [ ] Email [[John Smith]] partnership proposal update

### Attention Needed

- [[Partner Contact]] - Dormant 38 days (was active partnership)
```
