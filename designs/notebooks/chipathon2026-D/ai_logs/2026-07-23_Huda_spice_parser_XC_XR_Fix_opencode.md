# AI Log: spice_parser.py — XC/XR Parameter Extraction Fix

**Date**: 2026-07-23
**Team Member**: Huda
**Module**: `core/spice_parser.py`
**LLM Provider**: opencode (big-pickle)
**Branch**: `update/spice-parser` → merged to `main`
**Commit**: `36e5ffa`
**Files Changed**: `core/spice_parser.py`, `core/__init__.py`

---

## Context & Instructions

Huda had already modified `spice_parser.py` to add support for MIM Capacitor (XC) and
Resistor (XR) devices. The parsing blocks were working, but the parameters inside XC
and XR were not appearing in the returned result. Huda asked the LLM to find the bug.

---

## User Prompt

> "wait, I already modified spice_parser.py in the parse_netlist_with_pdk function.
> The paramaters inside XC and XR aren't define in the result/return. find the problem
> why that happen!"

---

## LLM Analysis

The LLM read the file and traced the code path, finding the bug on lines 147-150:

**Root Cause**: Two variables were defined for device type detection:

- `device_type = device_name[0].upper()` → For `XC1`, this is `'X'`
- `device_type_linear_dev = device_name.upper()[:2]` → For `XC1`, this is `'XC'`

The parsing blocks (lines 73, 97) correctly used `device_type_linear_dev` to detect
XC and XR devices. However, the parameter extraction block (lines 147-150) checked
`device_type` instead:

```python
# BEFORE (broken)
elif device_type == 'XC':    # 'X' != 'XC' — never true
    param_dict = { "c_width": ..., "c_length": ... }
elif device_type == 'XR':    # 'X' != 'XR' — never true
    param_dict = { "r_width": ..., "r_length": ... }
```

This caused XC/XR devices to fall through to the `else` block, which extracted
`w`, `l`, `m` parameters instead of `c_width`, `c_length` / `r_width`, `r_length`.

---

## User Prompt (Follow-up)

> "sure, fix that issue"

---

## LLM Response (Fix Applied)

Changed lines 147 and 149 to use `device_type_linear_dev`:

```python
# AFTER (fixed)
elif device_type_linear_dev == 'XC':
    param_dict = { "c_width": params['c_width'], "c_length": params['c_length'] }
elif device_type_linear_dev == 'XR':
    param_dict = { "r_width": params['r_width'], "r_length": params['r_length'] }
```

---

## Additional Context

### Changes in Same Commit (Huda's prior work)

- Removed unused `import json`
- Added `device_type_linear_dev` variable for 2-character device type detection
- Extended `params` dict with `c_width`, `c_length`, `r_width`, `r_length` defaults
- Added XC (MIM Capacitor) parsing block
- Added XR (Resistor) parsing block
- Added `parse_netlist_with_pdk` export in `core/__init__.py`

### Code Review Notes (Identified But Not Fixed)

During analysis, the LLM identified additional issues in `spice_parser.py`:

| # | Line(s) | Severity | Description |
|---|---------|----------|-------------|
| 1 | 146 | Medium | `parse_micrometer` uses `replace('-', '0')` which corrupts strings with hyphens |
| 2 | 180 | Medium | PMOS detection (`'p' in model[:2]`) fails for non-standard model names |
| 3 | 107 | High | IndexError on malformed device line (single-part) |
| 4 | 206 | Critical | `d in pmos_row` always False — NMOS connectivity ordering is dead logic |
| 5 | 192-200 | Low | Magic numbers in cell sizing undocumented |
| 6 | 276 | Medium | `port.Port` class used as sentinel instead of `None` |
| 7 | 155-156 | Low | `vdd_counts`/`vss_counts` computed but never used |

---

## Verification

The fix was verified by tracing the code path for a device like `XC1`:

1. `device_type = 'X'` (line 52)
2. `device_type_linear_dev = 'XC'` (line 53)
3. XC parsing block executes correctly (line 73) — nodes and model extracted
4. Parameter extraction now hits `device_type_linear_dev == 'XC'` (line 147) — ✅
5. `param_dict = { "c_width": ..., "c_length": ... }` returned correctly
