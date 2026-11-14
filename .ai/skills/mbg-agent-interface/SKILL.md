---
name: mbg-agent-interface
description: Use the public CLI and MCP tools for checked layout work.
class: GENERATING
owner: maintainers
capabilities: [agent_cli]
platforms: [opencode, claude, codex]
---

# mbg-agent-interface

## Purpose

Use the public CLI and MCP tools for checked layout work.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Run `scripts/mbg tools` and inspect the requested tool schema. Use `scripts/mbg doctor` to inspect the environment. Each tool returns a JSON result; keep artifact paths and stage statuses separate.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.
