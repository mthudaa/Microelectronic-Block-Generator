---

description: Create a new MBG OpenCode slash command using the project authoring standard
agent: build
------------

Create a new OpenCode slash command for the Microelectronic Block Generator
project.

Requested input:

```text
$ARGUMENTS
```

Interpret the first argument as the command name. Treat the remaining arguments
as the requested workflow or purpose.

## Requirements

1. Load the `mbg-extension-authoring` skill.
2. Require a command name beginning with `mbg-`.
3. Require lowercase alphanumeric kebab-case.
4. Create the command at:

```text
.opencode/commands/<command-name>.md
```

5. Do not overwrite an existing command without explicit approval.
6. Give the command one clear workflow.
7. Add valid YAML frontmatter.
8. Include a concise `description`.
9. Select an appropriate `agent`.
10. Use `$ARGUMENTS` or positional parameters such as `$1` when input is
    required.
11. Load the appropriate project skill.
12. Use an approved custom tool when one exists.
13. Define clear stopping and failure conditions.
14. Do not invent tools, modules, or project APIs that do not exist.

## ⚠️ PDK Body Constraint

**MOSFET body: pfet_03v3→VDD ONLY, nfet_03v3→VSS ONLY.** If your command
generates or processes SPICE netlists, it must enforce this rule.

## Required Frontmatter

```yaml
---
description: Describe the workflow performed by this command
agent: build
---
```

Use `plan` for read-only review or analysis workflows. Use `build` when the
workflow may create or update files.

## Command Template

```markdown
---
description: Run a specific MBG workflow
agent: build
---

Perform the requested workflow for:

$ARGUMENTS

## Required Workflow

1. Load the relevant `mbg-` skill.
2. Validate all required inputs.
3. Confirm that filesystem paths are repository-relative.
4. Use an approved custom tool when available.
5. Stop after the first actionable failure.
6. Report generated artifacts and evidence.
7. Do not stage, commit, or push automatically.

## Safety Requirements

- Never read or display `.env`.
- Never expose API keys.
- Never use personal absolute filesystem paths.
- Never claim simulation or verification success without evidence.
- Never modify files outside the requested scope.
```

Replace the placeholder content with the requested workflow.

## Input Rules

When the workflow requires one input, use:

```text
$1
```

When it requires the entire argument string, use:

```text
$ARGUMENTS
```

When it requires multiple positional inputs, use:

```text
$1
$2
$3
```

The command must stop and explain the missing input when a required argument is
not supplied.

## Safety Requirements

* Never read, display, or summarize `.env`.
* Never expose API keys or credentials.
* Never include personal absolute filesystem paths.
* Never run an unlimited retry or refinement loop.
* Never hide tool failures.
* Never claim DRC, LVS, PEX, or simulation success without report evidence.
* Never modify another team member's implementation outside the assigned scope.
* Never stage, commit, or push automatically.
* Require approval before destructive operations.

## Validation

After creating the command:

1. Run `mbg-validate-extension` on the new Markdown file.
2. Confirm that the file name starts with `mbg-`.
3. Confirm that frontmatter includes `description`.
4. Confirm that an appropriate `agent` is selected.
5. Confirm that required arguments are referenced.
6. Confirm that the command loads the relevant skill.
7. Confirm that failure and stopping conditions are explicit.
8. Run one valid-input test.
9. Run one missing-input test.
10. Do not claim completion if validation fails.

## Output Format

```text
Command:
Slash command:
Owner:
Purpose:
File created:
Arguments:
Agent:
Loaded skill:
Required tools:
Validation status:
Errors:
Warnings:
Success test:
Failure test:
Known limitations:
Git status:
```

If no command name is supplied, stop and request a valid `mbg-` command name.
