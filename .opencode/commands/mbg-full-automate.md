---
description: Full automatic analog IC design flow — SPICE→GDS+DRC+LVS+PEX+sim. AI-driven 9-stage pipeline from specification to tapeout-ready layout.
agent: build
---

Run the full MBG automated analog IC design flow for:

```text
$ARGUMENTS
```

## Pipeline

```
1.SELECT → 2.PARSE → 3.GENERATE → 4.SIMULATE → 5.CHECK → 6.LAYOUT → 7.DRC/LVS/PEX → 8.POST-LAYOUT → 9.REPORT
```

## Required Workflow

1. Load `mbg-spice-to-gds` and `mbg-ic-verify` skills.
2. Ask the user for design specifications (gain, BW, delay, power, offset).
3. Research topology and sizing based on specs.
4. Get user confirmation before proceeding.
5. Generate SPICE netlist with proper `XM1` prefix and `nf=N` fingers.
6. Run pre-layout simulation (ngspice) and finetune sizing.
7. Call `spice_to_gds_with_checks(netlist)` for layout + DRC + LVS + PEX.
8. If LVS fails: analyze report, simplify topology if needed, retry.
9. Run post-layout simulation and compare with pre-layout (≤10% deviation).
10. Report final results with all evidence.

## ⚠️ PDK Constraints (GF180MCU 3.3V)

- Use `nfet_03v3` / `pfet_03v3` ONLY
- W < 10µm, L < 10µm
- Prefer `nf=N` (fingers) over `m=N` (multipliers)
- Device prefix: `XM1` (not `M1`)

## ⚠️ Tapeout Gate

| Gate | Requirement |
|------|-------------|
| DRC | Zero violations (≤100 with note) |
| LVS | Netgen match |
| PEX | Extraction done |
| Post-layout | ≤10% deviation from pre-layout |

## Anti-Hallucination

- UNSURE: [param] + reason if uncertain
- Never fabricate simulation results
- Never claim DRC/LVS/PEX success without evidence
- Every spec claim must have justification

## Output

Report all generated artifacts: SPICE netlist, GDS path, SVG preview,
DRC/LVS/PEX summaries, simulation results, and final pass/fail status.
