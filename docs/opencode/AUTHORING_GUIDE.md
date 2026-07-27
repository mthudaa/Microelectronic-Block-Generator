# OpenCode Extension Authoring Guide

## Purpose

This guide defines the project standard for creating, reviewing, and
maintaining OpenCode extensions in the Microelectronic Block Generator
repository.

The guide covers:

* Skills
* Custom tools
* Slash commands
* Agents
* Project-level instructions
* Permissions
* Validation and testing

The intended audience includes:

* New contributors
* AI/LLM developers
* Project developers
* Reviewers
* Maintainers

## Project Locations

Project-specific OpenCode extensions are stored at the repository root:

```text
.opencode/
├── skills/
│   └── <skill-name>/
│       └── SKILL.md
├── tools/
│   └── <tool-name>.ts
├── commands/
│   └── <command-name>.md
└── agents/
    └── <agent-name>.md
```

Project-wide rules are stored in:

```text
AGENTS.md
```

OpenCode permissions and repository configuration are stored in:

```text
opencode.jsonc
```

## Naming Convention

All project-specific extensions must use the `mbg-` prefix.

Examples:

```text
mbg-extension-authoring
mbg-validate-extension
mbg-new-skill
mbg-layout-review
```

Names must:

* Use lowercase letters and digits.
* Use single hyphens as separators.
* Not contain spaces.
* Not contain underscores.
* Not begin or end with a hyphen.
* Not contain consecutive hyphens.

For skills, the directory name must match the YAML frontmatter `name`.

## Choosing an Extension Type

### Skill

Use a skill when the agent needs reusable domain instructions or a documented
workflow.

Examples:

* Reviewing an AI-generated SPICE netlist.
* Recording AI experiment metrics.
* Validating an LLM-to-GDS experiment.
* Creating another OpenCode extension.

A skill describes how work should be performed. It should not implement a
runtime operation by itself.

### Custom Tool

Use a custom tool when the agent needs to perform a concrete and validated
operation.

Examples:

* Validate an OpenCode extension file.
* Read structured experiment metadata.
* Run an approved project validation script.
* Generate a report from experiment records.

A tool should return a structured result and report failures explicitly.

### Slash Command

Use a slash command when users need a repeatable entry point for a workflow.

Examples:

```text
/mbg-new-skill
/mbg-new-tool
/mbg-new-command
/mbg-review-extension
```

A command should load the relevant skill and call an approved custom tool when
one exists.

### Agent

Use an agent when a focused role requires:

* A dedicated system prompt.
* Restricted permissions.
* A clearly defined responsibility.
* Separation from general-purpose project work.

Examples:

* Read-only OpenCode extension reviewer.
* AI experiment auditor.
* Documentation reviewer.

### Project Instructions

Use `AGENTS.md` for rules that apply broadly across the repository.

Do not place a one-off workflow in `AGENTS.md`. Use a skill or command instead.

## Skill Authoring

A skill must be stored at:

```text
.opencode/skills/<skill-name>/SKILL.md
```

### Skill Frontmatter

Use:

```yaml
---
name: mbg-example-skill
description: Explain exactly when the agent should load this skill.
license: Apache-2.0
compatibility: opencode
metadata:
  owner: jabir
  project: microelectronic-block-generator
  status: experimental
---
```

The description should state:

* What the skill does.
* When the skill should be loaded.
* Important boundaries where it should not be used.

### Skill Template

```markdown
---
name: mbg-example-skill
description: Use this skill when an agent must perform a specific MBG workflow.
license: Apache-2.0
compatibility: opencode
metadata:
  owner: jabir
  project: microelectronic-block-generator
  status: experimental
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

## Safety Rules

Document secret, filesystem, Git, and side-effect restrictions.

## Output Contract

Define the expected result structure.

## Failure Handling

Explain how errors are reported and what work must stop.

## Test Cases

Include at least one successful case and one failure case.
```

## Custom Tool Authoring

A custom tool must be stored at:

```text
.opencode/tools/<tool-name>.ts
```

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

## Slash Command Authoring

A command must be stored at:

```text
.opencode/commands/<command-name>.md
```

The file name becomes the slash-command name.

Example:

```text
.opencode/commands/mbg-review-extension.md
```

is invoked as:

```text
/mbg-review-extension
```

### Command Frontmatter

```yaml
---
description: Describe the workflow performed by this command
agent: build
---
```

Use:

* `plan` for read-only analysis and review.
* `build` when the workflow may create or edit files.

### Command Template

```markdown
---
description: Run a specific MBG workflow
agent: build
---

Perform the requested workflow for:

$ARGUMENTS

## Required Workflow

1. Load the relevant `mbg-` skill.
2. Validate required inputs.
3. Validate filesystem paths.
4. Use an approved custom tool.
5. Stop after the first actionable failure.
6. Report generated artifacts and evidence.
7. Do not stage, commit, or push automatically.

## Safety Requirements

- Never read `.env`.
- Never expose API keys.
- Never use personal absolute paths.
- Never claim verification success without evidence.
```

### Command Arguments

Use the full argument string:

```text
$ARGUMENTS
```

Use positional arguments:

```text
$1
$2
$3
```

A command must stop and report a missing required argument instead of guessing.

## Agent Authoring

An agent must be stored at:

```text
.opencode/agents/<agent-name>.md
```

An agent should define:

* Description
* Mode
* Model when required
* Focused permissions
* Responsibilities
* Boundaries
* Required output format

An agent must use only the permissions required for its role.

A read-only reviewer should not have unrestricted edit or shell permissions.

## Project Permissions

The repository configuration in `opencode.jsonc` should:

* Allow normal repository reads.
* Deny secret-file access.
* Require approval for edits.
* Require approval for shell commands by default.
* Allow safe Git inspection commands.
* Deny automatic `git push`.
* Deny destructive cleanup such as `rm -rf`.
* Allow approved `mbg-` skills.
* Allow approved read-only validation tools.

Permission rules should progress from general rules to more specific
restrictions.

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

Do not use real credentials in documentation or test fixtures.

## Ownership Boundaries

OpenCode extensions must respect project ownership.

### Jabir

Owns:

* AI and LLM integration
* Prompt engineering
* Experiment metadata
* AI metrics
* OpenCode extensions
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

An OpenCode extension may invoke an approved API owned by another member. It
must not modify that implementation unless the task explicitly includes the
owner's approval.

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

Before staging a skill, tool, command, or agent:

* [ ] Uses the `mbg-` prefix.
* [ ] Has one clear responsibility.
* [ ] Has a clear trigger.
* [ ] Identifies the correct owner.
* [ ] Identifies dependencies.
* [ ] Documents required inputs.
* [ ] Documents outputs.
* [ ] Documents side effects.
* [ ] Uses minimum permissions.
* [ ] Validates filesystem paths.
* [ ] Rejects parent traversal.
* [ ] Protects `.env` and credentials.
* [ ] Reports failures explicitly.
* [ ] Contains no personal absolute paths.
* [ ] Includes a success test.
* [ ] Includes a failure test.
* [ ] Does not automatically stage changes.
* [ ] Does not automatically commit.
* [ ] Does not automatically push.
* [ ] Does not claim unsupported simulation or verification results.

## Validation Workflow

Review an extension through OpenCode:

```text
/mbg-review-extension .opencode/skills/mbg-extension-authoring/SKILL.md
```

Create a skill:

```text
/mbg-new-skill mbg-netlist-review Review AI-generated SPICE netlists
```

Create a tool:

```text
/mbg-new-tool mbg-read-experiment Read and summarize experiment metadata
```

Create a command:

```text
/mbg-new-command mbg-review-netlist Review an AI-generated SPICE netlist
```

Before staging files, run:

```bash
git diff --check
git status --short
```

Stage files explicitly. Do not use `git add .` when generated experiment
artifacts are present.

## Definition of Done

An OpenCode extension is complete when:

1. Its name and path follow project conventions.
2. Its responsibility is clearly defined.
3. Inputs and outputs are documented.
4. Permissions are minimized.
5. Filesystem access is validated.
6. Secret access is prohibited.
7. Failures are reported explicitly.
8. Success and failure tests pass.
9. Ownership and dependencies are documented.
10. Validation reports no blocking errors.
11. Git changes contain only files related to the task.
