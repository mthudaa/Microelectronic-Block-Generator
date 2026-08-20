---
name: mbg-spice-to-gds
description: Converts a SPICE subcircuit netlist into a DRC-clean GDSII layout using gLayout, via the single entry point spice_to_gds_with_checks(netlist). Use when the user asks to generate GDS from SPICE, convert a netlist to layout, "layout my circuit", or "spice to gds" for the GF180MCU 3.3V PDK. Do not use for manual step-by-step placement/routing, simulation-only tasks, or verification-only tasks on an already-built GDS (use mbg-ic-verify for that).
license: Apache-2.0
compatibility: opencode
metadata:
  owner: huda
  project: microelectronic-block-generator
  status: experimental
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/skills/mbg-spice-to-gds/SKILL.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

# MBG SPICE to GDS Layout Generator

## Pipeline Entry Point

`spice_to_gds_with_checks(netlist)` is the single entry point. It drives the
DesignContext flow: analog-aware placement, the DRC-aware grid router, internal
OPEN/SHORT verification, then Magic DRC + netgen LVS + PEX.

Measured on the four reference blocks (inverter, ring oscillator, 5T OTA,
StrongArm comparator): 4/4 pass DRC and LVS. The older shape-router path passed
0/4 because it mislabelled top-level pins; it is still reachable via
`legacy=True` for comparison but should not be used for new work.

Returned keys: `outdir`, `gds_path`, `svg_path`, `cell_name`, `drc`, `lvs`,
`pex`, `all_pass`, plus `context`, `verification` and `metrics`.

## Purpose

Convert a SPICE subcircuit netlist into a DRC-clean GDSII layout with
auto-placement, power delivery, and negotiated-congestion routing, using the
project's single supported pipeline entry point.

## When to Use

- Converting a SPICE netlist to a GDS layout.
- Running the full layout + verification pipeline in one call.
- The user asks to "generate layout", "spice to gds", or "create GDS".

## When Not to Use

- Manual step-by-step placement or routing — inspect
  `mbg.placement_engine` / `mbg.router` directly instead (see
  `mbg-placement-debug` / `mbg-routing-debug`), or use a full-automate
  workflow that still calls the same pipeline entry point underneath.
- Simulation-only tasks with no layout requested.
- Verification-only tasks on an existing GDS — use `mbg-ic-verify`.
- Diagnosing why a placement or route failed — use `mbg-placement-debug` or
  `mbg-routing-debug`; this skill only describes the happy-path call.

## Required Inputs

- A SPICE subcircuit netlist string containing a `.subckt` definition with
  at least one supported device (`XM1`-style MOSFETs, resistors, MIM caps).
- PDK environment variables set (see Preconditions).
- Optional: an explicit output GDS path; otherwise the pipeline derives one
  from the subcircuit name.

## Preconditions

- `PDK_ROOT`, `PDK`, and `PDKPATH` must be set before calling the pipeline.
  Inside the IIC-OSIC-TOOLS container the project standard is:

  ```bash
  export PDK_ROOT=/foss/pdks
  export PDK=gf180mcuD
  export PDKPATH=/foss/pdks/gf180mcuD
  ```

  On a host-only install (no container), do not hardcode a personal home
  directory. Detect the actual PDK root instead, for example by checking
  whether `$PDK_ROOT/$PDK` exists, or by asking the user which PDK
  installation path to use. `mbg.checks` in
  `src/mbg/checks.py` already falls back to
  `/foss/pdks` when `PDK_ROOT` is unset, and `run_lvs` additionally searches
  under `PDK_ROOT` for the PDK setup file — read that module before assuming
  a path.
- The netlist must reference only `nfet_03v3` / `pfet_03v3` devices for the
  GF180MCU 3.3V flow (auto-detected from the `.lib`/`.inc` line by
  `mbg.spice_parser.parse_netlist_with_pdk`; the pipeline also supports
  `sky130` when that PDK is detected).
- Minimum five transistors is the informal threshold for meaningful analog
  layout mode; smaller circuits may still run but are not the intended case.

## PDK Constraints (GF180MCU 3.3V)

| Constraint | Value |
|-----------|-------|
| Supply | 3.3V single |
| MOSFET models | `nfet_03v3` / `pfet_03v3` ONLY |
| W limit | project guidance varies 5-10um per finger — check `AGENTS.md` and `mbg.pdk_rules` for the authoritative limit before sizing |
| L limit | project guidance varies 5-10um — same caveat |
| **Body** | **`pfet_03v3` -> VDD ONLY, `nfet_03v3` -> VSS ONLY** |
| Device prefix | `XM1` (not `M1`) |
| Fingers vs multipliers | Prefer `nf=N` over `m=N` for matching and compactness |

## Workflow

1. Load the netlist string. Reference the PDK library relative to
   `$PDK_ROOT`, never a hardcoded personal path:

   ```python
   from mbg.pipeline import spice_to_gds_with_checks

   netlist = """
   .lib "$PDK_ROOT/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
   .subckt my_design vdd vss in out
   XM1 out in vdd vdd pfet_03v3 L=1u W=4u nf=1
   XM2 out in vss vss nfet_03v3 L=1u W=2u nf=1
   .ends
   """
   ```

   In a live shell, expand `$PDK_ROOT` before writing the `.lib` line, or
   have the calling script substitute the real environment value — do not
   commit a resolved absolute path into a checked-in netlist example.
2. Call **only** `spice_to_gds_with_checks(netlist)`. Never call
   `mbg.placement_engine.place`, `mbg.router.GridRouter`, or
   `mbg.power` functions manually to produce a "final" layout — those are
   internals the pipeline already orchestrates.
3. The pipeline internally: parses the netlist and auto-detects the PDK,
   activates the PDK via gdsfactory, places devices, adds power strips,
   auto-routes, adds pin labels, and writes the GDS.
4. Inspect the returned dict (see Outputs) and report DRC/LVS/PEX results
   exactly as returned — never upgrade a `FAIL` or missing report to a
   claimed pass.

## Outputs

`spice_to_gds_with_checks(netlist)` returns:

| Key | Description |
|-----|-------------|
| `outdir` | Output directory path (named after the cell) |
| `gds_path` | GDS file path |
| `svg_path` | SVG preview path (may be `None` if preview generation failed) |
| `cell_name` | Top subcircuit name |
| `drc` | DRC result dict from `run_drc` |
| `lvs` | LVS result dict from `run_lvs` |
| `pex` | PEX result dict from `run_pex` |
| `all_pass` | `True` only if DRC clean AND LVS match AND PEX produced output |

For a from-scratch inspection of the same flow through the newer
`DesignContext`-based path (`spice_to_gds_ctx` /
`spice_to_gds_with_checks_ctx` in `core/pipeline.py`), see
`mbg-repo-analysis` — that path returns `component`, `context`,
`verification`, and `metrics` instead of a checks dict, and is not what
`spice_to_gds_with_checks` calls internally today.

## Failure Modes

- Missing `PDK_ROOT`/`PDK`/`PDKPATH` — the pipeline raises before layout
  starts; do not silently set a personal fallback path.
- Netlist has no `.subckt` or zero parsed components — the pipeline raises
  `ValueError` before layout starts.
- `drc["clean"]` is `False`, `lvs["match"]` is `False`, or `pex["pex_path"]`
  is `None` — report each stage's own `summary` field verbatim; do not
  claim `all_pass` when the dict says otherwise.
- Floating/unrouted internal nets — inspect with `mbg-routing-debug`
  (`mbg.connectivity.verify`) rather than guessing from the SVG preview.
