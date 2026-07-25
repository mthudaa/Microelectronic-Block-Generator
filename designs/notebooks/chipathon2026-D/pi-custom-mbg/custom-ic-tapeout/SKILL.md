---
name: custom-ic-tapeout
description: >
  Final sign-off and tapeout packaging. Runs complete verification checklist,
  generates all tapeout deliverables (GDS, netlist, reports, simulation data),
  and produces a summary report. Use as the final step before fabrication.
---

# Custom IC: Tapeout & Sign-off

## Setup

```bash
cd /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D
source pi-custom-mbg/common/env.sh
```

## Quick Start

```bash
python3 pi-custom-mbg/custom-ic-tapeout/scripts/package_tapeout.py \
  /tmp/ota_final.gds        `# GDS layout` \
  --netlist /tmp/ota.spice   `# SPICE schematic` \
  --cell ota_simple          `# Cell name` \
  --output /tmp/tapeout      `# Output directory`
```

## Run Final Checklist

```bash
python3 pi-custom-mbg/custom-ic-tapeout/scripts/final_checklist.py \
  /tmp/ota_final.gds --netlist /tmp/ota.spice --cell ota_simple
```

Example output:
```
  ✅ GDS Validation: OK (3 cells, 45kB)
  ✅ DRC: CLEAN
  ✅ LVS: MATCHED (Circuits match uniquely)
  ✅ PEX: OK (C-coupled)
  ❌ Post-layout sim: Degradation 22% > 20% threshold
```

## Tapeout Deliverables

```
tapeout/
├── gds/
│   └── ota_simple.gds
├── netlist/
│   └── ota_simple.spice
├── reports/
│   ├── drc.rpt
│   ├── lvs.out
│   └── pex.spice
├── simulation/
│   ├── pre_layout/
│   └── post_layout/
└── summary.md
```

## Acceptance Criteria

| Check | Required | How |
|-------|----------|-----|
| DRC | 0 violations | `run_drc()` |
| LVS | Circuits match uniquely | `run_lvs()` |
| PEX | Parasitics extracted | `run_pex()` |
| Pre-sim | All specs met | `run_spice()` |
| Post-sim | Degradation < 20% | Compare pre vs post |
| GDS | Valid file, correct cell | `validate_gds()` |

## Files

- `scripts/final_checklist.py` — Run all final checks
- `scripts/package_tapeout.py` — Package deliverables
- `templates/summary_template.md` — Report template
