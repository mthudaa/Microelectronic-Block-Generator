# MBG for any AI agent

MBG gives an AI the same hands a human analog designer gets from an EDA GUI,
in a form a language model can use well: text in, one small JSON document
out, bulk data on disk. This page says how each agent harness finds the
tools, the instructions and the skills. The tool reference itself is
[`TOOLS.md`](TOOLS.md), generated from `src/mbg/agent/registry.py`.

## Three layers, all generated from one source

| layer | what | read by |
| :--- | :--- | :--- |
| instructions | `AGENTS.md` (rules, tool quickstart, generated tool/skill index); `CLAUDE.md` points Claude Code at it | every harness below |
| tools | `scripts/mbg <group> <action>` (any shell) and `scripts/mbg mcp` (MCP, stdio) | every harness with a shell; every MCP client |
| skills | `.ai/skills/*/SKILL.md`, generated into `.agents/skills/`, `.claude/skills/`, `.opencode/skills/` and the Codex plugin | harnesses with a skills mechanism |

`python3 scripts/sync_agent_tools.py` regenerates every adapter, the MCP
configs, the `AGENTS.md` index and `TOOLS.md` from `.ai/manifest.json`,
`.ai/skills/`, `.ai/workflows/` and the tool registry;
`python3 scripts/validate_agent_integrations.py` checks that nothing drifted.

## Harness matrix

| harness | instructions | skills | tools | project config written here |
| :--- | :--- | :--- | :--- | :--- |
| Claude Code | `CLAUDE.md` → `AGENTS.md` | `.claude/skills/`, `.claude/commands/` | MCP + CLI | `.mcp.json`; `.claude/settings.json` pre-approves `scripts/mbg` and the `mbg` server |
| Codex CLI | `AGENTS.md` | `.agents/skills/`; plugin `plugins/mbg-analog` | MCP + CLI | `.codex/config.toml` (read for trusted projects only) |
| OpenCode | `AGENTS.md` | `.opencode/skills/`, `.opencode/commands/` (it also reads `.agents/skills/`) | MCP + CLI + custom tools `.opencode/tools/` | `mcp` block in `opencode.jsonc` |
| Pi (`pi.dev`) | `AGENTS.md` | `.agents/skills/` | CLI (Pi has no built-in MCP) | — |
| DeepSeek-based agents (Deep Code, DeepSeek-TUI) | `AGENTS.md` | `.agents/skills/` | CLI; MCP where the harness has a client | point its MCP config at `scripts/mbg mcp` |
| Gemini CLI | `AGENTS.md` (via `context.fileName`) | — | MCP + CLI | `.gemini/settings.json` |
| Cursor | `AGENTS.md` | — | MCP + CLI | `.cursor/mcp.json` |
| any other MCP client | — | — | `scripts/mbg mcp` | — |
| any agent with a shell | `AGENTS.md` | — | `scripts/mbg` | — |

A model used *through* one of these harnesses (DeepSeek, Qwen, GPT, Gemini,
Claude, a local model) gets the same tools; nothing in MBG depends on the
model vendor. `mbg.llm` is separate: it calls an LLM API directly to draft a
netlist, with rules generated from the PDK profile.

### What has been verified

| check | status | evidence |
| :--- | :--- | :--- |
| MCP protocol with the official Python SDK client, mcp 1.30 and 2.3 | PASS | `tests/test_mcp_server.py::OfficialSdkClient` (initialize, tools/list, tools/call) |
| MCP stdio server, protocol versions 2024-11-05 … 2025-11-25 | PASS | `tests/test_mcp_server.py` |
| CLI envelope, exit codes, one JSON document on stdout | PASS | `tests/test_agent_cli.py` |
| Claude Code discovers the generated skills | PASS | the new skills appeared in a running Claude Code session after a sync |
| Generated configs parse (JSON, TOML) | PASS | `scripts/validate_agent_integrations.py`, `sync --check` |
| Codex, OpenCode, Pi, Gemini CLI, Cursor load the configs and skills live | NOT RUN | needs those CLIs installed; not done in the session that built this |

## The MCP server

`scripts/mbg mcp` speaks JSON-RPC over stdio and needs no packages beyond
the standard library. Each `tools/call` runs the CLI in a subprocess, so the
layout stack is never imported into the server, a PDK switch cannot leak
between calls, and a stuck tool can be killed. Tools are coarse (one per
stage; `verify` takes `check: drc|lvs|pex`, `pdk` takes `action: list|info`,
`design` takes `action: init|status`, `job` takes `action: status|wait|cancel`).
Results are the same `mbg.result/1` envelope as text content and, from
protocol 2025-06-18, as `structuredContent`.

Calls longer than 50 s return a job id instead of blocking the client; the
`job` tool (`action: wait`) picks the result up. Raise your client's tool
timeout if it is below a minute (the generated configs set 1800 s).

## Adding a harness

1. If it reads `AGENTS.md` and `.agents/skills/`, nothing is needed.
2. If it has a project MCP config file, add a target to
   `render_mcp_configs` in `scripts/sync_agent_tools.py` and a path to
   `.ai/manifest.json#mcp.configs`, then run the sync.
3. If it has neither, `scripts/mbg` from its shell tool is the interface.
