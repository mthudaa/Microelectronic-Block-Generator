---
name: mbg-spice-sim
description: Simulate an explicit circuit and report measured results.
license: Apache-2.0
metadata:
  owner: maintainers
  project: microelectronic-block-generator
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/skills/mbg-spice-sim/SKILL.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

# mbg-spice-sim

## Purpose

Simulate an explicit circuit and report measured results.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Inspect `scripts/mbg tools sim.run`; select a PDK, supplies and analysis explicitly. Keep source and extracted netlists distinct. Preserve logs and do not claim a measurement when the solver failed.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.
