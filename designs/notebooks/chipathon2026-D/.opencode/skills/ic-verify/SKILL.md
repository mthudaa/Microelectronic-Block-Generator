---
name: ic-verify
description: >
  Runs DRC, LVS, and PEX verification for GDSII layouts using Magic/netgen.
  Auto-fixes port order in extracted layout netlists so LVS passes without
  manual intervention. Use when user asks to "run DRC", "check LVS",
  "extract parasitics", "verify layout", "run pex", or wants post-layout
  verification. Supports gf180mcuD and sky130 PDKs.
---

# IC Layout Verification (DRC/LVS/PEX)

## Prerequisites

```bash
export PDK_ROOT=/home/huda/.volare
export PDK=gf180mcuD
export PDKPATH=$PDK_ROOT/$PDK
```

Magic and netgen must be in PATH. PDK setup file is auto-resolved with symlink fallback.

## Quick Start

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(".")))
from core import run_drc, run_lvs, run_pex

# DRC
drc = run_drc("out.gds", cell_name="my_cell")
print(drc["summary"])   # "DRC: CLEAN" or "DRC: N ERRORS"

# LVS (auto-fixes port order, netgen permute 1 3 for D/S swapping)
lvs = run_lvs("out.gds", netlist_content=netlist, cell_name="my_cell")
print(lvs["summary"]["message"])  # "LVS OK" or "LVS MISMATCH"

# PEX
pex = run_pex("out.gds", cell_name="my_cell", mode=2)
print(pex["summary"])   # "PEX: OK (C-coupled)"
```

## Functions

### `extract_layout_netlist(gds_path, cell_name, workdir)`

Extracts a SPICE netlist from GDS using Magic (no-RC / LVS mode).

| Param | Default | Description |
|-------|---------|-------------|
| `gds_path` | required | Path to GDS file |
| `cell_name` | auto | Top cell name |
| `workdir` | temp dir | Working directory |

Returns: `{netlist_path, raw_ports, log}`

### `fix_port_order(extracted_path, correct_order, out_path)`

Rewrites the `.subckt` line of an extracted netlist to match the
schematic's port order.

| Param | Default | Description |
|-------|---------|-------------|
| `extracted_path` | required | Path to extracted .spice |
| `correct_order` | required | List of port names in correct order |
| `out_path` | same as input | Output path |

Returns: path to fixed netlist.

### `run_drc(gds_path, **kwargs)`

Runs DRC via `iic-drc.sh`.

| Param | Default | Description |
|-------|---------|-------------|
| `gds_path` | required | Path to GDS file |
| `cell_name` | auto | Top cell name |
| `engine` | `"magic"` | `"magic"`, `"klayout"`, or `"both"` |
| `workdir` | cwd | Working directory |
| `clean` | `False` | Remove previous result files |
| `timeout` | `600` | Max seconds |

Returns: `{clean, report_path, log, summary}` — `summary` is a
1-line string for AI parsing (e.g. `"DRC: CLEAN"`).

### `run_lvs(gds_path, **kwargs)`

Runs LVS via `iic-lvs.sh`. **Automatically** extracts the layout
netlist and reorders its ports to match the schematic before comparison.

| Param | Default | Description |
|-------|---------|-------------|
| `gds_path` | required | Path to GDS file |
| `netlist_path` | — | Path to schematic .spice file |
| `netlist_content` | — | SPICE netlist as a string |
| `cell_name` | auto | Top cell name |
| `workdir` | temp dir | Working directory |
| `auto_fix_ports` | `True` | Fix port order in extracted netlist |
| `timeout` | `600` | Max seconds |

Returns: `{match, report_path, log, summary}` — `summary` is a dict
with parsed LVS results for AI consumption:

```python
{
  "match": True|False,
  "device_mismatch": "8vs8",
  "net_mismatch": "9vs9",
  "port_swaps": [("vip", "vin")],
  "missing_devices": ["pfet_03v3:M2"],
  "message": "LVS OK"|"LVS MISMATCH"
}
```

### `run_pex(gds_path, **kwargs)`

Runs PEX via `iic-pex.sh`.

| Param | Default | Description |
|-------|---------|-------------|
| `gds_path` | required | Path to GDS file |
| `cell_name` | auto | Top cell name |
| `mode` | `2` | 1=C-decoupled, 2=C-coupled, 3=full-RC |
| `subcircuit` | `True` | Extract as .subckt block |
| `pex_name` | auto | Output subcircuit name |
| `workdir` | cwd | Working directory |
| `timeout` | `600` | Max seconds |

Returns: `{pex_path, mode, log, summary}`

## AI Agent Usage Pattern

```python
# 1. Generate layout
result = spice_to_gds(netlist, mode="analog", add_labels=True)
result.write_gds("out.gds")

# 2. Extract + verify in one call
lvs = run_lvs("out.gds", netlist_content=netlist, cell_name="opa_tuned3")
if lvs["match"]:
    pex = run_pex("out.gds", cell_name="opa_tuned3", mode=2)
    # Use pex["pex_path"] for post-layout simulation
else:
    s = lvs["summary"]
    if s["port_swaps"]:
        print(f"Ports swapped: {s['port_swaps']}")
    if s["missing_devices"]:
        print(f"Missing: {s['missing_devices']}")
```

## LVS Port-Order Auto-Fix

Magic extracts top-level ports in spatial order (left→right, bottom→top),
which rarely matches the schematic's `.subckt` order. The `run_lvs`
function now:

1. Calls `extract_layout_netlist()` to get the raw extracted netlist
2. Parses the schematic's `.subckt` line for the correct port order
3. Calls `fix_port_order()` to rewrite the extracted netlist
4. Feeds the fixed netlist to netgen for comparison

This eliminates `vin↔vip` and `vdd↔vss` swap errors automatically.

## ⚠️ PDK Body Constraint

**MOSFET body: pfet_03v3→VDD ONLY, nfet_03v3→VSS ONLY.** No other connections allowed.
