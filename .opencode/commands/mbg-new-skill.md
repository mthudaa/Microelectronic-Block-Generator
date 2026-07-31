---

description: Create a new MBG OpenCode skill using the project authoring standard
agent: build
------------

Create a new OpenCode skill for the Microelectronic Block Generator project.

Requested input:

```text
$ARGUMENTS
```

Interpret the first argument as the skill name. Treat the remaining arguments
as the requested purpose or capability.

## Requirements

1. Load the `mbg-extension-authoring` skill.
2. Require a skill name beginning with `mbg-`.
3. Require lowercase alphanumeric kebab-case.
4. Reject names containing:

   * Spaces.
   * Underscores.
   * Consecutive hyphens.
   * Leading or trailing hyphens.
5. Create the skill at:

```text
.opencode/skills/<skill-name>/SKILL.md
```

6. Ensure the folder name exactly matches the YAML frontmatter `name`.
7. Do not overwrite an existing skill without explicit approval.
8. Give the skill one clear responsibility.
9. Set the correct project owner and dependencies.
10. Do not invent tools, APIs, modules, or verification results.

## ⚠️ PDK Body Constraint

**MOSFET body: pfet_03v3→VDD ONLY, nfet_03v3→VSS ONLY.** If your skill
generates or processes SPICE netlists, it must enforce this rule.

## Required Frontmatter

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

Replace the example name, description, and owner with values appropriate to the
requested skill.

## Required Sections

The generated skill must include:

* `Purpose`
* `When to Use`
* `When Not to Use`
* `Required Inputs`
* `Preconditions`
* `Workflow`
* `Safety Rules`
* `Output Contract`
* `Failure Handling`
* `Test Cases`

## Safety Requirements

* Never read or display `.env`.
* Never include API keys or credentials.
* Never include personal absolute filesystem paths.
* Never use unlimited retry or refinement loops.
* Never claim simulation or verification success without evidence.
* Never modify another team member's implementation outside the assigned scope.
* Never stage, commit, or push automatically.

## Validation

After creating the skill:

1. Run `mbg-validate-extension` on the new `SKILL.md`.
2. Confirm that the folder and frontmatter names match.
3. Report every validation error and warning.
4. Run one success test.
5. Run one failure test.
6. Do not claim completion if validation fails.

## Output Format

```text
Skill:
Owner:
Purpose:
File created:
Validation status:
Errors:
Warnings:
Success test:
Failure test:
Dependencies:
Known limitations:
Git status:
```

If no skill name is supplied, stop and request a valid `mbg-` skill name.
