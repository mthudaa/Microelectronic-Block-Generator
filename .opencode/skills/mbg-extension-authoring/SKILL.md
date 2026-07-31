---
name: mbg-extension-authoring
description: Create or review OpenCode skills, custom tools, commands, agents, and project instructions for the Microelectronic Block Generator repository. Use this for files under .opencode or OpenCode authoring documentation. Do not use it for analog design, simulation, routing, DRC, LVS, or PEX implementation.
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

## When to Use

Use this skill when:

- Creating or reviewing a `SKILL.md`.
- Creating a custom OpenCode tool.
- Creating a slash command.
- Creating or reviewing an OpenCode agent.
- Updating project-level agent instructions.
- Reviewing files under `.opencode/`.

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

## Skill Requirements

A skill must be stored at:

```text
.opencode/skills/<skill-name>/SKILL.md