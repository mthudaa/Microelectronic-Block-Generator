# /mbg-full-automate — D08 Full Automatic Analog IC Flow

**PDK**: GF180MCU | 3.3V | nfet_03v3/pfet_03v3 | W<10µm L<10µm
**LAYOUT**: `spice_to_gds_with_checks(netlist)` — NEVER manual step-by-step
**IOPIN**: VDD→vdd | VSS→vss | Analog→iopin(T_EN=0,T_IE=1) | Digital in→iopin(0,1) | Digital out→iopin(1,0)

## Pipeline
```
1.SELECT → 2.PARSE → 3.GENERATE → 4.SIMULATE → 5.CHECK → 6.LAYOUT → 7.DRC/LVS/PEX → 8.POST-LAYOUT → 9.REPORT
```

## TAPEOUT GATE
| Gate | Requirement |
|------|-------------|
| DRC | Magic DRC = 0 |
| LVS | Netgen match |
| PEX | Extraction done |
| Post-layout | ≤10% deviation from pre-layout |

## Anti-Hallucination
- UNSURE: [param] + reason
- Never fabricate sim results
- Every claim has proof
- No DRC/LVS/PEX claim without evidence
