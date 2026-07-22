# Usage Guide

End-to-end usage instructions for Skuld — from installation to RTM management.

---

## Prerequisites

- Python ≥ 3.13
- pip (any recent version)

---

## Provider Setup

Skuld supports two LLM providers. The default config uses Anthropic for generation/refinement
and OpenAI for adversarial review, so a default real-provider run requires both keys.
You can run with a single provider only if your input config routes every used phase to
models from that provider.

### Environment Variables

| Variable | Provider | Required for |
|----------|----------|--------------|
| `SKULD_ANTHROPIC_KEY` | Anthropic | Claude models (`claude-sonnet-4-*`, `claude-haiku-4-*`) |
| `SKULD_OPENAI_KEY` | OpenAI | GPT models (`gpt-4o`, `gpt-5.5`), o-series (`o1-*`, `o3-*`, `o4-*`) |

Set them in your shell profile or inline:

```bash
# Option 1: Shell profile (~/.bashrc, ~/.zshrc)
export SKULD_ANTHROPIC_KEY="sk-ant-..."
export SKULD_OPENAI_KEY="sk-..."

# Option 2: Inline per-command for the default mixed-provider config
SKULD_ANTHROPIC_KEY="sk-ant-..." SKULD_OPENAI_KEY="sk-..." skuld generate story.yaml

# Option 3: From a vault/secret manager
SKULD_ANTHROPIC_KEY=$(vault kv get -field=key secret/skuld/anthropic) \
SKULD_OPENAI_KEY=$(vault kv get -field=key secret/skuld/openai) \
skuld generate story.yaml
```

**Windows PowerShell:**
```powershell
$env:SKULD_ANTHROPIC_KEY = "sk-ant-..."
$env:SKULD_OPENAI_KEY = "sk-..."
skuld generate story.yaml
```

### Provider Extras

Install the SDK for your chosen provider(s):

```bash
pip install -e ".[anthropic]"    # Anthropic only
pip install -e ".[openai]"       # OpenAI only
pip install -e ".[providers]"    # Both
```

If you run without the required SDK installed, Skuld gives a clear error:
```
ValueError: The 'anthropic' package is not installed. Install it with: pip install skuld[anthropic]
```

### Provider Selection

Skuld infers the provider from the model name in your config:
- `claude-*` → Anthropic
- `gpt-*`, `o1-*`, `o3-*`, `o4-*` → OpenAI

**Simple mode** (top-level config):
```yaml
config:
  generator_model: "claude-sonnet-4-20250514"
  reviewer_model: "gpt-4o"
```

This default simple-mode pairing spans both providers, so it requires both
`SKULD_ANTHROPIC_KEY` and `SKULD_OPENAI_KEY`.

**Single-provider simple mode** (Anthropic-only example):
```yaml
config:
  generator_model: "claude-sonnet-4-20250514"
  reviewer_model: "claude-haiku-4-20250514"
```

That example runs with only `SKULD_ANTHROPIC_KEY` set. Using two different models from
the same provider still gives meaningful adversarial separation (the reviewer has
different weights and reasoning patterns from the generator).

#### Single-provider end-to-end walkthrough (Anthropic-only)

1. **Install Skuld with the Anthropic extra:**
   ```bash
   pip install -e ".[anthropic]"
   ```

2. **Set your API key:**
   ```bash
   export SKULD_ANTHROPIC_KEY="sk-ant-..."
   # Windows PowerShell: $env:SKULD_ANTHROPIC_KEY = "sk-ant-..."
   ```

3. **Create your input YAML** (e.g. `story.yaml`):
   ```yaml
   story:
     id: "LOGIN-001"
     title: "User login with MFA"
     description: "As a user I want to log in with MFA so that my account is secure."

   acceptance_criteria:
     - id: "AC-1"
       description: "User can log in with email, password, and TOTP code"
       criticality: high
     - id: "AC-2"
       description: "User sees an error after 3 failed TOTP attempts"
       criticality: medium

   config:
     generator_model: "claude-sonnet-4-20250514"
     reviewer_model: "claude-haiku-4-20250514"
   ```

4. **Run the pipeline:**
   ```bash
   skuld generate story.yaml
   ```

