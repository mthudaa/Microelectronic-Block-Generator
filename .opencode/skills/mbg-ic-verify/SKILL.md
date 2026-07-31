---
name: mbg-ic-verify
description: >
  Runs DRC, LVS, and PEX verification for GDSII layouts using Magic/netgen.
  Auto-fixes port order in extracted layout netlists. Netgen permute 1 3 handles
  MOSFET D/S swapping natively. Use when user asks to "run DRC", "check LVS",
  "extract parasitics", "verify layout", "run pex", or wants post-layout verification.
  Supports GF180MCU PDK.
license: Apache-2.0
compatibility: opencode
metadata:
  owner: ahmad
  project: microelectronic-block-generator
  status: experimental
---

# MBG IC Layout Verification (DRC/LVS/PEX)

## Purpose

Run physical verification checks on GDSII layouts: Design Rule Check (DRC),
Layout vs Schematic (LVS), and Parasitic Extraction (PEX).

## Prerequisites

```bash
export PDK_ROOT=/home/huda/.volare
export PDK=gf180mcuD
export PDKPATH=$PDK_ROOT/$PDK
```

Magic and netgen must be in PATH. PDK setup file is auto-resolved.

## When to Use

- Running DRC on a GDS file
- Verifying LVS: layout matches schematic
- Extracting parasitics (PEX) for post-layout simulation
- User asks "verify my layout", "run DRC/LVS/PEX"

## When Not to Use

- Generating layout (use mbg-spice-to-gds)
- Running SPICE simulation (use mbg-spice-sim if available)
- Manual netlist editing

## Quick Start

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core import run_drc, run_lvs, run_pex

# DRC
drc = run_drc("out.gds", cell_name="my_cell")
print(drc["summary"])   # "DRC: CLEAN" or "DRC: N ERRORS"

# LVS (netgen permute 1 3 handles D/S swapping natively)
lvs = run_lvs("out.gds", netlist_content=netlist, cell_name="my_cell")
print(lvs["summary"]["message"])  # "LVS OK" or "LVS MISMATCH"

# PEX (mode: 1=C-decoupled, 2=C-coupled, 3=full-RC)
pex = run_pex("out.gds", cell_name="my_cell", mode=2)
print(pex["summary"])   # "PEX: OK (C-coupled)"
```

## Functions

### `run_drc(gds_path, cell_name, engine="magic", workdir, timeout=600)`

Returns: `{clean, report_path, error_count, log, summary}`

### `run_lvs(gds_path, netlist_content/netlist_path, cell_name, workdir, auto_fix_ports=True, timeout=600)`

Auto-fixes extracted port order to match schematic. Netgen's `permute 1 3` rule
is automatically added for nfet_03v3/pfet_03v3 D/S swapping.

Returns: `{match, report_path, log, summary}` where summary has:
`{match, device_mismatch, net_mismatch, port_swaps, missing_devices, message}`

### `run_pex(gds_path, cell_name, mode=2, subcircuit=True, workdir, timeout=600)`

Returns: `{pex_path, mode, log, summary}`

### `extract_layout_netlist(gds_path, cell_name, workdir, timeout=300)`

Extract SPICE netlist from GDS using Magic (no-RC / LVS mode).

Returns: `{netlist_path, raw_ports, log, success}`

## Output Contract

- DRC: `summary` is "DRC: CLEAN" or "DRC: N ERRORS"
- LVS: `summary["message"]` is "LVS OK" or "LVS MISMATCH"
- PEX: `summary` is "PEX: OK (C-coupled)" or "PEX: FAILED (...)"

## Safety Rules

- **MOSFET body: pfet_03v3→VDD ONLY, nfet_03v3→VSS ONLY**
- Never claim verification success without actual tool output
- PDK setup file must exist (auto-resolved with symlink fallback)
- LVS net merge is DISABLED (was corrupting schematic netlists)
- Property errors on LVS match are acceptable (W/L parameter warnings)
