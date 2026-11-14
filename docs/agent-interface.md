# Public CLI and MCP interface

Start with `scripts/mbg tools` and query each tool's schema. Use only the public
registry shipped with this release. `scripts/mbg mcp` serves the same tools on
stdio, so shell and MCP clients share validation and result semantics.

Canonical sources are .ai/manifest.json, .ai/skills and .ai/workflows. Regenerate
with `python3 scripts/sync_agent_tools.py`, then validate with
`python3 scripts/validate_agent_integrations.py`. Generated copies live under
.agents, .claude, .opencode and plugins/mbg-analog. Do not edit those copies.

MCP configs use repository-relative launch commands and no credentials. Clients
must launch in this repository. OpenCode uses opencode.jsonc; other supplied
clients use .mcp.json, .codex/config.toml, .cursor/mcp.json or .gemini/settings.json.
AGENTS.md defines confidentiality, source-path containment and publication rules.

Treat PASS, FAIL, PARTIAL, NOT RUN and NOT AVAILABLE as evidence labels. Preserve
selected input/output paths and distinguish each physical or simulation stage.
Only requested generating tools may write outputs. Read-only inspection must not
install packages, run network setup or publish any data.
