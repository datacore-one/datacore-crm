# CRM Hook: /today Integration

## Command Context

### When to Reference /today Command

**Always reference when:**
- User starts their day and runs /today
- Meetings are scheduled for today
- CRM follow-ups are due
- Contact context is needed for daily planning

**Key decisions the module informs:**
- Who you're meeting with today and their status
- Which CRM tasks are due
- Which high-value contacts are becoming dormant

### Quick Reference

| Question | Answer |
|----------|--------|
| When does this hook run? | Every time user runs /today command |
| What sections does it add? | Meeting context, follow-ups due, attention needed (optional) |
| Can sections be skipped? | Yes, if no data or auto_scan disabled for attention |
| Where does data come from? | calendar.org, next_actions.org, contacts-index.yaml |

### Agents This Command Invokes

| Agent | Purpose |
|-------|---------|
| None (reads data) | Hook reads pre-compiled index and calendar directly |

### Integration Points

- **/today command** - Calls this hook to inject CRM sections
- **crm-interaction-extractor** - Provides fresh interaction data (if auto_scan enabled)
- **Nightshift** - Ensures contact index is fresh each morning

---

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
