---
name: mbg-ordinary-macro
description: Prepare an ordinary guard-ring macro through the checked layout tool.
metadata:
  short-description: Prepare an ordinary guard-ring macro through the checked layout tool.
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/skills/mbg-ordinary-macro/SKILL.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

# mbg-ordinary-macro

## Purpose

Prepare an ordinary guard-ring macro through the checked layout tool.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Inspect `scripts/mbg tools layout.generate` for the supported macro configuration. Use only an ordinary ring and explicit supply mappings supported by the selected PDK. Report generated views separately from physical qualification.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.
