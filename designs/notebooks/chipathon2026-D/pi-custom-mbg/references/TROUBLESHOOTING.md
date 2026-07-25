# MBG Troubleshooting Guide

## DRC Issues

### "Metal3 spacing < 0.28um"
- **Cause**: Two met3 traces too close (gap < 0.28µm)
- **Fix**: Increase y-separation between horizontal met3 segments. Ensure VDD port via met3 and vout met3 have ≥ 0.28µm gap
- **Rule of thumb**: Keep met3 segments on same x-range separated by ≥ 0.5µm vertically

### "Metal2 spacing < 0.28um" / "Metal2 width < 0.28um"
- **Cause**: met2_pin rectangles overlapping or too small
- **Fix**: Remove met2_pin rectangles — Magic only needs the label on met2_label layer
- **Rule**: Don't add extra met2 polygons at port locations; the device already provides met2

### "Via4 spacing < 0.24um"
- **Cause**: Two via stacks too close at VDD/VSS strips
- **Fix**: Don't add redundant `via_met4_met5` segments in routes — `manual_power` already creates vias at the strip
- **Acceptable**: This is often a false positive from power strip via stacks

## LVS Issues

### "Ports X and Y are electrically shorted"
- **Cause**: Metal traces from different nets are shorted
- **Check**: Run `python3 -c "import gdstk; lib = gdstk.read_gds('file.gds'); top = lib.top_level()[0]"` and inspect met2/met3/met4 polygons
- **Fix**: Ensure met4 verticals at same x have ≥ 0.5µm separation or different y-ranges

### "Circuits match uniquely" fails after port fix
- **Cause**: Extracted netlist uses X-elements but schematic uses M-elements
- **Fix**: Call `_flatten_netlist()` to replace X-element wrappers with flat M-elements

### "Unable to permute model nfet_03v3 pins 1, 3"
- **Cause**: Netgen can't find pin definitions for the model
- **Fix**: This is normal for placeholder models — the permute still works if the model is in the cells list

### Port order mismatch
- **Cause**: Magic extracts ports in spatial order (left→right, bottom→top)
- **Fix**: Set `auto_fix_ports=True` in `run_lvs()` — this rewrites the .subckt line

## Simulation Issues

### ngspice "No such parameter" / "Undefined parameter"
- **Cause**: Missing `fnoicor`/`fnostic` parameter definitions
- **Fix**: Include `design.ngspice` BEFORE `sm141064.ngspice`:
  ```
  .include /path/to/design.ngspice
  .lib /path/to/sm141064.ngspice typical
  ```

### ngspice "incomplete or empty netlist"
- **Cause**: No `.tran`, `.ac`, `.dc`, or `.control` block
- **Fix**: Add simulation commands

### PEX "No such file"
- **Cause**: `iic-pex.sh` not found or PDK not set
- **Fix**: Check `PDK_ROOT`, `PDK`, `PDKPATH` environment variables

## Placement Issues

### Device not found in GDS
- **Cause**: Cell name mismatch between placement and extraction
- **Fix**: Set `top._cell.name = "your_cell_name"` before `write_gds()`

### Port map empty
- **Cause**: Device generation failed (wrong W/L, missing PDK)
- **Fix**: Check PDK activation: `pdk.activate()` or use `glayout.gf180` directly

## Routing Issues

### Trace disconnected from port via
- **Cause**: Via offset places via at shifted position, trace starts at port center
- **Fix**: Start trace at via-center y (port_y - 0.25 for orientation 90, port_y + 0.25 for 270)

### Missing via at layer transition
- **Cause**: met3→met4 transition without `via_met3_met4` segment
- **Fix**: Add explicit via segment at every layer transition point

### Auto_router destroys power strips
- **Cause**: Known bug — `auto_router` removes all polygons above baseline
- **Fix**: Add power strips AFTER routing, or use `manual_route` instead

## Environment Issues

### "ModuleNotFoundError: No module named 'glayout'"
```bash
pip install glayout@git+https://github.com/ReaLLMASIC/gLayout.git --no-deps
```

### "magic: command not found"
```bash
export PATH=/foss/tools/magic/bin:$PATH
```

### "netgen: command not found"
```bash
export PATH=/foss/tools/netgen/bin:$PATH
```

### NumPy errors on Python 3.14+
```python
import numpy as np
if not hasattr(np, 'float_'):
    np.float_ = np.float64
```
This polyfill is already in `core/__init__.py`.
