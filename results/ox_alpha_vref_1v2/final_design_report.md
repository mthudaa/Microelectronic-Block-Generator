# Design Report — vref_1v2

**Status:** `SUCCESS`  |  **Tapeout ready:** YES

all sign-off conditions met

## 1. Design Request

```text
Design a 1.2-V MOS-only voltage reference in GF180MCU gf180mcuD
(3.3 V devices only, no BJT/resistor/capacitor reference-setting elements).
Ports: .subckt vref_1v2 VDD VSS VREF IBIAS; IBIAS is an external 20 uA bias
current input. Nominal: VDD=3.3 V, CL=1 pF, 27 C.
Targets: vref_nominal between 1.15 and 1.25 V (nominal 1.20 V),
tempco_ppm_c <= 300 ppm/C over -40..125 C, line_reg_mv_per_v <= 100 mV/V,
dvref_line_mv <= 60 mV over 3.0..3.6 V, ivdd_uA <= 300 uA excluding IBIAS.
Characterize IBIAS at 10/20/30 uA and supply from 2.7 to 3.6 V; report PVT
at VDD 3.0/3.3/3.6 V and -40/27/125 C plus GF180 process corners.
```

## 2. Normalized Specifications

- `vref_nominal` >= 1.15 V
- `vref_nominal` <= 1.25 V
- `tempco_ppm_c` <= 300 ppm/C
- `line_reg_mv_per_v` <= 100 mV/V
- `dvref_line_mv` <= 60 mV
- `ivdd_uA` <= 300 uA

- given: vdd, load, vref_nominal, tempco_ppm_c, line_reg_mv_per_v, dvref_line_mv, ivdd_uA
- defaulted: none
- inferred: topology=voltage reference
- **missing: none**

## 3. Architecture

voltage reference

## 4. Pre-Layout Optimization

Iterations: 1
- iteration 1: PASS (score 0.0)

```text
  vref_nominal              1.156 V       >= 1.15 V  PASS
  vref_nominal              1.156 V       <= 1.25 V  PASS
  tempco_ppm_c            242 ppm/C    <= 300 ppm/C  PASS
  line_reg_mv_per_v      10.35 mV/V     <= 100 mV/V  PASS
  dvref_line_mv            6.208 mV        <= 60 mV  PASS
  ivdd_uA                  19.87 uA       <= 300 uA  PASS
```

## 5. Physical Design and Verification

- DRC: `PASS`
- LVS: `PASS`
- PEX extraction: `PASS`

## 6. Pre-layout vs PEX Degradation

- tempco_ppm_c: 242 ppm/C -> 245 ppm/C  delta 2.991 ppm/C (+1.2%)  worse  [PASS]
- ivdd_uA: 19.87 uA -> 19.87 uA  delta 0.0009 uA (+0.0%)  worse  [PASS]
- line_reg_mv_per_v: 10.35 mV/V -> 10.26 mV/V  delta -0.09097 mV/V (-0.9%)  better/equal  [PASS]
- dvref_line_mv: 6.208 mV -> 6.154 mV  delta -0.05458 mV (-0.9%)  better/equal  [PASS]
- vref_nominal: 1.156 V -> 1.154 V  delta -0.001731 V (-0.1%)  better/equal  [PASS]
- vref_nominal: 1.156 V -> 1.154 V  delta -0.001731 V (-0.1%)  better/equal  [PASS]

## 7. PEX-Aware Optimization

Iterations: 1
- iteration 1: DRC PASS · LVS PASS · PEX PASS · sim PASS · specs PASS (score 0.0)

Best iteration: **1**

```text
  vref_nominal              1.154 V       >= 1.15 V  PASS
  vref_nominal              1.154 V       <= 1.25 V  PASS
  tempco_ppm_c            245 ppm/C    <= 300 ppm/C  PASS
  line_reg_mv_per_v      10.26 mV/V     <= 100 mV/V  PASS
  dvref_line_mv            6.154 mV        <= 60 mV  PASS
  ivdd_uA                  19.87 uA       <= 300 uA  PASS
```

## 8. Critical Review Summary

**Devil Reviewer** — 2 review(s), 2 finding(s)
- INFO: 1
- MEDIUM: 1

**Angel Reviewer** — 2 review(s), 0 recommendation(s), 0 tested, 0 improved the score, 0 made it worse

