# Microelectronic Block Generator Agent Rules

## Project Scope

This repository implements an AI-assisted analog-layout workflow for the SSCS
Chipathon 2026 gLayout track.

The documented project flow uses:

* Technology: GF180MCU
* PDK identifier: `gf180mcuD`
* Container PDK path: `/foss/pdks/gf180mcuD`
* Main project directory:
  `designs/notebooks/chipathon2026-D`
* Python package: `src/mbg` (`import mbg`); agent tool surface: `scripts/mbg`
* Second PDK: `sky130A` (smoke-verified: MOS-only layout, Magic DRC, LVS,
  PEX, simulation). Select it with `--pdk sky130A`; never mix the two.

Do not mix results from another PDK into a GF180MCU experiment unless that work
is explicitly documented as a separate experiment.

## Team Ownership

Respect the existing module ownership.

### Huda

Primary ownership:

* Analog circuit design
* Device selection and sizing
* Placement
* Routing
* Power structures
* Simulation implementation

Relevant modules:

* `src/mbg/placement.py`, `src/mbg/placement_engine.py`
* `src/mbg/routing.py`, `src/mbg/router.py`
* `src/mbg/power.py`
* `src/mbg/simulation.py`, `src/mbg/analysis.py`, `src/mbg/measure.py`
* `src/mbg/spice_parser.py`
* `src/mbg/passives.py`, `src/mbg/fixed_cells.py`
* `src/mbg/pdk_profile.py`, `src/mbg/pdks/*.json`

### Ahmad

Primary ownership:

* DRC
* LVS
* PEX
* Physical-verification automation
* Verification environment and scripts

Relevant modules:

* `src/mbg/checks.py`, `src/mbg/drc.py`, `src/mbg/connectivity.py`
* `src/mbg/utils.py`
* Verification scripts

### Jabir

Primary ownership:

* AI and LLM integration
* Prompt engineering
* Experiment metadata
* AI evaluation metrics
* OpenCode skills, tools, commands, and agents
* AI-related documentation

Relevant files:

* `src/mbg/pipeline.py`
* `src/mbg/agent/` (tool registry, `mbg` CLI, MCP server)
* `tests/notebooks/llm_to_gds.ipynb`
* `.opencode/`, `.agents/`, `.ai/`
* `README.md`
* `ISSUE_UPDATE.md`

Do not modify another member's implementation merely to complete an AI or
documentation task. Record the requirement as a dependency or reviewer issue.

## Context Economy

How you gather information here decides whether you finish. A measured
session in this repository spent **87% of a 1 MB conversation on tool
output** — one 1000-line file re-read 22 times, `git status` polled 27+
times, and 33 KB spent searching `$HOME` for a repo already named by
`$MBG_ROOT`.

* Resolve the repository from `$MBG_ROOT`. Never search `$HOME` for it.
* Index a module before reading it — `grep -n '^def \|^class '` costs about
  280 tokens against 12,500 for `src/mbg/checks.py`.
* A file you have read is already in context. Re-read only after editing it,
  or when a tool contradicts what you have.
* `git status` twice per task — once before editing, once before committing.
  Not between every command.
* Run the cheapest check that answers the question, and read finished
  artifacts off disk rather than re-running the flow to inspect one stage.
* Cap command output (`| head`, `| tail`, `grep -c`); put bulk reading in a
  sub-agent where the platform has one.

Reading less is the goal. **Checking less is not** — if you skip a check to
save budget, say that it did not run rather than implying it passed. Full
rules: the `mbg-context-economy` skill.

## Development Environment

Two supported set-ups. `scripts/mbg doctor` reports which one you are in, the
tool versions and the installed PDKs — run it instead of guessing.

**Native install** (`./install.sh`): a project `.venv`, Magic/netgen/KLayout/
ngspice, and the PDKs under `PDK_ROOT` (default `~/.volare`). `scripts/mbg`
uses `<repo>/.venv` automatically; `$MBG_PYTHON` or `$MBG_VENV` override it.

**IIC-OSIC-TOOLS container**: the repository is stored in WSL; EDA tools and
the GF180MCU PDK run inside the container.

Before activating the `GLdev` environment inside the container:

```bash
unset PYTHONPATH
unset PYTHONHOME
unset LD_LIBRARY_PATH

source /headless/conda-env/miniconda3/etc/profile.d/conda.sh
conda activate GLdev
```

Required PDK variables:

```bash
export PDK_ROOT=/foss/pdks
export PDK=gf180mcuD
export PDKPATH=/foss/pdks/gf180mcuD
export STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0
```

