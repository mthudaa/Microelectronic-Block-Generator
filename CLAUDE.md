<!-- GENERATED FILE — do not edit by hand. Source: .ai/manifest.json, .ai/skills/**, .ai/workflows/** (via scripts/sync_agent_tools.py). Regenerate with: python3 scripts/sync_agent_tools.py -->

@AGENTS.md

## Claude Code Adapter for Microelectronic Block Generator

This section is generated. Shared project rules live in AGENTS.md above (Claude Code does not read AGENTS.md natively, hence the `@AGENTS.md` import); this section adds the Claude-Code-specific inventory of generated skills and commands.

### Generated skills (`.claude/skills/`)

- `mbg-agent-interface` — How any AI agent drives MBG through its tool surface — the `scripts/mbg` command line or the same tools over MCP (`scripts/mbg mcp`) — discovering what is legal, checking and simulating a netlist, generating and inspecting a layout, steering placement with a hints file, verifying, and reading the one-JSON-envelope result of every call. Use at the start of any design, simulation, layout or verification task in this repository, whatever the harness. Do not use it to change the tools themselves (edit src/mbg/agent/) or for repository setup (use mbg-setup).
- `mbg-ai-experiment-audit` — Audits an MBG AI-assisted analog-design experiment record for reproducibility, prompt independence, bounded LLM refinement, artifact completeness, AI metrics, and evidence-based results. Use this skill when reviewing experiment.json, generated SPICE, GDS, simulation outputs, or DRC/LVS/PEX reports for an AI experiment. Do not use it to modify analog-design, simulation, routing, or verification implementations.
- `mbg-context-economy` — How to work in this repository without burning the context window - resolve the repo from $MBG_ROOT instead of searching $HOME, read a file once at the right granularity, never poll git state, and climb the verification ladder cheapest-first instead of re-running the whole flow. Use at the start of any multi-step task in this repo, and whenever a session starts feeling slow or repetitive. Do not use it to decide what a design should be - it governs how you gather information, not what you conclude.
- `mbg-design-regression` — Reads AI-Generated-Design-Result as both working design output and regression evidence, understands the "<design>_designcontext_v2/" convention for new pipeline runs kept beside preserved baselines, and inventories the artifacts (.gds, .lvs.out, .magic.drc.rpt, .spice, REPORT.md) each design directory holds. Use before comparing a new run against a prior one, or before writing anything into AI-Generated-Design-Result. Do not use it to generate a new layout or run verification — this skill is read-only and never overwrites a previous result.
- `mbg-extension-authoring` — Creates or reviews canonical agent skills and workflows under .ai/, plus OpenCode-only custom tools under .opencode/tools, for the Microelectronic Block Generator repository. Use this for authoring or reviewing SKILL.md files, .ai/workflows entries, or .opencode/tools/*.ts files. Do not use it for analog design, simulation, routing, DRC, LVS, or PEX implementation.
- `mbg-full-auto` — Fully automated analog design from one request — the /mbg-full-auto command. Parses the specification, runs pre-layout optimization, layout, DRC, LVS, PEX extraction, PEX simulation and PEX-aware fine-tuning, with Devil and Angel reviewers at every stage, then a tapeout-ready sign-off gate and an automatic design report. Use when the user gives a design request and wants it carried through autonomously. Do not use for a single isolated stage (use the stage skills), or for layout with no performance target (use mbg-spice-to-gds).
- `mbg-ic-verify` — Runs DRC, LVS, and PEX physical verification for GDSII layouts using Magic and netgen, with automatic port-order fixing for LVS. Use when the user asks to "run DRC", "check LVS", "extract parasitics", "verify layout", "run pex", or otherwise wants post-layout verification of an existing GDS under GF180MCU. Do not use it to generate layout (use mbg-spice-to-gds) or to run SPICE simulation.
- `mbg-pex-aware-flow` — Drives the MBG two-loop design methodology — pre-layout optimization, then PEX-aware post-layout optimization. Use whenever a design has performance targets (gain, bandwidth, phase margin, offset, delay, power) and must be taken from specification to a sign-off candidate. Use it to decide what to do when post-layout simulation misses spec. Do not use it for layout-only tasks with no performance target (use mbg-spice-to-gds), or for pure verification of an existing GDS (use mbg-ic-verify).
- `mbg-placement-debug` — Inspects analog device placement — matching groups, symmetry constraints, device bounding boxes and overlap, pin access points, reserved zones, routing channels, congestion, and the placement-routability feedback loop. Use when a layout's device placement looks wrong, a net cannot find a routable path, or you need to explain why the placer chose a given floorplan. Do not use it to change the router or to generate a new layout end to end.
- `mbg-repo-analysis` — Maps the Microelectronic Block Generator repository, traces the active execution path from a design script to the layout pipeline, separates active implementations from legacy code kept only for backward compatibility, and analyzes SPICE netlists (devices, nets, terminals, connectivity). Use before modifying or debugging any core module, or when asked what a design script actually calls. Do not use it to generate layout, run verification, or modify implementation — this skill is read-only.
- `mbg-reviewers` — The Devil and Angel critic sub-agents and how their reviews are synthesized into a decision. Use when acting as a reviewer for a design stage, when interpreting review findings, or when deciding whether a design may proceed or be signed off. Do not use it to modify a design directly — reviewers advise, the Designer changes, the tools decide.
- `mbg-routing-debug` — Traces nets, inspects vias and metal-layer usage, and detects shorts, opens, and route conflicts using the DesignContext grid router and internal connectivity checker. Use when a route failed, a net looks shorted or open, or you need to verify physical connectivity against the SPICE netlist before external DRC/LVS signoff. Do not use it to change the router implementation or to run external Magic/netgen signoff — that is mbg-ic-verify.
- `mbg-setup` — Sets up this repository on a new machine — the Python environment, the GF180MCU PDK, the EDA tools (Magic, netgen, KLayout), the shell integration in $HOME/.mbg, and the OpenCode / Claude Code / Codex agent integrations, repo-scoped or for the whole user account — then verifies the result. Use when someone has just cloned the repository, when imports fail, when the PDK or EDA tools cannot be found, when `mbg check` or a `/mbg-*` command does not work, or when a teammate asks how to install. Do not use it to design or verify a circuit.
- `mbg-spice-sim` — Runs ngspice simulations for analog blocks in this repository and turns the raw output into readable data, using mbg.simulation (run_spice, raw_to_csv, parse_dat). Use when the user asks to simulate a netlist, measure gain, bandwidth, delay or offset, sweep corners, or compare pre-layout against post-layout behaviour. Do not use it to generate layout (use mbg-spice-to-gds) or to run DRC, LVS or PEX (use mbg-ic-verify).
- `mbg-spice-to-gds` — Converts a SPICE subcircuit netlist into a DRC-clean GDSII layout using gLayout, via the single entry point spice_to_gds_with_checks(netlist). Use when the user asks to generate GDS from SPICE, convert a netlist to layout, "layout my circuit", or "spice to gds" for the GF180MCU 3.3V PDK. Do not use for manual step-by-step placement/routing, simulation-only tasks, or verification-only tasks on an already-built GDS (use mbg-ic-verify for that).
- `mbg-voltage-reference` — Designs, characterises and lays out a voltage reference (bandgap with vertical PNPs and poly resistors, or MOS-only zero-TC) on gf180mcuD with the MBG tools — topology choice, first-cut sizing equations, the `mbg measure vref` recipe across temperature, supply, corners and IBIAS, and layout matching through placement hints. Use when the task is a voltage or current reference, a bandgap, a PTAT/CTAT generator or a VREF.md-style specification. Do not use it for amplifiers (use mbg-pex-aware-flow with `mbg measure ota`) or for verification of an existing GDS (use mbg-ic-verify).

### Generated commands (`.claude/commands/`)

- `/mbg-full-auto` — Fully automated analog design from one request — specification to tapeout-ready package or a diagnosed non-convergence report, with multi-agent review, branch-and-compare search, and PEX-aware optimization.
- `/mbg-install` — Set up this repository for AI-agent use — Python, PDK, EDA tools, the $HOME/.mbg shell integration, then the OpenCode / Claude Code / Codex integrations, repo-scoped or user-wide — and verify the result.
- `/mbg-new-command` — Scaffold a new canonical MBG workflow under .ai/workflows using the project authoring standard, then resync all platform adapters.
- `/mbg-new-skill` — Scaffold a new canonical MBG skill under .ai/skills using the project authoring standard, then resync all platform adapters.
- `/mbg-partial-automate` — Semi-automatic analog IC design flow with user confirmation at each step, from specification to tapeout.
- `/mbg-review-ai-experiment` — Review an MBG AI experiment for reproducibility, bounded refinement, artifact completeness, metrics, and evidence-backed status.
- `/mbg-review-extension` — Review an MBG agent extension (skill, workflow, or OpenCode tool) against the project authoring and safety rules.
- `/mbg-setup-env` — Create or repair the Python environment, EDA tools and shell integration for this repository, and report exactly what is installed, what is missing, and what the PDK looks like.

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
