---
name: custom-ic-verify
description: >
  Runs DRC, LVS, and PEX on a GDSII layout using Magic VLSI and netgen.
  Provides all-in-one verification script with structured results.
  Auto-fixes port order and flattens hierarchical netlists for LVS.
  Use after GDS generation.
---

# Custom IC: Physical Verification (DRC/LVS/PEX)

## Setup

```bash
cd /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D
source pi-custom-mbg/common/env.sh
```

## Quick Start (All-in-One)

```bash
python3 pi-custom-mbg/custom-ic-verify/scripts/run_all_checks.py \
  /tmp/ota.gds --netlist /tmp/ota.spice --cell ota_simple
```

This runs DRC → LVS → PEX and prints a summary.

## Individual Checks

### DRC

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from core.checks import run_drc
drc = run_drc("/tmp/ota.gds", cell_name="ota_simple", engine="magic", workdir="/tmp/drc")
print(f"DRC: {'CLEAN' if drc['clean'] else 'ERRORS'}")
if not drc['clean']:
    print(f"  {drc['error_count']} violations")
```

### LVS

```python
from core.checks import run_lvs
lvs = run_lvs("/tmp/ota.gds", netlist_content=open("/tmp/ota.spice").read(),
              cell_name="ota_simple", workdir="/tmp/lvs", auto_fix_ports=True)
print(f"LVS: {'MATCHED' if lvs['match'] else 'MISMATCHED'}")
if not lvs["match"]:
    print(f"  Port swaps: {lvs['summary']['port_swaps']}")
    print(f"  Missing: {lvs['summary']['missing_devices']}")
```

### PEX

```python
from core.checks import run_pex
pex = run_pex("/tmp/ota.gds", cell_name="ota_simple", mode=2, workdir="/tmp/pex")
print(f"PEX: {'OK' if pex['pex_path'] else 'FAILED'}")
```

### Parse Reports

```bash
python3 pi-custom-mbg/custom-ic-verify/scripts/parse_report.py /tmp/drc/ota_simple.magic.drc.rpt
python3 pi-custom-mbg/custom-ic-verify/scripts/parse_report.py /tmp/lvs/ota_simple.lvs.out
```

## LVS Auto-Fix

The LVS flow automatically:
1. Extracts layout SPICE via Magic
2. **Flattens** hierarchical netlist (X-elements → M-elements)
3. **Fixes port order** to match schematic
4. Runs netgen comparison

## Acceptance Criteria

| Check | Required | Command |
|-------|----------|---------|
| DRC | 0 violations | `run_drc()` |
| LVS | Circuits match uniquely | `run_lvs()` |
| PEX | Parasitics extracted | `run_pex()` |

## Files

- `scripts/run_all_checks.py` — DRC + LVS + PEX in one command
- `scripts/parse_report.py` — Human-readable report summary
- `setup/env.sh` — Environment configuration