Do not assume that a terminal is inside the container. Confirm the environment
before running container-only commands. Code that switches PDK uses
`mbg.pdk_profile` (`profile.env()`), which overrides these variables for the
duration of a run.

## Tool Surface — Any Agent

MBG is driven by tool calls, not by hand-written Python. The same tools are
available on two surfaces, generated from one registry
(`src/mbg/agent/registry.py`):

* **Command line** — `scripts/mbg <group> <action> [args]`. Works in every
  harness that has a shell (Claude Code, Codex, OpenCode, Pi, Deep Code,
  Gemini CLI, Cursor, Aider, …). `python -m mbg` is the same program.
* **MCP** — `scripts/mbg mcp` (stdio). Project configs: `.mcp.json` (Claude
  Code), `.codex/config.toml` (Codex, trusted projects), `opencode.jsonc`,
  `.cursor/mcp.json`, `.gemini/settings.json`.

Every call prints exactly one JSON envelope (`mbg.result/1`) on stdout:
`status` (the labels below), `summary`, `metrics`, `artifacts`, `issues`
(each with a `hint`) and `next`. Logs go to `<run_dir>/log.txt`. Exit code 0
PASS, 1 FAIL/PARTIAL, 2 usage error, 3 NOT RUN/NOT AVAILABLE, 4 job running.

```bash
scripts/mbg doctor                         # environment, tools, PDKs
scripts/mbg tools [<id>]                   # what you can call, with schemas
scripts/mbg pdk info --pdk gf180mcuD       # legal devices, limits, corners
scripts/mbg design init <name> --netlist x.spice --model <model id>
scripts/mbg netlist check --design <name>
scripts/mbg sim run --design <name> --analysis op --supplies '{"VDD":3.3,"VSS":0}'
scripts/mbg layout generate --design <name> [--hints hints.json]
scripts/mbg layout view --design <name>    # text view of the floorplan
scripts/mbg flow run --design <name> --recipe vref --spec vref_md
```

Skill `mbg-agent-interface` explains the envelope, placement hints and
background jobs.

<!-- BEGIN GENERATED: agent index (scripts/sync_agent_tools.py) -->
<!-- Edit .ai/ or src/mbg/agent/registry.py, then run `python3 scripts/sync_agent_tools.py`. -->

### Tools (`scripts/mbg <group> <action>`; same tools over MCP: `scripts/mbg mcp`)

| command | what it does |
| :--- | :--- |
| `mbg doctor` | Check the environment: Python stack, Magic/netgen/KLayout/ngspice versions, installed PDKs |
| `mbg pdk list` | List supported PDK variants and whether each is installed |
| `mbg pdk info` | What is legal in a PDK: supply, device models with terminal order and size limits, which devices the layout engine supports, simulation corners, sign-off decks, the tested complexity ceiling |
| `mbg design init` | Create a design workspace outputs/<name>/ (AGENTS.md artifact layout + experiment.json) |
| `mbg design status` | Summarise a workspace: which stages ran, their status, key metrics and artifacts |
| `mbg netlist check` | Static checks before simulating or laying out: syntax, models vs the PDK catalogue, terminal counts, W/L limits and units, body ties, instance prefixes, floating nets, layout support per device, and complexity against the tested ceiling |
| `mbg sim run` | Simulate the subcircuit with ngspice in a generated testbench: op, dc (source, supply or temp sweep), ac or tran |
| `mbg measure vref` | Characterise a voltage reference: VREF at 27 C, temperature coefficient (box method), line regulation, supply current, IBIAS sensitivity, PSRR, startup, across corners; evaluates a spec |
| `mbg measure ota` | Characterise an amplifier: DC gain, -3 dB bandwidth, unity-gain frequency, phase margin and supply current |
| `mbg spec check` | Evaluate metrics against a specification; PASS only if every required spec is met |
| `mbg layout generate` | SPICE -> GDS with the analog placer and DRC-aware router, then Magic + KLayout DRC, netgen LVS and PEX |
| `mbg layout view` | Text view of a generated layout: ASCII floorplan, device boxes, rows, per-device nets and routing failures, in the coordinates hints use |
| `mbg verify drc` | Magic DRC plus the PDK's KLayout deck on a GDS (dual-engine sign-off) |
| `mbg verify lvs` | netgen LVS of a GDS against its schematic netlist |
| `mbg verify pex` | Magic parasitic extraction to a SPICE netlist for post-layout simulation |
| `mbg flow run` | One call from netlist to sign-off: netlist check, pre-layout measurement, layout + DRC/LVS/PEX, post-layout measurement on the extracted netlist, spec evaluation pre vs post |
| `mbg job status` | State of a background job; its result when finished |
| `mbg job wait` | Wait for a background job and return its result |
| `mbg job cancel` | Stop a background job |

