# MBG Design Results — Summary

Every AI/LLM-generated analog block produced by the Microelectronic Block
Generator, as recorded in this directory. One row per design, generated from
the artifacts on disk (`full_auto_result.json`, `final/drc_summary.json`,
`final/*.lvs.out`, `final/*.gds`) rather than transcribed by hand.

- Designs: **13**
- PDK: **GF180MCU-D** (`gf180mcuD`), 3.3 V single supply
- Flow: `/mbg-full-auto` — specification → pre-layout optimisation → layout →
  DRC → LVS → PEX extraction → PEX-aware re-optimisation → sign-off

## At a glance

| Design | Model | Block | Devices | Nets | Size (µm) | Area (µm²) | DRC | LVS | PEX | Sign-off |
| :--- | :--- | :--- | ---: | ---: | :--- | ---: | :---: | :---: | :---: | :---: |
| `claude-opus-5_temp_sensor` | Claude Opus 5 | Temperature sensor | 18 | 12 | 88.28 × 156.02 | 13,773 | ✅ | ✅ | ✅ | ✅ |
| `deepseek_oscillator` | DeepSeek | Ring oscillator | 6 | 5 | 35.8 × 30.56 | 1,094 | ✅ | ✅ | ✅ | ✅ |
| `deepseek_ota` | DeepSeek | 5T-OTA | 6 | 8 | 27.08 × 38.72 | 1,048 | ✅ | ✅ | ✅ | ✅ |
| `deepseek_strongarm_comparator` | DeepSeek | StrongArm comparator | 11 | 10 | 49.52 × 40.76 | 2,018 | ✅ | ✅ | ✅ | ✅ |
| `deepseek_vref_1v2` | DeepSeek | 1.2 V voltage reference | 5 | 5 | 31.42 × 30.56 | 960 | ✅ | ✅ | ✅ | ✅ |
| `gpt-5.6-luna_oscillator` | GPT-5.6-Luna | Ring oscillator | 10 | 7 | 50.02 × 30.56 | 1,529 | ✅ | ✅ | ✅ | ✅ |
| `gpt-5.6-luna_ota` | GPT-5.6-Luna | 5T-OTA | 6 | 8 | 26.3 × 54.02 | 1,421 | ✅ | ✅ | ✅ | ✅ |
| `gpt-5.6-luna_strongarm_comparator` | GPT-5.6-Luna | StrongArm comparator | 11 | 10 | 60.74 × 53.3 | 3,237 | ✅ | ✅ | ✅ | ✅ |
| `gpt-5.6-luna_vref_1v2` | GPT-5.6-Luna | 1.2 V voltage reference | 4 | 5 | 31.44 × 35.66 | 1,121 | ✅ | ✅ | ✅ | ✅ |
| `ox_alpha_oscillator` | OX-Alpha | Ring oscillator | 18 | 11 | 84.76 × 30.56 | 2,590 | ✅ | ✅ | ✅ | ✅ |
| `ox_alpha_ota` | OX-Alpha | 5T-OTA | 6 | 8 | 50.8 × 55.04 | 2,796 | ✅ | ✅ | ✅ | ✅ |
| `ox_alpha_strongarm_comparator` | OX-Alpha | StrongArm comparator | 11 | 10 | 42.88 × 49.94 | 2,141 | ✅ | ✅ | ✅ | ✅ |
| `ox_alpha_vref_1v2` | OX-Alpha | 1.2 V voltage reference | 4 | 5 | 32.74 × 35.66 | 1,168 | ✅ | ✅ | ✅ | ✅ |
| **Total** | | **13 designs** | | | | **34,898** | **13/13** | **13/13** | **13/13** | **13/13** |

All thirteen designs reach `tapeout_ready: true` in their own run record:
Magic DRC clean, KLayout sign-off clean, netgen LVS matching, a parasitic
netlist extracted, and post-layout simulation meeting the specification the
run was given.

## What "PASS" means here

Each design carries a `signoff` block listing the conditions it had to meet.
The conditions are identical across all thirteen:

- artifact consistency
- pre-layout specs
- PEX specs
- DRC clean
- DRC sign-off (Magic + KLayout)
- LVS match
- PEX extraction
- final GDS
- final PEX netlist
- no CRITICAL findings
- reviews complete
- PVT corners
- Monte Carlo / mismatch
- design report

A design is only marked ready when **all** of them pass. `all_pass` is not a
DRC summary — it is Magic clean *and* KLayout sign-off PASS *and* LVS match
*and* internal connectivity clean. A checker that did not run counts as a
failure, not a pass.

## 5T-OTA — three candidates

Common specification: gain ≥ 35 dB, unity-gain frequency ≥ 1 MHz, all three
post-layout (PEX) values.

