---
name: mbg-partial-automate
description: Semi-automatic analog IC design flow with user confirmation at each step, from specification to tapeout.
agent: build
platforms: [opencode, claude]
---

Run the MBG partial-automate analog IC design flow for:

```text
$ARGUMENTS
```

## Pipeline (user confirms each step)

```
1.INPUT -> 2.RESEARCH -> 3.NETLIST -> 4.PRE-SIM -> [LOOP A: fine-tune]
  -> 5.LAYOUT -> 6.DRC/LVS -> 7.PEX EXTRACTION -> 8.PEX SIMULATION
  -> 9.SPEC EVALUATION -> [LOOP B: PEX-aware fine-tune] -> 10.TAPEOUT

Two loops, canonical definition in `.ai/knowledge/DESIGN_FLOW.md`.
PEX is feedback, not a final stamp.
```

## Required Workflow

1. Load the `mbg-spice-to-gds` and `mbg-ic-verify` skills.
2. **INPUT** — Ask the user for design specs and confirm understanding.
3. **RESEARCH** — Research topology options, present trade-offs, get
   approval.
4. **NETLIST** — Generate a SPICE netlist, get user review/approval.
5. **PRE-SIM (LOOP A)** — Run ngspice, evaluate against the targets, show
   results. If specs are missed, propose a sizing change and repeat with the
   user's approval. Proceed to layout only once pre-layout passes.
6. **LAYOUT** — Call `spice_to_gds_with_checks(netlist)`, show the SVG
   preview.
7. **DRC/LVS** — Run verification, show reports, get approval.
8. **PEX EXTRACTION** — Extract parasitics. If DRC or LVS failed, this stage
   and everything after it is `SKIP`.
9. **PEX SIMULATION** — Simulate the *extracted* netlist. This is a separate
   stage from extraction: extraction succeeding says the toolchain worked,
   not that the design meets spec.
10. **SPEC EVALUATION (LOOP B)** — Evaluate the PEX results against the same
   targets, and show the pre-layout vs post-layout degradation. If specs are
   missed, propose a circuit and/or layout-constraint change, regenerate the
   layout with approval, and re-run DRC → LVS → PEX → PEX simulation.
   Compare pre/post-layout — save plots as
   `.png`.
11. **TAPEOUT** — Confirm all gates pass *including the post-layout spec
    evaluation*, and report ready status with the iteration history.

## PDK Constraints

- GF180MCU 3.3V, `nfet_03v3`/`pfet_03v3` only.
- **Body: `pfet_03v3` -> VDD ONLY, `nfet_03v3` -> VSS ONLY.**
- Prefer `nf=N` over `m=N`; use the `XM1` device prefix.
- Primary API: `spice_to_gds_with_checks(netlist)`.

## Core Tools

| Tool | Import |
|------|--------|
| Pipeline | `from mbg.pipeline import spice_to_gds_with_checks` |
| DRC | `from mbg.checks import run_drc` |
| LVS | `from mbg.checks import run_lvs` |
| PEX extraction | `from mbg.checks import run_pex` |
| PEX simulation | `from mbg import make_hooks, DesignFlow` (or `mbg.analysis.Testbench` on the `.pex.spice`) |
| Spec evaluation | `from mbg import Spec, evaluate_specs, compare_degradation` |
| Simulation | `from mbg.simulation import run_spice` |

## Output

At each step, present results and wait for user confirmation before
proceeding. Final report: all artifacts, verification evidence, pass/fail
status.
