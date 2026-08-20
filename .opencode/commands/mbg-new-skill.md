---
description: Scaffold a new canonical MBG skill under .ai/skills using the project authoring standard, then resync all platform adapters.
agent: build
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/workflows/mbg-new-skill.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

Create a new canonical skill for the Microelectronic Block Generator
project.

Requested input:

```text
$ARGUMENTS
```

Interpret the first argument as the skill name. Treat the remaining
arguments as the requested purpose or capability.

## Requirements

1. Load the `mbg-extension-authoring` skill.
2. Require a skill name beginning with `mbg-`.
3. Require lowercase alphanumeric kebab-case.
4. Reject names containing spaces, underscores, consecutive hyphens, or
   leading/trailing hyphens.
5. Create the skill at:

   ```text
   .ai/skills/<skill-name>/SKILL.md
   ```

   Do **not** create it directly under `.opencode/skills/`,
   `.claude/skills/`, or `plugins/mbg-analog/skills/` — those are
   generated output; a hand-edit there is discarded the next time the sync
   script runs.
6. Ensure the directory name exactly matches the YAML frontmatter `name`.
7. Do not overwrite an existing skill without explicit approval.
8. Give the skill one clear responsibility.
9. Set the correct project owner (`huda`, `ahmad`, or `jabir`) and list
   real capability ids that either already exist in
   `.ai/manifest.json`'s `capabilities` section or are being added
   alongside this skill.
10. Do not invent tools, APIs, modules, or verification results — verify
    every referenced entry point against the actual source before writing
    it into the skill.

## PDK Body Constraint

**MOSFET body: `pfet_03v3` -> VDD ONLY, `nfet_03v3` -> VSS ONLY.** If the
new skill generates or processes SPICE netlists, it must enforce this rule.

## Required Frontmatter

Flat `key: value` lines only; list fields written inline. The sync
script's parser is minimal (no PyYAML in this repo's Python
environments) — nested maps, block lists, and multi-line folded scalars
are not supported.

```yaml
---
name: mbg-example-skill
description: 2-4 sentences — what it does, when to use it, when not to.
class: READ-ONLY | GENERATING | MUTATING | DESTRUCTIVE
owner: huda | ahmad | jabir
capabilities: [cap_id]
platforms: [opencode, claude, codex]
---
```

Replace the example name, description, class, owner, and capabilities with
values appropriate to the requested skill.

## Required Sections

The generated skill body must include, per
`docs/opencode/AUTHORING_GUIDE.md`'s section layout: `## Purpose`,
`## When to Use`, `## When Not to Use`, `## Required Inputs`,
`## Preconditions`, `## Workflow`, `## Outputs`, `## Failure Modes`.

Keep the body platform-neutral — do not mention a specific platform by
name unless the skill is genuinely about authoring for that one platform.

## Safety Requirements

- Never read or display `.env`.
- Never include API keys or credentials.
- Never include personal absolute filesystem paths.
- Never use unlimited retry or refinement loops.
- Never claim simulation or verification success without evidence.
- Never modify another team member's implementation outside the assigned
  scope.
- Never stage, commit, or push automatically.

## Validation

After creating the skill:

1. Confirm that the directory and frontmatter `name` match.
2. Confirm the frontmatter is flat (no nested YAML).
3. Confirm every referenced module/function actually exists in the repo.
4. Report every validation error and warning found.
5. Do not claim completion if validation fails.
6. **Run `python3 scripts/sync_agent_tools.py`** to regenerate the
   OpenCode, Claude, and Codex adapters from the new `.ai/skills/` entry.
   If the skill introduces a new capability, coordinate with whoever owns
   `.ai/manifest.json` to add the corresponding entry there — this
   workflow does not hand-edit the manifest itself.

## Output Format

```text
Skill:
Owner:
Purpose:
File created:
Manifest capability entry needed:
Sync command run: python3 scripts/sync_agent_tools.py
Validation status:
Errors:
Warnings:
Known limitations:
Git status:
```

If no skill name is supplied, stop and request a valid `mbg-` skill name.
