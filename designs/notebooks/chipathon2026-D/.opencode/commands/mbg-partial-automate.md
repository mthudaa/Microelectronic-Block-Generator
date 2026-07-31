# /mbg-partial-automate — D08 Semi-Automatic Analog IC Flow

**PDK**: GF180MCU | 3.3V | nfet_03v3/pfet_03v3 | W<10µm L<10µm
**BODY**: pfet_03v3→VDD ONLY | nfet_03v3→VSS ONLY
**LAYOUT**: `spice_to_gds_with_checks(netlist)` — NEVER manual step-by-step

## Pipeline (user confirms each step)
```
1.INPUT → 2.RESEARCH → 3.NETLIST → 4.PRE-SIM → 5.LAYOUT → 6.DRC/LVS → 7.PEX → 8.TAPEOUT
```

## TAPEOUT GATE
| Gate | Requirement |
|------|-------------|
| DRC | 0 violations |
| LVS | Match |
| PEX | Done |
| Post-layout | ≤10% deviation |

> **⚠️ Sim plots required:** Save AC/DC/TRAN plots as `.png` in workdir.

## Core Tools Reference (from ~/.pi/core/)

| Tool | Import | Usage |
|------|--------|-------|
| **Pipeline (full)** | `from core.pipeline import spice_to_gds_with_checks` | `r = spice_to_gds_with_checks(netlist)` |
| **Pipeline (layout only)** | `from core.pipeline import spice_to_gds` | `c = spice_to_gds(netlist, run_checks=False)` |
| **SPICE Parser** | `from core.spice_parser import parse_netlist_with_pdk` | `config = parse_netlist_with_pdk(netlist)` |
| **DRC** | `from core.checks import run_drc` | `run_drc(gds_path, cell_name)` |
| **LVS** | `from core.checks import run_lvs` | `run_lvs(gds, netlist, cell_name)` |
| **PEX** | `from core.checks import run_pex` | `run_pex(gds_path, cell_name)` |
| **Simulation** | `from core.simulation import run_spice` | `run_spice(spice_path)` |

### Quick Start
```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.pipeline import spice_to_gds_with_checks
r = spice_to_gds_with_checks(netlist)
```
