---
name: custom-ic-spec-to-netlist
description: >
  Converts analog IC design specifications into a validated SPICE subcircuit
  netlist via LLM (DeepSeek). Provides spec template, netlist generation script,
  and validation tool. Use at the start of any custom IC design project.
---

# Custom IC: Specification to SPICE Netlist

## Setup

```bash
cd /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D
source pi-custom-mbg/common/env.sh

# Required for LLM generation
export DEEPSEEK_API_KEY=sk-your-key-here
```

## Quick Start

### Option A: Auto-generate from spec prompt

```bash
python3 pi-custom-mbg/custom-ic-spec-to-netlist/scripts/generate_netlist.py \
  --prompt "Design a 5-transistor OTA: DC gain > 60dB, GBW > 5MHz, power < 0.5mW" \
  --output /tmp/ota.spice
```

### Option B: Write manually using template

```bash
cp pi-custom-mbg/custom-ic-spec-to-netlist/templates/spec_template.yaml /tmp/my_spec.yaml
# Edit /tmp/my_spec.yaml with your specs, then:
python3 pi-custom-mbg/custom-ic-spec-to-netlist/scripts/generate_netlist.py \
  --prompt-file /tmp/my_spec.yaml --output /tmp/ota.spice
```

### Validate the generated netlist

```bash
python3 pi-custom-mbg/custom-ic-spec-to-netlist/scripts/validate_netlist.py /tmp/ota.spice
```

## Manual Netlist Format

```spice
.include /home/huda/.volare/gf180mcuD/libs.tech/ngspice/design.ngspice
.lib /home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice typical

.subckt ota_simple vin_p vin_n vout vbias vdd vss
XM1 n1 vin_p ntail vss nfet_03v3 W=10u L=1u nf=1
XM2 vout vin_n ntail vss nfet_03v3 W=10u L=1u nf=1
XM3 n1 n1 vdd vdd pfet_03v3 W=20u L=1u nf=1
XM4 vout n1 vdd vdd pfet_03v3 W=20u L=1u nf=1
XM5 ntail vbias vss vss nfet_03v3 W=15u L=1u nf=1
.ends ota_simple
```

**Rules:**
- Use `XM<name>` for MOSFET instances (glayout convention)
- Models: `nfet_03v3`, `pfet_03v3`
- PMOS body → vdd, NMOS body → vss
- Include PDK `.lib` and `.include` lines

## From Python

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from core.pipeline import generate_netlist_from_prompt
from core.spice_parser import parse_netlist_with_pdk

netlist = generate_netlist_from_prompt("Design an inverter with Wp=1u Wn=0.5u")
parsed = parse_netlist_with_pdk(netlist)
print(f"OK: {len(parsed['components'])} components")
```

## Output

Validated netlist saved to file. Pass to `custom-ic-pre-sim` for simulation.

## Files

- `scripts/generate_netlist.py` — LLM-based netlist generation
- `scripts/validate_netlist.py` — SPICE syntax validation
- `templates/spec_template.yaml` — Specification template
