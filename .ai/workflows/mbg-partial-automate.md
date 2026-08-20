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
1.INPUT -> 2.RESEARCH -> 3.NETLIST -> 4.PRE-SIM -> 5.LAYOUT -> 6.DRC/LVS -> 7.PEX -> 8.TAPEOUT
```

## Required Workflow

1. Load the `mbg-spice-to-gds` and `mbg-ic-verify` skills.
2. **INPUT** — Ask the user for design specs and confirm understanding.
3. **RESEARCH** — Research topology options, present trade-offs, get
   approval.
4. **NETLIST** — Generate a SPICE netlist, get user review/approval.
5. **PRE-SIM** — Run ngspice simulation, show results, get approval.
6. **LAYOUT** — Call `spice_to_gds_with_checks(netlist)`, show the SVG
   preview.
7. **DRC/LVS** — Run verification, show reports, get approval.
8. **PEX** — Extract parasitics, compare pre/post-layout — save plots as
   `.png`.
9. **TAPEOUT** — Confirm all gates pass, report ready status.

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
| PEX | `from mbg.checks import run_pex` |
| Simulation | `from mbg.simulation import run_spice` |

## Output

At each step, present results and wait for user confirmation before
proceeding. Final report: all artifacts, verification evidence, pass/fail
status.
