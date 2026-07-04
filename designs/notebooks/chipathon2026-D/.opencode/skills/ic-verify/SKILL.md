---
name: ic-verify
description: Runs DRC, LVS, and PEX verification for GDSII layouts using Magic/netgen. Use when the user asks to "run DRC", "check LVS", "extract parasitics", "verify layout", "run pex", or wants post-layout verification. Supports gf180mcuD and sky130 PDKs via iic-drc.sh, iic-lvs.sh, iic-pex.sh shell scripts.
---

# IC Layout Verification (DRC/LVS/PEX)

Run Design Rule Check (DRC), Layout-vs-Schematic (LVS), and Parasitic
Extraction (PEX) on GDSII layouts using Magic VLSI and netgen.

## Prerequisites

```bash
export PDK_ROOT=/home/huda/.volare
export PDK=gf180mcuD
export PDKPATH=/home/huda/.volare/gf180mcuD
export STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0
```

Magic and netgen must be installed and in PATH.

## Quick start

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(".")))
from core import run_drc, run_lvs, run_pex

# DRC (Magic engine)
drc = run_drc("out.gds", cell_name="comp_strongarm")
print("DRC clean:", drc["clean"])

# LVS (compare layout vs schematic)
lvs = run_lvs("out.gds", netlist_content=netlist, cell_name="comp_strongarm")
print("LVS match:", lvs["match"])

# PEX (mode 2 = C-coupled parasitics)
pex = run_pex("out.gds", cell_name="comp_strongarm", mode=2)
print("PEX output:", pex["pex_path"])
```

## DRC — `run_drc(gds_path, **kwargs)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gds_path` | required | Path to GDSII file |
| `cell_name` | auto | Top cell name |
| `engine` | `"magic"` | `"magic"` or `"klayout"` |
| `workdir` | cwd | Working directory for temp files |

Returns: `{clean: bool, report_path: str|None, log: str}`

The wrapper calls `iic-drc.sh -m <workdir> <gds> <cell>`.

## LVS — `run_lvs(gds_path, **kwargs)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gds_path` | required | Path to GDSII file |
| `netlist_path` | - | Path to .spice file (or pass `netlist_content`) |
| `cell_name` | auto | Top cell name |
| `workdir` | cwd | Working directory |

Returns: `{match: bool, report_path: str, log: str}`

The wrapper calls `iic-lvs.sh -s <spice> -l <gds> -c <cell> -w <workdir>`.

## PEX — `run_pex(gds_path, **kwargs)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `gds_path` | required | Path to GDSII file |
| `cell_name` | auto | Top cell name |
| `mode` | `2` | 1=C-decoupled, 2=C-coupled, 3=full-RC |
| `subcircuit` | True | Extract as .subckt block |
| `pex_name` | auto | Output name prefix |

Returns: `{pex_path: str|None, mode: str, log: str}`

The wrapper calls `iic-pex.sh -m <mode> -s -n <name> -w <workdir> <gds> <cell>`.

## Post-PEX simulation fix

PEX-extracted netlists often have floating pins. The simulation module
includes automatic fixes:
- `_fix_pex_pin_connections()` — shorts PEX pins to 1-hop capacitor neighbors
- `_fix_pex_supplies()` — shorts vdd/vss to well/substrate body nodes

These are applied automatically by `compare_comp_pre_post()` and
`compare_pre_post()`.

## Full flow (layout → verify → simulate)

```python
from core import spice_to_gds, run_drc, run_lvs, run_pex, compare_comp_pre_post

# Generate layout + run checks in one call
result = spice_to_gds(netlist, mode="analog", run_checks=True)

# Or step by step:
drc = run_drc("out.gds", cell_name="comp_strongarm")
if drc["clean"]:
    lvs = run_lvs("out.gds", netlist_content=netlist, cell_name="comp_strongarm")
    if lvs["match"]:
        pex = run_pex("out.gds", cell_name="comp_strongarm")
        cmp = compare_comp_pre_post(netlist, pex["pex_path"], "comp_strongarm")
```

## Script locations

- `iic-drc.sh` — DRC script (408 lines, supports Magic and KLayout)
- `iic-lvs.sh` — LVS script (417 lines, netgen-based)
- `iic-pex.sh` — PEX script (306 lines, Magic parasitic extraction)
