---
name: custom-ic-mbg
description: >
  Complete custom analog IC design flow from specification to tapeout-ready GDSII.
  Two modes: /mbg-full-automate (AI-driven) and /mbg-partial-automate (user-guided).
  PRIMARY API: Always use spice_to_gds_with_checks(netlist) for SPICE-to-GDS conversion.
  DO NOT manually call placement → power → routing — the pipeline handles everything.
  Trigger on any IC design task.
---

# Custom IC Design Flow — Microelectronic Block Generator (MBG)

## ⚠️ CRITICAL: Always Use `spice_to_gds_with_checks(netlist)`

**NEVER** manually call individual placement, power, or routing functions.
The pipeline function `spice_to_gds_with_checks()` handles everything automatically:

```python
from core.pipeline import spice_to_gds_with_checks

netlist = """
.lib "..." typical
.subckt my_design vdd vss in out
...
.ends
"""

result = spice_to_gds_with_checks(netlist)
# Returns: outdir, gds_path, svg_path, drc, lvs, pex, all_pass
```

### When to use which function

| Function | Use Case |
|----------|----------|
| `spice_to_gds_with_checks(netlist)` | **PRIMARY** — full SPICE→GDS+DRC+LVS+PEX |
| `spice_to_gds(netlist, run_checks=False)` | Layout only, skip DRC/LVS/PEX |
| `spice_to_gds(netlist, run_checks=True)` | Layout + checks inline |
| `llm_to_gds_with_manifest(prompt)` | LLM prompt→GDS with experiment tracking |

### ❌ NEVER do this (manual step-by-step)
```python
# WRONG — don't call these manually:
top_level, port_map = placement(config, pdk)       # NO
top_level, _ = manual_power(top_level, pdk, ...)   # NO
top_level = auto_router(top_level, connections)     # NO
```
The pipeline calls all of these automatically in the correct order.

## ⚠️ CAUTION: Prefer `nf` (Fingers) over `m` (Multipliers)

**ALWAYS use finger number (`nf`) instead of multiplier (`m`) for MOSFET sizing.**

| Parameter | Behavior | Recommendation |
|-----------|----------|----------------|
| `nf=N` | Creates N gate fingers sharing diffusion | ✅ **PREFERRED** — better matching, compact |
| `m=N` | Creates N separate transistor instances | ❌ **AVOID** — worse matching, larger area |

```spice
* ✅ CORRECT — use nf for wider transistors
XM1 out in vdd vdd pfet_03v3 L=1u W=2u nf=4 m=1

* ❌ WRONG — using multiplier instead of fingers
XM1 out in vdd vdd pfet_03v3 L=1u W=2u nf=1 m=4
```

**Why**: Fingered transistors share diffusion regions, reducing parasitic capacitance and improving matching for differential pairs and current mirrors. Multipliers create isolated instances that must be routed separately, increasing area and mismatch.

## Quick Start

Choose your mode:

| Command | Mode | User Involvement |
|---------|------|-----------------|
| `/mbg-full-automate` | AI-driven | Minimal — confirm at key checkpoints |
| `/mbg-partial-automate` | User-guided | Full — confirm every step |

## /mbg-full-automate — Full Automatic Flow

```
User Spec → Research → Confirm → Pre-Sim → Layout → LVS → PEX → Tapeout
    │           │         │         │         │       │      │       │
    └─ AI asks  └─ AI     └─ User   └─ AI     └─ AI   └─ AI  └─ AI   └─ Done
       user      researches  approves  finetunes  places  checks matches final
```

**Steps**: See `commands/mbg-full-automate.md` for detailed workflow.

## /mbg-partial-automate — Semi-Automatic Flow

```
User Spec → Research → Netlist → Pre-Sim → Layout → DRC/LVS → PEX → Tapeout
    │          │         │         │         │         │       │       │
    └─ AI asks └─ User   └─ User   └─ User   └─ User   └─ User └─ User └─ User
                reviews   edits     reviews    directs   reviews compares approves
```

**Steps**: See `commands/mbg-partial-automate.md` for detailed workflow.

## Development Tracking

See `pi.dev.md` for active tasks, priorities, and completed items.


## Working Directory

All generated files default to `$MBG_WORKDIR` (`/tmp/mbg_workspace`). Override:

