<!-- GENERATED FILE — do not edit by hand. Source: .ai/manifest.json, .ai/skills/**, .ai/workflows/** (via scripts/sync_agent_tools.py). Regenerate with: python3 scripts/sync_agent_tools.py -->

@AGENTS.md

## Claude Code Adapter for Microelectronic Block Generator

This section is generated. Shared project rules live in AGENTS.md above (Claude Code does not read AGENTS.md natively, hence the `@AGENTS.md` import); this section adds the Claude-Code-specific inventory of generated skills and commands.

### Generated skills (`.claude/skills/`)

- `mbg-agent-interface` — Use the public CLI and MCP tools for checked layout work.
- `mbg-ic-verify` — Run DRC, LVS and parasitic extraction on a selected layout.
- `mbg-ordinary-macro` — Prepare an ordinary guard-ring macro through the checked layout tool.
- `mbg-placement-debug` — Inspect device locations and layout access without changing connectivity.
- `mbg-repo-analysis` — Find the public entry points and relevant source modules.
- `mbg-routing-debug` — Inspect route failures, opens and shorts in a selected run.
- `mbg-setup` — Install and inspect the public Python, PDK and EDA environment.
- `mbg-spice-sim` — Simulate an explicit circuit and report measured results.
- `mbg-spice-to-gds` — Generate a checked layout from an explicit SPICE input.

### Generated commands (`.claude/commands/`)

- `/mbg-install` — Install the public MBG environment.
- `/mbg-layout` — Generate a checked layout from an explicit input.
- `/mbg-verify` — Verify a selected layout against explicit circuit inputs.

### Keeping this in sync

```bash
python3 scripts/sync_agent_tools.py          # regenerate adapters + project index
python3 scripts/sync_agent_tools.py --check  # CI: fail if adapters are stale
python3 scripts/validate_agent_integrations.py  # validate the result
./install.sh --stage agents                     # setup / refresh Codex
```

### Tools

Design stages are tools, not Python snippets: `scripts/mbg tools` lists
them, every call prints one JSON envelope, and the same tools are
registered as the project MCP server `mbg` (`.mcp.json`). See
`docs/TOOLS.md` and the `mbg-agent-interface` skill.
