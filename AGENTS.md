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

* `core/placement.py`
* `core/routing.py`
* `core/power.py`
* `core/simulation.py`
* `core/spice_parser.py`

### Ahmad

Primary ownership:

* DRC
* LVS
* PEX
* Physical-verification automation
* Verification environment and scripts

Relevant modules:

* `core/checks.py`
* `core/utils.py`
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

* `core/pipeline.py`
* `llm_to_gds.ipynb`
* `.opencode/`
* `README.md`
* `ISSUE_UPDATE.md`

Do not modify another member's implementation merely to complete an AI or
documentation task. Record the requirement as a dependency or reviewer issue.

## Development Environment

The repository is stored in WSL. EDA tools and the GF180MCU PDK run inside the
IIC-OSIC-TOOLS Docker container.

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
before running container-only commands.

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
verification). On the four reference blocks the previous shape-router path
passed 0/4 — it could not label top-level pins correctly and failed LVS pin
matching — while the current path passes 4/4 with DRC clean, LVS match and
zero opens or shorts. Pass `legacy=True`, or call
`spice_to_gds_with_checks_legacy(...)`, to run the old implementation:

```python
from mbg.pipeline import spice_to_gds_with_checks
r = spice_to_gds_with_checks(netlist)
# r["outdir"], r["gds_path"], r["drc"], r["lvs"], r["pex"], r["all_pass"]
```

## ⚠️ Tapeout Gate

| Gate | Requirement |
|------|-------------|
| DRC | Magic DRC zero violations (≤100 with note acceptable) |
| LVS | Netgen LVS: netlist matches layout |
| PEX | Parasitic extraction complete |
| Post-layout | Matches pre-layout within 10% tolerance |

A design passing DRC+LVS+PEX = **ready for tapeout**.

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

This repository supports three AI coding agents: OpenCode, Claude Code and
Codex. Their extension files are GENERATED from one canonical source. Do not
hand-edit a generated file — the next sync will overwrite it.

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
CLAUDE.md
.ai/project-index.json
```

Platform-specific files that are maintained by hand:

```text
opencode.jsonc            OpenCode permissions
.claude/settings.json     Claude Code permissions
.opencode/tools/*.ts      OpenCode custom tools (only OpenCode supports code tools)
```

First-time setup on a new machine, for any of the three agents:

```bash
./scripts/install_agents.sh          # add --check to inspect without changing anything
```

OpenCode and Claude Code read this repository directly and need no
registration. Codex has no repo-scoped skills, so its plugin is registered
once per machine; because Codex caches the plugin at install time, re-run
`./scripts/install_agents.sh --only codex` after a sync to refresh it.

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
