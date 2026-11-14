---
name: mbg-setup
description: Install and inspect the public Python, PDK and EDA environment.
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/skills/mbg-setup/SKILL.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

# mbg-setup

## Purpose

Install and inspect the public Python, PDK and EDA environment.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Read docs/install.md. Use `./install.sh --check` before changes. Installation is an explicit user action; never install or fetch tools during a read-only request. EDA helper sources belong under scripts/eda.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.

The shell stage uses `MBG_HOME` (default `~/.mbg`) for activation and launchers.
After installing it, use `mbg check` to inspect the environment. From a checkout,
`scripts/mbg doctor` provides the same public environment report.
