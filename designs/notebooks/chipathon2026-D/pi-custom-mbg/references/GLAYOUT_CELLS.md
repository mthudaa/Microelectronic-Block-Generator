# gLayout Cell Library Reference

Available pre-built cells from [gLayout](https://github.com/ReaLLMASIC/gLayout/tree/main/src/glayout/cells).

## Elementary Cells

| Cell | File | Description |
|------|------|-------------|
| **current_mirror** | `elementary/current_mirror/` | Simple current mirror (NMOS/PMOS) |
| **diff_pair** | `elementary/diff_pair/` | Differential pair with tail |
| **FVF** | `elementary/FVF/` | Flipped Voltage Follower |
| **transmission_gate** | `elementary/transmission_gate/` | CMOS transmission gate |

## Composite Cells

| Cell | File | Description |
|------|------|-------------|
| **diffpair_cmirror_bias** | `composite/diffpair_cmirror_bias/` | Diff pair + current mirror + bias |
| **differential_to_single_ended_converter** | `composite/differential_to_single_ended_converter/` | Diff to single-ended converter |
| **fvf_based_ota** | `composite/fvf_based_ota/` | FVF-based OTA (includes n_block, p_block, ota, cmirror, ota_perf_eval) |
| **low_voltage_cmirror** | `composite/low_voltage_cmirror/` | Low-voltage cascode current mirror |
| **opamp** | `composite/opamp/` | Opamp cells (diff_pair_stackedcmirror, twostage, row_camplifier) |
| **stacked_current_mirror** | `composite/stacked_current_mirror/` | Stacked cascode current mirror |

## How to Use

### Simple Import (if cells are in Python path)

```python
from glayout.cells.elementary.diff_pair import diff_pair
from glayout.cells.elementary.current_mirror import current_mirror
from glayout.cells.composite.opamp import opamp_twostage
```

### Via gLayout Primitives (always available)

If specific cells aren't importable, use the building blocks:

```python
from glayout import nmos, pmos, multiplier, via_stack, tapring
from glayout.primitives import *
```

### Cell Composition Pattern

Most cells follow this pattern:
```python
cell = pmos(pdk, width=W, length=L, fingers=NF, multipliers=M,
            with_substrate_tap=False, with_tie=True, with_dummy=False)
```

## Using Cells in MBG Flow

When designing a circuit, check if a pre-built cell exists:

1. Check the table above
2. Try importing from `glayout.cells.*`
3. If not available, build from `glayout.nmos`/`glayout.pmos` primitives
4. Save as a new cell for future reuse

## Cell Location

```
https://github.com/ReaLLMASIC/gLayout/tree/main/src/glayout/cells
```
