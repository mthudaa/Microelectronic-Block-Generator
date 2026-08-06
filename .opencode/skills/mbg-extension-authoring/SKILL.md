---
name: mbg-extension-authoring
description: Create or review OpenCode skills, custom tools, commands, agents, and project instructions for the Microelectronic Block Generator repository. Use this for files under .opencode or OpenCode authoring documentation, including any extension that emits a design report, result table, or simulation figure, which must follow the project IEEE presentation standard. Do not use it for analog design, simulation, routing, DRC, LVS, or PEX implementation.
license: Apache-2.0
compatibility: opencode
metadata:
  owner: jabir
  project: microelectronic-block-generator
  status: experimental
---

# MBG OpenCode Extension Authoring

## Purpose

Create safe, consistent, and reviewable OpenCode extensions for the
Microelectronic Block Generator project.

Supported extension types:

- Skills
- Custom tools
- Commands
- Agents
- Project instructions

The full project standard lives in `docs/opencode/AUTHORING_GUIDE.md`. This
skill is the working checklist an agent applies while writing or reviewing an
extension; the guide is the reference it defers to when the two need more
detail than a checklist can carry.

## When to Use

Use this skill when:

- Creating or reviewing a `SKILL.md`.
- Creating a custom OpenCode tool.
- Creating a slash command.
- Creating or reviewing an OpenCode agent.
- Updating project-level agent instructions.
- Reviewing files under `.opencode/`.
- Adding or changing how any extension presents data, figures, or reports to a
  user or prompter.

## When Not to Use

Do not use this skill to implement:

- Analog circuit topology.
- Transistor sizing.
- Device placement.
- Routing.
- Power structures.
- Simulation algorithms.
- DRC, LVS, or PEX engines.

These tasks remain dependencies of their respective project owners.

## Required Inputs

Before creating an extension, determine:

1. Extension type.
2. Extension name.
3. Primary responsibility.
4. Intended user or agent.
5. Required inputs.
6. Expected outputs.
7. Side effects.
8. Required permissions.
9. Failure conditions.
10. Owner and dependencies.
11. Whether the extension emits figures, tables, or a report to a user.

Item 11 determines whether the presentation requirements below apply. An
extension that only returns structured JSON to another agent does not present
data to a human and is exempt.

## Naming Rules

Project-specific extensions must use the `mbg-` prefix.

Examples:

- `mbg-extension-authoring`
- `mbg-layout-review`
- `mbg-validate-extension`
- `mbg-new-skill`

Use lowercase alphanumeric kebab-case.

For skills, the folder name must match the `name` value in the YAML
frontmatter.

## ⚠️ PDK Body Constraint (all generated SPICE)

**MOSFET body: pfet_03v3→VDD ONLY, nfet_03v3→VSS ONLY.** Any skill, tool,
command, or agent that generates or processes SPICE netlists must enforce
this rule.

## Presentation Requirements

Any extension that produces a design report, a result table, or a simulation
figure for a human reader must comply with:

```text
.opencode/skills/mbg-ai-experiment-audit/references/IEEE_REPORT_STYLE.md
```

The reference Matplotlib implementation is:

```text
.opencode/skills/mbg-ai-experiment-audit/references/mbg_ieee_style.py
```

### Rules for extension authors

1. Do not restate the IEEE rules inside a new extension. Reference the
   standard by path so there remains one source of truth.
2. An extension that generates plots must import `mbg_ieee_style` rather than
   configuring Matplotlib itself. An extension that configures fonts, colors,
   or figure sizes independently will drift from the standard the moment the
   standard changes.
3. An extension that emits a numeric result for a human reader must carry the
   unit, the measurement condition, and the source artifact path alongside the
   value. A bare number is not a result.
4. An extension that writes a figure must emit a vector format in addition to
   any PNG preview, and must name the file `<cell>_<analysis>_<stage>`.
5. An extension that produces a report must follow the section order in
   standard section 1 and must not invent additional top-level sections.
6. A command whose workflow ends in a deliverable to a prompter must include a
   step that loads `mbg-ai-experiment-audit` to check presentation before the
   deliverable is declared complete.

### Boundary

Presentation format is owned by Jabir. Plot content — which signals to show,
which operating points matter, what constitutes a meaningful comparison — is
owned by Huda for simulation and Ahmad for verification. An extension may
standardize how a result is drawn. It must not decide which result is worth
drawing.