5. **Optional: save output to a file:**
   ```bash
   skuld generate story.yaml --output report.md
   ```

> **Tip:** If you only have an OpenAI key, swap the models:
> ```yaml
> config:
>   generator_model: "gpt-4o"
>   reviewer_model: "gpt-4o-mini"
> ```
> Then set `SKULD_OPENAI_KEY` and run the same commands.

#### Cross-provider end-to-end walkthrough (Anthropic + OpenAI)

This is the default and recommended configuration — it maximises adversarial diversity
by using models from different providers for generation vs review.

1. **Install Skuld with both provider extras:**
   ```bash
   pip install -e ".[providers]"
   ```

2. **Set both API keys:**
   ```bash
   export SKULD_ANTHROPIC_KEY="sk-ant-..."
   export SKULD_OPENAI_KEY="sk-..."
   # Windows PowerShell:
   # $env:SKULD_ANTHROPIC_KEY = "sk-ant-..."
   # $env:SKULD_OPENAI_KEY = "sk-..."
   ```

3. **Create your input YAML** (e.g. `story.yaml`):
   ```yaml
   story:
     id: "CHECKOUT-042"
     title: "Guest checkout with saved address"
     description: "As a guest user I want to check out using a previously saved address."

   acceptance_criteria:
     - id: "AC-1"
       description: "Guest can select a saved address during checkout"
       criticality: high
     - id: "AC-2"
       description: "Guest sees validation error if address is incomplete"
       criticality: medium

   config:
     generator_model: "claude-sonnet-4-20250514"
     reviewer_model: "gpt-4o"
   ```

   With this config, Skuld uses Anthropic (Claude) for test generation and refinement,
   and OpenAI (GPT-4o) for the adversarial review phase.

4. **Run the pipeline:**
   ```bash
   skuld generate story.yaml
   ```

5. **Optional: save output and merge into an RTM:**
   ```bash
   skuld generate story.yaml --output report.md --rtm-file rtm.yaml
   ```

#### Model pairing examples

Below are practical config snippets showing different model combinations. Pick the
pairing that fits your budget, latency needs, and adversarial separation goals.

| Strategy | Generator | Reviewer | Keys needed | Notes |
|----------|-----------|----------|-------------|-------|
| Max diversity (default) | `claude-sonnet-4-20250514` | `gpt-4o` | Both | Best adversarial separation |
| Anthropic-only (strong) | `claude-sonnet-4-20250514` | `claude-haiku-4-20250514` | Anthropic | Different model weights; fast reviewer |
| Anthropic-only (same family) | `claude-sonnet-4-20250514` | `claude-opus-4-20250514` | Anthropic | Opus reviews Sonnet output — strongest same-provider pairing |
| OpenAI-only (budget) | `gpt-4o` | `gpt-4o-mini` | OpenAI | Mini is cheaper/faster as reviewer |
| OpenAI-only (reasoning) | `gpt-4o` | `o3-mini` | OpenAI | o3-mini uses chain-of-thought for deeper review |
| Cost-optimised cross | `claude-haiku-4-20250514` | `gpt-4o-mini` | Both | Lowest cost; less adversarial depth |

**Anthropic same-family example** — Opus reviews Sonnet output:
```yaml
config:
  generator_model: "claude-sonnet-4-20250514"
  reviewer_model: "claude-opus-4-20250514"
```

**OpenAI reasoning-model reviewer:**
```yaml
config:
  generator_model: "gpt-4o"
  reviewer_model: "o3-mini"
```

**Per-phase fine-tuning with `model_routing`** — different temperatures per role:
```yaml
config:
  max_tokens_per_run: 48000
  model_routing:
    generator:
      model: "claude-sonnet-4-20250514"
      provider: "anthropic"
      temperature: 0.8
      max_tokens: 8192
    reviewer:
      model: "claude-opus-4-20250514"
      provider: "anthropic"
      temperature: 0.1
      max_tokens: 4096
    refinement:
      model: "claude-sonnet-4-20250514"
      provider: "anthropic"
      temperature: 0.5
      max_tokens: 8192
```