| Model | Devices | Size (µm) | Area (µm²) | Gain (dB) | UGF (MHz) | Runtime (s) |
| :--- | ---: | :--- | ---: | ---: | ---: | ---: |
| DeepSeek | 6 | 27.08 × 38.72 | 1,048 | 43.55 | 4.37 | 51.5 |
| GPT-5.6-Luna | 6 | 26.3 × 54.02 | 1,421 | 44.51 | 2.24 | 64.5 |
| OX-Alpha | 6 | 50.8 × 55.04 | 2,796 | 50.45 | 4.66 | 459.0 |

All three clear the 35 dB / 1 MHz targets. OX-Alpha has the highest gain
(50.4 dB) and the widest bandwidth, at 2.7× the area of DeepSeek's. DeepSeek
produced the smallest layout and the fastest run.

## StrongArm comparator — three candidates

| Model | Devices | Size (µm) | Area (µm²) | Decision time | Avg current | Runtime (s) |
| :--- | ---: | :--- | ---: | ---: | ---: | ---: |
| DeepSeek | 11 | 49.52 × 40.76 | 2,018 | 1.323 ns | 6.72 µA | 88.8 |
| GPT-5.6-Luna | 11 | 60.74 × 53.3 | 3,237 | 2.494 ns | 5.99 µA | 725.1 |
| OX-Alpha | 11 | 42.88 × 49.94 | 2,141 | see note | 5.70 µA | 70.6 |

All three resolve correctly on every tested vector and draw single-digit µA.
GPT-5.6-Luna was by far the most expensive run (725 s, 2 PEX iterations, 5
Devil findings) — the only design in the set that needed a second PEX loop.

> **Note on OX-Alpha decision time.** Its run records
> `decision_time_s = 0.0`. A literally zero decision time is not physical; it
> means the measurement resolved below the simulation time step rather than
> that the comparator is infinitely fast. The pass/fail flags
> (`correct_frac = 1.0`, `swing_ratio = 1.0`) are meaningful; that one number
> is not, and should be re-measured with a finer step before being quoted.

## 1.2 V voltage reference — three candidates

| Model | Devices | Size (µm) | Area (µm²) | V_ref (V) | Tempco (ppm/°C) | Line reg (mV/V) | I_dd (µA) |
| :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: |
| DeepSeek | 5 | 31.42 × 30.56 | 960 | 1.2254 | 59.9 | 5.27 | 61.30 |
| GPT-5.6-Luna | 4 | 31.44 × 35.66 | 1,121 | 1.1666 | 274.7 | 11.13 | 39.87 |
| OX-Alpha | 4 | 32.74 × 35.66 | 1,168 | 1.1540 | 245.0 | 10.26 | 19.87 |

DeepSeek's reference is the clear winner on quality: **60 ppm/°C** against
245 and 275 ppm/°C, and 5.3 mV/V line regulation against ~10–11 mV/V — a 4×
better temperature coefficient in the smallest area of the three. It pays for
it in supply current (61 µA against 20–40 µA). Note that none of the three
lands exactly on 1.2 V: 1.225 V, 1.167 V and 1.154 V respectively.

## Ring oscillator — three candidates

| Model | Devices | Size (µm) | Area (µm²) | Frequency | Duty (%) | Startup | Current |
| :--- | ---: | :--- | ---: | ---: | ---: | ---: | ---: |
| DeepSeek | 6 | 35.8 × 30.56 | 1,094 | 44.75 MHz | 44.0 | 0.685 µs | 55.7 µA |
| GPT-5.6-Luna | 10 | 50.02 × 30.56 | 1,529 | 64.00 MHz | 47.9 | 0.0096 µs | 90.9 µA |
| OX-Alpha | 18 | 84.76 × 30.56 | 2,590 | 45.33 MHz | 48.7 | ~0 | 104.4 µA |

> **Rail overshoot.** All three record output levels outside the 0–3.3 V
> rails — highs of 3.46–3.53 V and lows of −0.20 to −0.42 V. That is
> capacitive ringing at the output node in the extracted netlist, not a
> supply violation, but it means the waveform is not rail-to-rail clean and
> would stress a receiving gate. Worth damping before reuse.

None of the three oscillators is instantiated in the `mbg-d08` top level.

## Temperature sensor — Claude Opus 5

A relaxation oscillator whose frequency is the temperature output: a
beta-multiplier/PTAT reference with poly degeneration, an M4/M5 MIM timing
capacitor, a Schmitt trigger and an output buffer.

| Metric | Value |
| :--- | ---: |
| Devices / nets | 18 / 12 |
| Size | 88.28 × 156.02 µm (13,773 µm²) |
| Frequency | 1.031 MHz |
| Temperature coefficient | 3,868.1 ppm/°C |
| Monotonic over temperature | yes |
| Duty cycle | 45.5–48.7 % |
| Output levels | -0.001 V to 3.301 V |
| Average current | 56.3 µA |
| Runtime | 137.4 s |

It is by far the largest block in the set — 13,773 µm², nearly as much as the
other nine `mbg-d08` blocks put together (15,911 µm²) — and the only one with a
deliberately *large* temperature coefficient: 3,868 ppm/°C is the sensing
mechanism, not an error. Its output swings the full rail cleanly, unlike the ring oscillators.