```bash
export MBG_WORKDIR=/my/project/folder
source pi-custom-mbg/common/env.sh
```

## Quick Start

## Pipeline Overview

```
┌──────────┐    ┌─────────────┐    ┌──────────┐    ┌───────────┐    ┌──────┐    ┌─────────┐    ┌──────────┐
│ Research │───▶│ Spec/Netlist │───▶│ Pre-Sim │───▶│ Layout    │───▶│ DRC  │───▶│ Post-Sim│───▶│ Tapeout  │
│(topology,│    │              │    │ (verify)│    │ (place/   │    │/LVS  │    │ (compare)│    │ Package  │
│ sizing,  │    │              │    │         │    │  power/   │    │/PEX  │    │          │    │          │
│ trade-   │    │              │    │         │    │  route)   │    │      │    │          │    │          │
│ offs)    │    │              │    │         │    │           │    │      │    │          │    │          │
└──────────┘    └─────────────┘    └──────────┘    └───────────┘    └──────┘    └─────────┘    └──────────┘
```
       ▲                 ▲               ▲              ▲            ▲               ▲
       │                 │               │              │            │               │
       └─────────────────┴───────────────┴──────────────┴────────────┴───────────────┘
                                         │
                                    ┌────┴────┐
                                    │ SPICE-  │
                                    │ in-the- │
                                    │ Loop    │
                                    └─────────┘
