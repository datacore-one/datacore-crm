# Agent: crm-relationship-scorer

Calculates relationship health scores for contacts based on interaction patterns.

## Trigger

Called by:
- `crm-interaction-extractor` after scan
- `/crm` status workflow
- `/gtd-weekly-review` CRM section

## Input

```yaml
contacts: all | [contact-name]
recalculate: true | false  # Force recalculation even if recent
```

## Scoring Algorithm

### Components

| Factor | Weight | Description |
|--------|--------|-------------|
| Recency | 40% | Exponential decay from last interaction |
| Frequency | 30% | Interactions per month |
| Depth | 20% | Interaction type quality |
| Reciprocity | 10% | Two-way vs one-way |

### Recency Score (0-1)

```
recency = exp(-days_since_last / decay_constant)
decay_constant = 30  # Half-life of ~21 days
```

| Days Since | Score |
|------------|-------|
| 0-7 | 0.8-1.0 |
| 8-14 | 0.6-0.8 |
| 15-30 | 0.4-0.6 |
| 31-60 | 0.2-0.4 |
| 60+ | <0.2 |

### Frequency Score (0-1)

```
frequency = min(interactions_per_month / target_frequency, 1.0)
target_frequency = 4  # Weekly contact is max score
```

### Depth Score (0-1)

Interaction types weighted by quality:

| Type | Weight |
|------|--------|
| meeting | 1.0 |
| call | 0.8 |
| email | 0.5 |
| message | 0.4 |
| mention | 0.2 |

```
depth = weighted_average(interaction_types)
```

### Reciprocity Score (0-1)

```
reciprocity = min(outbound, inbound) / max(outbound, inbound)
```

Where outbound = interactions I initiated, inbound = interactions they initiated.

### Final Score

```
score = (recency * 0.4) + (frequency * 0.3) + (depth * 0.2) + (reciprocity * 0.1)
```

## Status Thresholds

| Score Range | Status | Description |
|-------------|--------|-------------|
| > 0.7 | Active | Strong, engaged relationship |
| 0.5 - 0.7 | Warming | Building relationship |
| 0.4 - 0.5 | Cooling | Needs attention |
| < 0.4 | Dormant | Risk of losing connection |

## Output

```yaml
scores:
  - contact: "John Smith"
    score: 0.72
    status: active
    components:
      recency: 0.85
      frequency: 0.60
      depth: 0.75
      reciprocity: 0.50
    trend: stable  # improving | stable | declining
    last_interaction: 2025-12-15

  - contact: "Jane Doe"
    score: 0.35
    status: dormant
    components:
      recency: 0.15
      frequency: 0.40
      depth: 0.60
      reciprocity: 0.30
    trend: declining
    last_interaction: 2025-10-20

summary:
  total_scored: 45
  active: 12
  warming: 8
  cooling: 10
  dormant: 15

attention_needed:
  - contact: "Jane Doe"
    reason: "Dormant 58 days, was active investor lead"
    suggested_action: "Schedule catch-up call"
```

## Actions

After scoring:
1. Update `status` in contact frontmatter
2. Flag contacts needing attention
3. Generate suggested follow-up actions
4. Update cross-space index

## Your Boundaries

**YOU CAN:**
- Read contact notes and interaction logs
- Update contact status field
- Generate suggestions

**YOU CANNOT:**
- Create tasks automatically (only suggest)
- Modify interaction history
- Delete or archive contacts

**YOU MUST:**
- Use the documented scoring algorithm consistently
- Flag all contacts below dormant threshold
- Include trend analysis (improving/stable/declining)

## Related

- [crm-interaction-extractor](crm-interaction-extractor.md) - Provides interaction data
- [/crm](../commands/crm.md) - Displays scores in status view
