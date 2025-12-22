# CRM Hook: Research Integration

## Command Context

### When to Reference Research Module

**Always reference when:**
- Research processor creates literature notes
- Research link processor creates reports
- New entities (people, companies, projects) appear in research
- Building network from research activities

**Key decisions the module informs:**
- Which entities from research should become contacts
- How to populate CRM from research workflows
- Confidence levels for auto-creation decisions

### Quick Reference

| Question | Answer |
|----------|--------|
| When does this hook run? | After gtd-research-processor or research-link-processor completes |
| Does it auto-create contacts? | Only if auto_create_drafts setting is true (default: false) |
| What triggers extraction? | New literature note or research report creation |
| How are entities reported? | Appended to research output with confidence scores |

### Agents This Command Invokes

| Agent | Purpose |
|-------|---------|
| crm-entity-extractor | Extract and classify entities from research content |

### Integration Points

- **gtd-research-processor** - Triggers hook after literature note creation
- **research-link-processor** - Triggers hook after research report creation
- **crm-entity-extractor** - Performs actual entity extraction
- **crm-contact-maintainer** - Deduplicates any auto-created contacts

---

Extracts entities from research outputs when research processor completes.

## Trigger

Called after:
- `gtd-research-processor` creates literature note
- `research-link-processor` creates research report

## Input

```yaml
file_path: string    # Path to newly created literature note or report
source_url: string   # Original URL that was processed
```

## Actions

### 1. Check Entity Extraction Setting

```yaml
# If settings.entity_extraction.auto_create_drafts is false (default):
# - Report entities found, don't create contacts

# If true:
# - Create draft contacts for high-confidence entities
```

### 2. Run Entity Extractor

Invoke `crm-entity-extractor` with the new file:

```yaml
input:
  file_path: "{{file_path}}"
  auto_create: "{{settings.entity_extraction.auto_create_drafts}}"
  space: "{{current_space}}"
```

### 3. Report Results

**If entities found:**
```
CRM: Extracted {{count}} entities from research

High confidence (>0.8):
- Protocol Labs (company)
- Juan Benet (person)
- Filecoin (project)

Run `/crm extract {{file_path}}` to review and create contacts.
```

**If no entities:**
```
CRM: No entities detected in {{file_path}}
```

## Output

Appended to research output:

```markdown
---

## CRM Entities Detected

| Entity | Type | Confidence |
|--------|------|------------|
| Protocol Labs | company | 0.95 |
| Juan Benet | person | 0.85 |

*Run `/crm extract` to create contacts*
```

## Your Boundaries

**YOU CAN:**
- Read the research output file
- Run entity extraction
- Append summary to research output
- Create draft contacts (if auto_create enabled)

**YOU CANNOT:**
- Modify the original research content
- Create contacts without draft status
- Skip reporting entities found

**YOU MUST:**
- Always report extraction results
- Respect auto_create_drafts setting
- Include confidence scores in report

## Related

- [crm-entity-extractor](../agents/crm-entity-extractor.md) - Extraction logic
- [gtd-research-processor](../../../agents/gtd-research-processor.md) - Triggers this hook