## Integration status

Ten of the thirteen are instantiated in the `mbg-d08` top level submitted to
the Chipathon (block **BV**, 550 × 1110 µm):

| In `mbg-d08` | Designs |
| :--- | :--- |
| ✅ 5T-OTA ×3 | `ota` · `ota$1` · `ota$2` |
| ✅ StrongArm comparator ×3 | `strongarm_comparator` · `$3` · `$2` |
| ✅ 1.2 V reference ×3 | `vref_1v2` · `$1` · `$2` |
| ✅ Temperature sensor ×1 | `temp_sensor` |
| ❌ Ring oscillator ×3 | generated and verified, but not placed |

The three oscillators are kept in the module library and are included in the
top-level SPICE import list for completeness, but `mbg-d08.gds` contains no
oscillator instance.

## Generation effort

| Design | Runtime (s) | Pre-layout iters | PEX iters | Devil findings | Angel recs |
| :--- | ---: | ---: | ---: | ---: | ---: |
| `gpt-5.6-luna_strongarm_comparator` | 725.1 | 1 | 2 | 5 | 0 |
| `ox_alpha_ota` | 459.0 | 1 | 1 | 2 | 0 |
| `gpt-5.6-luna_oscillator` | 166.6 | 1 | 1 | 3 | 0 |
| `claude-opus-5_temp_sensor` | 137.4 | 1 | 1 | 2 | 0 |
| `ox_alpha_vref_1v2` | 122.9 | 1 | 1 | 2 | 0 |
| `deepseek_vref_1v2` | 115.0 | 1 | 1 | 2 | 0 |
| `gpt-5.6-luna_vref_1v2` | 106.7 | 1 | 1 | 2 | 0 |
| `deepseek_strongarm_comparator` | 88.8 | 1 | 1 | 2 | 0 |
| `ox_alpha_strongarm_comparator` | 70.6 | 1 | 1 | 3 | 0 |
| `gpt-5.6-luna_ota` | 64.5 | 1 | 1 | 2 | 0 |
| `deepseek_oscillator` | 53.3 | 1 | 1 | 2 | 0 |
| `deepseek_ota` | 51.5 | 1 | 1 | 2 | 0 |
| `ox_alpha_oscillator` | 47.2 | 1 | 1 | 2 | 0 |
| **Total** | **2,208.6** | | | | |

Thirteen tapeout-ready analog blocks in **36.8 minutes** of total
flow runtime. Twelve of the thirteen converged in a single PEX iteration;
only the GPT-5.6-Luna comparator needed a second, and it accounts for 33 % of
the total runtime on its own.

## Caveats — read before quoting these numbers

1. **Spec sets are not standardised across models.** Each generated design
   defined its own acceptance metrics, so the counts differ wildly — the
   DeepSeek OTA is checked against 16 metrics, the GPT-5.6-Luna OTA against
   2. "PASS" therefore means *met its own stated specification*, and a design
   with fewer metrics was held to a looser standard. Cross-model comparison
   is only sound where the same quantity was measured (gain and UGF for the
   OTAs; tempco and line regulation for the references).
2. **Metric names and units differ** between models for the same quantity
   (`freq_mhz` vs `frequency_hz` vs `freq_hz`; `i_avg_ua` vs `idd_ma` vs
   `i_avg_a`). Values in the tables above are normalised to a common unit;
   the raw records are not.
3. **These are simulation results, not silicon.** Post-layout means
   parasitic-extracted ngspice, at nominal corner unless a design states
   otherwise. No PVT sweep is claimed here.
4. **DRC clean excludes density.** The metal and poly density rules are
   whole-die coverage minima satisfied by dummy fill at chip integration, not
   by an individual macro. See the top-level README for the eight open items
   on `mbg-d08`.
5. **Two numbers need re-measurement** before publication: the OX-Alpha
   comparator's zero decision time, and the ring-oscillator rail overshoot,
   both flagged in their sections above.

## Per-design artifacts

Every design directory holds the same structure:

```text
<model>_<block>/
├── full_auto_result.json     run record: specs, metrics, sign-off, reviews
├── final_design_report.md    generated narrative report
├── history.json              iteration history
├── review_history.json       Devil / Angel review transcript
├── run.log                   full flow log
├── iterations/run/<cell>/    source SPICE + intermediate layout
├── sim/pre  sim/pex          pre- and post-layout simulation data
└── final/
    ├── <cell>.gds            signed-off layout
    ├── <cell>.pex.spice      parasitic-extracted netlist
    ├── <cell>.lvs.out        netgen LVS report
    ├── <cell>.magic.drc.rpt  Magic DRC report
    ├── <cell>.klayout.lyrdb  KLayout marker database
    ├── drc_summary.json      dual-engine DRC verdict
    └── iteration_history.json
```

---

*Generated from the artifacts in this directory on 2026-08-29.*
