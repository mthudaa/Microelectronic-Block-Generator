---
name: spice-to-gds
description: Converts SPICE subcircuit netlist to DRC-clean GDSII layout using gLayout. Use when the user asks to generate GDS from SPICE, convert netlist to layout, "layout my circuit", "spice to gds", or mentions chipathon/analog layout generation. Supports gf180mcuD and sky130 PDKs with auto-placement, power strips, and PathFinder auto-routing.
---

# SPICE → GDS Layout Generator

Convert a SPICE subcircuit netlist into a DRC-clean GDSII layout using gLayout
with auto-placement, power delivery, and negotiated-congestion routing.

## Quick start

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(".")))
from core import spice_to_gds, display_component

netlist = """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt my_ota vin_p vin_n vout vbias vdd vss
M1 n1 vin_p ntail vss nfet_03v3 W=10u L=1u
M2 vout vin_n ntail vss nfet_03v3 W=10u L=1u
M3 n1 n1 vdd vdd pfet_03v3 W=20u L=1u
M4 vout n1 vdd vdd pfet_03v3 W=20u L=1u
M5 ntail vbias vss vss nfet_03v3 W=15u L=1u
.ends
"""
result = spice_to_gds(netlist, mode="analog", add_labels=True)
result.write_gds("out.gds")
display_component(result, scale=2)
```

## Key parameters for `spice_to_gds()`

| Parameter    | Default    | Description |
|-------------|------------|-------------|
| `netlist_input` | required | SPICE netlist string |
| `mode`       | `"analog"` | `"analog"` or `"digital"` — affects PDK activation |
| `add_labels` | `True`    | Add pin labels on metal3 |
| `run_checks` | `False`   | Set `True` to run DRC+LVS+PEX automatically |

## Layout pipeline steps

1. **Parse** netlist via `spice2net` — auto-detects PDK (gf180/sky130), extracts MOSFET params (W, L, M, nodes)
2. **Activate** PDK via gdsfactory
3. **Place** devices — PMOS top row, NMOS bottom row, ALIGN-inspired spacing
4. **Power strips** — VDD/VSS on metal5 with via stacks (met2→met5)
5. **Auto-route** — PathFinder negotiated-congestion router (M3/M4/M5, I/L/Z/U patterns)
6. **Labels** — pin labels on metal3, snap to 5nm grid
7. **Write** GDSII

## Netlist requirements

- First line: `.lib "<model_path>" typical` (path auto-detected from PDK_ROOT/PDK env vars)
- Models: `nfet_03v3` (NMOS), `pfet_03v3` (PMOS) for gf180mcuD
- Supply: 1.8V, body connections: NMOS→vss, PMOS→vdd
- Format: `M<name> <drain> <gate> <source> <body> <model> W=<w>u L=<l>u`
- W between 1u–50u, L=1u for analog (0.5u for comparator)

## Constraints

- Minimum 5 transistors for analog mode
- All internal nets must be routed (no floating nodes)
- PDK_ROOT and PDK env vars must point to valid PDK installation

## Related modules

- `core/pipeline.py` — `spice_to_gds()`, `llm_to_gds()`, `generate_netlist_from_prompt()`
- `core/placement.py` — device placement engine
- `core/routing.py` — PathFinder auto-router
- `core/power.py` — power strip and guard ring generation
- `core/utils.py` — GDS display utilities
