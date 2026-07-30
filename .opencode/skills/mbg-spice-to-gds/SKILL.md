---
name: mbg-spice-to-gds
description: >
  Converts SPICE subcircuit netlist to DRC-clean GDSII layout using gLayout.
  PRIMARY API: spice_to_gds_with_checks(netlist) — handles layout, DRC, LVS, PEX.
  Use when the user asks to generate GDS from SPICE, convert netlist to layout,
  "layout my circuit", "spice to gds", or mentions analog layout generation.
  Supports GF180MCU 3.3V PDK with auto-placement, power strips, and PathFinder routing.
license: Apache-2.0
compatibility: opencode
metadata:
  owner: huda
  project: microelectronic-block-generator
  status: experimental
---

# MBG SPICE → GDS Layout Generator

## Purpose

Convert a SPICE subcircuit netlist into a DRC-clean GDSII layout with
auto-placement, power delivery, and negotiated-congestion routing.

## ⚠️ CRITICAL: Always Use `spice_to_gds_with_checks(netlist)`

**NEVER** manually call individual placement, power, or routing functions.
The pipeline handles everything:

```python
from core.pipeline import spice_to_gds_with_checks

netlist = """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt my_design vdd vss in out
XM1 out in vdd vdd pfet_03v3 L=1u W=4u nf=1
XM2 out in vss vss nfet_03v3 L=1u W=2u nf=1
.ends
"""

r = spice_to_gds_with_checks(netlist)
# Returns: outdir, gds_path, svg_path, drc, lvs, pex, all_pass
```

## When to Use

- Converting SPICE netlist to GDS layout
- Running full layout + verification pipeline
- User asks "generate layout", "spice to gds", "create GDS"

## When Not to Use

- Manual step-by-step placement/routing (use mbg-full-automate instead)
- Simulation-only tasks (use mbg-spice-sim)
- Verification-only tasks (use mbg-ic-verify)

## ⚠️ PDK Constraints (GF180MCU 3.3V)

| Constraint | Value |
|-----------|-------|
| Supply | 3.3V single |
| MOSFET models | nfet_03v3 / pfet_03v3 ONLY |
| W limit | < 5µm per finger |
| L limit | < 5µm |
| Device prefix | XM1 (not M1) |
| Fingers vs multipliers | Prefer nf=N over m=N |

## Layout Pipeline

1. Parse netlist — auto-detect PDK, extract MOSFET params (W, L, nf, nodes)
2. Activate PDK via gdsfactory
3. Place devices — PMOS top row, NMOS bottom row
4. Power strips — VDD/VSS on metal5 with via stacks
5. Auto-route — PathFinder NCR (M3/M4/M5, I/L/Z/U patterns)
6. Labels — pin labels on metal3
7. Write GDSII

## Output

| Key | Description |
|-----|-------------|
| `outdir` | Output directory path |
| `gds_path` | GDS file path |
| `svg_path` | SVG preview |
| `drc` | DRC result dict |
| `lvs` | LVS result dict |
| `pex` | PEX result dict |
| `all_pass` | True if DRC+LVS+PEX all pass |

## Safety Rules

- Never claim DRC/LVS/PEX success without evidence
- PDK_ROOT and PDK env vars must be set
- All internal nets must be routed (no floating nodes)
- Minimum 5 transistors for analog mode
