---
name: mbg-ic-verify
description: Run DRC, LVS and parasitic extraction on a selected layout.
license: Apache-2.0
compatibility: opencode
metadata:
  owner: maintainers
  project: microelectronic-block-generator
  status: experimental
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/skills/mbg-ic-verify/SKILL.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

# mbg-ic-verify

## Purpose

Run DRC, LVS and parasitic extraction on a selected layout.

## Required inputs

An explicitly selected project, PDK, input and task. Read AGENTS.md first.

## Workflow

Use `scripts/mbg verify drc`, `scripts/mbg verify lvs` and `scripts/mbg verify pex` with explicit inputs. Query each schema first. Extraction alone does not establish successful extracted simulation or specifications.

## Outputs and side effects

Report actual tool status and artifact locations. Generating tasks write only to
the selected output tree; read-only tasks make no changes. Protect confidential
inputs and artifacts. Reject traversal, secret paths and escaping symlinks.

## Failure modes

Stop the affected stage when inputs or tools are unavailable. Report the missing
dependency, including circuit/placement or physical-verification ownership as
applicable. Do not substitute an unsupported device or claim an unexecuted check.
