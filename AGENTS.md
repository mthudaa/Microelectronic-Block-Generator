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

## OpenCode Extension Rules

Project-specific OpenCode extensions must use the `mbg-` prefix.

Locations:

```text
.opencode/skills/<skill-name>/SKILL.md
.opencode/tools/<tool-name>.ts
.opencode/commands/<command-name>.md
.opencode/agents/<agent-name>.md
```

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
