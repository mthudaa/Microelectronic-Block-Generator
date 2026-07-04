---
name: spice-sim
description: Runs ngspice simulations for analog circuits — OTA AC analysis (DC gain, GBW, phase margin, f_3dB), clocked comparator transient (delay, offset), and PVT corners (7 corners: TT/SS/FF/SF/FS at -40C/25C/125C). Use when user asks to simulate, verify, measure performance, "run simulation", "check gain/phase/delay/offset", "PVT corners", or compare pre/post-layout. Requires ngspice installed and PDK_ROOT/PDK env vars set.
---

# SPICE Simulation (ngspice)

Run ngspice simulations for analog circuit blocks — OTA AC analysis and
clocked comparator transient with PVT corner sweep.

## Quick start

```python
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(".")))
from core import run_comparator_tran, run_comparator_pvt

netlist = open("my_circuit.spice").read()

# Delay measurement
res = run_comparator_tran(netlist, "comp_strongarm",
                          vdd=1.8, vcm=0.9,
                          clk_period=10e-9, tstop=30e-9)
print(f"tdelay = {res['tdelay']}")

# Offset measurement (use ramp method)
off = run_comparator_tran(netlist, "comp_strongarm",
                          vdd=1.8, vcm=0.9,
                          clk_period=20e-9, tstop=100e-9,
                          measure_offset=True)
print(f"vos = {off['vos']}")

# PVT corners (7 corners)
pvt = run_comparator_pvt(netlist, "comp_strongarm",
                          vdd=1.8, vcm=0.9,
                          clk_period=10e-9, tstop=30e-9)
print(pvt["summary"])
```

## Comparator simulation API

### `run_comparator_tran(netlist, cell_name, **kwargs)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vdd` | 1.8 | Supply voltage (V) |
| `vcm` | 0.9 | Common-mode input voltage |
| `clk_period` | 20e-9 | Clock period (s) |
| `tstop` | 50e-9 | Simulation stop time (s) |
| `measure_offset` | False | If True, use slow ramp to measure Vos |
| `corner` | "typical" | Model corner: `typical`, `ss`, `ff`, `sf`, `fs` |
| `temperature` | None | Celsius temperature for `.temp` directive |

Returns: `{vout_high, vout_low, tdelay, vos, tran_data, log, corner, temperature}`

### `run_comparator_pvt(netlist, cell_name, **kwargs)`

Runs 7 PVT corners:
| Corner | Temperature | VDD |
|--------|-------------|-----|
| TT | 25°C | 1.80V |
| SS | 125°C | 1.62V |
| SS | -40°C | 1.62V |
| FF | -40°C | 1.98V |
| FF | 125°C | 1.98V |
| SF | 25°C | 1.80V |
| FS | 25°C | 1.80V |

Returns: `{corners: [...], offset: {...}, summary: {tdelay_typ, tdelay_min, tdelay_max, vos}}`

### `run_ota_ac(netlist, cell_name, **kwargs)`

| Parameter | Default | Description |
|-----------|---------|-------------|
| `vdd` | 1.8 | Supply voltage |
| `vcm` | 0.9 | Common-mode input voltage |
| `vbias` | 0.55 | Bias voltage for tail current |
| `cload` | 1e-12 | Load capacitance |
| `fstart` | 1 | AC sweep start frequency (Hz) |
| `fstop` | 1e9 | AC sweep stop frequency (Hz) |

Returns: `{dc_gain_db, gbw_hz, phase_margin_deg, f_3db_hz, ac_data, log}`

## Pre/Post-layout comparison

```python
from core import compare_comp_pre_post

cmp = compare_comp_pre_post(schematic_netlist, pex_path, "comp_strongarm",
                             vdd=1.8, vcm=0.9)
print(f"PRE tdelay: {cmp['pre']['tdelay']}")
print(f"POST tdelay: {cmp['post']['tdelay']}")
print(f"Delta: {cmp['delta']}")
```

## Model corners (gf180mcuD)

| Corner key | `.LIB` section | Description |
|-----------|---------------|-------------|
| `typical` | `.LIB typical` | Nominal (TT) |
| `ss` | `.LIB ss` | Slow NMOS, Slow PMOS |
| `ff` | `.LIB ff` | Fast NMOS, Fast PMOS |
| `sf` | `.LIB sf` | Slow NMOS, Fast PMOS |
| `fs` | `.LIB fs` | Fast NMOS, Slow PMOS |

## Prerequisites

- **ngspice** installed (`ngspice -v`)
- **PDK_ROOT** and **PDK** env vars set
- Model file at `$PDK_ROOT/$PDK/libs.tech/ngspice/sm141064.ngspice`

## LLM feedback for finetuning

Simulation failures automatically generate structured feedback for LLM-based
circuit refinement. The log includes the SPICE testbench context so the LLM
understands exactly which nodes/params caused the failure.
