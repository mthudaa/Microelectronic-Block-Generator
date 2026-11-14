---
name: mbg-placement-debug
description: Inspect device locations and layout access without changing connectivity.
metadata:
  short-description: Inspect device locations and layout access without changing connectivity.
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/skills/mbg-placement-debug/SKILL.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

# mbg-placement-debug

## Purpose

Inspect device locations and layout access without changing connectivity.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Use `scripts/mbg layout view` on the chosen design. Inspect device bounds, spacing and access points. Report concrete spacing or access issues and preserve the netlist topology.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.
