# Non-Convergence Report — strongarm_comparator

**Status:** `TOOL_FAILURE`  |  **Tapeout ready:** NO

AttributeError: 'CandidateResult' object has no attribute 'circuit'

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
  t_dec_ns            0.6111 ns         <= 5 ns  PASS
  out_swing_v             3.3 V       >= 2.97 V  PASS
  i_avg_ua              5.27 uA       <= 500 uA  PASS
  i_static_ua        0.02649 uA        <= 10 uA  PASS
  n_correct                  10           == 10  PASS
  precharge_ok               10           == 10  PASS
  regenerate_ok              10           == 10  PASS
  icmr_lo                 0.9 V          <= 1 V  PASS
  icmr_hi                 2.7 V        >= 2.3 V  PASS
```

## 5. Physical Design and Verification

- DRC: `SKIP`
- LVS: `SKIP`
- PEX extraction: `SKIP`

## 6. Pre-layout vs PEX Degradation

- icmr_hi: 2.7 V -> 2.1 V  delta -0.6 V (-22.2%)  worse  [FAIL]
- n_correct: 10 -> 9  delta -1 (-10.0%)  worse  [FAIL]
- t_dec_ns: 0.6111 ns -> 0.9958 ns  delta 0.3848 ns (+63.0%)  worse  [PASS]
- i_avg_ua: 5.27 uA -> 6.685 uA  delta 1.415 uA (+26.9%)  worse  [PASS]
- i_static_ua: 0.02649 uA -> 0.0007043 uA  delta -0.02579 uA (-97.3%)  better/equal  [PASS]
- out_swing_v: 3.3 V -> 3.3 V  delta 2.419e-07 V (+0.0%)  better/equal  [PASS]
- precharge_ok: 10 -> 10  delta 0 (+0.0%)  better/equal  [PASS]
- regenerate_ok: 10 -> 10  delta 0 (+0.0%)  better/equal  [PASS]
- icmr_lo: 0.9 V -> 0.9 V  delta 0 V (+0.0%)  better/equal  [PASS]

## 7. PEX-Aware Optimization

Iterations: 2
- iteration 1: DRC PASS · LVS PASS · PEX PASS · sim PASS · specs FAIL (score 0.186957)
- iteration 2: DRC SKIP · LVS SKIP · PEX SKIP · sim SKIP · specs FAIL (score None)

Best iteration: **1**

```text
  t_dec_ns            0.9958 ns         <= 5 ns  PASS
  out_swing_v             3.3 V       >= 2.97 V  PASS
  i_avg_ua             6.685 uA       <= 500 uA  PASS
  i_static_ua      0.0007043 uA        <= 10 uA  PASS
  n_correct                   9           == 10  FAIL
  precharge_ok               10           == 10  PASS
  regenerate_ok              10           == 10  PASS
  icmr_lo                 0.9 V          <= 1 V  PASS
  icmr_hi                 2.1 V        >= 2.3 V  FAIL
```

## 8. Critical Review Summary

**Devil Reviewer** — 2 review(s), 6 finding(s)
- CRITICAL: 1
- HIGH: 4
- INFO: 1

**Angel Reviewer** — 2 review(s), 0 recommendation(s), 0 tested, 0 improved the score, 0 made it worse

**Unresolved CRITICAL findings:** 
- Sign-off requested while required specifications are unmet.

## 9. Sign-Off Gate

```text
  artifact consistency            FAIL      specs are from iteration 1 but the packaged layout is from iteration 2
  pre-layout specs                PASS    
  PEX specs                       FAIL    
  DRC clean                       PASS    
  DRC sign-off (Magic + KLayout)  PASS    
  LVS match                       PASS    
  PEX extraction                  PASS    
  final GDS                       PASS    
  final PEX netlist               PASS    
  no CRITICAL findings            FAIL      1 unresolved
  reviews complete                PASS    
  PVT corners                     NOT REQUIRED  not part of this flow
  Monte Carlo / mismatch          NOT REQUIRED  not part of this flow
  design report                   PASS    