## Skill Requirements

A skill must be stored at:

```text
.opencode/skills/<skill-name>/SKILL.md
```

### Frontmatter

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

Frontmatter rules:

- Open and close with exactly three hyphens on their own line. A longer run of
  hyphens is not a valid delimiter and will cause the parser to read body text
  as metadata.
- Leave no blank line between the opening delimiter and the first key.
- Nest `owner`, `project`, and `status` under `metadata`. Top-level placement
  is silently ignored.
- Keep `description` under 1024 characters.
- State in `description` what the skill does, when to load it, and where its
  boundary lies.

### Required sections

The validator warns when any of these `##` headings is absent, and expects the
exact heading text:

```text
## Purpose
## When to Use
## When Not to Use
## Required Inputs
## Workflow
## Safety Rules
## Output Contract
## Failure Handling
## Test Cases
```

`## Audit Workflow` or `## Design Workflow` will not satisfy the `Workflow`
check. Use the exact heading and place a more specific name in a subsection if
needed.

## Tool Requirements

A custom tool must be stored at `.opencode/tools/<tool-name>.ts` and must:

1. Have one clear responsibility.
2. Use a project-specific `mbg-` name that is not a reserved OpenCode name.
3. Define a precise description.
4. Define validated arguments with a schema.
5. Return a structured result.
6. Preserve actionable errors and stderr.
7. Document side effects.
8. Report generated artifacts by repository-relative path.
9. Protect credentials.
10. Use the minimum required permissions.

Path handling must reject empty paths, absolute paths, parent traversal, and
any target outside the Git worktree. Use the `resolveInsideWorktree` pattern in
the authoring guide rather than writing a new check.

A tool must never convert a failure into a successful-looking result. A summary
field that reports success while the underlying artifact reports failure is the
most damaging defect this project can ship, because every downstream report
inherits it.

## Command Requirements

A command must be stored at `.opencode/commands/<command-name>.md` with
frontmatter declaring `description` and `agent`. Use `plan` for read-only
review and `build` when files may be written.

A command workflow must:

1. Load the relevant `mbg-` skill.
2. Validate required inputs and stop on a missing argument rather than guessing.
3. Validate filesystem paths.
4. Use an approved custom tool when one exists.
5. Stop after the first actionable failure.
6. Report generated artifacts and evidence.
7. Check presentation compliance when the output reaches a human reader.
8. Never stage, commit, or push automatically.

## Agent Requirements

An agent must be stored at `.opencode/agents/<agent-name>.md` and must declare
its description, mode, permissions, responsibilities, boundaries, and required
output format. A read-only reviewer must not hold edit or unrestricted shell
permissions.

## Workflow

### 1. Determine Extension Type

Match the need to the type. Reusable domain instructions become a skill. A
concrete validated operation becomes a tool. A repeatable user entry point
becomes a command. A focused role with restricted permissions becomes an
agent. A repository-wide rule belongs in `AGENTS.md`.

If two types seem to fit, the extension probably has two responsibilities.
Split it.

### 2. Validate the Name and Path

Confirm the `mbg-` prefix, kebab-case, and that no reserved name is used. For
a skill, confirm the folder name matches the frontmatter `name`.

### 3. Draft from the Template

Use the template for the chosen type in `docs/opencode/AUTHORING_GUIDE.md`.
Include every required section even when a section is short.

### 4. Define Inputs, Outputs, and Side Effects

State what the extension reads, what it writes, and what it changes outside
the worktree. An undocumented side effect is a defect.

### 5. Apply Presentation Requirements

If the extension emits figures, tables, or a report, reference the IEEE
standard by path and use `mbg_ieee_style` for plots. Do not copy rules.

### 6. Apply Safety Constraints

Confirm path validation, credential protection, permission minimization, and
that no automatic Git operation is possible.

### 7. Write Tests

Include at least one success case and one failure case. Add path-traversal and
missing-input cases for any extension that accepts a path.

### 8. Validate

Run the validator on the new file:

```text
/mbg-review-extension .opencode/skills/<skill-name>/SKILL.md
```

Resolve every blocking error. Record any accepted warning with a reason.

### 9. Report

Report the created or reviewed file, its type, its owner, its dependencies,
and the validation result. Do not stage the file.