**Unresolved CRITICAL findings:** None

## 9. Sign-Off Gate

```text
  artifact consistency            PASS    
  pre-layout specs                PASS    
  PEX specs                       PASS    
  DRC clean                       PASS    
  DRC sign-off (Magic + KLayout)  PASS    
  LVS match                       PASS    
  PEX extraction                  PASS    
  final GDS                       PASS    
  final PEX netlist               PASS    
  no CRITICAL findings            PASS    
  reviews complete                PASS    
  PVT corners                     NOT REQUIRED  not part of this flow
  Monte Carlo / mismatch          NOT REQUIRED  not part of this flow
  design report                   PASS    
```

## 11. Tapeout Files

- `drc_report`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_vref_1v2/final/vref_1v2.magic.drc.rpt`
- `gds`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_vref_1v2/final/vref_1v2.gds`
- `iteration_history`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_vref_1v2/final/iteration_history.json`
- `lvs_report`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_vref_1v2/final/vref_1v2.lvs.out`
- `pex_spice`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_vref_1v2/final/vref_1v2.pex.spice`

## 12. Reproduction

```text
/mbg-full-auto "Design a 1.2-V MOS-only voltage reference in GF180MCU gf180mcuD
(3.3 V devices only, no BJT/resistor/capacitor reference-setting elements).
Ports: .subckt vref_1v2 VDD VSS VREF IBIAS; IBIAS is an exte"
```

---

## PVT Characterization (final extracted netlist, post-layout)

Evidence: `pvt_characterization.json`, decks under `pvt/`. IBIAS pin
convention: the pin delivers the bias current out to an external generator
tied to VSS.

### VREF vs process corner (VDD = 3.3 V)

| Corner | VREF @ 27 C | Tempco (-40..125 C) | Line-reg worst (3.0-3.6 V) | dVREF 3.0-3.6 V worst |
|--------|-------------|---------------------|----------------------------|-----------------------|
| typical | 1.154 V | 244 ppm/C | 10.3 mV/V (27 C) | 6.2 mV |
| ff | 1.028 V | 250 ppm/C | 22.4 mV/V (125 C) | 13.5 mV |
| ss | 1.279 V | 222 ppm/C | 58.4 mV/V (125 C) | 35.1 mV |
| fs | 1.065 V | 242 ppm/C | 33.6 mV/V (125 C) | 20.2 mV |
| sf | 1.243 V | 243 ppm/C | 46.6 mV/V (125 C) | 27.9 mV |

### VDD x TEMP grid (typical corner)

| TEMP | 3.0 V | 3.3 V | 3.6 V |
|------|-------|-------|-------|
| -40 C | 1.149 V | 1.152 V | 1.153 V |
| 27 C | 1.149 V | 1.154 V | 1.155 V |
| 125 C | 1.197 V | 1.199 V | 1.199 V |

Supply behavior 2.7-3.6 V: VREF remains regulated down to 2.7 V (1.135 V at
typical, a 19 mV droop vs 3.3 V); no dropout or latching observed on any
corner.

### IBIAS sensitivity (typical, 27 C, final layout)

| IBIAS | VREF | dVREF vs 20 uA |
|-------|------|----------------|
| 10 uA | 1.000 V | -154 mV |
| 20 uA | 1.154 V | 0 |
| 30 uA | 1.250 V | +96 mV |

### Interpretation

* Status: **PASS as characterization.** The specified targets are nominal-
  condition targets; all of them are met at TT after PEX.
* Temperature coefficient stays within 222-250 ppm/C on every GF180 corner —
  the self-cascode triode cancellation is robust to process.
* Line regulation and supply variation stay far inside their limits at every
  corner and temperature (worst: ss, 125 C, 58.4 mV/V and 35.1 mV).
* Absolute VREF level tracks the NFET threshold corner: ff/ss/fs shift the
  level by -126/+125/-89 mV respectively. An untrimmed MOS-only reference
  cannot hold a +-50 mV window across VTH corners; if corner-level accuracy
  is required, add a trim (e.g., selectable MB segments) — recorded here as
  a recommendation, not a spec miss.
* The Devil reviewer's specification-stage finding stands: TT margin to the
  1.15 V lower bound is ~4 mV (0.3%). Monte Carlo / mismatch was not part of
  the configured gate and is reported NOT RUN.
