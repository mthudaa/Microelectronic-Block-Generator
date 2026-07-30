# /mbg-full-automate — D08 Full Automatic Analog IC Flow

**PDK**: GF180MCU | 3.3V | nfet_03v3/pfet_03v3 | W<10µm L<10µm
**LAYOUT**: `spice_to_gds_with_checks(netlist)` — NEVER manual step-by-step
**IOPIN**: VDD→vdd | VSS→vss | Analog→iopin(T_EN=0,T_IE=1) | Digital in→iopin(0,1) | Digital out→iopin(1,0)

## Pipeline
```
1.SELECT → 2.PARSE → 3.GENERATE → 4.SIMULATE → 5.CHECK → 6.LAYOUT → 7.DRC/LVS/PEX → 8.POST-LAYOUT → 9.REPORT
```

## TAPEOUT GATE
| Gate | Requirement |
|------|-------------|
| DRC | Magic DRC < 100 errors|
| LVS | Netgen match |
| PEX | Extraction done |
| Post-layout | ≤10% deviation from pre-layout |

## Anti-Hallucination
- UNSURE: [param] + reason
- Never fabricate sim results
- Every claim has proof
- No DRC/LVS/PEX claim without evidence

## Core Tools Reference (from ~/.pi/core/)

| Tool | Import | Usage |
|------|--------|-------|
| **Pipeline** | `from core.pipeline import spice_to_gds_with_checks` | `r = spice_to_gds_with_checks(netlist)` |
| **Pipeline (no checks)** | `from core.pipeline import spice_to_gds` | `c = spice_to_gds(netlist, run_checks=False)` |
| **SPICE Parser** | `from core.spice_parser import parse_netlist_with_pdk` | `config = parse_netlist_with_pdk(netlist)` |
| **DRC** | `from core.checks import run_drc` | `result = run_drc(gds_path, cell_name)` |
| **LVS** | `from core.checks import run_lvs` | `result = run_lvs(gds_path, netlist_path, cell_name)` |
| **PEX** | `from core.checks import run_pex` | `result = run_pex(gds_path, cell_name)` |
| **Simulation** | `from core.simulation import run_spice` | `result = run_spice(spice_path)` |
| **Experiment** | `from core.experiment_manifest import ExperimentManifest` | `m = ExperimentManifest(experiment_id="...")` |

### Quick Start
```python
import sys, os
# Add the pi-custom-mbg directory to PYTHONPATH
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from core.pipeline import spice_to_gds_with_checks

netlist = """..."""
r = spice_to_gds_with_checks(netlist)
# r["outdir"], r["gds_path"], r["svg_path"], r["drc"], r["lvs"], r["pex"], r["all_pass"]
```