> **Guidance:** Skuld warns when generator and reviewer are the exact same model —
> this defeats the adversarial purpose. Using different models from the same provider
> (e.g. Sonnet + Haiku, or GPT-4o + o3-mini) is fine and still provides useful tension.

#### Supported models reference

Skuld routes models to providers based on the model name prefix. Any model whose name
starts with a recognised prefix works — you don't need to update Skuld when your
provider releases new models under the same prefix.

| Prefix | Provider | Example models | Notes |
|--------|----------|----------------|-------|
| `claude-*` | Anthropic | `claude-opus-4-20250514`, `claude-sonnet-4-20250514`, `claude-haiku-4-20250514`, `claude-3.5-sonnet-20241022`, `claude-3.5-haiku-20241022` | All Claude model versions are supported |
| `gpt-*` | OpenAI | `gpt-4o`, `gpt-4o-mini`, `gpt-4-turbo`, `gpt-4`, `gpt-3.5-turbo` | Chat Completions API models |
| `o1-*` | OpenAI | `o1`, `o1-mini`, `o1-preview` | Reasoning models (may ignore temperature) |
| `o3-*` | OpenAI | `o3`, `o3-mini`, `o3-pro` | Reasoning models |
| `o4-*` | OpenAI | `o4-mini` | Reasoning models |

**Key points:**

- The table above is not exhaustive — any model name matching these prefixes will work.
  When providers release new models (e.g. `claude-sonnet-5-*` or `gpt-5-*`), they will
  be picked up automatically as long as the prefix convention holds.
- Models not matching any known prefix require `model_routing` with an explicit
  `provider` field. This also applies to custom deployment aliases (e.g.
  `my-company-claude-prod`).
- Reasoning models (`o1-*`, `o3-*`, `o4-*`) may behave differently with the
  `temperature` parameter — some ignore it or only accept specific values. Skuld passes
  it through; the provider SDK will report an error if the value is unsupported.
- Open/local models (Ollama, vLLM, Mistral, Gemini) are not supported yet. Support for
  additional providers is planned for a future release.

**Advanced mode** (`model_routing` for per-phase control):
```yaml
config:
  max_tokens_per_run: 32000
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

> **Note:** For custom deployment aliases (e.g. `my-company-claude-prod`), use `model_routing` with an explicit `provider` field. Skuld only auto-infers providers for standard model name prefixes.

### Token Budget

All three pipeline phases (generate → review → refine) share a single token budget per run. Default: 32,000 tokens. Configure via:

```yaml
config:
  max_tokens_per_run: 64000
```

If the budget is exceeded mid-run, Skuld stops and reports the error.

### Dry-Run Mode

Use `--dry-run` to test your pipeline without consuming API tokens:
```bash
skuld generate story.yaml --dry-run
```

Dry-run uses a deterministic FakeLLM that produces structurally valid output. It's useful for:
- Verifying input YAML validity
- Testing RTM merge workflows
- Running benchmarks locally

---

## Installation

```bash
git clone git@github.com:sandeep-singh-79/Skuld.git
cd Skuld
pip install -e ".[dev]"
```

Verify:

```bash
skuld --help
```

---

## Workflow 1: Generate Test Cases

Given a story YAML, Skuld runs a two-pass adversarial LLM pipeline and produces a test case report with RTM scoring.

### Step 1 — Write your story YAML

Create `story.yaml` with the required fields. See [V1-INPUT-TEMPLATE.md](V1-INPUT-TEMPLATE.md) for the full schema.

Minimum viable input:

```yaml
story:
  id: "PROJ-101"
  title: "User login with MFA"
  description: "As a registered user, I want to log in using MFA."

acceptance_criteria:
  - id: "AC-1"
    description: "User can log in with valid email and password"
    criticality: high
  - id: "AC-2"
    description: "Login fails after 3 incorrect MFA attempts"
    criticality: medium

config:
  generator_model: "claude-sonnet-4-20250514"
  reviewer_model: "gpt-4o"
```

### Step 2 — Run generate

```bash
# Real provider (requires API key in environment)
skuld generate story.yaml

# Dry-run (no API keys needed)
skuld generate story.yaml --dry-run

