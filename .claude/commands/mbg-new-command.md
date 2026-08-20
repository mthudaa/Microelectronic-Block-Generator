---
description: Scaffold a new canonical MBG workflow under .ai/workflows using the project authoring standard, then resync all platform adapters.
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/workflows/mbg-new-command.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

Create a new canonical workflow for the Microelectronic Block Generator
project.

Requested input:

```text
$ARGUMENTS
```

Interpret the first argument as the workflow name. Treat the remaining
arguments as the requested workflow or purpose.

## Requirements

1. Load the `mbg-extension-authoring` skill.
2. Require a workflow name beginning with `mbg-`.
3. Require lowercase alphanumeric kebab-case.
4. Create the workflow at:

   ```text
   .ai/workflows/<workflow-name>.md
   ```

   Do **not** create it directly under `.opencode/commands/` or
   `.claude/commands/` — those are generated output and are overwritten by
   the sync script.
5. Do not overwrite an existing workflow without explicit approval.
6. Give the workflow one clear job.
7. Add flat YAML frontmatter (see below).
8. Include a concise `description`.
9. Select an appropriate `agent`: `plan` for read-only analysis/review,
   `build` when the workflow may create or edit files.
10. Set `platforms` to the platforms that actually support this workflow —
    `[opencode, claude]` for a normal workflow, since Codex does not
    support repo-scoped commands (see `.ai/manifest.json`'s codex
    `unsupported` list).
11. Use `$ARGUMENTS` for the full argument string, or `$1`/`$2`/`$3` for
    positional inputs, when input is required.
12. Load the appropriate project skill from `.ai/skills/`.
13. Do not invent tools, modules, or project APIs that do not exist.

## PDK Body Constraint

**MOSFET body: `pfet_03v3` -> VDD ONLY, `nfet_03v3` -> VSS ONLY.** If the
new workflow generates or processes SPICE netlists, it must enforce this
rule.

## Required Frontmatter

```yaml
---
name: mbg-example-workflow
description: One sentence describing the workflow.
agent: build
platforms: [opencode, claude]
---
```

## Workflow Template

```markdown
---
name: mbg-example-workflow
description: Run a specific MBG workflow.
agent: build
platforms: [opencode, claude]
---

Perform the requested workflow for:

$ARGUMENTS

## Required Workflow

1. Load the relevant `.ai/skills/mbg-*` skill.
2. Validate all required inputs.
3. Confirm that filesystem paths are repository-relative.
4. Stop after the first actionable failure.
5. Report generated artifacts and evidence.
6. Do not stage, commit, or push automatically.

## Safety Requirements

- Never read or display `.env`.
- Never expose API keys.
- Never use personal absolute filesystem paths.
- Never claim simulation or verification success without evidence.
- Never modify files outside the requested scope.
```

Replace the placeholder content with the requested workflow.

## Input Rules

- One input: `$1`.
- The entire argument string: `$ARGUMENTS`.
- Multiple positional inputs: `$1`, `$2`, `$3`.

The workflow must stop and explain the missing input when a required
argument is not supplied.

## Safety Requirements

- Never read, display, or summarize `.env`.
- Never expose API keys or credentials.
- Never include personal absolute filesystem paths.
- Never run an unlimited retry or refinement loop.
- Never hide tool failures.
- Never claim DRC, LVS, PEX, or simulation success without report evidence.
- Never modify another team member's implementation outside the assigned
  scope.
- Never stage, commit, or push automatically.
- Require approval before destructive operations.

## Validation

After creating the workflow:

1. Confirm the file name starts with `mbg-` and matches the frontmatter
   `name`.
2. Confirm frontmatter includes `description`, `agent`, and `platforms`.
3. Confirm required arguments are referenced.
4. Confirm the workflow loads the relevant `.ai/skills/` skill.
5. Confirm failure and stopping conditions are explicit.
6. Do not claim completion if validation fails.
7. **Run `python3 scripts/sync_agent_tools.py`** to regenerate the
   OpenCode and Claude adapters from the new `.ai/workflows/` entry. If the
   workflow should be discoverable via `.ai/manifest.json`'s `workflows`
   section, coordinate with whoever owns that file rather than hand-editing
   it here.

## Output Format

```text
Workflow:
Owner:
Purpose:
File created:
Arguments:
Agent:
Platforms:
Loaded skill:
Sync command run: python3 scripts/sync_agent_tools.py
Validation status:
Errors:
Warnings:
Known limitations:
Git status:
```

If no workflow name is supplied, stop and request a valid `mbg-` workflow
name.
