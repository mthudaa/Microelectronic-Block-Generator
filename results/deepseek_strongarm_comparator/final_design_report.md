# Design Report — strongarm_comparator

**Status:** `SUCCESS`  |  **Tapeout ready:** YES

all sign-off conditions met

## 1. Design Request

```text
Design a Strong-Arm clocked comparator in GF180MCU (gf180mcuD) with ports strongarm_comparator VDD VSS INP INN CLK OUTP OUTN. VDD=3.3 V, VSS=0 V, VCM=1.65 V, 27 C, CLK=10 MHz, CL_OUTP=CL_OUTN=20 fF. Minimum differential input <= 5 mV with correct decision at +/-5 mV, decision time <= 5 ns, differential output swing >= 90% of VDD, static current between comparisons ~0, average current at 10 MHz <= 500 uA, input common-mode range at least 1.0-2.3 V, reset/precharge operation required, regenerative evaluation required. Characterize decision time versus |VIN_DIFF| = 5/10/25/50/100 mV in both polarities, and input-referred offset by mismatch Monte Carlo (1-sigma <= 10 mV). PVT: VDD 3.0/3.3/3.6 V, -40/27/125 C, gf180 typical/ff/ss/fs/sf.
```

## 2. Normalized Specifications

- `t_dec_ns` <= 5 ns
- `out_swing_v` >= 2.97 V
- `i_avg_ua` <= 500 uA
- `i_static_ua` <= 10 uA
- `n_correct` == 10
- `precharge_ok` == 10
- `regenerate_ok` == 10
- `icmr_lo` <= 1 V
- `icmr_hi` >= 2.3 V

- given: vdd, t_dec_ns, out_swing_v, i_avg_ua, i_static_ua, n_correct, precharge_ok, regenerate_ok, icmr_lo, icmr_hi
- defaulted: none
- inferred: topology=comparator
- **missing: load capacitance**

## 3. Architecture

comparator

## 4. Pre-Layout Optimization

Iterations: 1
- iteration 1: PASS (score 0.0)

```text
  t_dec_ns            0.9309 ns         <= 5 ns  PASS
  out_swing_v             3.3 V       >= 2.97 V  PASS
  i_avg_ua             5.426 uA       <= 500 uA  PASS
  i_static_ua        0.03284 uA        <= 10 uA  PASS
  n_correct                  10           == 10  PASS
  precharge_ok               10           == 10  PASS
  regenerate_ok              10           == 10  PASS
  icmr_lo                 0.9 V          <= 1 V  PASS
  icmr_hi                 2.7 V        >= 2.3 V  PASS
```

## 5. Physical Design and Verification

- DRC: `PASS`
- LVS: `PASS`
- PEX extraction: `PASS`

## 6. Pre-layout vs PEX Degradation

- t_dec_ns: 0.9309 ns -> 1.323 ns  delta 0.3922 ns (+42.1%)  worse  [PASS]
- i_avg_ua: 5.426 uA -> 6.725 uA  delta 1.299 uA (+23.9%)  worse  [PASS]
- i_static_ua: 0.03284 uA -> 0.000131 uA  delta -0.03271 uA (-99.6%)  better/equal  [PASS]
- out_swing_v: 3.3 V -> 3.3 V  delta 1.721e-07 V (+0.0%)  better/equal  [PASS]
- n_correct: 10 -> 10  delta 0 (+0.0%)  better/equal  [PASS]
- precharge_ok: 10 -> 10  delta 0 (+0.0%)  better/equal  [PASS]
- regenerate_ok: 10 -> 10  delta 0 (+0.0%)  better/equal  [PASS]
- icmr_lo: 0.9 V -> 0.9 V  delta 0 V (+0.0%)  better/equal  [PASS]
- icmr_hi: 2.7 V -> 2.7 V  delta 0 V (+0.0%)  better/equal  [PASS]

## 7. PEX-Aware Optimization

Iterations: 1
- iteration 1: DRC PASS · LVS PASS · PEX PASS · sim PASS · specs PASS (score 0.0)

Best iteration: **1**

```text
  t_dec_ns             1.323 ns         <= 5 ns  PASS
  out_swing_v             3.3 V       >= 2.97 V  PASS
  i_avg_ua             6.725 uA       <= 500 uA  PASS
  i_static_ua       0.000131 uA        <= 10 uA  PASS
  n_correct                  10           == 10  PASS
  precharge_ok               10           == 10  PASS
  regenerate_ok              10           == 10  PASS
  icmr_lo                 0.9 V          <= 1 V  PASS
  icmr_hi                 2.7 V        >= 2.3 V  PASS
```

