---
name: mbg-full-automate
description: Full automatic analog IC design flow — SPICE to GDS with DRC, LVS, PEX, and simulation, driven by the AI agent from specification to tapeout-ready layout.
agent: build
platforms: [opencode, claude]
---

Run the full MBG automated analog IC design flow for:

```text
$ARGUMENTS
```

## Pipeline

```
1.SELECT -> 2.PARSE -> 3.GENERATE -> 4.SIMULATE -> 5.CHECK -> 6.LAYOUT -> 7.DRC/LVS/PEX -> 8.POST-LAYOUT -> 9.REPORT
```

## Required Workflow

1. Load the `mbg-spice-to-gds` and `mbg-ic-verify` skills.
2. Ask the user for design specifications (gain, BW, delay, power, offset).
3. Research topology and sizing based on specs.
4. Get user confirmation before proceeding.
5. Generate a SPICE netlist with proper `XM1` prefix and `nf=N` fingers.
6. Run pre-layout simulation (ngspice) and finetune sizing.
7. Call `spice_to_gds_with_checks(netlist)` for layout + DRC + LVS + PEX.
8. If LVS fails: analyze the report, simplify topology if needed, retry.
9. Run post-layout simulation and compare with pre-layout (target: <=10% deviation).
10. Save all simulation plots as `.png` (AC/DC/TRAN, pre- and post-layout) in
    the working directory.
11. Report final results with all evidence.

## PDK Constraints (GF180MCU 3.3V)

- Use `nfet_03v3` / `pfet_03v3` ONLY.
- Check `AGENTS.md` and `mbg.pdk_rules` for the current W/L per-finger
  limit before sizing — do not assume a fixed number without checking.
- Prefer `nf=N` (fingers) over `m=N` (multipliers).
- Device prefix: `XM1` (not `M1`).
- **Body: `pfet_03v3` -> VDD ONLY, `nfet_03v3` -> VSS ONLY.**

## Tapeout Gate

| Gate | Requirement |
|------|-------------|
| DRC | Zero violations (a small count with a documented note may be acceptable — confirm current project threshold) |
| LVS | Netgen match |
| PEX | Extraction done |
| Post-layout | Within target deviation of pre-layout |

## Anti-Hallucination

- Mark uncertain parameters as `UNSURE: [param]` with the reason.
- Never fabricate simulation results.
- Never claim DRC/LVS/PEX success without evidence.
- Every spec claim must have justification.

## Output

Report all generated artifacts: SPICE netlist, GDS path, SVG preview,
DRC/LVS/PEX summaries, simulation results, and final pass/fail status.
