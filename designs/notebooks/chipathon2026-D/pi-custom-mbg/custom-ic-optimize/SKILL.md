---
name: custom-ic-optimize
description: >
  SPICE-in-the-loop optimization: iterates simulation → feedback → LLM revision
  until specifications are met. Provides optimizer script, spec checker, and
  default specs configuration. Use when pre/post-layout simulation fails specs.
---

# Custom IC: SPICE-in-the-Loop Optimization

## Setup

```bash
cd /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D
source pi-custom-mbg/common/env.sh
export DEEPSEEK_API_KEY=sk-your-key-here
```

## Quick Start

```bash
# Edit specs first
cp pi-custom-mbg/custom-ic-optimize/config/default_specs.json /tmp/my_specs.json
# Edit /tmp/my_specs.json with your targets

# Run optimization
python3 pi-custom-mbg/custom-ic-optimize/scripts/optimize_loop.py \
  "Design a 5T OTA with gain > 60dB" \
  --specs /tmp/my_specs.json \
  --max-iterations 5
```

## From Python

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from core.pipeline import generate_netlist_from_prompt
from core.simulation import run_spice
from core import spice_to_gds

specs = {"dc_gain_db": 60, "gbw_mhz": 5}
max_iter = 5

for i in range(max_iter):
    netlist = generate_netlist_from_prompt(
        "Design OTA with gain > 60dB",
        llm_feedback=feedback if i > 0 else None
    )
    result = run_spice(netlist)
    metrics = extract_metrics(result)
    
    if metrics["dc_gain_db"] >= specs["dc_gain_db"]:
        layout = spice_to_gds(netlist, mode="analog")
        layout.write_gds(f"/tmp/ota_optimized.gds")
        break
    
    feedback = f"DC gain was {metrics['dc_gain_db']:.1f}dB, need ≥ {specs['dc_gain_db']}dB"
```

## Convergence Criteria

- All specs met (within 5% tolerance)
- Max iterations reached (default: 5)
- No improvement over 2 consecutive iterations

## Files

- `scripts/optimize_loop.py` — Main optimization loop
- `scripts/spec_checker.py` — Spec validation
- `config/default_specs.json` — Default specification targets
