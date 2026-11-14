---
name: mbg-repo-analysis
description: Find the public entry points and relevant source modules.
metadata:
  short-description: Find the public entry points and relevant source modules.
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/skills/mbg-repo-analysis/SKILL.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

# mbg-repo-analysis

## Purpose

Find the public entry points and relevant source modules.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Read AGENTS.md, docs/agent-interface.md and the module symbol index. Index a module before reading relevant spans. Never inspect credentials or infer a completed check from documentation.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.