# Write to file
skuld generate story.yaml --output report.md

# JSON output format
skuld generate story.yaml --format json

# Merge into persistent RTM
skuld generate story.yaml --rtm-file rtm.yaml
```

### Step 3 — Read the report

See [V1-OUTPUT-TEMPLATE.md](V1-OUTPUT-TEMPLATE.md) for a full annotated example.

The report contains five sections:
1. **Story Context** — story metadata and ACs
2. **Test Cases** — full test case table
3. **Requirements Traceability Matrix** — AC × test case coverage grid
4. **Confidence Score** — overall score, tier, and breakdown
5. **Coverage Gaps** — ACs missing negative or edge-case tests

---

## Workflow 2: Score Without LLM

Score an existing set of test cases deterministically — no LLM call, no API keys.

### Input format (JSON)

```json
{
  "test_cases": [
    {
      "id": "TC-001",
      "story_id": "PROJ-101",
      "ac_ids": ["AC-1"],
      "test_type": "functional",
      "priority": "P1",
      "preconditions": "User is registered",
      "steps": ["Navigate to login", "Enter credentials", "Submit"],
      "expected_result": "User is authenticated"
    }
  ],
  "acceptance_criteria": [
    {"id": "AC-1", "description": "Valid login", "criticality": "high"}
  ]
}
```

### Run score

```bash
# JSON output (default — for downstream processing)
skuld score test_cases.json

# Markdown output (for human readability)
skuld score test_cases.json --format markdown
```

---

## Workflow 3: RTM Management

The RTM (`rtm.yaml`) is a persistent artifact that accumulates coverage across multiple stories and runs.

### View coverage summary

```bash
skuld rtm report --rtm-file rtm.yaml
```

### List coverage gaps

```bash
skuld rtm gaps --rtm-file rtm.yaml
```

### Merge test cases into RTM (without regeneration)

```bash
skuld rtm update test_cases.json --rtm-file rtm.yaml
```

All entries in `test_cases.json` must belong to the same `story_id`.

### View history for a specific AC

```bash
skuld rtm history --rtm-file rtm.yaml --ac AC-1
```

---

## Workflow 4: Benchmark

Run a full pipeline against a pre-defined scenario and validate the output against an assertions file.

```bash
skuld benchmark benchmarks/login-mfa.input.yaml benchmarks/login-mfa.assertions.yaml --dry-run
```

### Assertion file formats

**Simple format:**
```yaml
assertions:
  - type: contains
    value: "## Test Cases"
  - type: min_length
    value: "500"
```

**Spec format:**
```yaml
must_include_headings:
  - "## Test Cases"
  - "## Confidence Score"
must_include_substrings:
  - "functional"
  - "AC-1"
```

---

## CLI Reference

### `skuld generate`

```
skuld generate INPUT_FILE [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--output, -o` | path | stdout | Write output to file |
| `--format` | markdown\|json | markdown | Output format |
| `--rtm-file` | path | — | Merge results into persistent RTM |
| `--force` | flag | false | Force full RTM regeneration for this story |
| `--dry-run` | flag | false | Use FakeLLMClient (no API keys needed) |

### `skuld score`

```
skuld score TEST_CASES_FILE [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--format` | markdown\|json | json | Output format |

### `skuld rtm report`

```
skuld rtm report --rtm-file RTM_FILE
```

### `skuld rtm gaps`

```
skuld rtm gaps --rtm-file RTM_FILE
```

### `skuld rtm update`

```
skuld rtm update TEST_CASES_FILE --rtm-file RTM_FILE [--force]
```

Input JSON must have a `test_cases` array. All entries must share the same `story_id`.

### `skuld rtm history`

```
skuld rtm history --rtm-file RTM_FILE --ac AC_ID
```

### `skuld benchmark`

```
skuld benchmark INPUT_FILE ASSERTIONS_FILE [OPTIONS]
```

| Option | Type | Default | Description |
|--------|------|---------|-------------|
| `--dry-run / --no-dry-run` | flag | dry-run | Use FakeLLMClient |

---

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success |
| 1 | Benchmark assertions failed against output |
| 2 | Malformed input, validation error, or pipeline error |
