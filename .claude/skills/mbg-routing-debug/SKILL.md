---
name: mbg-routing-debug
description: Inspect route failures, opens and shorts in a selected run.
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/skills/mbg-routing-debug/SKILL.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

# mbg-routing-debug

## Purpose

Inspect route failures, opens and shorts in a selected run.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Read the selected layout view and internal connectivity report. Distinguish missing access, opens and shorts. Do not rerun physical verification merely to read an existing report.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.