## 8. Critical Review Summary

**Devil Reviewer** — 2 review(s), 2 finding(s)
- HIGH: 1
- INFO: 1

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

- `drc_report`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/final/strongarm_comparator.magic.drc.rpt`
- `gds`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/final/strongarm_comparator.gds`
- `iteration_history`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/final/iteration_history.json`
- `lvs_report`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/final/strongarm_comparator.lvs.out`
- `pex_spice`: `/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/final/strongarm_comparator.pex.spice`

## 12. Reproduction

```text
/mbg-full-auto "Design a Strong-Arm clocked comparator in GF180MCU (gf180mcuD) with ports strongarm_comparator VDD VSS INP INN CLK OUTP OUTN. VDD=3.3 V, VSS=0 V, VCM=1.65 V, 27 C, CLK=10 MHz, CL_OUTP=CL_OUTN=20 fF. M"
```

---

## Supplementary characterization

**Nominal (typical / 27 C / 3.3 V):**
- t_dec_ns = 0.9308502785527093
- out_swing_v = 3.3000034439863497
- i_avg_ua = 5.426072867078992
- i_static_ua = 0.032842222430053435
- n_correct = 10
- precharge_ok = 10
- regenerate_ok = 10
- icmr_lo = 0.9
- icmr_hi = 2.8

**Decision time vs |VIN_DIFF| (nominal, worst polarity):**

**PVT matrix (VDD x TEMP x corner):**