```

## 10. What to do next

- `n_correct` still misses: 9 vs == 10
- `icmr_hi` still misses: 2.1 vs >= 2.3 V

Recommended manual intervention: review the unresolved findings above, then either relax an infeasible target or supply a stronger `tune_post` for the failing metric.

## 12. Reproduction

```text
/mbg-full-auto "Design a Strong-Arm clocked comparator in GF180MCU (gf180mcuD) with ports strongarm_comparator VDD VSS INP INN CLK OUTP OUTN. VDD=3.3 V, VSS=0 V, VCM=1.65 V, 27 C, CLK=10 MHz, CL_OUTP=CL_OUTN=20 fF. M"
```

---

## Supplementary characterization

**Nominal (typical / 27 C / 3.3 V):**
- t_dec_ns = 0.6110850249404205
- out_swing_v = 3.30000344275556
- i_avg_ua = 5.269835802989866
- i_static_ua = 0.02649400860700202
- n_correct = 10
- precharge_ok = 10
- regenerate_ok = 10
- icmr_lo = 0.8
- icmr_hi = 2.8

**Decision time vs |VIN_DIFF| (nominal, worst polarity):**

**PVT matrix (VDD x TEMP x corner):**

| corner | temp | VDD | t_dec (ns) | correct | swing (V) | precharge | regenerate | i_avg (uA) |
|---|---|---|---|---|---|---|---|---|
| typical | -40 | 3.0 | 0.501922573128679 | 10 | 3.0000026145347 | 10 | 10 | 7.805837335880258 |
| typical | -40 | 3.3 | 0.48752205643591995 | 10 | 3.3000026134692297 | 10 | 10 | 8.952651959665568 |
| typical | -40 | 3.6 | 0.4809887333528496 | 10 | 3.60000261191466 | 10 | 10 | 11.029765844499975 |
| typical | 27 | 3.0 | 0.6173364639643013 | 10 | 3.00000344414083 | 10 | 10 | 7.307818948927958 |
| typical | 27 | 3.3 | 0.5930380933706715 | 10 | 3.30000344283543 | 10 | 10 | 7.623983242242336 |
| typical | 27 | 3.6 | 0.5835048613823482 | 10 | 3.60000344088918 | 10 | 10 | 9.129713395387848 |
| typical | 125 | 3.0 | 0.7932522693689612 | 10 | 3.00000462376455 | 10 | 10 | 6.46164562575834 |
| typical | 125 | 3.3 | 0.7657455606687861 | 10 | 3.30000462267927 | 10 | 10 | 7.634010333463664 |
| typical | 125 | 3.6 | 0.7536250300722612 | 10 | 3.6000046203875202 | 10 | 10 | 9.40899052877342 |
| ff | -40 | 3.0 | 0.41230862978872906 | 10 | 3.00000223053998 | 10 | 10 | 8.67162895221266 |
| ff | -40 | 3.3 | 0.40281916704396864 | 10 | 3.3000022293649196 | 10 | 10 | 10.41816152627133 |
| ff | -40 | 3.6 | 0.3977895399959482 | 10 | 3.60000222739332 | 10 | 10 | 12.684167850102169 |
| ff | 27 | 3.0 | 0.5102328655228464 | 10 | 3.00000293298471 | 10 | 10 | 8.210666830197049 |
| ff | 27 | 3.3 | 0.49487843560896044 | 10 | 3.30000293150792 | 10 | 10 | 9.925507056214464 |
| ff | 27 | 3.6 | 0.4893221493335153 | 10 | 3.60000291904675 | 10 | 10 | 12.524008013965055 |
| ff | 125 | 3.0 | 0.6561430220006637 | 10 | 3.00000329218722 | 10 | 10 | 7.75385134052364 |
| ff | 125 | 3.3 | 0.6366592587055027 | 10 | 3.3000033042904997 | 10 | 10 | 9.133572677317863 |
| ff | 125 | 3.6 | 0.6293611162881222 | 10 | 3.60000330232118 | 10 | 10 | 11.584197890219361 |
| ss | -40 | 3.0 | 0.6282960862833048 | 10 | 3.00000311606613 | 10 | 10 | 6.5360833121690485 |
| ss | -40 | 3.3 | 0.6017151304824968 | 10 | 3.30000311515713 | 10 | 10 | 7.983949335695136 |
| ss | -40 | 3.6 | 0.5916947151970614 | 10 | 3.60000311386913 | 10 | 10 | 10.15828150667304 |
| ss | 27 | 3.0 | 0.7705388448920573 | 10 | 3.00000410016518 | 10 | 10 | 6.119167305754915 |
| ss | 27 | 3.3 | 0.7397989171122682 | 10 | 3.3000040988792496 | 10 | 10 | 7.334760468865145 |
| ss | 27 | 3.6 | 0.7272948685619555 | 10 | 3.60000409726601 | 10 | 10 | 7.460573739093007 |
| ss | 125 | 3.0 | 0.9750253612191708 | 10 | 3.00000557773601 | 10 | 10 | 5.734281141568326 |
| ss | 125 | 3.3 | 0.9366342986554754 | 10 | 3.3000055761609697 | 10 | 10 | 6.600499226239404 |
| ss | 125 | 3.6 | 0.921312656044126 | 10 | 3.60000557391926 | 10 | 10 | 7.84577647314859 |
| fs | -40 | 3.0 | 0.474303528936221 | 10 | 3.00000233352325 | 10 | 10 | 8.077905015062782 |
| fs | -40 | 3.3 | 0.4567279127268484 | 10 | 3.3000023326391297 | 10 | 10 | 8.41572038587069 |
| fs | -40 | 3.6 | 0.44645725152727367 | 10 | 3.60000233138553 | 10 | 10 | 10.133085409636525 |
| fs | 27 | 3.0 | 0.58063825474421 | 10 | 3.00000306432001 | 10 | 10 | 6.815006899453275 |
| fs | 27 | 3.3 | 0.5575402405827016 | 10 | 3.30000306321406 | 10 | 10 | 7.881852283420099 |
| fs | 27 | 3.6 | 0.5472200665689567 | 10 | 3.60000306163949 | 10 | 10 | 9.27914152175782 |
| fs | 125 | 3.0 | 0.75073440787145 | 10 | 3.00000378805208 | 10 | 10 | 6.5865561536753034 |
| fs | 125 | 3.3 | 0.7165004723948227 | 10 | 3.3000037984686204 | 10 | 10 | 7.720983797327297 |
| fs | 125 | 3.6 | 0.6992940106286452 | 10 | 3.60000380708246 | 10 | 10 | 8.202414223915476 |
| sf | -40 | 3.0 | 0.5410277735623219 | 10 | 3.00000295376612 | 10 | 10 | 8.220480090397961 |
| sf | -40 | 3.3 | 0.5244835144867637 | 10 | 3.30000295250544 | 10 | 10 | 10.36186812113343 |
| sf | -40 | 3.6 | 0.5222199892454016 | 10 | 3.60000295054734 | 10 | 10 | 11.657535245025167 |
| sf | 27 | 3.0 | 0.6619681650906714 | 10 | 3.00000388491727 | 10 | 10 | 7.425412007701938 |
| sf | 27 | 3.3 | 0.6453595511077254 | 10 | 3.30000388332097 | 10 | 10 | 8.434207598775702 |
| sf | 27 | 3.6 | 0.6444369619444204 | 10 | 3.60000388080425 | 10 | 10 | 10.670045789120218 |
| sf | 125 | 3.0 | 0.8465948250342514 | 10 | 3.0000052189440103 | 10 | 10 | 6.281531708175367 |
| sf | 125 | 3.3 | 0.8245278360989435 | 10 | 3.30000521812512 | 10 | 10 | 7.549795406569444 |
| sf | 125 | 3.6 | 0.8207740184598079 | 10 | 3.60000521540774 | 10 | 10 | 9.50415128471851 |

**Input-referred offset (mismatch Monte Carlo):**
- runs = 60
- mean offset = -1.583 mV
- 1-sigma offset = 4.030 mV
- 3-sigma offset = 12.091 mV
