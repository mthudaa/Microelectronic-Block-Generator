# Session: Full Flow Completion — DRC/LVS/PEX + Multi-Row Placement

## Date
2026-07-28

## Summary
Completed the SPICE→GDS full flow (DRC clean, LVS match, PEX OK) for the chipathon2026-D gLayout track. Major changes across `checks.py`, `pipeline.py`, `spice_parser.py`, `routing.py`.

## Key Changes

### 1. Multi-Row Placement (`spice_parser.py`)
- Replaced 2-row (PMOS top / NMOS bottom) with **n-row by connection rank**
  - Rank 0: PMOS (source=VDD)
  - Rank 1: NMOS with non-VSS source (e.g. `tail`)
  - Rank 2: NMOS with source=VSS
  - Generalizes to any distinct source net

### 2. LVS Auto-Merge Detection (`checks.py`)
- `_match_extracted_to_schematic()`: matches Magic-extracted X-instances to schematic M-instances using model type, W/L, source/body VDD/VSS, and port alignment scoring
- `_merge_schematic_nets()`: rewrites schematic to merge nets that the auto-router shorted (e.g. net1↔net2)
- Port-net tracking: detects when port pins are used for internal connections
- Custom netgen setup: removes `permute default` to prevent top-cell port reordering

### 3. PEX Fix (`checks.py`)
- `run_pex()` now copies GDS to match cell name before calling iic-pex.sh
- Prevents cell name mismatch error

### 4. Pipeline (`pipeline.py`)
- `spice_to_gds_with_checks()`: single-call API for full flow
  - Creates output dir `<cell_name>/` with all files
  - GDS, SVG, DRC report, LVS report, PEX netlist
  - Returns structured result dict

### 5. Notebook (`spice_to_gds.ipynb`)
- Restructured to 4 cells: Intro → Env → Netlist → Full Flow
- Uses `spice_to_gds_with_checks()` for one-click DRC+LVS+PEX

## Tested Circuits
| Circuit | DRC | LVS | PEX |
|---------|-----|-----|-----|
| INV (2t) | OK | OK | OK |
| BUFFER (4t) | OK | OK | OK |
| 5T-OTA (5t with tail) | OK | OK | OK |
| Comparator (5t diff pair) | OK | OK | OK |
| StrongARM (11t) | OK | FAIL* | OK |

*StrongARM: auto-router shorts cross-coupled latch outputs (out↔out_n). Requires specialized routing.

## Files Changed
- `core/checks.py`: LVS merge detection, PEX cell-name fix, custom netgen setup
- `core/pipeline.py`: `spice_to_gds_with_checks()` function
- `core/spice_parser.py`: multi-row placement by connection rank
- `designflow.txt`: updated to reflect all changes
- `spice_to_gds.ipynb`: simplified to 4 cells with single-call flow