## Safety Rules

- Never read, display, or summarize `.env`.
- Never copy an API key into a prompt, notebook, tool argument, or example.
- Use `DEEPSEEK_API_KEY=sk-your-key-here` as the placeholder in documentation.
- Never write a personal absolute filesystem path into an extension.
- Never grant an extension more permission than its role requires.
- Never stage, commit, or push automatically.
- Never allow `git add .` in an extension workflow while generated artifacts
  are present.
- Never modify an implementation owned by another team member. Invoke its
  approved API instead and record the dependency.
- Never let an extension claim simulation or verification success without a
  supporting artifact.
- Never duplicate the IEEE presentation rules into a new extension file.

## Output Contract

Use:

```text
Extension:
Type:
Path:
Owner:
Status:

Naming:
- Prefix:
- Case:
- Folder and frontmatter match:

Frontmatter:
- Delimiters:
- Required keys:
- Metadata nesting:
- Description length:

Structure:
- Required sections present:
- Missing sections:

Inputs and outputs:
- Required inputs:
- Outputs:
- Side effects:
- Permissions:

Presentation:
- Emits figures or reports:
- References IEEE standard:
- Uses mbg_ieee_style:
- Restates rules instead of referencing:

Safety:
- Path validation:
- Credential protection:
- Git safety:
- Ownership boundary:

Tests:
- Success case:
- Failure case:

Validation result:
- Blocking errors:
- Warnings:

Dependencies:
- ...

Required corrections:
1. ...

Recommended next action:
...
```

## Failure Handling

If the extension type cannot be determined from the path:

1. Report the supported paths.
2. Stop. Do not guess the type.

If a required frontmatter key is missing or malformed:

1. Report the exact key and the expected form.
2. Do not write the file with a placeholder value.

If a required section is missing:

1. List every missing section by its exact heading.
2. Report the file as incomplete rather than partially valid.

If the extension would modify code owned by another member:

1. Stop before editing.
2. Report the file, its owner, and the change that would be required.
3. Record it as a dependency for that owner.

If the extension emits figures or reports without referencing the IEEE
standard:

1. Report a blocking finding.
2. Require a path reference rather than an inline copy of the rules.

## Test Cases

### Success Case — New Skill

Input:

```text
/mbg-new-skill mbg-netlist-review Review AI-generated SPICE netlists
```

Expected:

- File created at `.opencode/skills/mbg-netlist-review/SKILL.md`.
- Frontmatter delimited by exactly three hyphens, metadata nested.
- All nine required sections present with exact headings.
- Success and failure test cases documented.
- Validation reports no blocking errors.

### Failure Case — Malformed Frontmatter

Input:

```text
---

name: mbg-example
owner: jabir
--------------------
```

Expected:

- Blocking error: blank line after the opening delimiter.
- Blocking error: closing delimiter is not exactly three hyphens.
- Blocking error: `owner` is not nested under `metadata`.
- Do not proceed to section validation until the frontmatter parses.

### Failure Case — Wrong Workflow Heading

Input:

A skill containing `## Audit Workflow` but no `## Workflow`.

Expected:

- Warning: recommended section `Workflow` is missing.
- Correction: rename to `## Workflow` and demote the specific name to a
  subsection.

### Failure Case — Truncated File

Input:

A `SKILL.md` ending inside an unclosed fenced code block.

Expected:

- Blocking error: unterminated code fence.
- Blocking error: list every required section absent after the truncation
  point.
- Do not report the file as valid because its frontmatter parsed.

### Failure Case — Missing Name Prefix

Input:

```text
.opencode/tools/validate-experiment.ts
```

Expected:

- Blocking error: project-specific tool names must start with `mbg-`.
- Correction: rename to `mbg-validate-experiment.ts`.

### Failure Case — Duplicated Presentation Rules

Input:

A new plotting skill that inlines its own font sizes, figure widths, and color
palette.

Expected:

- Blocking finding: presentation rules duplicated instead of referenced.
- Correction: reference `IEEE_REPORT_STYLE.md` by path and import
  `mbg_ieee_style`.

### Failure Case — Ownership Violation

Input:

A skill that edits `core/routing.py` to change trace width.

Expected:

- Stop before editing.
- Report `core/routing.py` as owned by Huda.
- Record the change as a dependency rather than performing it.
