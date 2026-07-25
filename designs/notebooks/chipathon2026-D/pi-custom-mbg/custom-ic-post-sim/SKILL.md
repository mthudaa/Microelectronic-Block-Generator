---
name: custom-ic-post-sim
description: >
  Runs post-layout simulation using PEX-extracted parasitic netlist and compares
  results against pre-layout (ideal) simulation. Computes deltas for key metrics.
  Provides comparison script and plot generation. Use after verification passes.
---

# Custom IC: Post-Layout Simulation

## Setup

```bash
cd /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D
source pi-custom-mbg/common/env.sh

# Requires PEX output from verification step
ls /tmp/pex/*.pex.spice 2>/dev/null || echo "Run custom-ic-verify first"
```

## Quick Start

```bash
python3 pi-custom-mbg/custom-ic-post-sim/scripts/compare_sim.py \
  /tmp/ota.spice            `# pre-layout schematic` \
  /tmp/pex/ota.pex.spice    `# post-layout PEX netlist` \
  --cell ota_simple         `# cell name`
```

## From Python

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from core.simulation import run_spice
from core.checks import run_pex
import numpy as np

# Pre-layout
pre = run_spice(open("/tmp/ota.spice").read())

# Post-layout
pex = run_pex("/tmp/ota.gds", cell_name="ota_simple", mode=2)
if pex["pex_path"]:
    pex_text = open(pex["pex_path"]).read()
    post_netlist = open("/tmp/ota.spice").read() + "\n" + pex_text
    post = run_spice(post_netlist)
```

## Compare Results

```python
from scripts.analyze_results import parse_raw, analyze_transient

pre_data = parse_raw("/tmp/pre.raw")
post_data = parse_raw("/tmp/post.raw")
pre_m = analyze_transient(pre_data)
post_m = analyze_transient(post_data)

for k in ["voh", "vol", "swing_mv", "tphl_ns"]:
    p = pre_m.get(k, 0)
    q = post_m.get(k, 0)
    d = (q - p) / p * 100 if p else 0
    print(f"{k:12s}: pre={p:.3f} post={q:.3f} Δ={d:+.1f}%")
```

## Acceptance Criteria

| Parameter | Max Degradation | Action |
|-----------|----------------|--------|
| VOH | -5% | Reduce trace resistance |
| tPHL | +20% | Shorten critical paths |
| Swing | -10% | Reduce parasitic caps |
| DC Gain | -10% | Use thicker metals |

If degradation exceeds limits, optimize routing and re-run layout.

## Files

- `scripts/compare_sim.py` — Pre vs post comparison script
- `scripts/plot_results.py` — Simple ASCII plot of results
