---
name: custom-ic-pre-sim
description: >
  Runs pre-layout SPICE simulation to verify a subcircuit netlist meets design
  specifications before committing to layout. Provides simulation runner,
  result analyzer, and testbench templates. Use after creating a netlist.
---

# Custom IC: Pre-Layout Simulation

## Setup

```bash
cd /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D
source pi-custom-mbg/common/env.sh
```

## Quick Start

### Run transient simulation

```bash
# Generate testbench and simulate
python3 pi-custom-mbg/custom-ic-pre-sim/scripts/run_simulation.py /tmp/ota.spice \
  --type tran --output /tmp/sim.raw
```

### Analyze results

```bash
python3 pi-custom-mbg/custom-ic-pre-sim/scripts/analyze_results.py /tmp/sim.raw --type tran
```

Example output:
```
============================================================
  Simulation Results
============================================================
  Signals: ['time', 'v(vout)', 'v(vin)']
  VOH = 1.847 V
  VOL = -0.038 V
  Swing = 1885 mV
  tPHL = 0.130 ns
  tPLH = 0.250 ns
```

### AC analysis (for amplifiers)

```bash
python3 pi-custom-mbg/custom-ic-pre-sim/scripts/run_simulation.py /tmp/ota.spice \
  --type ac --output /tmp/ac.raw
python3 pi-custom-mbg/custom-ic-pre-sim/scripts/analyze_results.py /tmp/ac.raw --type ac
```

## From Python

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from core.simulation import run_spice, raw_to_csv

netlist = open("/tmp/ota.spice").read()
result = run_spice(netlist, timeout=120)

if result["raw_path"]:
    from scripts.analyze_results import parse_raw, analyze_transient
    data = parse_raw(result["raw_path"])
    metrics = analyze_transient(data)
    print(f"VOH={metrics['voh']:.3f}V VOL={metrics['vol']:.3f}V")
```

## Testbench Templates

- Transient: `templates/tb_tran.spice`
- AC: `templates/tb_ac.spice`

## Passing Criteria

| Metric | Inverter | OTA | Comparator |
|--------|----------|-----|------------|
| VOH | ≥ 1.7V | — | ≥ 1.7V |
| VOL | ≤ 0.1V | — | ≤ 0.1V |
| DC Gain | — | ≥ 60dB | — |
| GBW | — | ≥ 1MHz | — |
| Delay | — | — | ≤ 10ns |

If all specs pass, proceed to `custom-ic-netlist-to-layout`.

## Files

- `scripts/run_simulation.py` — Testbench builder + ngspice runner
- `scripts/analyze_results.py` — Result parser + metric extractor
