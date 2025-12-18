# CRM Hook: Nightshift Integration

Automated CRM maintenance tasks for nightshift execution.

## Trigger

Called by nightshift when:
- Nightly batch runs (midnight)
- Manual `/tomorrow` queue includes CRM tasks

## Tasks to Queue

### 1. Daily Interaction Scan

Scan journals from the past 24 hours for new interactions.

**Task:**
```org
* TODO CRM: Scan daily interactions                              :AI:crm:
  SCHEDULED: <[tomorrow]>
  :PROPERTIES:
  :EFFORT: 0:15
  :AI_TYPE: crm
  :END:
```

**Execution:**
```bash
PYTHONPATH=.datacore/lib:.datacore/modules/crm/lib python3 -c "
from adapters import scan_all_adapters, aggregate_by_contact
results = scan_all_adapters(days=1)
total = sum(len(v) for v in results.values())
print(f'Scanned: {total} interactions in last 24h')
for channel, interactions in results.items():
    if interactions:
        print(f'  {channel}: {len(interactions)}')
"
```

**Output:** List of new interactions detected, contacts updated.

### 2. Index Recompilation

Update the cross-space contact index with latest data.

**Task:**
```org
* TODO CRM: Recompile contact index                              :AI:crm:
  SCHEDULED: <[tomorrow]>
  :PROPERTIES:
  :EFFORT: 0:10
  :AI_TYPE: crm
  :END:
```

**Execution:**
```bash
PYTHONPATH=.datacore/lib:.datacore/modules/crm/lib python3 -c "
from index_compiler import IndexCompiler
compiler = IndexCompiler()
index = compiler.compile_index(scan_days=90)
compiler.save_index(index)
print(f'Index compiled: {index[\"summary\"][\"total\"]} contacts')
print(f'Saved to: {compiler.index_path}')
"
```

**Output:** Updated index at `.datacore/state/crm/contacts-index.yaml`

### 3. Attention Report

Generate report of contacts needing attention for morning briefing.

**Task:**
```org
* TODO CRM: Generate attention report                            :AI:crm:
  SCHEDULED: <[tomorrow]>
  :PROPERTIES:
  :EFFORT: 0:05
  :AI_TYPE: crm
  :END:
```

**Execution:**
```bash
PYTHONPATH=.datacore/lib:.datacore/modules/crm/lib python3 -c "
from index_compiler import IndexCompiler
compiler = IndexCompiler()
attention = compiler.get_attention_needed(threshold_days=30)
if attention:
    print(f'Contacts needing attention: {len(attention)}')
    for c in attention[:5]:
        print(f'  - {c[\"name\"]}: {c[\"reason\"]}')
else:
    print('No contacts need immediate attention.')
"
```

**Output:** Attention list for inclusion in `/today` briefing.

## Conditions

| Condition | Behavior |
|-----------|----------|
| No contacts folder | Skip all tasks |
| No journal changes | Skip scan task |
| Index fresh (<6h) | Skip recompile |
| CRM disabled | Skip all tasks |

## Frequency

| Task | Schedule | Duration |
|------|----------|----------|
| Daily scan | Every night | ~2 min |
| Index recompile | Every night | ~3 min |
| Attention report | Every night | ~1 min |

Total: ~6 minutes nightly

## Error Handling

| Error | Action |
|-------|--------|
| No contacts folder | Log warning, skip |
| Import error | Log error, continue with other tasks |
| Index write fails | Retry once, then warn in morning briefing |

## Output Format

Results written to `0-inbox/nightshift-crm-*.md`:

```markdown
---
type: nightshift-output
task: crm-maintenance
status: completed
score: 0.95
timestamp: 2025-12-19T06:00:00
---

# CRM Nightshift Maintenance

## Interaction Scan
- Scanned: 12 interactions
- Journal: 8 mentions
- Calendar: 4 meetings

## Index Update
- Contacts: 45 total
- Active: 12
- Dormant: 15

## Attention Needed
- [[John Smith]] - Dormant 35 days
- [[Jane Doe]] - Declining (0.65 → 0.45)

## Recommendations
1. Schedule follow-up with [[John Smith]]
2. Review relationship with [[Jane Doe]]
```

## Integration

Add to `module.yaml`:
```yaml
hooks:
  nightshift_queue: "commands/nightshift-hook.md"
```

Nightshift reads this hook to discover CRM tasks to queue during overnight batch.
