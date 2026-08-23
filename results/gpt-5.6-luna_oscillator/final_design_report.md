# Design Report — oscillator

**Status:** `SUCCESS`  |  **Tapeout ready:** YES

all sign-off conditions met

## 1. Design Request

```text
Design a self-starting CMOS ring oscillator in GF180MCU gf180mcuD. Use exactly VDD VSS OSC_OUT and .subckt oscillator VDD VSS OSC_OUT. Use gf180mcuD 3.3 V nfet_03v3 and pfet_03v3 devices. Nominal VDD=3.3 V, VSS=0 V, TEMP=27 C. It must start automatically on normal power-up, oscillate at 10-100 MHz, start in under 5 us, have 40-60 percent duty cycle, OSC_OUT high above 2.97 V and low below 0.33 V, average supply current below 1 mA, and sustain at least 100 cycles. Characterize VDD at 3.0/3.3/3.6 V, TEMP at -40/27/125 C, and meaningful gf180 corners. The final acceptance transient must not use a startup pulse or forced internal initial condition.
```

## 2. Normalized Specifications

- `autonomous_startup` >= 1
- `frequency_hz` >= 1e+07 Hz
- `frequency_hz` <= 1e+08 Hz
- `startup_time_us` <= 5 us
- `duty_cycle` >= 0.4
- `duty_cycle` <= 0.6
- `osc_high_v` >= 2.97 V
- `osc_low_v` <= 0.33 V
- `idd_ma` <= 1 mA
- `sustained_cycles` >= 100

- given: vdd, autonomous_startup, frequency_hz, startup_time_us, duty_cycle, osc_high_v, osc_low_v, idd_ma, sustained_cycles
- defaulted: none
- inferred: topology=ring oscillator
- **missing: load capacitance**

## 3. Architecture

ring oscillator

## 4. Pre-Layout Optimization

Iterations: 1
- iteration 1: PASS (score 0.0)

```text
  autonomous_startup               1            >= 1  PASS
  frequency_hz          7.541e+07 Hz     >= 1e+07 Hz  PASS
  frequency_hz          7.541e+07 Hz     <= 1e+08 Hz  PASS
  startup_time_us         0.03699 us         <= 5 us  PASS
  duty_cycle                  0.4808          >= 0.4  PASS
  duty_cycle                  0.4808          <= 0.6  PASS
  osc_high_v                 3.581 V       >= 2.97 V  PASS
  osc_low_v                 -0.242 V       <= 0.33 V  PASS
  idd_ma                  0.09022 mA         <= 1 mA  PASS
  sustained_cycles               118          >= 100  PASS
```

## 5. Physical Design and Verification

- DRC: `PASS`
- LVS: `PASS`
- PEX extraction: `PASS`

## 6. Pre-layout vs PEX Degradation

- osc_low_v: -0.242 V -> -0.2023 V  delta 0.03969 V (+16.4%)  worse  [PASS]
- sustained_cycles: 118 -> 103  delta -15 (-12.7%)  worse  [PASS]
- osc_high_v: 3.581 V -> 3.534 V  delta -0.04684 V (-1.3%)  worse  [PASS]
- idd_ma: 0.09022 mA -> 0.09093 mA  delta 0.0007012 mA (+0.8%)  worse  [PASS]
- startup_time_us: 0.03699 us -> 0.009601 us  delta -0.02739 us (-74.0%)  better/equal  [PASS]
- frequency_hz: 7.541e+07 Hz -> 6.4e+07 Hz  delta -1.14e+07 Hz (-15.1%)  better/equal  [PASS]
- frequency_hz: 7.541e+07 Hz -> 6.4e+07 Hz  delta -1.14e+07 Hz (-15.1%)  better/equal  [PASS]
- duty_cycle: 0.4808 -> 0.4786  delta -0.002188 (-0.5%)  better/equal  [PASS]
- duty_cycle: 0.4808 -> 0.4786  delta -0.002188 (-0.5%)  better/equal  [PASS]
- autonomous_startup: 1 -> 1  delta 0 (+0.0%)  better/equal  [PASS]

## 7. PEX-Aware Optimization

Iterations: 1
- iteration 1: DRC PASS · LVS PASS · PEX PASS · sim PASS · specs PASS (score 0.0)

Best iteration: **1**

```text
  autonomous_startup               1            >= 1  PASS
  frequency_hz            6.4e+07 Hz     >= 1e+07 Hz  PASS
  frequency_hz            6.4e+07 Hz     <= 1e+08 Hz  PASS
  startup_time_us        0.009601 us         <= 5 us  PASS
  duty_cycle                  0.4786          >= 0.4  PASS
  duty_cycle                  0.4786          <= 0.6  PASS
  osc_high_v                 3.534 V       >= 2.97 V  PASS
  osc_low_v                -0.2023 V       <= 0.33 V  PASS
  idd_ma                  0.09093 mA         <= 1 mA  PASS
  sustained_cycles               103          >= 100  PASS
```

## 8. Critical Review Summary

**Devil Reviewer** — 2 review(s), 3 finding(s)
- INFO: 1
- MEDIUM: 2

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
  PVT corners                     NOT REQUIRED  separately characterized below
  Monte Carlo / mismatch          NOT REQUIRED  not part of this flow
  design report                   PASS    
```

## 11. Tapeout Files

- `drc_report`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_oscillator/final/oscillator.magic.drc.rpt`
- `gds`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_oscillator/final/oscillator.gds`
- `iteration_history`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_oscillator/final/iteration_history.json`
- `lvs_report`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_oscillator/final/oscillator.lvs.out`
- `pex_spice`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_oscillator/final/oscillator.pex.spice`

## 12. Reproduction

```text
/mbg-full-auto "Design a self-starting CMOS ring oscillator in GF180MCU gf180mcuD. Use exactly VDD VSS OSC_OUT and .subckt oscillator VDD VSS OSC_OUT. Use gf180mcuD 3.3 V nfet_03v3 and pfet_03v3 devices. Nominal VDD="
```

## 13. Post-PEX PVT Characterization

- **Status:** `PASS`
- Nominal process grid: VDD 3.0/3.3/3.6 V x TEMP -40/27/125 C, typical.
- Process corners: typical, ff, ss, sf, fs at 3.3 V and 27 C.
- Detailed measurements: `pvt_results.json`.
