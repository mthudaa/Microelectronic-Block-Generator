# Agent Extension Authoring Guide

> This file lives at `docs/opencode/AUTHORING_GUIDE.md` for path stability —
> `.ai/skills/mbg-extension-authoring/SKILL.md` and
> `.ai/workflows/mbg-new-skill.md` both link to this exact path, and those
> files are outside this guide's own ownership, so the path is not moving.
> The **content**, however, now covers the canonical authoring model used by
> all three supported agents (OpenCode, Claude Code, Codex), not OpenCode
> alone. See `README.md`'s "AI Coding Agent Integrations" section for the
> platform-by-platform setup, sync, and troubleshooting story; this guide is
> about *authoring* a skill, workflow, or tool correctly in the first place.

## Purpose

This guide defines the project standard for creating, reviewing, and
maintaining agent extensions in the Microelectronic Block Generator
repository: skills and workflows that ship identically to OpenCode, Claude
Code and Codex, plus OpenCode-only custom code tools.

The guide covers:

* Skills
* Workflows (slash commands)
* OpenCode custom code tools
* Project-level instructions
* Permissions
* Validation and testing

The intended audience includes:

* New contributors
* AI/LLM developers
* Project developers
* Reviewers
* Maintainers

## The canonical model

`.ai/` is the single source of truth. A sync script reads it and regenerates
the per-platform adapters — hand-editing a generated file is pointless, it
is silently overwritten the next time anyone runs the sync.

```text
SOURCE OF TRUTH (author here)
.ai/manifest.json            capabilities, workflows, platform mapping
.ai/skills/<name>/SKILL.md   canonical skill definitions
.ai/workflows/<name>.md      canonical workflow/slash-command definitions
.ai/knowledge/PROJECT.md     canonical project knowledge
AGENTS.md                    shared rules (read natively by OpenCode & Codex)

GENERATED — never hand-edit, always resync instead
.opencode/skills/<name>/SKILL.md      .opencode/commands/<name>.md
.claude/skills/<name>/SKILL.md        .claude/commands/<name>.md
plugins/mbg-analog/skills/<name>/SKILL.md
plugins/mbg-analog/.codex-plugin/plugin.json
.agents/plugins/marketplace.json
CLAUDE.md                             (imports @AGENTS.md)
.ai/project-index.json

PLATFORM-SPECIFIC, MAINTAINED BY HAND — not derived from .ai/
.opencode/tools/<name>.ts    OpenCode custom code tools (the ONLY platform
                             of the three that supports repo-scoped code
                             tools — see "OpenCode custom tool authoring")
opencode.jsonc               OpenCode permissions
.claude/settings.json        Claude Code permissions
```

Every generated Markdown/JSON file starts with a banner (an HTML comment for
Markdown, a `"$generated"` block for JSON) naming its source and the
regeneration command. If a file has that banner, don't touch it — edit the
named source under `.ai/` and resync. If it doesn't, it's meant to be
hand-edited in place.

## Naming Convention

All project-specific extensions must use the `mbg-` prefix.

Examples:

```text
mbg-extension-authoring
mbg-repo-analysis
mbg-new-skill
```

Names must:

* Use lowercase letters and digits.
* Use single hyphens as separators.
* Not contain spaces.
* Not contain underscores.
* Not begin or end with a hyphen.
* Not contain consecutive hyphens.

For a skill, the directory name (`.ai/skills/<name>/`) must match the YAML
frontmatter `name`. For a workflow, the file basename
(`.ai/workflows/<name>.md`) must match the frontmatter `name`.

## Choosing an Extension Type

### Skill

Use a skill when the agent needs reusable domain instructions or a
documented read-only/generating workflow.

Examples:

* Reviewing an AI-generated SPICE netlist.
* Recording AI experiment metrics.
* Debugging placement or routing.
* Creating another canonical skill or workflow.

A skill describes how work should be performed. It should not implement a
runtime operation by itself — it references the real implementation (e.g. a
`core.*` entry point) rather than duplicating it.

### Workflow (slash command)

Use a workflow when users need a repeatable, multi-step entry point.

Examples:

```text
/mbg-new-skill
/mbg-new-command
/mbg-review-extension
```

A workflow should load the relevant skill(s) and follow a defined sequence
of steps with explicit stop conditions.

Workflows currently ship to OpenCode and Claude Code only. **Codex has no
repo-scoped slash-command mechanism** (`.ai/manifest.json` →
`platforms.codex.unsupported` lists `repo_scoped_commands` and
`repo_scoped_agents`) — do not add `codex` to a workflow's `platforms` list;
the sync script rejects it.

### OpenCode Custom Tool

Use a custom tool when an agent needs to perform a concrete, validated,
code-level operation, and that operation must run identically every time
rather than being re-derived by the model from prose instructions.

Examples:

* Validate an extension file against the authoring rules.
* Read and summarize structured experiment metadata.
* Run an approved project validation script.

This is the **one deliberate exception** to "author under `.ai/`": custom
code tools are OpenCode-only (Claude Code and Codex have no repo-scoped code
tool runtime), so they are authored directly under `.opencode/tools/*.ts`
and are not generated from anything.

### Project Instructions

Use `AGENTS.md` for rules that apply broadly across the repository and all
three agents. Do not place a one-off workflow in `AGENTS.md`; use a skill or
workflow instead. Do not hand-edit `CLAUDE.md` — it is generated and imports
`AGENTS.md` for you.

## Skill Authoring

A skill must be stored at:

```text
.ai/skills/<skill-name>/SKILL.md
```

### Frontmatter parser constraints

The sync script (`scripts/sync_agent_tools.py`) uses a hand-rolled flat
frontmatter parser — no PyYAML or `tomllib` is available in every Python
environment this repo runs under. This means:

* No nested YAML maps.
* No YAML block lists (`- item` on its own line).
* No multi-line folded/literal scalars.
* List fields must be written **inline**: `capabilities: [cap_a, cap_b]`,
  `platforms: [opencode, claude, codex]`.

A malformed frontmatter line (missing `:`, unmatched bracket) makes the sync
script fail loudly (`SyncError`) rather than silently mis-parsing — treat
that failure as the review gate, not an obstacle to work around.

### Skill Frontmatter

```yaml
---
name: mbg-example-skill
description: 2-4 sentences — what it does, when to load it, when not to.
class: READ-ONLY | GENERATING | MUTATING | DESTRUCTIVE
owner: huda | ahmad | jabir
capabilities: [cap_id]
platforms: [opencode, claude, codex]
---
```

All six keys (`name`, `description`, `class`, `owner`, `capabilities`,
`platforms`) are required; the sync script rejects a skill missing any of
them, an unrecognized `class`, an unrecognized `owner`, or a `platforms`
entry outside `opencode`/`claude`/`codex`.

The description should state:

* What the skill does.
* When the skill should be loaded.
* Important boundaries where it should not be used.

### Skill Template

Match the section layout every current canonical skill already uses (see
`.ai/skills/*/SKILL.md`):

```markdown
---
name: mbg-example-skill
description: Use this skill when an agent must perform a specific MBG workflow.
class: GENERATING
owner: huda
capabilities: [example_capability]
platforms: [opencode, claude, codex]
---

# MBG Example Skill

## Purpose

Describe one responsibility.

## When to Use

Describe the exact triggers for this skill.

## When Not to Use

Describe related work that remains outside the skill.

## Required Inputs

List required files, arguments, environment, and dependencies.

## Preconditions

List conditions that must be true before execution.

## Workflow

1. Inspect inputs.
2. Validate inputs.
3. Execute approved operations.
4. Verify outputs.
5. Report results.

## Outputs

Define the expected result structure.

## Failure Modes

Explain how errors are reported and what work must stop.
```

Add extra sections only when the skill genuinely needs them — several
canonical skills add `## PDK Body Constraint` (SPICE-generating/processing
skills must state and enforce `pfet_03v3 → VDD ONLY`, `nfet_03v3 → VSS
ONLY`), `## Safety Rules`, or `## Naming Rules`. Keep the eight core
sections above as the baseline for every skill.

Keep the body **platform-neutral** — the same body ships to all three
adapters verbatim (with only the frontmatter re-rendered per platform), so
don't write "in OpenCode, click..." unless the skill is genuinely about
authoring for one specific platform.

After writing or editing a skill:

1. Register/confirm its capability entry in `.ai/manifest.json` (the
   manifest is the lead's file — coordinate rather than editing it
   unreviewed if you don't own it).
2. Run `python3 scripts/sync_agent_tools.py` to regenerate all three
   adapters.
3. Run `python3 scripts/sync_agent_tools.py --check` to confirm nothing is
   left stale.

## Workflow Authoring

A workflow must be stored at:

```text
.ai/workflows/<workflow-name>.md
```

It becomes the slash command `/<workflow-name>` on OpenCode and Claude Code
(there is no Codex equivalent — see above).

### Workflow Frontmatter

```yaml
---
name: mbg-example-workflow
description: Describe the workflow performed by this command
agent: build | plan
platforms: [opencode, claude]
---
```

Use:

* `plan` for read-only analysis and review.
* `build` when the workflow may create or edit files.
* `platforms` may include `opencode` and/or `claude`, but never `codex` —
  the sync script raises a `SyncError` if it does.

`agent: build|plan` selects one of OpenCode's/Claude Code's own **built-in**
agent modes for the command to run under. This repository does not
currently define any custom subagent files (there is no `.opencode/agents/`
or `.claude/agents/` directory here) — if a task genuinely needs a
dedicated, permission-restricted subagent persona rather than the built-in
`build`/`plan` modes, treat that as a new kind of extension to design and
discuss, not something this template already covers.

### Workflow Template

```markdown
---
name: mbg-example-workflow
description: Run a specific MBG workflow
agent: build
platforms: [opencode, claude]
---

Perform the requested workflow for:

$ARGUMENTS

## Required Workflow

1. Load the relevant `mbg-` skill.
2. Validate required inputs.
3. Validate filesystem paths.
4. Stop after the first actionable failure.
5. Report generated artifacts and evidence.
6. Do not stage, commit, or push automatically.
```

Use `$ARGUMENTS` for the full argument string, or `$1`/`$2`/... for
positional arguments. A workflow must stop and report a missing required
argument instead of guessing.

Reference only skills and capabilities that actually exist — check
`.ai/manifest.json`'s `capabilities` and `workflows` sections before writing
a reference into the body.

After writing or editing a workflow, run
`python3 scripts/sync_agent_tools.py` (and `--check` to confirm) the same as
for a skill.

## OpenCode Custom Tool Authoring

A custom tool must be stored at:

```text
.opencode/tools/<tool-name>.ts
```

This is authored directly in place — it has no `.ai/` source and the sync
script never touches it.

### Tool Template

```typescript
import { tool } from "@opencode-ai/plugin"

export default tool({
  description: "Describe one exact MBG operation.",

  args: {
    inputPath: tool.schema
      .string()
      .describe("Repository-relative input path"),
  },

  async execute(args, context) {
    return JSON.stringify(
      {
        status: "not-implemented",
        worktree: context.worktree,
        inputPath: args.inputPath,
      },
      null,
      2,
    )
  },
})
```

### Tool Requirements

Every custom tool must:

1. Have one clear responsibility.
2. Use a project-specific `mbg-` name.
3. Define a precise description.
4. Define validated arguments.
5. Return a structured result.
6. Preserve actionable errors.
7. Document side effects.
8. Report generated artifacts.
9. Protect credentials.
10. Use minimum required permissions.
11. Resolve the **canonical** implementation
    (`src/mbg/`), not
    `.opencode/tools/core/` — that directory is a stale, partial mirror kept
    only as a last-resort fallback for a broken checkout, and is being
    retired. Existing tools already do this (see the `CANONICAL_CORE_PARENT`
    / `CORE_DIR` resolution at the top of `.opencode/tools/mbg-spice-to-gds.ts`)
    — follow the same pattern in any new tool rather than importing
    `.opencode/tools/core/` directly.

### Path Validation

When accepting repository paths:

* Reject empty paths.
* Reject absolute paths when a relative path is expected.
* Resolve paths against `context.worktree`.
* Reject `../` parent traversal.
* Reject paths outside the Git worktree.
* Do not read `.env` or credential files.
* Do not include user-specific absolute paths.

Recommended pattern:

```typescript
import path from "node:path"

function resolveInsideWorktree(
  worktree: string,
  inputPath: string,
): string {
  const trimmed = inputPath.trim()

  if (!trimmed) {
    throw new Error("Path cannot be empty")
  }

  if (path.isAbsolute(trimmed)) {
    throw new Error("Use a repository-relative path")
  }

  const target = path.resolve(worktree, trimmed)
  const relative = path.relative(worktree, target)

  if (
    relative === "" ||
    relative === ".." ||
    relative.startsWith("../") ||
    path.isAbsolute(relative)
  ) {
    throw new Error("Path must remain inside the Git worktree")
  }

  return target
}
```

### Process Execution

When a tool executes another process:

* Prefer argument arrays.
* Do not concatenate untrusted input into shell commands.
* Preserve stderr.
* Check the exit code.
* Use a timeout for long-running operations.
* Require approval for destructive side effects.
* Do not silently convert failures into successful results.

## Project Permissions

Permissions are platform-specific and hand-maintained — they are not
generated from `.ai/`.

`opencode.jsonc` (OpenCode) should:

* Allow normal repository reads; deny `*.env`/`*.env.*` reads.
* Require approval (`"ask"`) for edits and for shell commands by default.
* Allow-list safe, read-only Git/inspection commands explicitly
  (`git status`, `git diff`, `git log`, `git branch`, `docker ps`, `ls`,
  `find`, `grep`, `pwd`).
* Deny `git push` and `rm -rf` outright.
* Allow the approved `mbg-*` skills.

`.claude/settings.json` (Claude Code) should:

* Mirror the same intent using its own `permissions.allow` / `.deny` /
  `.ask` pattern lists, e.g. `Bash(git status:*)`,
  `Bash(python3 scripts/sync_agent_tools.py:*)`.
* Deny `Bash(git push:*)`, `Bash(rm -rf:*)`, and any `.env` read.

Permission rules should progress from general rules to more specific
restrictions, and a new command or script only becomes prompt-free once it
is explicitly added to the relevant allow-list — do not widen a wildcard
(`bash: "*": "allow"`, an empty `deny`, etc.) as a shortcut.

## Secret Protection

Never:

* Read `.env`.
* Display `.env`.
* Summarize `.env`.
* Copy API keys into prompts.
* Store API keys in notebooks.
* Store API keys in experiment metadata.
* Commit API keys.

Use placeholders in examples:

```text
DEEPSEEK_API_KEY=sk-your-key-here
```

Do not use real credentials in documentation or test fixtures. Do not use a
personal absolute filesystem path (e.g. a home directory) anywhere in a
skill, workflow, tool, or example — discover the repository root
dynamically instead (see `find_repo_root()` in
`scripts/sync_agent_tools.py` for the pattern this repo already uses: ask
`git rev-parse --show-toplevel`, then fall back to walking up from the
script's own location).

## Ownership Boundaries

Agent extensions must respect project ownership (see `AGENTS.md` for the
authoritative module list).

### Jabir

Owns:

* AI and LLM integration
* Prompt engineering
* Experiment metadata
* AI evaluation metrics
* Canonical agent skills and workflows (`.ai/skills/`, `.ai/workflows/`)
* OpenCode-only custom tools (`.opencode/tools/`)
* AI-related documentation

### Huda

Owns:

* Analog design
* Device selection
* Placement
* Routing
* Power
* Simulation implementation

### Ahmad

Owns:

* DRC
* LVS
* PEX
* Verification automation
* Verification scripts

An extension may invoke an approved API owned by another member. It must
not modify that implementation unless the task explicitly includes the
owner's approval — record the need as a dependency instead.

## Testing Requirements

Every extension must include or document:

### Success Test

A valid input that demonstrates the intended workflow.

### Failure Test

An invalid input that demonstrates correct error reporting.

Recommended additional tests:

* Missing input.
* Invalid name.
* Absolute path.
* Parent traversal.
* Missing file.
* Secret-file request.
* Unsupported extension type.
* Duplicate file.
* Permission-denied operation.

## Review Checklist

Before staging a skill, workflow, or tool:

* [ ] Uses the `mbg-` prefix.
* [ ] Has one clear responsibility.
* [ ] Has a clear trigger.
* [ ] Identifies the correct owner.
* [ ] Identifies dependencies.
* [ ] Documents required inputs.
* [ ] Documents outputs.
* [ ] Documents side effects.
* [ ] Uses minimum permissions.
* [ ] Validates filesystem paths (tools).
* [ ] Rejects parent traversal (tools).
* [ ] Protects `.env` and credentials.
* [ ] Reports failures explicitly.
* [ ] Contains no personal absolute paths.
* [ ] Includes a success test.
* [ ] Includes a failure test.
* [ ] Does not automatically stage changes.
* [ ] Does not automatically commit.
* [ ] Does not automatically push.
* [ ] Does not claim unsupported simulation or verification results.
* [ ] Was authored under `.ai/` (skill/workflow) or `.opencode/tools/`
      (code tool) — never directly under a generated adapter path.
* [ ] `python3 scripts/sync_agent_tools.py --check` passes after the change.

## Validation Workflow

Regenerate every platform adapter from the canonical `.ai/` sources:

```bash
python3 scripts/sync_agent_tools.py
```

Confirm nothing is stale without writing anything (useful in CI or before a
commit):

```bash
python3 scripts/sync_agent_tools.py --check
```

Then run the full validator:

```bash
python3 scripts/validate_agent_integrations.py
```

> `sync_agent_tools.py --check` only answers "are the adapters stale?".
> `validate_agent_integrations.py` is the authoritative check: ten checks
> covering root discovery, frontmatter parsing, adapter completeness, broken
> references, sync determinism, capability parity, documented-command
> existence, hardcoded home directories, and phantom APIs (every `core.*`
> symbol a skill names must actually exist). Run it before committing.

Before staging files, run:

```bash
git diff --check
git status --short
```

Stage files explicitly. Do not use `git add .` when generated experiment
artifacts are present, and always commit a canonical `.ai/` change together
with its regenerated adapter output in the same commit.

## Definition of Done

An agent extension is complete when:

1. Its name and path follow project conventions.
2. Its responsibility is clearly defined.
3. Inputs and outputs are documented.
4. Permissions are minimized.
5. Filesystem access is validated (tools).
6. Secret access is prohibited.
7. Failures are reported explicitly.
8. Success and failure tests pass.
9. Ownership and dependencies are documented.
10. `python3 scripts/sync_agent_tools.py --check` reports up to date.
11. Git changes contain only files related to the task, with the canonical
    `.ai/` source and its regenerated adapters committed together.