```

## Flow Completion Deliverables

When any design flow finishes, the AI must provide:

| # | Deliverable | Description | Location |
|---|-------------|-------------|----------|
| 1 | **🖼️ SVG** | Layout visualization from GDS | `$MBG_WORKDIR/*.svg` |
| 2 | **📊 Simulation files** | Pre & post testbenches + raw data | `$MBG_WORKDIR/simulation/*.spice` |
| 3 | **📚 Research references** | Papers, PDK docs, sources consulted | Listed inline in AI response |
| 4 | **📦 GDS** | Final layout | `$MBG_WORKDIR/*.gds` |
| 5 | **📋 Reports** | DRC/LVS/PEX reports | `$MBG_WORKDIR/{drc,lvs,pex}/` |

Example final output:
```
✅ Full flow complete!

🖼️  Layout: $MBG_WORKDIR/ota_final.svg
📊  Pre-sim: $MBG_WORKDIR/simulation/pre_sim.spice
📊  Post-sim: $MBG_WORKDIR/simulation/post_sim.spice
📚  References: [1] IEEE JSSC 2021 [2] Razavi 2022
📦  GDS: $MBG_WORKDIR/ota_final.gds
📋  DRC: $MBG_WORKDIR/drc/ota.magic.drc.rpt
📋  LVS: $MBG_WORKDIR/lvs/ota.lvs.out
```

## Slash Commands (pi.dev)

| Command | Description |
|---------|-------------|
| `/mbg-full-automate` | **Fully automatic**: AI interviews you about specs, researches, proposes a plan, gets approval, then fully automates netlist → pre-sim → layout → DRC → LVS → PEX → post-sim → tapeout. AI asks for confirmation at each gate. |
| `/mbg-cowork-design` | **Co-working mode**: AI guides you step-by-step through each phase. You make key decisions, AI executes and explains trade-offs. Supports interactive debugging and what-if exploration. |

### Research Integration

All slash commands automatically invoke `custom-ic-research` during the specification phase to:
- Research optimal circuit topology for given specs
- Extract PDK parameters for accurate first-pass sizing
- Find published work on similar designs
- Analyze power/area/speed trade-offs

### How `/mbg-full-automate` works:

```
/user: "/mbg-full-automate Design an OTA for a sensor interface"
  │
  ▼ AI asks about specs (gain, BW, power, supply, load)
  ▼ AI does deep research on similar designs
  ▼ AI presents proposal with topology + device sizing
  ▼ User gives feedback → AI re-researches if needed
  ▼ User approves plan
  ─────────────────────────────────────────────
  ▼ AI generates SPICE netlist
  ▼ AI runs pre-sim → meets specs? → iterate or proceed
  ▼ AI generates layout (placement → power → route)
  ▼ AI runs DRC → clean? → fix or proceed
  ▼ AI runs LVS → match? → fix or proceed
  ▼ AI runs PEX
  ▼ AI runs post-sim → compares pre vs post
  ─────────────────────────────────────────────
  ▼ AI presents final results
  ▼ AI asks: "Approve?" or "Debug?"
  ▼ User approves → tapeout package
```

### How `/mbg-cowork-design` works:

```
/user: "/mbg-cowork-design Let's build an inverter"
  │
  ▼ AI shows topology options with trade-offs
  ▼ User picks topology
  ▼ AI suggests sizes, user adjusts
  ▼ AI runs simulation, shows waveforms
  ▼ User tweaks parameters → AI re-runs
  ▼ AI shows layout options → user chooses
  ▼ AI shows SVG preview → user approves
  ▼ AI runs DRC, shows violation map
  ▼ User decides fix strategy → AI implements
  ▼ AI runs LVS, shows result
  ▼ AI runs post-sim, compares pre vs post
  ▼ User signs off → tapeout package
```

## Sub-skills

| Skill | Description | When to Use |
|-------|-------------|-------------|
| `custom-ic-spec-to-netlist` | Convert specs → SPICE netlist via LLM | Start of project |
| `custom-ic-pre-sim` | Pre-layout simulation & verification | After netlist, before layout |
| `custom-ic-netlist-to-layout` | SPICE → GDS layout (place/power/route) | After pre-sim passes |
| `custom-ic-verify` | DRC + LVS + PEX verification | After layout |
| `custom-ic-post-sim` | Post-layout sim & pre-vs-post comparison | After verification |
| `custom-ic-optimize` | SPICE-in-the-loop iteration | When specs not met |
| `custom-ic-tapeout` | Final checks + deliverable packaging | Before tapeout |
| `custom-ic-research` | Deep research on topologies, sizing, trade-offs, PDK | Before starting a new design |

## Environment Setup

```bash
source pi-custom-mbg/common/env.sh
```

This sets `PDK_ROOT`, `PDK`, `PDKPATH`, and `PYTHONPATH`.

## Supported PDKs

- **GF180MCU** (default): GlobalFoundries 180nm CMOS
- **Sky130**: SkyWater 130nm open-source PDK

## Quick Reference

```python
# Core API (all importable from core)
from core import (
    spice_to_gds,           # SPICE → GDS layout
    generate_netlist_from_prompt,  # LLM → SPICE
    llm_to_gds,             # LLM → GDS (end-to-end)
    run_drc, run_lvs, run_pex,  # Verification
    check_tools, validate_gds,  # Utilities
    run_spice,              # Simulation
)

# Manual layout (AI-agent friendly)
from core.placement import manual_placement
from core.power import manual_power
from core.routing import manual_route
```

## ⚠️ CRITICAL RULE: No Hallucination

**The AI must NEVER fabricate or guess any of the following:**

| What | Rule |
|------|------|
| **Simulation results** | Never generate fake gain/BW/power numbers. Only report ngspice output. |
| **DRC violations** | Never claim DRC is clean without running it. Only report Magic/KLayout output. |
| **LVS match** | Never claim LVS matched without running netgen. Only report netgen output. |
| **Device sizes** | Never make up W/L values. Only use what the user specified or what `generate_netlist_from_prompt` returned. |
| **Research references** | Never cite a paper you haven't actually read or verified exists. |
| **PDK parameters** | Never guess Vth, Cox, or other PDK parameters. Extract them from the actual PDK model files. |
| **SVG/GDS** | Never claim a layout was generated without calling `write_gds()` + `write_svg()`. |
| **Netlist correctness** | Never claim a netlist is valid without running `parse_netlist_with_pdk()` or `ngspice -b`. |

### Enforcement

1. **Every claim must be traceable to a tool execution.** If you say "Gain = 45 dB", you must have run ngspice and parsed the `.raw` file.
2. **Run tools first, report results second.** Never reverse the order.
3. **If a tool fails, report the failure.** Do not fabricate a fallback value.
4. **If you don't know something, say so.** Do not make up PDK parameters or reference designs.
5. **SVG must be generated from the actual GDS file** using `gdstk`, not drawn by hand.

### Before making any claim, ask yourself:

- Did I actually run ngspice/magic/netgen for this?
- Can I show the exact command and output?
- Is this a real PDK parameter I extracted, or did I guess?
- Have I verified this file exists on disk?

**Hallucination = unacceptable. Real data only.**

## Setup & Installation

The `setup/` directory provides three installation methods:

| Method | Script | Requirements | Best For |
|--------|--------|-------------|----------|
| **Native install** | `setup/install_all.sh` | Linux/macOS, sudo | Full native setup |
| **Docker sandbox** | `setup/docker_sandbox.py` | Docker only | Quick start, no install |
| **Check prereqs** | `setup/check_prereqs.sh` | None | Verify existing setup |

### Python Virtual Environment

The project includes an isolated `.venv` with all Python dependencies pre-configured:

```bash
# Create the .venv (one-time)
bash pi-custom-mbg/setup/create_venv.sh

# Activate it
source pi-custom-mbg/common/activate_venv.sh
# Or just source env.sh — it auto-detects .venv
source pi-custom-mbg/common/env.sh
```

The `.venv` includes: numpy, scipy, gdsfactory, gdstk, glayout. The `create_venv.sh` script handles NumPy 2.0+ compatibility (`np.float_` polyfill) automatically.

### What `install_all.sh` does:

1. Installs system dependencies (build-essential, X11 libs, Tcl/Tk, etc.)
2. Installs Python packages (numpy, gdsfactory, gdstk, glayout)
3. **Builds ngspice** from source (v46+, with XSPICE/OpenMP)
4. **Builds Magic VLSI** from source (v8.3+)
5. **Builds netgen** from source (v1.5+)
6. **Installs GF180MCU PDK** via volare
7. Verifies all tools

### Docker sandbox

The `docker_sandbox.py` script uses the official IIC-OSIC-TOOLS Docker image which comes with all EDA tools pre-installed:

```bash
# Check prerequisites first
python3 pi-custom-mbg/setup/check_prereqs.sh

# Run the full inverter flow in Docker
python3 pi-custom-mbg/setup/docker_sandbox.py

# Run a custom command
python3 pi-custom-mbg/setup/docker_sandbox.py --cmd "python3 -c 'from core import spice_to_gds; print(\"OK\")'"

# Stop the sandbox
python3 pi-custom-mbg/setup/docker_sandbox.py --stop
```

## Pre-Built Cells (gLayout Library)

Available cells from the gLayout library that can be used directly or as building blocks:

```python
from glayout.cells.elementary import (
    diff_pair,        # Differential pair with tail
    current_mirror,   # Simple current mirror  
    fvf,              # Flipped Voltage Follower
    transmission_gate,# CMOS transmission gate
)
from glayout.cells.composite import (
    diffpair_cmirror_bias,              # Diff pair + mirror + bias
    differential_to_single_ended_converter,  # Diff→SE converter
    low_voltage_cmirror,                # Low-V cascode mirror
    stacked_current_mirror,             # Stacked cascode mirror
    opamp_twostage,                     # Two-stage opamp
    fvf_based_ota,                      # FVF-based OTA
)
```

See [references/GLAYOUT_CELLS.md](references/GLAYOUT_CELLS.md) for the full catalog including descriptions and composition patterns.

When designing, always check if a pre-built cell matches your needs before building from scratch.

## File Structure

```
pi-custom-mbg/
├── SKILL.md                    # This file (master orchestrator)
├── common/
│   ├── env.sh                 # Environment setup
│   └── utils.py               # Shared utilities
├── custom-ic-{skill}/
│   ├── SKILL.md               # Skill instructions
│   ├── scripts/               # Helper scripts
│   ├── templates/             # Templates
│   └── config/                # Configuration
├── references/
│   ├── DESIGN_FLOW.md         # Complete flow documentation
│   ├── API_REFERENCE.md       # Core library API
│   └── TROUBLESHOOTING.md     # Common issues & fixes
└── ../../core/                # MBG Python library
    ├── placement.py
    ├── routing.py
    ├── power.py
    ├── pipeline.py
    ├── checks.py
    ├── simulation.py
    └── spice_parser.py
```

## Design Flow Reference

See [references/DESIGN_FLOW.md](references/DESIGN_FLOW.md) for the complete methodology,
[references/API_REFERENCE.md](references/API_REFERENCE.md) for the Python API,
and [references/TROUBLESHOOTING.md](references/TROUBLESHOOTING.md) for common issues.
