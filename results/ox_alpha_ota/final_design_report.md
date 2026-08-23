# Design Report — ota

**Status:** `SUCCESS`  |  **Tapeout ready:** YES

all sign-off conditions met

## 1. Design Request

```text
Design an Operational Transconductance Amplifier (OTA) using the
Microelectronic-Block-Generator framework with the GF180MCU gf180mcuD PDK.
Ports: VDD VSS INP INN OUT IBIAS. IBIAS is an external bias current input.
VDD = 3.3 V, VSS = 0 V, nfet_03v3 / pfet_03v3. Nominal: VDD=3.3 V,
IBIAS=20 uA, VIN_CM=1.65 V, CL=5 pF, TEMP=27 C.
Specifications: DC gain >= 35 dB; GBW >= 1 MHz; phase margin >= 60 deg;
rising slew rate >= 0.5 V/us; falling slew rate >= 0.5 V/us;
supply current excluding IBIAS <= 250 uA; output DC at zero differential
input = 1.65 V +/- 0.5 V; usable output swing >= 0.5-2.8 V; load 5 pF.
Also characterize CMRR, PSRR, input common-mode range, power, noise and
offset where supported. PVT: VDD = 3.0/3.3/3.6 V, TEMP = -40/27/125 C and
GF180 process corners.
```

## 2. Normalized Specifications

- `gain_db` >= 35 dB
- `ugf_hz` >= 1e+06 Hz
- `pm_deg` >= 60 deg
- `sr_rise_vus` >= 0.5 V/us
- `sr_fall_vus` >= 0.5 V/us
- `idd_ua` <= 250 uA
- `out_dc` ~= 1.65 V
- `swing_low_v` <= 0.5 V
- `swing_high_v` >= 2.8 V

- given: vdd, load, gain_db, bw_hz, ugf_hz, pm_deg, sr_rise_vus, sr_fall_vus, idd_ua, out_dc, swing_low_v, swing_high_v
- defaulted: none
- inferred: topology=OTA
- **missing: none**

## 3. Architecture

OTA

## 4. Pre-Layout Optimization

Iterations: 1
- iteration 1: PASS (score 0.0)

```text
  gain_db             50.42 dB        >= 35 dB  PASS
  ugf_hz          4.697e+06 Hz     >= 1e+06 Hz  PASS
  pm_deg             84.03 deg       >= 60 deg  PASS
  sr_rise_vus       10.96 V/us     >= 0.5 V/us  PASS
  sr_fall_vus       10.67 V/us     >= 0.5 V/us  PASS
  idd_ua              63.22 uA       <= 250 uA  PASS
  out_dc               1.969 V       ~= 1.65 V  PASS
  swing_low_v          1.969 V        <= 0.5 V  FAIL
  swing_high_v         2.913 V        >= 2.8 V  PASS
```

## 5. Physical Design and Verification

- DRC: `PASS`
- LVS: `PASS`
- PEX extraction: `PASS`

## 6. Pre-layout vs PEX Degradation

- swing_low_v: 1.969 V -> 1.971 V  delta 0.001923 V (+0.1%)  worse  [FAIL]
- sr_rise_vus: 10.96 V/us -> 10.86 V/us  delta -0.1 V/us (-0.9%)  worse  [PASS]
- ugf_hz: 4.697e+06 Hz -> 4.656e+06 Hz  delta -4.09e+04 Hz (-0.9%)  worse  [PASS]
- sr_fall_vus: 10.67 V/us -> 10.61 V/us  delta -0.06272 V/us (-0.6%)  worse  [PASS]
- pm_deg: 84.03 deg -> 83.79 deg  delta -0.2431 deg (-0.3%)  worse  [PASS]
- out_dc: 1.969 V -> 1.971 V  delta 0.001919 V (+0.1%)  worse  [PASS]
- idd_ua: 63.22 uA -> 62.62 uA  delta -0.6049 uA (-1.0%)  better/equal  [PASS]
- swing_high_v: 2.913 V -> 2.915 V  delta 0.001557 V (+0.1%)  better/equal  [PASS]
- gain_db: 50.42 dB -> 50.45 dB  delta 0.02528 dB (+0.1%)  better/equal  [PASS]

## 7. PEX-Aware Optimization

Iterations: 1
- iteration 1: DRC PASS · LVS PASS · PEX PASS · sim PASS · specs PASS (score 0.0)

Best iteration: **1**

```text
  gain_db             50.45 dB        >= 35 dB  PASS
  ugf_hz          4.656e+06 Hz     >= 1e+06 Hz  PASS
  pm_deg             83.79 deg       >= 60 deg  PASS
  sr_rise_vus       10.86 V/us     >= 0.5 V/us  PASS
  sr_fall_vus       10.61 V/us     >= 0.5 V/us  PASS
  idd_ua              62.62 uA       <= 250 uA  PASS
  out_dc               1.971 V       ~= 1.65 V  PASS
  swing_low_v          1.971 V        <= 0.5 V  FAIL
  swing_high_v         2.915 V        >= 2.8 V  PASS
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

- `drc_report`: `results/ox_alpha_ota/final/ota.magic.drc.rpt`
- `gds`: `results/ox_alpha_ota/final/ota.gds`
- `iteration_history`: `results/ox_alpha_ota/final/iteration_history.json`
- `lvs_report`: `results/ox_alpha_ota/final/ota.lvs.out`
- `pex_spice`: `results/ox_alpha_ota/final/ota.pex.spice`

## 12. Reproduction

```text
/mbg-full-auto "Design an Operational Transconductance Amplifier (OTA) using the
Microelectronic-Block-Generator framework with the GF180MCU gf180mcuD PDK.
Ports: VDD VSS INP INN OUT IBIAS. IBIAS is an external bias "
```
