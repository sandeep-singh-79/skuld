# V1 Input Template

Canonical input schema reference for Skuld. The tool accepts a single YAML document.

---

## Top-Level Structure

```yaml
story:           # Required — story metadata
acceptance_criteria:  # Required — list of ACs
comments:        # Optional — team comments for context
domain_context:  # Optional — domain-specific information
strategy_ref:    # Optional — strategy approval reference
config:          # Optional — model and generation config
```

---

## `story`

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | string | Yes | Unique story identifier (e.g. `"PROJ-101"`) |
| `title` | string | Yes | Human-readable story title |
| `description` | string | Yes | As-a-user story description |

---

## `acceptance_criteria[]`

List of acceptance criteria objects. At least 1 required; maximum 30.

| Field | Type | Required | Default | Valid Values | Description |
|-------|------|----------|---------|--------------|-------------|
| `id` | string | Yes | — | — | Unique AC identifier (e.g. `"AC-1"`) |
| `description` | string | Yes | — | — | What the AC requires |
| `criticality` | string | No | `"medium"` | `high`, `medium`, `low` | Drives test priority assignment |

---

## `comments[]`

Optional list of strings. Skuld filters these for signal (dev notes, QA concerns, scope constraints) and uses them to enrich edge-case generation.

```yaml
comments:
  - "Dev: what about session timeout during MFA flow?"
  - "QA: handle SMS delivery failure gracefully"
  - "PM: biometric login explicitly out of scope for v1"
```

---

## `domain_context`

Optional dict providing industry and application context for richer, domain-relevant test generation.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `industry` | string | No | Industry vertical (e.g. `"fintech"`, `"insurance"`) |
| `application_type` | string | No | Application category (e.g. `"banking portal"`) |
| `users` | string | No | Description of end users |
| `compliance` | list[string] | No | Regulatory frameworks (e.g. `["PCI-DSS", "SOX"]`) |
| `business_rules` | list[string] | No | Domain business rules relevant to testing |

```yaml
domain_context:
  industry: "fintech"
  application_type: "banking portal"
  users: "retail banking customers"
  compliance:
    - "PCI-DSS"
    - "SOX"
  business_rules:
    - "All login attempts must be audit-logged"
```

---

## `strategy_ref`

Optional reference to an approved QEStrategyForge output. If provided, triggers a HITL (human-in-the-loop) gate check.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | string | No | Path to strategy output file |
| `approved` | boolean | No | Whether the strategy was approved |
| `reviewed_by` | string | No | Who approved the strategy |

```yaml
strategy_ref:
  path: "path/to/strategy_output.md"
  approved: true
  reviewed_by: "sandeep.singh"
```

---

## `config`

Optional configuration block. If omitted, defaults apply.

| Field | Type | Default | Valid Values | Description |
|-------|------|---------|--------------|-------------|
| `generator_model` | string | `"claude-sonnet-4-20250514"` | Any model identifier | LLM for test case generation |
| `reviewer_model` | string | `"gpt-4o"` | Any model identifier | LLM for adversarial review (must differ from generator) |
| `min_negative_per_ac` | int | `1` | ≥1 | Minimum negative tests required per AC |
| `min_edge_case_per_ac` | int | `1` | ≥1 | Minimum edge-case tests required per AC |
| `output_format` | string | `"markdown"` | `markdown`, `json` | Default output format |
| `filter_comments` | bool | `true` | `true`, `false` | Run signal-over-noise filter on comments before injection |
| `generator_temperature` | number | `0.7` | `0.0`–`2.0` | Temperature for generator phase (simple mode) |
| `reviewer_temperature` | number | `0.2` | `0.0`–`2.0` | Temperature for reviewer phase (simple mode) |
| `refinement_temperature` | number | `0.5` | `0.0`–`2.0` | Temperature for refinement phase (simple mode) |
| `max_tokens` | integer | `4096` | `> 0` | Max output tokens per LLM call |
| `max_tokens_per_run` | integer | `32000` | `> 0` | Total token budget shared across all phases |

---

## Validation Rules

- `story.id`, `story.title`, `story.description` — must all be present and non-empty
- `acceptance_criteria` — at least 1, maximum 30 entries; all `id` values must be unique
- `config.generator_model` and `config.reviewer_model` — must differ (Skuld warns if the same)
- File size — must be ≤ 1MB

---

## Complete Annotated Example

```yaml
story:
  id: "AUTH-101"
  title: "User login with MFA"
  description: >
    As a registered user, I want to log in using multi-factor authentication
    so that my account is protected from unauthorised access.

acceptance_criteria:
  - id: "AC-1"
    description: "User can log in with valid email and password"
    criticality: high
  - id: "AC-2"
    description: "MFA code sent to registered phone after password validation"
    criticality: high
  - id: "AC-3"
    description: "Login fails after 3 incorrect MFA attempts with account lock"
    criticality: medium
  - id: "AC-4"
    description: "Meaningful error message for expired MFA code"
    criticality: low

comments:
  - "Dev: what about session timeout during MFA flow?"
  - "QA: handle SMS delivery failure gracefully"

domain_context:
  industry: "fintech"
  application_type: "banking portal"
  users: "retail banking customers"
  compliance:
    - "PCI-DSS"
    - "SOX"

config:
  generator_model: "claude-sonnet-4"
  reviewer_model: "gpt-5.5"
  filter_comments: true
  output_format: "markdown"
```

Run it:

```bash
skuld generate story.yaml --dry-run
```

---

## `config.model_routing` (Advanced)

Per-phase model routing for full control over which provider/model is used at each pipeline stage.

When `model_routing` is present, it takes precedence over top-level `generator_model`/`reviewer_model`.

| Field | Type | Required | Default | Valid Values |
|-------|------|----------|---------|--------------|
| `generator` | object | Yes (if routing used) | — | Phase config object |
| `reviewer` | object | Yes (if routing used) | — | Phase config object |
| `refinement` | object | Yes (if routing used) | — | Phase config object |

### Phase Config Object

| Field | Type | Required | Default | Valid Values |
|-------|------|----------|---------|--------------|
| `model` | string | Yes | — | Any valid model name |
| `provider` | string | No | Inferred from model name | `anthropic`, `openai` |
| `temperature` | number | No | `0.7` | `0.0` to `2.0` |
| `max_tokens` | integer | No | `4096` | `> 0` |

### Provider inference rules

| Model prefix | Inferred provider |
|-------------|-------------------|
| `claude-*` | `anthropic` |
| `gpt-*` | `openai` |
| `o1-*`, `o3-*`, `o4-*` | `openai` |
| Other | Must supply explicit `provider` |

### Validation rules

- All three phases (`generator`, `reviewer`, `refinement`) must be present.
- `model` must be a non-empty string.
- If `provider` is explicit and model has a known prefix, they must match.
- `temperature` must be a number between 0.0 and 2.0.
- `max_tokens` must be a positive integer.
- Boolean values (`true`/`false`) are rejected for numeric fields.

### Example

```yaml
config:
  max_tokens_per_run: 48000
  model_routing:
    generator:
      model: "claude-sonnet-4-20250514"
      provider: "anthropic"
      temperature: 0.7
      max_tokens: 4096
    reviewer:
      model: "gpt-4o"
      provider: "openai"
      temperature: 0.2
      max_tokens: 4096
    refinement:
      model: "claude-sonnet-4-20250514"
      provider: "anthropic"
      temperature: 0.5
      max_tokens: 4096
```
