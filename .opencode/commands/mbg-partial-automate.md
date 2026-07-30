---
description: Semi-automatic analog IC design flow with user confirmation at each step. User-guided pipeline from specification to tapeout.
agent: build
---

Run the MBG partial-automate analog IC design flow for:

```text
$ARGUMENTS
```

## Pipeline (user confirms each step)

```
1.INPUT → 2.RESEARCH → 3.NETLIST → 4.PRE-SIM → 5.LAYOUT → 6.DRC/LVS → 7.PEX → 8.TAPEOUT
```

## Required Workflow

1. Load `mbg-spice-to-gds` and `mbg-ic-verify` skills.
2. **INPUT**: Ask user for design specs and confirm understanding.
3. **RESEARCH**: Research topology options, present trade-offs, get approval.
4. **NETLIST**: Generate SPICE netlist, get user review/approval.
5. **PRE-SIM**: Run ngspice simulation, show results, get approval.
6. **LAYOUT**: Call `spice_to_gds_with_checks(netlist)`, show SVG preview.
7. **DRC/LVS**: Run verification, show reports, get approval.
8. **PEX**: Extract parasitics, compare pre/post-layout.
9. **TAPEOUT**: Confirm all gates pass, report ready status.

## ⚠️ PDK Constraints

- GF180MCU 3.3V | nfet_03v3/pfet_03v3 | W<10µm L<10µm
- Prefer `nf=N` over `m=N` | Use `XM1` prefix
- Primary API: `spice_to_gds_with_checks(netlist)`

## Core Tools

| Tool | Import |
|------|--------|
| Pipeline | `from core.pipeline import spice_to_gds_with_checks` |
| DRC | `from core.checks import run_drc` |
| LVS | `from core.checks import run_lvs` |
| PEX | `from core.checks import run_pex` |
| Simulation | `from core.simulation import run_spice` |

## Output

At each step, present results and wait for user confirmation before proceeding.
Final report: all artifacts, verification evidence, pass/fail status.
