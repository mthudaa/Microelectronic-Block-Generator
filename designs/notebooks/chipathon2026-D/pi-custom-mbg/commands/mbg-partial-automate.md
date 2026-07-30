# /mbg-partial-automate — D08 Semi-Automatic Analog IC Flow

**PDK**: GF180MCU | 3.3V | nfet_03v3/pfet_03v3 | W<10µm L<10µm
**LAYOUT**: `spice_to_gds_with_checks(netlist)` — NEVER manual step-by-step

## Pipeline (user confirms each step)
```
1.INPUT → 2.RESEARCH → 3.NETLIST → 4.PRE-SIM → 5.LAYOUT → 6.DRC/LVS → 7.PEX → 8.TAPEOUT
```

## TAPEOUT GATE
| Gate | Requirement |
|------|-------------|
| DRC | 0 violations |
| LVS | Match |
| PEX | Done |
| Post-layout | ≤10% deviation |
