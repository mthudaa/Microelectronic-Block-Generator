---
name: mbg-spice-to-gds
description: Generate a checked layout from an explicit SPICE input.
class: GENERATING
owner: maintainers
capabilities: [spice_to_gds]
platforms: [opencode, claude, codex]
---

# mbg-spice-to-gds

## Purpose

Generate a checked layout from an explicit SPICE input.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Inspect `scripts/mbg tools layout.generate`, check the netlist and PDK first, then call the checked layout tool. Preserve the original input and report every verification stage separately.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.
