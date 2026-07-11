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
- **Moh. Jabir Mubarok (AI/LLM Integration & Software Architect)**: Integrates the AI model (DeepSeek) into the pipeline and performs prompt engineering to ensure stable SPICE netlist generation. Main modules: `pipeline.py`, and the `llm_to_gds.ipynb` notebook.

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
jupyter notebook inverter.ipynb
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

```
chipathon2026-D/
├── spice_to_gds.ipynb     # Main SPICE → GDS notebook
├── llm_to_gds.ipynb       # LLM → netlist → GDS pipeline
├── test_comparator_loop.ipynb  # SPICE-in-the-loop finetuning
├── designflow.txt          # Detailed design flow documentation
├── core/                   # All-in-one Python library
│   ├── pipeline.py         # spice_to_gds(), llm_to_gds()
│   ├── simulation.py       # run_ota_ac(), run_comparator_tran(), run_comparator_pvt()
│   ├── checks.py           # run_drc(), run_lvs(), run_pex()
│   ├── placement.py        # Device placement & port mapping
│   ├── routing.py          # PathFinder NCR auto-router
│   ├── power.py            # Power strips, guard rings
│   ├── spice_parser.py     # SPICE netlist parser
│   ├── utils.py            # Display helpers, paths
│   └── __init__.py
├── scripts/                # Verification shell scripts
│   ├── iic-drc.sh          # Magic/KLayout DRC
│   ├── iic-lvs.sh          # netgen LVS
│   └── iic-pex.sh          # Magic PEX
├── outputs/                # Generated output files
│   ├── gds/                # GDSII layout files
│   └── reports/            # DRC reports, SVGs
└── examples/               # Example SPICE netlists
```

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
