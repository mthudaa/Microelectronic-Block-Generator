---
description: Review an MBG agent extension (skill, workflow, or OpenCode tool) against the project authoring and safety rules.
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/workflows/mbg-review-extension.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

Review the following Microelectronic Block Generator agent extension:

```text
$1
```

## Required Workflow

1. Load the `mbg-extension-authoring` skill.
2. Confirm that the provided path:
   - Is repository-relative.
   - Is located under `.ai/skills/`, `.ai/workflows/`, or
     `.opencode/tools/` (a code tool) — not under a generated adapter
     directory such as `.opencode/skills/`, `.claude/skills/`,
     `.opencode/commands/`, or `.claude/commands/`. If the path is under a
     generated directory, stop and redirect the review to the
     corresponding `.ai/` source file instead.
   - Does not contain parent-directory traversal.
3. Review the extension against `mbg-extension-authoring`'s requirements:
   - One clear responsibility.
   - Correct `mbg-` naming and directory/frontmatter `name` match.
   - Flat frontmatter only (no nested YAML, matching the sync script's
     minimal parser).
   - Correct owner and dependencies.
   - Documented required inputs, outputs, and side effects.
   - Platform-neutral body (no platform name mentioned unless the skill is
     genuinely about authoring for that one platform).
   - Safe filesystem handling (repository-relative paths, rejected
     traversal) for any code tool.
   - Secret and API-key protection.
   - Explicit failure modes.
   - No invented tools, APIs, modules, or verification results — cross-check
     referenced entry points against the actual source.
4. Report errors before warnings.
5. Reference the exact file and rule for every finding.
6. Do not modify the reviewed file.
7. Do not stage, commit, or push changes.

## PDK Body Constraint

**MOSFET body: `pfet_03v3` -> VDD ONLY, `nfet_03v3` -> VSS ONLY.**
Extensions that generate or process SPICE must enforce this rule.

## Output Format

```text
Extension:
Type:
Validation status:
Errors:
Warnings:
Owner:
Dependencies:
Security findings:
Required corrections:
Recommended next action:
```

If no path is supplied, stop and request a repository-relative path under
`.ai/skills/`, `.ai/workflows/`, or `.opencode/tools/`.
