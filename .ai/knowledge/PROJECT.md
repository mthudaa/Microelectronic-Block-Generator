# Microelectronic Block Generator — Project Knowledge

## Purpose

An AI-assisted analog-layout workflow for the SSCS Chipathon 2026 gLayout
track: an agent takes a specification or a SPICE subcircuit and produces a
DRC/LVS/PEX-verified GDSII layout, with generated designs preserved as
regression evidence.

## Framework and PDK

- Layout generation: **gLayout** (analog layout generator) on top of
  **gdsfactory** (`gdsfactory` 7.7.0 / `glayout` 0.1.1).
- PDK: **GF180MCU**, identifier `gf180mcuD`, 3.3V single supply,
  `nfet_03v3` / `pfet_03v3` devices only.
- Container PDK path: `/foss/pdks/gf180mcuD`, inside the IIC-OSIC-TOOLS
  Docker container. Required environment:

  ```bash
  export PDK_ROOT=/foss/pdks
  export PDK=gf180mcuD
  export PDKPATH=/foss/pdks/gf180mcuD
  export STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0
  ```

  Do not hardcode a personal home-directory PDK path anywhere. If running
  outside the container, detect the real install (check whether
  `$PDK_ROOT/$PDK` exists, or ask) rather than assuming a fixed location.
- MOSFET body rule, enforced everywhere generated SPICE is produced or
  processed: **`pfet_03v3` -> VDD ONLY, `nfet_03v3` -> VSS ONLY.**
- Device instance prefix is `XM1` (not `M1`); prefer `nf=N` (fingers) over
  `m=N` (multipliers) for matching and compactness.

## Core Utilities

`src/mbg/` — the framework internals:

- `pipeline.py` — the two SPICE-to-GDS flows (see below).
- `spice_parser.py` — `parse_netlist_with_pdk`, `build_design_context`.
- `design_context.py` — the `DesignContext` data model (devices, nets,
  matching groups, placements, access points, routes, violations).
- `placement.py` (legacy) / `placement_engine.py` (active, DesignContext-
  aware) — device placement.
- `routing.py` (legacy shape router) / `router.py` (active, A* grid maze
  router with rip-up/reroute) — routing.
- `connectivity.py` — internal open/short/spacing/via-legality checks
  ahead of external signoff.
- `checks.py` — `run_drc`, `run_lvs`, `run_pex`, netlist extraction.
- `pdk_rules.py`, `pdk_devices.py` — PDK geometry rules and device catalog.
- `simulation.py` — ngspice simulation helpers.

Two implementations coexist for placement and for routing (legacy +
active); neither is dead by default. Confirm which one a given design
script calls before assuming either is safe to remove — see
`mbg-repo-analysis`.

## Generated-Design Workspace

`AI-Generated-Design-Result/` holds AI-generated design runs: layouts,
verification reports, simulation plots, and per-design `REPORT.md` files.
Multiple directory naming conventions coexist for the same circuit (e.g.
`<design>/` alongside a newer `<design>_designcontext_v2/`) — see
`mbg-design-regression` before reading or writing anything here.

## Primary Pipeline API

Always use the single documented entry point for SPICE-to-GDS generation:

```python
from mbg.pipeline import spice_to_gds_with_checks
r = spice_to_gds_with_checks(netlist)
# r["outdir"], r["gds_path"], r["drc"], r["lvs"], r["pex"], r["all_pass"]
```

Never call placement, power, or routing functions individually to produce
a "final" layout. A second, newer flow (`spice_to_gds_ctx` /
`spice_to_gds_with_checks_ctx`) exists using the `DesignContext`/
`GridRouter` engine, but it is not what current design scripts call — see
`mbg-repo-analysis` before assuming which one produced a given result.

## Tapeout Gate

A design passing DRC + LVS + PEX, with post-layout simulation within
tolerance of pre-layout, is ready for tapeout. Never claim any of these
stages passed without the actual report/evidence.

## Team Ownership

- **Huda** — analog circuit design, device selection/sizing, placement,
  routing, power, simulation implementation.
- **Ahmad** — DRC, LVS, PEX, physical-verification automation.
- **Jabir** — AI/LLM integration, prompt engineering, experiment metadata,
  AI metrics, agent-extension authoring.

Do not modify another member's owned implementation for an unrelated task
— record it as a dependency instead.

## Standing Rules

1. **Inspect the active implementation before modifying it.** Two
   generations of placement/routing code coexist (`placement_engine.py`,
   `router.py` vs. legacy `placement.py`, `routing.py`) — confirm which
   path is live for the case at hand before changing anything.
2. **Do not create a parallel, unused placement or router implementation.**
   Extend or replace one of the two existing engines deliberately, with
   the design-script call graph updated to match.
3. **Preserve the gLayout / gdsfactory integration** — do not bypass it
   with ad hoc geometry generation.
4. **Treat `AI-Generated-Design-Result/` as regression evidence.** Existing
   design directories are preserved comparison baselines, not scratch
   space.
5. **Never destructively overwrite a previous result.** New runs get a
   new, distinctly-named directory.
6. **`.ai/` is the source of truth for skills and workflows.** Adapters are
   generated from `.ai/skills/`, `.ai/workflows/`, and `.ai/manifest.json`
   by `python3 scripts/sync_agent_tools.py`. Never hand-edit a generated
   adapter file (`.opencode/skills/*`, `.claude/skills/*`,
   `plugins/mbg-analog/skills/*`, `.opencode/commands/*`,
   `.claude/commands/*`) — the only exception is `.opencode/tools/*.ts`
   (OpenCode-only, not generated).
7. **Prefer dynamic inspection over static memorization.** Read the current
   source and run the tests (`designs/notebooks/chipathon2026-D/tests/`)
   before asserting behavior — this document is a map, not a snapshot.
8. **Use only these status labels:** `PASS`, `FAIL`, `PARTIAL`, `NOT RUN`,
   `NOT AVAILABLE`. Avoid unsupported absolute-success language.
9. **Protect secrets and personal paths.** Never read, display, or commit
   `.env`; never write a user-specific absolute filesystem path into
   checked-in code, examples, or generated scripts.
