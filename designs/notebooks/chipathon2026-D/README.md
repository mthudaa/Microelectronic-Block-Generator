# Chipathon 2026 — AI Agentic Analog Layout with gLayout

**SSCS Chipathon 2026 — gLayout Track (D): AI/LLM for Analog Circuits**

Converts SPICE subcircuit netlists to DRC-clean GDSII layout using
[gLayout](https://github.com/ReaLLMASIC/gLayout) + custom auto-router.
Supports AC/transient simulation, DRC/LVS/PEX verification, and
pre/post-layout comparison.

## Team Roles & Ownership

This project is developed by a 3-person team with the following module breakdown:

- **Huda (Lead Analog / Mixed-Signal Designer)**: Responsible for the logic and structure of the analog layout, power strips, routing, and pre/post-layout simulation. Main modules: `placement.py`, `routing.py`, `power.py`, `simulation.py`, `spice_parser.py`.
- **Ahmad Jabar Ilmi (Physical Verification & Automation Engineer)**: Manages the automated integration system for DRC, LVS, PEX, and environment setup. Main modules: `checks.py`, `utils.py`, and all bash scripts in `scripts/`.
- **Moh. Jabir Mubarok (AI/LLM Integration & Software Architect)**: Integrates the AI model (DeepSeek) into the pipeline, performs prompt engineering to ensure stable SPICE netlist generation, and collects datasets for future LLM fine-tuning. Main modules: `pipeline.py`, and the `llm_to_gds.ipynb` notebook.

## Git Workflow & Contribution

> [!IMPORTANT]
> **Branching is Mandatory:** Do not push directly to the `main` branch. 
> 
> If you are developing a new feature, fixing a bug, or doing an AI experiment:
> 1. Create a new branch first (e.g., `git checkout -b feature/huda-ota-layout` or `fix/jabir-prompt-error`).
> 2. Commit your changes and ensure they are tested and working correctly.
> 3. Create a **Pull Request (PR)** for review before merging into `main`.

## Quick Start

```bash
# Environment
export PDK_ROOT=/foss/pdks
export PDK=gf180mcuD
export PDKPATH=/foss/pdks/gf180mcuD
export STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0

# LLM API key (for generate_netlist_from_prompt)
cp .env.example .env    # lalu isi DEEPSEEK_API_KEY=sk-...
# atau:
export DEEPSEEK_API_KEY=sk-...

# Run
jupyter lab --ip=0.0.0.0 --no-browser --port=8888
```

## Single API Call (AI Agentic)

```python
from core import spice_to_gds, run_ota_ac

# 1. Layout from SPICE
netlist = """
.lib "/foss/pdks/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt ota_simple vin_p vin_n vout vbias vdd vss
M1 n1 vin_p ntail vss nfet_03v3 W=10u L=1u
M2 vout vin_n ntail vss nfet_03v3 W=10u L=1u
M3 n1 n1 vdd vdd pfet_03v3 W=20u L=1u
M4 vout n1 vdd vdd pfet_03v3 W=20u L=1u
M5 ntail vbias vss vss nfet_03v3 W=15u L=1u
.ends
"""

result = spice_to_gds(netlist, mode="analog", add_labels=True)
result.write_gds("ota_simple.gds")

# 2. Pre-simulation
pre = run_ota_ac(netlist, "ota_simple", vdd=1.8, vcm=0.9, vbias=0.65)
print(f"DC Gain={pre['dc_gain_db']:.1f} dB  GBW={pre['gbw_hz']/1e6:.1f} MHz  PM={pre['phase_margin_deg']:.1f} deg")

# 3. DRC/LVS/PEX (requires Magic + netgen)
# result = spice_to_gds(netlist, mode="analog", add_labels=True, run_checks=True)
```

## Quick Start — AI/LLM Pipeline

The AI-assisted workflow is executed inside the IIC-OSIC-TOOLS Docker container using the `GLdev` Conda environment.

### 1. Enter the project environment

```bash
cd /foss/designs/notebooks/chipathon2026-D

# Prevent the container Python libraries from conflicting with Conda
unset PYTHONPATH
unset PYTHONHOME
unset LD_LIBRARY_PATH

source /headless/conda-env/miniconda3/etc/profile.d/conda.sh
conda activate GLdev
```

Configure the GF180MCU environment:

```bash
export PDK_ROOT=/foss/pdks
export PDK=gf180mcuD
export PDKPATH=/foss/pdks/gf180mcuD
export STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0
```

Verify the environment:

```python
from core import check_tools

status = check_tools()
print(status)

assert status["magic"], "Magic was not found"
assert status["netgen"], "Netgen was not found"
assert status["pdk_ok"], status["message"]
```

Expected result:

```text
{
    "magic": True,
    "netgen": True,
    "pdk_ok": True,
    "message": "All tools OK"
}
```

### 2. Configure the DeepSeek API key

Create a local environment file:

```bash
cp -n .env.example .env
chmod 600 .env
```

Edit `.env` and add:

```text
DEEPSEEK_API_KEY=sk-your-key-here
```

Do not:

* Commit `.env`.
* Store the API key directly in a notebook.
* Print the complete API key in logs.
* Include the API key in experiment records.

### 3. Start JupyterLab

```bash
cd /foss/designs
jupyter lab --ip=0.0.0.0 --no-browser --port=8888
```

Open the following address from the host browser:

```text
http://localhost:8888/lab
```

Then open:

```text
notebooks/chipathon2026-D/llm_to_gds.ipynb
```

The obsolete notebook startup command is not used by the current AI workflow.

## AI-Assisted Design Flow

The AI pipeline separates language-model generation from physical-layout generation so that every intermediate artifact can be inspected and recorded.

```text
User prompt
    │
    ▼
LLM-generated SPICE netlist
    │
    ▼
Syntax and device-model validation
    │
    ▼
Pre-layout simulation
    │
    ▼
gLayout placement and routing
    │
    ▼
Generated GDSII
    │
    ▼
DRC and LVS
    │
    ▼
PEX
    │
    ▼
Post-layout simulation
    │
    ▼
Pre-layout versus post-layout comparison
```

The project currently targets:

```text
Technology: GF180MCU
PDK identifier: gf180mcuD
PDK path: /foss/pdks/gf180mcuD
Supply target: 1.8 V
```

References to other PDKs must not be used for GF180MCU experiment results unless a separate experiment is explicitly performed and documented.

## LLM-to-GDS Example

The recommended workflow generates and validates the SPICE netlist before layout generation.

```python
from pathlib import Path

from core import (
    generate_netlist_from_prompt,
    parse_netlist_with_pdk,
    spice_to_gds,
    validate_gds,
)

prompt = """
Design a CMOS inverter for the GF180MCU PDK.

Requirements:
- Supply voltage: 1.8 V
- Subcircuit name: llm_inverter
- Port order: vin vout vdd vss
- Return only a valid SPICE subcircuit
"""

output_dir = Path("outputs/llm_inverter")
output_dir.mkdir(parents=True, exist_ok=True)

netlist = generate_netlist_from_prompt(prompt)

if not netlist:
    raise RuntimeError("The LLM did not generate a valid SPICE netlist")

netlist_path = output_dir / "llm_inverter.spice"
netlist_path.write_text(netlist, encoding="utf-8")

parsed = parse_netlist_with_pdk(netlist)
print("Detected PDK:", parsed["metadata"]["pdk"])
print("Components:", len(parsed["components"]))

layout = spice_to_gds(
    netlist,
    mode="analog",
    add_labels=True,
)

gds_path = output_dir / "llm_inverter.gds"
layout.write_gds(str(gds_path))

gds_result = validate_gds(str(gds_path))

print("SPICE:", netlist_path)
print("GDS:", gds_path)
print("GDS valid:", gds_result["valid"])
```

For a compact end-to-end API call:

```python
from core import llm_to_gds

layout = llm_to_gds(
    """
    Design a CMOS inverter for GF180MCU using a 1.8 V supply.
    Return a valid SPICE subcircuit suitable for layout generation.
    """
)

layout.write_gds("outputs/llm_inverter_direct.gds")
```

The compact API is useful for demonstrations, but the separated workflow is preferred for experiments because it preserves the generated netlist and validation results.

## LLM Output Acceptance Rules

An LLM response is not accepted only because the API request completed successfully.

A generated design must be evaluated stage by stage.

| Stage                  | Required evidence                                          |
| ---------------------- | ---------------------------------------------------------- |
| Prompt generation      | Original prompt is saved                                   |
| LLM response           | Model identifier and generated text are recorded           |
| Netlist validation     | Valid `.subckt` and supported devices are detected         |
| Pre-layout simulation  | Simulation report and waveforms are stored                 |
| GDS generation         | Generated GDS path is recorded                             |
| GDS validation         | GDS opens successfully and contains a valid top cell       |
| DRC                    | DRC report is stored                                       |
| LVS                    | LVS report is stored when a reference netlist is available |
| PEX                    | Extracted netlist is stored                                |
| Post-layout simulation | Post-layout metrics and waveforms are stored               |
| Final result           | Evidence-based status is reported                          |

Only the following result labels should be used:

```text
PASS
FAIL
PARTIAL
NOT RUN
NOT AVAILABLE
```

A result may be marked `PASS` only when every required acceptance criterion has supporting evidence.

Absolute success claims must not be used when simulation, offset, PVT, physical verification, or post-layout results are incomplete.

## Prompt-Independence Evaluation

To evaluate how much design work is performed by the LLM, experiments should use three prompt-detail levels.

### Minimal Prompt

```text
Design a clocked dynamic comparator for GF180MCU with a 1.8 V supply.
Return a valid SPICE subcircuit suitable for layout generation.
```

### Constraint-Based Prompt

```text
Design a clocked dynamic comparator for GF180MCU.

Requirements:
- 1.8 V supply
- Differential inputs
- Differential outputs
- Clocked reset and regeneration
- Use approved GF180MCU devices
- Return only a valid SPICE subcircuit
```

### Detailed Prompt

A detailed prompt may include:

* Expected topology.
* Exact port order.
* Approved model names.
* Connectivity constraints.
* Approximate transistor sizes.
* Reference implementation details.

The detailed prompt evaluates constrained generation. The minimal prompt evaluates greater LLM design independence.

The prompt levels should be compared using the same simulation and verification criteria.

## AI Experiment Metrics

AI results must be generated from structured experiment records instead of being copied manually into slides.

Recommended metrics:

| Metric                        | Definition                                                |
| ----------------------------- | --------------------------------------------------------- |
| Total prompts                 | Number of independent design requests                     |
| API calls                     | Total model requests                                      |
| First-pass valid-netlist rate | Valid netlists produced without refinement                |
| Final valid-netlist rate      | Valid netlists produced after bounded refinement          |
| Average refinement iterations | Mean retries before acceptance                            |
| Layout-generation rate        | Valid netlists that successfully generate GDS             |
| DRC-clean rate                | Generated layouts that pass DRC                           |
| LVS-match rate                | Generated layouts that pass LVS                           |
| End-to-end success rate       | Runs completing all required stages                       |
| LLM runtime                   | Time spent waiting for model responses                    |
| Total runtime                 | Prompt-to-final-report runtime                            |
| Token usage                   | Input and output token counts when available              |
| Estimated API cost            | Cost calculated when token and pricing data are available |

An initial evaluation should contain at least 10 independent runs. Larger experiment sets are preferred for final reporting.

Example experiment record:

```json
{
  "experiment_id": "comparator-minimal-001",
  "model": "model-identifier",
  "pdk": "gf180mcuD",
  "prompt_level": "minimal",
  "api_calls": 2,
  "refinement_iterations": 1,
  "netlist_valid": true,
  "pre_simulation_status": "PASS",
  "gds_generated": true,
  "drc_status": "PASS",
  "lvs_status": "PASS",
  "pex_status": "NOT RUN",
  "post_simulation_status": "NOT RUN",
  "llm_runtime_seconds": 18.4,
  "total_runtime_seconds": 94.2,
  "final_status": "PARTIAL"
}
```

Every experiment should preserve:

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

## Graphical Netlist Representation

The LLM-generated SPICE netlist should also be represented graphically.

The visualization should identify:

* Subcircuit ports.
* Device names.
* Device types.
* Gate, source, drain, and body connections.
* Internal nets.
* Supply and ground nets.

The graphical representation may be a connectivity graph generated from the parsed netlist. It should be exported as SVG or PNG and associated with the same experiment ID as the generated SPICE and GDS files.

A connectivity graph is not a substitute for final schematic review, but it provides readable evidence of the topology generated by the LLM.

## AI Agentic Interface

The `core` package exposes a Python interface for AI-assisted analog-layout workflows.

| Function                                    | Purpose                                                 | Primary owner   |
| ------------------------------------------- | ------------------------------------------------------- | --------------- |
| `generate_netlist_from_prompt(prompt, ...)` | Generate a SPICE netlist from a natural-language prompt | AI/LLM          |
| `llm_to_gds(prompt, ...)`                   | Execute prompt → netlist → layout                       | AI/LLM          |
| `parse_netlist_with_pdk(netlist, ...)`      | Parse devices and identify the target PDK               | Shared pipeline |
| `spice_to_gds(netlist, ...)`                | Convert a validated SPICE netlist to a layout           | Shared pipeline |
| `run_ota_ac(netlist, ...)`                  | Run OTA AC simulation                                   | Simulation      |
| `run_comparator_tran(netlist, ...)`         | Run comparator transient simulation                     | Simulation      |
| `run_drc(gds, ...)`                         | Run Design Rule Check                                   | Verification    |
| `run_lvs(gds, netlist, ...)`                | Compare layout and schematic connectivity               | Verification    |
| `run_pex(gds, ...)`                         | Extract post-layout parasitics                          | Verification    |
| `compare_pre_post(...)`                     | Compare schematic and post-layout performance           | Simulation      |

The AI pipeline may call simulation and verification APIs, but their internal implementation remains owned by the corresponding simulation and physical-verification modules.

## AI Coding Agent Extensions

Agent extensions are no longer authored per-platform. A canonical layer at the
repository root is the single source of truth, and platform adapters for
OpenCode, Claude Code and Codex are generated from it:

```text
.ai/manifest.json            capabilities, workflows, platform mapping
.ai/skills/<name>/SKILL.md   canonical skills
.ai/workflows/<name>.md      canonical workflows (slash commands)
.ai/knowledge/PROJECT.md     canonical project knowledge
        │
        │  python3 scripts/sync_agent_tools.py
        ▼
.opencode/  .claude/  plugins/mbg-analog/ + .agents/plugins/marketplace.json
```

Editing a generated file under `.opencode/`, `.claude/` or `plugins/` is
pointless — the next sync overwrites it. Edit the canonical file instead, then:

```bash
python3 scripts/sync_agent_tools.py            # regenerate all three platforms
python3 scripts/validate_agent_integrations.py # ten checks, exits non-zero on failure
```

The full authoring standard — frontmatter contract, skill section layout,
workflow format, OpenCode custom-tool rules and the review checklist — lives in
[`docs/opencode/AUTHORING_GUIDE.md`](../../../docs/opencode/AUTHORING_GUIDE.md).
It is kept in one place deliberately; this file previously carried a second
copy that drifted out of date.

See the repository [README](../../../README.md#-ai-coding-agent-integrations)
for per-platform setup, the capability matrix and troubleshooting.

## Design Flow

```
SPICE Netlist
    │
    ▼
┌──────────────────┐
│ spice2net parser  │  auto-detect PDK, parse devices
└────────┬─────────┘
         ▼
┌──────────────────┐
│   placement       │  ALIGN-inspired PMOS-top/NMOS-bottom
└────────┬─────────┘
         ▼
┌──────────────────┐
│   power strips    │  VDD/VSS metal5 rails + via stacks
└────────┬─────────┘
         ▼
┌──────────────────┐
│  auto-router      │  PathFinder NCR (M3/M4/M5, 4 routing patterns)
└────────┬─────────┘
         ▼
┌──────────────────┐
│  labels + snap    │  pin labels, grid snap (5nm)
└────────┬─────────┘
         ▼
    ┌─────────┐     ┌──────────┐     ┌──────────┐
    │   GDS    │────▶│ DRC/LVS  │────▶│   PEX    │
    └─────────┘     └──────────┘     └──────────┘
         │                                │
         ▼                                ▼
    ┌─────────┐                    ┌───────────┐
    │ PRE SIM │                    │ POST SIM  │  (ngspice AC/TRAN)
    └─────────┘                    └───────────┘
```

## Specifications

| Parameter | Target (Chipathon 2026) |
|-----------|------------------------|
| Technology | GF180MCU (gf180mcuD) |
| Supply | 1.8 V |
| DC Gain | ≥ 70 dB |
| Phase Margin | ≥ 45° |
| GBW | ≥ 1 MHz |
| Power | < 0.5 mW |
| Output Swing | ≥ 1 Vpp |

## Requirements

- Python 3.10+
- gLayout + gdsfactory
- ngspice 46+
- Magic VLSI 8.3+ (for DRC/LVS/PEX)
- netgen 1.5+ (for LVS)
- GF180MCU PDK installed at `$PDK_ROOT/gf180mcuD`

## File Structure

The Python engine now lives at the repository root (`<repo>/src/mbg/`, imported
as `mbg`). This directory keeps the Chipathon design work.

```text
chipathon2026-D/
├── notebooks/              # Primary entry points
│   ├── spice_to_gds.ipynb  # SPICE → GDS
│   └── llm_to_gds.ipynb    # LLM → netlist → GDS
│
├── tests/                  # All test suites
│   ├── test_router_synthetic.py    # 8 deterministic placement/routing tests
│   ├── test_agent_integrations.py  # 11 agent-layer integration tests
│   ├── test_experiment_manifest.py # 7 manifest tests
│   └── test_all_designs.py         # end-to-end regression over 4 blocks
│
├── scripts/                # EDA verification scripts, found by mbg.checks
│   ├── iic-drc.sh          # Magic DRC
│   ├── iic-lvs.sh          # netgen LVS
│   └── iic-pex.sh          # Magic PEX
│
├── examples/               # Runnable examples and sample netlists
│   ├── inv_full_flow.py    # full inverter flow, start to finish
│   └── ota_simple.spice
│
├── docs/                   # Long-form reference
│   ├── designflow.txt
│   └── ISSUE_UPDATE.md
│
├── outputs/                # Generated artifacts (gitignored)
│   ├── gds/                # GDSII output
│   └── designs/            # per-design run directories
│
├── ai_logs/                # Dated AI session records (see ai_logs/README.md)
└── dataset/                # Local experiment data (gitignored)
```

The engine is at `<repo>/src/mbg/`; import it as `mbg`:

```python
from mbg.pipeline import spice_to_gds_with_checks, spice_to_gds_ctx
from mbg.checks import run_drc, run_lvs, run_pex
```

Everything resolves its own paths — tests, examples and `mbg.checks` walk up to
find `src/mbg` and this directory's `scripts/`, so they work from any working
directory and in any clone.

## AI Agentic Interface

The `core` package provides a clean Python API designed for AI coding agents:

| Function | Purpose |
|----------|---------|
| `spice_to_gds(netlist, ...)` | SPICE → GDS layout |
| `generate_netlist_from_prompt(prompt)` | LLM → SPICE netlist |
| `llm_to_gds(prompt)` | LLM → netlist → GDS (end-to-end) |
| `run_ota_ac(netlist, ...)` | AC simulation (DC gain, GBW, PM) |
| `run_comparator_tran(netlist, ...)` | Transient simulation (tdelay, offset) |
| `run_drc(gds, ...)` | Design Rule Check |
| `run_lvs(gds, netlist, ...)` | Layout vs Schematic |
| `run_pex(gds, ...)` | Parasitic Extraction |
| `compare_pre_post(sch, pex, ...)` | Pre vs Post comparison |

## License

Apache 2.0
