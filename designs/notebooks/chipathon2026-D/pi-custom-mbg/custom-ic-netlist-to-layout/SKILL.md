---
name: custom-ic-netlist-to-layout
description: >
  Converts a validated SPICE netlist to a DRC-clean GDSII layout. Provides
  full-automatic (spice_to_gds) and step-by-step manual (placement/power/routing)
  flows. Includes verified inverter routing example. Use after pre-sim passes.
---

# Custom IC: Netlist to GDS Layout

## ⚠️ No Hallucination

Run tools first, report results second. Never fabricate simulation results,
DRC/LVS status, or references. Only report actual tool output.

## Setup

```bash
cd /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D
source pi-custom-mbg/common/env.sh
```

## Quick Start (Full Auto)

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from core import spice_to_gds
netlist = open('/tmp/ota.spice').read()
result = spice_to_gds(netlist, mode='analog', add_labels=True)
result.write_gds('/tmp/ota.gds')
```

## Verified Complete Example: CMOS Inverter

This example is **tested end-to-end** — produces DRC-clean, LVS-matched layout with body connections.

### 1. Pre-layout Simulation

```python
import numpy as np, textwrap, subprocess, re, shutil, os
if not hasattr(np, 'float_'): np.float_ = np.float64

def run_cmd(cmd, timeout=300, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.returncode, r.stdout, r.stderr
    except: return -1, "", "failed"

pre_netlist = textwrap.dedent("""\
* Pre-layout inverter
.model NMOS nmos (VTO=0.7 KP=200e-6)
.model PMOS pmos (VTO=-0.7 KP=100e-6)
.subckt inv vdd vin vout vss
M1 vdd vin vout vdd PMOS W=1u L=0.5u
M2 vss vin vout vss NMOS W=1u L=0.5u
.ends inv
XINV vdd vin vout vss inv
VDD vdd 0 DC 1.8; VSS vss 0 DC 0
VIN vin 0 PULSE(0 1.8 0 100p 100p 20n 40n); CL vout 0 10fF
.control; tran 0.1n 80n; write pre_sim.raw vout vin; .endc; .end
""")
run_cmd(["ngspice","-b","pre_sim.spice"], cwd="/tmp/mbg_workspace")
```

### 2. Placement

```python
import glayout, gdsfactory as gf
from core.placement import manual_placement
from core.routing import set_pdk

pdk = glayout.gf180; set_pdk(pdk)

devices = [
    {"name": "MP", "model": "pfet_03v3", "width": 1, "length": 0.5, "x": 0, "y": 8},
    {"name": "MN", "model": "nfet_03v3", "width": 1, "length": 0.5, "x": 0, "y": 0},
]
top, pmap, _ = manual_placement(devices, pdk)

def gp(dev, term, direc):
    return pmap[dev][term][direc]["param"]
```

### 3. Power Strips

```python
from core.power import manual_power

strips = [
    {"net": "VDD", "layer": "met5", "y": 14, "x_start": -10, "x_end": 10, "width": 1.0, "via_x": 2.5},
    {"net": "VSS", "layer": "met5", "y": -7, "x_start": -10, "x_end": 10, "width": 1.0, "via_x": -2.5},
]
top, _ = manual_power(top, pdk, strips=strips, guardring=None)
```

### 4. Routing (CRITICAL — follow exactly)

**Routing rules:**
- met3 = horizontal, met4 = vertical, met5 = power strips
- Each met4 vertical needs UNIQUE x-track (≥ 2µm apart)
- Add `via_met3_met4` at every met3↔met4 transition
- Use `via1_layer: "met3"` / `via2_layer: "met3"` for VDD/VSS port vias
- **Must route body ties** (PMOS body→VDD, NMOS body→VSS)

```python
from core.routing import manual_route

# Get port centers
mp_src  = gp("MP","source","N").center
mp_drn  = gp("MP","drain","S").center
mp_gate = gp("MP","gate","W").center
mp_body = gp("MP","body","W").center  # PMOS body tie on met1
mn_src  = gp("MN","source","S").center
mn_drn  = gp("MN","drain","N").center
mn_gate = gp("MN","gate","W").center
mn_body = gp("MN","body","W").center  # NMOS body tie on met1

# Via-center y offsets (orientation-dependent)
vdd_m3_y = mp_src[1] - 0.25
vss_m3_y = mn_src[1] + 0.25

routes = [
    # VDD: MP.source → met3 → via → met4 → VDD strip
    {"net_name": "VDD", "port1": gp("MP","source","N"), "via1_layer": "met3",
     "segments": [(mp_src[0],vdd_m3_y,2.5,vdd_m3_y,"met3"),
                  (2.5,vdd_m3_y,2.5,vdd_m3_y,"via_met3_met4"),
                  (2.5,vdd_m3_y,2.5,14,"met4")]},
    # VSS: VSS strip → met4 → via → met3 → MN.source
    {"net_name": "VSS", "port2": gp("MN","source","S"), "via2_layer": "met3",
     "segments": [(-2.5,-7,-2.5,vss_m3_y,"met4"),
                  (-2.5,vss_m3_y,-2.5,vss_m3_y,"via_met4_met3"),
                  (-2.5,vss_m3_y,0,vss_m3_y,"met3")]},
    # vout: MP.drain → MN.drain (direct met4 vertical at x=0)
    {"net_name": "vout", "port1": gp("MP","drain","S"), "port2": gp("MN","drain","N"),
     "segments": [(mp_drn[0],mp_drn[1],mn_drn[0],mn_drn[1],"met4")]},
    # vin: MP.gate → met3 → via → met4 → via → met3 → MN.gate
    {"net_name": "vin", "port1": gp("MP","gate","W"), "port2": gp("MN","gate","W"),
     "via1_layer": "met3", "via2_layer": "met3",
     "segments": [(mp_gate[0],mp_gate[1],-1.5,mp_gate[1],"met3"),
                  (-1.5,mp_gate[1],-1.5,mp_gate[1],"via_met3_met4"),
                  (-1.5,mp_gate[1],-1.5,mn_gate[1],"met4"),
                  (-1.5,mn_gate[1],-1.5,mn_gate[1],"via_met4_met3"),
                  (-1.5,mn_gate[1],mn_gate[0],mn_gate[1],"met3")]},
    # MP body → VDD (body tie on met1 → met3 → VDD met4)
    {"net_name": "VDD", "port1": gp("MP","body","W"), "via1_layer": "met3",
     "segments": [(mp_body[0],mp_body[1],2.5,mp_body[1],"met3"),
                  (2.5,mp_body[1],2.5,mp_body[1],"via_met3_met4"),
                  (2.5,mp_body[1],2.5,14,"met4")]},
    # MN body → VSS (body tie on met1 → met3 → VSS met4)
    {"net_name": "VSS", "port2": gp("MN","body","W"), "via2_layer": "met3",
     "segments": [(-2.5,-7,-2.5,mn_body[1],"met4"),
                  (-2.5,mn_body[1],-2.5,mn_body[1],"via_met4_met3"),
                  (-2.5,mn_body[1],mn_body[0],mn_body[1],"met3")]},
]
top, _ = manual_route(top, routes)
```

### 5. Labels + GDS + SVG

```python
top._cell.name = "inv"
top.write_gds("/tmp/mbg_workspace/inv.gds")
import gdstk
gdstk.read_gds("/tmp/mbg_workspace/inv.gds").top_level()[0].write_svg("/tmp/mbg_workspace/inv.svg")
```

### 6. Verify

```python
from core.checks import run_drc, run_lvs, validate_gds

v = validate_gds("/tmp/mbg_workspace/inv.gds")
drc = run_drc("/tmp/mbg_workspace/inv.gds", cell_name="inv")
lvs = run_lvs("/tmp/mbg_workspace/inv.gds",
              netlist_content=open("/tmp/mbg_workspace/pre_sim.spice").read(),
              cell_name="inv", auto_fix_ports=True)
print(f"GDS: {v['valid']}  DRC: {drc['summary']}  LVS: {'MATCHED' if lvs['match'] else 'MISMATCHED'}")
```

### Met4 x-track Map

```
VDD  @ x= 2.5  (source + body → VDD strip)
vout @ x= 0    (MP.drain → MN.drain)
vin  @ x=-1.5  (MP.gate → MN.gate)
VSS  @ x=-2.5  (VSS strip → source + body)
```

## Common Routing Mistakes

| Mistake | Why Wrong | Fix |
|---------|-----------|-----|
| Missing `via1_layer: "met3"` | Port via creates met4 at x=0 → shorts with vout | Set for VDD/VSS port vias |
| No `via_met3_met4` | met3 and met4 traces don't connect | Add at every layer transition |
| Two met4 at same x | Short circuit | Assign unique x per net (≥2µm) |
| Redundant `via_met4_met5` | Power strip already has via → DRC error | Omit — power strip creates it |
| Start trace at port center y | Via is shifted ±0.25, trace misses it | Use `port_y ± 0.25` |
| Missing body route | Body tie left floating → reliability issue | Always route body_W to supply |