| corner | temp | VDD | t_dec (ns) | correct | swing (V) | precharge | regenerate | i_avg (uA) |
|---|---|---|---|---|---|---|---|---|
| typical | -40 | 3.0 | 0.755375220394366 | 10 | 3.00000261541481 | 10 | 10 | 6.628110845231316 |
| typical | -40 | 3.3 | 0.7535592004363012 | 10 | 3.3000026133636897 | 10 | 10 | 8.00861257849311 |
| typical | -40 | 3.6 | 0.7848434484728862 | 10 | 3.60000261044831 | 10 | 10 | 9.779454369204641 |
| typical | 27 | 3.0 | 0.9252695218630469 | 10 | 3.0000034466239 | 10 | 10 | 6.6540983035799535 |
| typical | 27 | 3.3 | 0.9208470545716689 | 10 | 3.3000034439938197 | 10 | 10 | 8.231020142997506 |
| typical | 27 | 3.6 | 0.9508330061208944 | 10 | 3.6000034402999903 | 10 | 10 | 9.442295932269955 |
| typical | 125 | 3.0 | 1.1675411008652163 | 10 | 3.00000457543255 | 10 | 10 | 6.425734389279855 |
| typical | 125 | 3.3 | 1.1574250789767446 | 10 | 3.30000457414294 | 10 | 10 | 7.2885275367789335 |
| typical | 125 | 3.6 | 1.1812378718657417 | 10 | 3.60000457057034 | 10 | 10 | 8.450252945424383 |
| ff | -40 | 3.0 | 0.60947099361183 | 10 | 3.0000022281708 | 10 | 10 | 8.123517785928012 |
| ff | -40 | 3.3 | 0.6129046263106925 | 10 | 3.30000222596063 | 10 | 10 | 9.48146036394523 |
| ff | -40 | 3.6 | 0.6436022780116033 | 10 | 3.60000222235414 | 10 | 10 | 11.267022073358289 |
| ff | 27 | 3.0 | 0.7505178472216796 | 10 | 3.00000293063348 | 10 | 10 | 7.8090197102808006 |
| ff | 27 | 3.3 | 0.7535779538579488 | 10 | 3.3000029278745897 | 10 | 10 | 8.625462210736726 |
| ff | 27 | 3.6 | 0.7849084666255873 | 10 | 3.6000029134127502 | 10 | 10 | 11.35887138202033 |
| ff | 125 | 3.0 | 0.9502015178692337 | 10 | 3.00000284073478 | 10 | 10 | 7.617737967220699 |
| ff | 125 | 3.3 | 0.9531499063616461 | 10 | 3.3000028620408197 | 10 | 10 | 8.697110420353374 |
| ff | 125 | 3.6 | 0.9832984330834216 | 10 | 3.60000286207455 | 10 | 10 | 10.244611943652275 |
| ss | -40 | 3.0 | 0.9642718030561728 | 10 | 3.00000312148012 | 10 | 10 | 6.086417143675048 |
| ss | -40 | 3.3 | 0.9517467936147608 | 10 | 3.30000311937405 | 10 | 10 | 6.756411637518211 |
| ss | -40 | 3.6 | 0.9764500445604573 | 10 | 3.6000031166915 | 10 | 10 | 7.5808120580252165 |
| ss | 27 | 3.0 | 1.1689355790331302 | 10 | 3.00000410818094 | 10 | 10 | 5.7766465674291885 |
| ss | 27 | 3.3 | 1.1536736336372566 | 10 | 3.3000041053492497 | 10 | 10 | 6.643929663941172 |
| ss | 27 | 3.6 | 1.176665722663411 | 10 | 3.60000410194321 | 10 | 10 | 7.732563666918694 |
| ss | 125 | 3.0 | 1.4524332175574257 | 10 | 3.00000558283475 | 10 | 10 | 5.735912722846646 |
| ss | 125 | 3.3 | 1.4271992081157279 | 10 | 3.3000055792695497 | 10 | 10 | 7.104731983592144 |
| ss | 125 | 3.6 | 1.4466090145114916 | 10 | 3.60000557492745 | 10 | 10 | 8.079429728790075 |
| fs | -40 | 3.0 | 0.6920566636560335 | 10 | 3.0000023321649 | 10 | 10 | 6.857028121115768 |
| fs | -40 | 3.3 | 0.6832005215437102 | 10 | 3.30000233045402 | 10 | 10 | 7.7043452682121885 |
| fs | -40 | 3.6 | 0.6929579323598711 | 10 | 3.60000232811608 | 10 | 10 | 8.876001027646328 |
| fs | 27 | 3.0 | 0.8468895165477718 | 10 | 3.00000306369853 | 10 | 10 | 6.1214523140957215 |
| fs | 27 | 3.3 | 0.8371132427460396 | 10 | 3.3000030615451097 | 10 | 10 | 7.042630480343342 |
| fs | 27 | 3.6 | 0.8439368048393181 | 10 | 3.60000305858536 | 10 | 10 | 8.12254717194255 |
| fs | 125 | 3.0 | 1.0725732803101702 | 10 | 3.00000356658935 | 10 | 10 | 6.18058889008521 |
| fs | 125 | 3.3 | 1.050684295252348 | 10 | 3.30000358058555 | 10 | 10 | 7.015485083816392 |
| fs | 125 | 3.6 | 1.0595171709745028 | 10 | 3.60000358937354 | 10 | 10 | 9.416509791255068 |
| sf | -40 | 3.0 | 0.8417938989483861 | 10 | 3.00000295769621 | 10 | 10 | 7.435213529195156 |
| sf | -40 | 3.3 | 0.8590889860913913 | 10 | 3.30000295512896 | 10 | 10 | 8.758089229270135 |
| sf | -40 | 3.6 | 0.8897822472206377 | 10 | 3.60000295149948 | 10 | 10 | 10.056835906054445 |
| sf | 27 | 3.0 | 1.029391841432982 | 10 | 3.00000389114017 | 10 | 10 | 7.104015692710466 |
| sf | 27 | 3.3 | 1.0417188577649736 | 10 | 3.30000388791796 | 10 | 10 | 7.7594766350235655 |
| sf | 27 | 3.6 | 1.0763467653578882 | 10 | 3.6000038831947903 | 10 | 10 | 9.271151081814557 |
| sf | 125 | 3.0 | 1.2874195967269804 | 10 | 3.00000517528278 | 10 | 10 | 6.956071712295113 |
| sf | 125 | 3.3 | 1.2937033782361498 | 10 | 3.30000517514886 | 10 | 10 | 8.46044215334392 |
| sf | 125 | 3.6 | 1.3355003247015593 | 10 | 3.60000517162605 | 10 | 10 | 9.377828542030825 |

**Input-referred offset (mismatch Monte Carlo):**
- runs = 60
- mean offset = -0.417 mV
- 1-sigma offset = 3.328 mV
- 3-sigma offset = 9.984 mV

### Decision time vs |VIN_DIFF| (nominal, worst of both polarities)

| |VIN_DIFF| (mV) | t_dec worst (ns) | decisions |
|---|---|---|
| 5 | 0.931 | 10/10 correct |
| 10 | 0.853 | 10/10 correct |
| 25 | 0.774 | 10/10 correct |
| 50 | 0.699 | 10/10 correct |
| 100 | 0.662 | 10/10 correct |