Full input schemas: `scripts/mbg tools <id>` or `docs/TOOLS.md`.

### Skills (`.ai/skills/`, generated into `.agents/skills/`, `.claude/skills/`, `.opencode/skills/` and the Codex plugin)

- `mbg-agent-interface` — How any AI agent drives MBG through its tool surface — the `scripts/mbg` command line or the same tools over MCP (`scripts/mbg mcp`)…
- `mbg-ai-experiment-audit` — Audits an MBG AI-assisted analog-design experiment record for reproducibility, prompt independence, bounded LLM refinement, artifact…
- `mbg-context-economy` — How to work in this repository without burning the context window - resolve the repo from $MBG_ROOT instead of searching $HOME, read a file…
- `mbg-design-regression` — Reads AI-Generated-Design-Result as both working design output and regression evidence, understands the "<design>_designcontext_v2/"…
- `mbg-extension-authoring` — Creates or reviews canonical agent skills and workflows under .ai/, plus OpenCode-only custom tools under .opencode/tools, for the…
- `mbg-full-auto` — Fully automated analog design from one request — the /mbg-full-auto command.
- `mbg-ic-verify` — Runs DRC, LVS, and PEX physical verification for GDSII layouts using Magic and netgen, with automatic port-order fixing for LVS.
- `mbg-pex-aware-flow` — Drives the MBG two-loop design methodology — pre-layout optimization, then PEX-aware post-layout optimization.
- `mbg-placement-debug` — Inspects analog device placement — matching groups, symmetry constraints, device bounding boxes and overlap, pin access points, reserved…
- `mbg-repo-analysis` — Maps the Microelectronic Block Generator repository, traces the active execution path from a design script to the layout pipeline…
- `mbg-reviewers` — The Devil and Angel critic sub-agents and how their reviews are synthesized into a decision.
- `mbg-routing-debug` — Traces nets, inspects vias and metal-layer usage, and detects shorts, opens, and route conflicts using the DesignContext grid router and…
- `mbg-setup` — Sets up this repository on a new machine — the Python environment, the GF180MCU PDK, the EDA tools (Magic, netgen, KLayout), the shell…
- `mbg-spice-sim` — Runs ngspice simulations for analog blocks in this repository and turns the raw output into readable data, using mbg.simulation (run_spice…
- `mbg-spice-to-gds` — Converts a SPICE subcircuit netlist into a DRC-clean GDSII layout using gLayout, via the single entry point…
- `mbg-voltage-reference` — Designs, characterises and lays out a voltage reference (bandgap with vertical PNPs and poly resistors, or MOS-only zero-TC) on gf180mcuD…

<!-- END GENERATED: agent index -->

## ⚠️ PDK Design Constraints (GF180MCU 3.3V)

These constraints are enforced at every pipeline stage:

| Constraint | Value | Notes |
|-----------|-------|-------|
| **Supply** | **3.3V** single | Use `nfet_03v3` / `pfet_03v3` ONLY |
| **MOSFET W** | < 10µm | Per finger width |
| **MOSFET L** | < 10µm | Per transistor |
| **Device prefix** | `XM1` (not `M1`) | Standard for gf180mcuD |
| **Fingers vs mult** | Prefer `nf=N` over `m=N` | Better matching, compact |
| **VDD pad** | `gf180mcu_fd_io__vdd` | Dedicated supply cell |
| **VSS pad** | `gf180mcu_fd_io__vss` | Dedicated supply cell |
| **Analog I/O** | `gf180mcu_fd_io__asign` analog mode | T_EN=0, T_IE=1 |

## ⚠️ Primary Pipeline API

**Always use `spice_to_gds_with_checks(netlist)`** for SPICE→GDS conversion.
NEVER call individual placement, power, or routing functions manually.

Since v0.2 this entry point drives the DesignContext flow (analog-aware
placement plus the DRC-aware grid router with internal connectivity
verification). The previous shape-router path could not label top-level pins
correctly and failed LVS pin matching on every reference block; the current
path passes all eight designs in `tests/netlists/` on all four legs — Magic
DRC clean, KLayout sign-off PASS, LVS match, and zero opens, shorts or
missing access points. Pass `legacy=True`, or call
`spice_to_gds_with_checks_legacy(...)`, to run the old implementation:

```python
from mbg.pipeline import spice_to_gds_with_checks
r = spice_to_gds_with_checks(netlist)
# r["outdir"], r["gds_path"], r["drc"], r["drc_signoff"], r["lvs"],
# r["pex"], r["verification"], r["metrics"], r["all_pass"]
```

`all_pass` is all four legs, not a DRC summary: Magic clean AND
`drc_signoff["verdict"] == "PASS"` AND LVS match AND
`verification["clean"]`. A KLayout engine that did not run counts as a
failure — silence from a checker is not a pass.

## ⚠️ Complexity

The tested ceiling is 12 MOS / 11 nets / max net degree 16, flat (single
`.subckt`). Device count does not predict difficulty: the 11-MOS StrongArm
comparator and the 12-MOS clocked comparator have the same maximum net
degree, and only the latter exposed a boundary — device-size heterogeneity
did, not size. Read `tests/test_complexity_ladder.py` for the metrics before
attributing a failure to circuit size. Nested `.subckt` are parsed but NOT
flattened; `.param` is not expanded. Do not claim support above what the
regression demonstrates.

One design in the regression sits above that ceiling:
`tests/netlists/vref_bgr_1v2.spice` (10 MOS + 4 vertical PNP + 5 poly
resistors, 14 nets, VSS degree 21) passes all four legs. It is a single data
point with mostly long-channel devices, not a new ceiling — `mbg netlist
check` still reports `ABOVE_TESTED_CEILING` for it.

## ⚠️ Tapeout Gate

| Gate | Requirement |
|------|-------------|
| DRC | Magic DRC zero violations (≤100 with note acceptable) |
| LVS | Netgen LVS: netlist matches layout |
| PEX extraction | Parasitic netlist produced |
| PEX simulation | Extracted netlist simulated successfully |
| PEX specifications | Post-layout results meet the target specifications |

A design passing DRC + LVS + PEX **extraction** is verified, not finished.
Ready for tapeout means the *extracted* design meets its specifications —
see `.ai/knowledge/DESIGN_FLOW.md`. PEX is feedback into a second
optimisation loop, not a final stamp.

## ⚠️ LVS Notes

- Netgen `permute 1 3` handles MOSFET D/S swapping natively — no Python permute needed.
- Auto net-merge is **disabled** in `run_lvs` (was corrupting schematic netlists).
- PDK setup file is auto-resolved with symlink fallback.
- Property errors on LVS match (W/L warnings) are acceptable.

## AI and LLM Rules

* Load API credentials from `.env` or environment variables.
* Never read, print, summarize, copy, or commit `.env`.
* Never place an API key directly inside a notebook or source file.
* Record the model identifier used for every experiment.
* Preserve the original prompt and generated SPICE netlist.
* Record API-call count and refinement-iteration count.
* Every refinement loop must have a defined maximum iteration count.
* Validate generated SPICE syntax before layout generation.
* Validate generated device models against the approved GF180MCU model list.
* Do not treat a successful API response as proof of circuit correctness.
* Do not claim simulation, DRC, LVS, PEX, or post-layout success without
  supporting evidence.

## Experiment Status Values

Use only these result labels:

* `PASS`
* `FAIL`
* `PARTIAL`
* `NOT RUN`
* `NOT AVAILABLE`

A run may be marked `PASS` only when all required acceptance criteria have
supporting artifacts or reports.

Avoid unsupported absolute claims such as fully autonomous or completely
functional when some stages are missing or unsuccessful.

## Experiment Artifacts

A complete AI experiment should preserve:

```text
outputs/<experiment-id>/
├── experiment.json
├── prompt.txt
├── generated_netlist.spice
├── circuit_graph.svg
├── generated_layout.gds
├── pre_simulation/
├── drc/
├── lvs/
├── pex/
└── post_simulation/
```

Structured experiment metadata should include:

* Experiment identifier
* Model identifier
* PDK identifier
* Prompt-detail level
* API calls
* Refinement iterations
* Netlist-validation status
* GDS-generation status
* DRC status
* LVS status
* PEX status
* Pre-layout simulation status
* Post-layout simulation status
* Runtime
* Final status

## Agent Extension Rules

This repository has first-class adapters for OpenCode, Claude Code and Codex,
and a generic Agent Skills tree (`.agents/skills/`) plus MCP configs that
other harnesses (Pi, Deep Code and other DeepSeek-based agents, Gemini CLI,
Cursor) pick up. All of these files are GENERATED from one canonical source.
Do not hand-edit a generated file — the next sync will overwrite it.

Source of truth:

```text
.ai/manifest.json            capabilities, workflows and platform mapping
.ai/skills/<name>/SKILL.md   canonical skill definitions
.ai/workflows/<name>.md      canonical command/workflow definitions
.ai/knowledge/PROJECT.md     canonical project knowledge
AGENTS.md                    shared agent rules (this file)
```

Generated adapters (do not edit by hand):

```text
.opencode/skills/<name>/SKILL.md      .opencode/commands/<name>.md
.claude/skills/<name>/SKILL.md        .claude/commands/<name>.md
plugins/mbg-analog/skills/<name>/SKILL.md
plugins/mbg-analog/.codex-plugin/plugin.json
.agents/plugins/marketplace.json
.agents/skills/<name>/SKILL.md        (Agent Skills standard: Codex, OpenCode, Pi, Deep Code)
.mcp.json  .codex/config.toml  .cursor/mcp.json  .gemini/settings.json
CLAUDE.md
.ai/project-index.json
docs/TOOLS.md                         (from src/mbg/agent/registry.py)
AGENTS.md, between the GENERATED agent-index markers
```

Platform-specific files that are maintained by hand:

```text
opencode.jsonc            OpenCode permissions and its `mcp` entry
.claude/settings.json     Claude Code permissions
.opencode/tools/*.ts      OpenCode custom tools — thin wrappers over scripts/mbg
```

First-time setup on a new machine, for any of the three agents:

```bash
./install.sh --stage agents          # add --check to inspect without changing anything
```

OpenCode, Claude Code, Pi and Deep Code read this repository directly
(`AGENTS.md`, `.agents/skills/`, their own directories) and need no
registration. Codex reads `AGENTS.md` and `.agents/skills/` too; its plugin
(commands and the marketplace entry) is registered once per machine, and
because Codex caches the plugin at install time, re-run
`./install.sh --stage agents` after a sync to refresh it. Harnesses without a
skills mechanism only need `AGENTS.md` and `scripts/mbg`.

To add or change a capability:

1. Edit the canonical definition under `.ai/`.
2. Add the implementation if one is needed.
3. Update `.ai/manifest.json`.
4. Run `python3 scripts/sync_agent_tools.py`.
5. Run `python3 scripts/validate_agent_integrations.py`.
6. Commit the canonical change together with the regenerated adapters.

Project-specific extensions must use the `mbg-` prefix.

Every extension must:

1. Have one clear responsibility.
2. Identify its owner.
3. Document required inputs.
4. Document outputs and side effects.
5. Validate filesystem paths.
6. Reject parent-directory traversal.
7. Protect secrets.
8. Report failures explicitly.
9. Use minimum required permissions.
10. Include one success test.
11. Include one failure test.
12. Identify dependencies on other team members.

Do not create a custom tool named after a built-in tool such as `bash`, `read`,
`write`, or `edit` unless overriding the built-in behavior is explicitly
required.

Do not hardcode absolute paths such as a personal home directory into any
skill, tool or script. Discover the repository root dynamically.

## Filesystem Safety

* Prefer repository-relative paths.
* Reject absolute user-provided paths when a repository-relative path is
  expected.
* Reject paths containing parent traversal such as `../`.
* Do not write outside the Git worktree unless a temporary directory is
  explicitly required.
* Do not inspect secret files.
* Do not delete generated files without explicit approval.
* Never use `rm -rf` as a default cleanup method.

## Generated Files

Notebook execution may modify or create:

* `.ipynb`
* `.svg`
* `.gds`
* `.spice`
* `.log`
* Verification reports

Do not automatically stage generated files. Treat them as experiment artifacts
until the user explicitly decides that they belong in version control.

## Git Rules

* Work only on a feature or fix branch.
* Never push directly to `main`.
* Do not run `git add .` when generated artifacts are present.
* Stage only files related to the current task.
* Do not commit `.env`, API keys, personal paths, or temporary outputs.
* Do not run `git push` without explicit user approval.
* Do not discard uncommitted user work without explicit approval.

Before committing:

```bash
git diff --check
git status --short
git diff --cached
```

## Required Reporting

When completing work, report:

* Files inspected
* Files changed
* Validation performed
* Tests performed
* Generated artifacts
* Dependencies
* Unresolved issues
* Exact Git status
