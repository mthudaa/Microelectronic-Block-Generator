# Chipathon 2026 — AI Agentic Analog Layout with gLayout

**SSCS Chipathon 2026 — gLayout Track (D): AI/LLM for Analog Circuits**

Converts SPICE subcircuit netlists to DRC-clean GDSII layout using
[gLayout](https://github.com/ReaLLMASIC/gLayout) + custom auto-router.
Supports AC/transient simulation, DRC/LVS/PEX verification, and
pre/post-layout comparison.

## Quick Start

```bash
# Environment
export PDK_ROOT=/foss/pdks
export PDK=gf180mcuD
export PDKPATH=/foss/pdks/gf180mcuD
export STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0

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
├── inverter.ipynb        # Main entry-point notebook
├── designflow.txt         # Detailed design flow documentation
├── core/                  # Modular Python library
│   ├── utils.py           # Display helpers, paths
│   ├── routing.py         # PathFinder NCR auto-router
│   ├── placement.py       # Device placement & port mapping
│   ├── power.py           # Power strips, guard rings
│   ├── pipeline.py        # spice_to_gds() master pipeline
│   ├── checks.py          # run_drc(), run_lvs(), run_pex()
│   ├── simulation.py      # run_ota_ac(), run_comparator_tran()
│   └── __init__.py
├── spice2net/             # SPICE netlist parser
├── routefinder/           # Standalone A* 3D router
├── iic-drc.sh             # Magic/KLayout DRC script
├── iic-lvs.sh             # netgen LVS script
└── iic-pex.sh             # Magic PEX script
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
