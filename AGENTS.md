# Public MBG agent rules

This release provides Basic and Intermediate analog-layout tools: inspect SPICE,
check a netlist, simulate it, generate a layout, inspect placement/routing, and
run physical verification. Use the CLI or the same registry over MCP.

## Confidentiality and authorization

Unreleased user inputs, circuit netlists, generated artifacts, simulation data,
and local session logs are confidential unless the user explicitly authorizes
publication. Repository access alone does not authorize publication. Never read
credential files, expose secrets, or include user data in examples or fixtures.
Git push and other publication require explicit user authorization. Preserve the
existing human Git identity and license; do not add AI authorship trailers.
Do not overwrite user work or delete generated evidence without authorization.

## Working safely

Use repository-relative paths for source inputs and reject parent traversal and
escaping symlinks. Explicit output destinations remain authoritative; default
runs use MBG_OUT or ~/mbg. Keep output authorization separate from source trust.
Select one PDK per run. Query `scripts/mbg pdk info` before choosing devices.
Use `scripts/mbg tools` for the current schemas and bounded run controls.
A tool process completing does not prove a circuit is correct. Report checks as
PASS, FAIL, PARTIAL, NOT RUN or NOT AVAILABLE only with supporting evidence.
DRC, LVS, extraction, extracted simulation and specifications are distinct gates.
Report inspected/changed files, actual validation, artifacts and unresolved issues.

## Canonical agent configuration

Edit .ai/manifest.json, .ai/skills and .ai/workflows; regenerate adapters with
`python3 scripts/sync_agent_tools.py`, then run
`python3 scripts/validate_agent_integrations.py`. Generated adapters must not be
edited by hand. All harnesses share these rules and the deterministic CLI/MCP
registry. Setup and EDA helper scripts live under scripts/setup and scripts/eda.

<!-- BEGIN GENERATED: agent index (scripts/sync_agent_tools.py) -->
<!-- Edit .ai/ or src/mbg/agent/registry.py, then run `python3 scripts/sync_agent_tools.py`. -->

### Tools (`scripts/mbg <group> <action>`; same tools over MCP: `scripts/mbg mcp`)

| command | what it does |
| :--- | :--- |
| `mbg doctor` | Check the environment: Python stack, Magic/netgen/KLayout/ngspice versions, installed PDKs |
| `mbg pdk list` | List supported PDK variants and whether each is installed |
| `mbg pdk info` | What is legal in a PDK: supply, device models with terminal order and size limits, which devices the layout engine supports, simulation corners, sign-off decks, the tested complexity ceiling |
| `mbg design init` | Create a design workspace ~/mbg/<name>/ (AGENTS.md artifact layout + experiment.json) |
| `mbg design status` | Summarise a workspace: which stages ran, their status, key metrics and artifacts |
| `mbg netlist check` | Static checks before simulating or laying out: syntax, models vs the PDK catalogue, terminal counts, W/L limits and units, body ties, instance prefixes, floating nets, layout support per device, and complexity against the tested ceiling |
| `mbg sim run` | Simulate the subcircuit with ngspice in a generated testbench: op, dc (source, supply or temp sweep), ac or tran |
| `mbg measure vref` | Characterise a voltage reference: VREF at 27 C, temperature coefficient (box method), line regulation, supply current, IBIAS sensitivity, PSRR, startup, across corners; evaluates a spec |
| `mbg measure ota` | Characterise an amplifier: DC gain, -3 dB bandwidth, unity-gain frequency, phase margin and supply current |
| `mbg spec check` | Evaluate metrics against a specification; PASS only if every required spec is met |
| `mbg layout generate` | SPICE -> GDS with placement and grid routing, then Magic DRC, netgen LVS and PEX |
| `mbg layout view` | Text view of a generated layout: ASCII floorplan, device boxes, rows, per-device nets and routing failures, in floorplan coordinates |
| `mbg verify drc` | Magic DRC on a GDS with an executed report required for PASS |
| `mbg verify lvs` | netgen LVS of a GDS against its schematic netlist |
| `mbg verify pex` | Magic parasitic extraction to a SPICE netlist for post-layout simulation |
| `mbg measure adc` | Evaluate source-bound ADC transition INL/DNL and missing codes |
| `mbg measure dac` | Evaluate measured DAC code voltages, INL/DNL and monotonicity |
| `mbg job status` | State of a background job; its result when finished |
| `mbg job wait` | Wait for a background job and return its result |
| `mbg job cancel` | Stop a background job |

Full input schemas: `scripts/mbg tools <id>` or `docs/TOOLS.md`.

### Skills (`.ai/skills/`, generated into `.agents/skills/`, `.claude/skills/`, `.opencode/skills/` and the Codex plugin)

- `mbg-agent-interface` — Use the public CLI and MCP tools for checked layout work.
- `mbg-ic-verify` — Run DRC, LVS and parasitic extraction on a selected layout.
- `mbg-ordinary-macro` — Prepare an ordinary guard-ring macro through the checked layout tool.
- `mbg-placement-debug` — Inspect device locations and layout access without changing connectivity.
- `mbg-repo-analysis` — Find the public entry points and relevant source modules.
- `mbg-routing-debug` — Inspect route failures, opens and shorts in a selected run.
- `mbg-setup` — Install and inspect the public Python, PDK and EDA environment.
- `mbg-spice-sim` — Simulate an explicit circuit and report measured results.
- `mbg-spice-to-gds` — Generate a checked layout from an explicit SPICE input.

<!-- END GENERATED: agent index -->
