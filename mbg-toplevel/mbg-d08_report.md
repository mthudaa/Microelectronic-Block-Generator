# MBG-D08 pre/post-layout verification report

Date: 2026-08-28  
Layout: `layout/mbg-d08.gds`  
Technology: GF180MCU-D, 5LM, nominal 3.3 V

## Result summary

| Check | Result |
|---|---|
| Pre-layout top-level ngspice simulation | PASS — 100 µs run completed; sensor oscillates |
| Post-layout top-level ngspice simulation | PASS — 100 µs PEX run completed; sensor oscillates |
| KLayout LVS | PASS — netlists match |
| KLayout DRC | CLEAN for completed rule tables; 0 reported violation items |

The KLayout DRC driver also logged an exception in the optional `mslot` rule table (`undefined method sized for nil`). The driver continued with the other tables and reported the aggregate run clean; this table should be rerun/fixed before treating the result as unconditional signoff.

## Netlists and mapping

The generated pre-simulation netlist is [mbg-d08_pre_sim.spice](/foss/designs/mbg-toplevel/mbg-d08_pre_sim.spice). It includes all 14 files in `spice/` as subcircuit sources. The three legacy oscillator subcircuits are included but not instantiated; the new `temp_sensor` GDS cell is instantiated as the Claude Opus 5 relaxation-oscillator temperature sensor.

| GDS cell | Referenced SPICE subcircuit |
|---|---|
| `ota` | `deepseek_ota` |
| `ota$1` | `gpt-5.6-luna_ota` |
| `ota$2` | `ox_alpha_ota` |
| `strongarm_comparator` | `deepseek_strongarm_comparator` |
| `strongarm_comparator$3` | `gpt-5.6-luna_strongarm_comparator` |
| `strongarm_comparator$2` | `ox_alpha_strongarm_comparator` |
| `vref_1v2` | `deepseek_vref_1v2` |
| `vref_1v2$1` | `gpt-5.6-luna_vref_1v2` |
| `vref_1v2$2` | `ox_alpha_vref_1v2` |
| `temp_sensor` | `claude-opus-5_temp_sensor` |
| `io_secondary_3p3` | `io_secondary_3p3` |

The named top-level pads include `VDD`, `VSS`, `CLK`, `INP`, `INN`, `IBIAS`, `TEMP_OUT`, nine named analog outputs, and the `io_secondary_3p3` pad cells. `TEMP_OUT` was included after confirming it is a named GDS port.

The active GF180 model library is loaded once in the top-level simulation decks. The `mimcap_typical` section is also loaded for the sensor's M4/M5 2 fF/µm² timing capacitor. The sensor's poly resistor and MIM capacitor use the GF180-required `r_width/r_length` and `c_width/c_length` parameters.

## Simulation setup

The testbenches are [mbg-d08_pre_tb.spice](/foss/designs/mbg-toplevel/mbg-d08_pre_tb.spice) and [mbg-d08_post_tb.spice](/foss/designs/mbg-toplevel/mbg-d08_post_tb.spice). Their stimulus follows the patterns in `/foss/designs/results`: 3.3 V supply, 20 µA bias, 1.65 V common-mode inputs, 10 µs clock period with 5 µs high time, 27 °C, and a 1 ns to 100 µs transient analysis. The inputs use a single complementary linear ramp: `INP` is -200 mV to +200 mV relative to common mode while `INN` is +200 mV to -200 mV. Therefore, the actual pins ramp 1.45 V to 1.85 V and 1.85 V to 1.45 V over 100 µs, and `V(INP)-V(INN)` ramps -400 mV to +400 mV.

### Operating point

| Output | Pre-layout (V) | Post-layout (V) |
|---|---:|---:|
| `deepseek_ota` | 0.461669 | 0.467198 |
| `gpt_ota` | 0.533016 | 0.535390 |
| `oxa_ota` | 3.299819 | 3.299820 |
| `deepseek_cmp` | 3.299980 | 3.299981 |
| `gpt_cmp` | 3.299983 | 3.299984 |
| `oxa_cmp` | 3.299974 | 3.299976 |
| `deepseek_vref` | 0.984673 | 0.979306 |
| `gpt_vref` | 0.960434 | 0.961217 |
| `oxa_vref` | 0.953484 | 0.952775 |
| `temp_out` | 1.030780 | 1.030780 |

### Transient ranges over 0–100 µs

| Output | Pre-layout min–max (V) | Post-layout min–max (V) |
|---|---:|---:|
| `deepseek_ota` | 0.461536–3.297381 | 0.466708–3.297999 |
| `gpt_ota` | 0.532884–3.299909 | 0.535012–3.299912 |
| `oxa_ota` | 0.497873–3.299814 | 0.500000–3.299844 |
| `deepseek_cmp` | -0.003484–3.357636 | -0.005077–3.352012 |
| `gpt_cmp` | 3.127698–3.343060 | 3.060043–3.343027 |
| `oxa_cmp` | 3.209509–3.325152 | 3.171269–3.327072 |
| `deepseek_vref` | 0.984673–0.984674 | 0.978645–0.979969 |
| `gpt_vref` | 0.960433–0.960435 | 0.961157–0.961276 |
| `oxa_vref` | 0.953483–0.953485 | 0.952715–0.952834 |
| `temp_out` | -0.001409–3.301228 | -0.001173–3.301020 |
| `INP-INN` | -0.400000–0.400000 | -0.400000–0.400000 |

Both simulations completed without ngspice errors and wrote 100,599 pre-layout and 100,519 post-layout transient data rows, respectively, through 100.000 µs.

### Simulation plot

The figure below overlays the pre-layout and post-layout top-level transient results for the 100 µs run with a 10 µs clock period. It includes the ten monitored outputs, including the new `temp_out` waveform, and the complementary `INP/INN` differential ramp. Time is shown in µs, output voltage in V, and differential input in mV.

![MBG-D08 pre-layout versus post-layout transient simulation](/foss/designs/mbg-toplevel/mbg-d08_simulation_plot.png)

### Claude Opus 5 relaxation-oscillator temperature sensor

The new `temp_sensor` layout cell is connected to the named `temp_out` pad through `io_secondary_3p3`. Its source is [claude-opus-5_temp_sensor.spice](/foss/designs/mbg-toplevel/spice/claude-opus-5_temp_sensor.spice): a self-starting beta-multiplier/PTAT reference, 35 kΩ poly degeneration resistor, 34 µm × 34 µm M4/M5 MIM timing capacitor, Schmitt trigger, and output buffer. It produces a continuous rail-to-rail relaxation waveform at 27 °C.

| View | Rising edges in 100 µs | Median period | Frequency | Extraction shift |
|---|---:|---:|---:|---:|
| Pre-layout | 107 | 941.5 ns | 1.062 MHz | — |
| Post-layout PEX | 101 | 998.0 ns | 1.002 MHz | -5.66% |

The sensor waveform and frequency comparison are shown below. The standalone PVT corner runs were not used for signoff because the isolated closed-loop oscillator remains numerically startup-sensitive; the verified top-level pre- and post-layout runs include the real `temp_out` pad and demonstrate startup plus sustained oscillation. Temperature-to-frequency calibration still needs a dedicated PVT characterization with a defined power-up/noise protocol.

![Claude Opus 5 temperature-sensor simulation](/foss/designs/mbg-toplevel/temp_sensor_simulation_plot.png)

### Comparator behavior

The comparator cells are clocked strong-arm latches with pins `VDD VSS INP INN CLK OUTP OUTN`. The top-level netlist connects each named comparator output pad to `OUTP` (for example, `deepseek_cmp_core`) and keeps `OUTN` internal (`deepseek_cmp_n`). Consequently, the report plot shows only one side of each differential comparator output. During the reset phase, both latch outputs are precharged near `VDD`; the decision is visible during the active clock phase and should be interpreted together with the complementary `OUTN` node.

In this 10 µs-clock run, the exported `OUTP` ranges were `-3.5 mV..3.358 V` pre-layout and `-5.1 mV..3.352 V` post-layout for `deepseek_cmp`, but only `3.128..3.343 V` / `3.059..3.343 V` for `gpt_cmp` and `3.210..3.325 V` / `3.171..3.327 V` for `oxa_cmp`. This means the single exported node does not provide a clean rail-to-rail logic indication for all three supplied comparator subcircuits; the clock-correlated pulses are latch activity, not a static comparator output. A functional signoff should expose or probe both `OUTP` and `OUTN` and sample them after the active clock edge.

### Standalone comparator + `io_secondary_3p3` diagnostic

Each supplied comparator was simulated separately with `io_secondary_3p3` on `INP`, `INN`, `CLK`, `OUTP`, and `OUTN`. The test used the same 3.3 V supply, 10 µs clock period (5 µs high), 100 µs transient, and complementary input ramp. Both the comparator core nodes and the external pad-side nodes were saved. The standalone decks used a 100 ns transient reporting interval with Gear integration to make the regenerative latch/IO network converge; the source clock edges remain 0.1 ns.

| Comparator | `OUTP` core min–max (V) | `OUTN` core min–max (V) | `OUTP` pad min–max (V) | `OUTN` pad min–max (V) |
|---|---:|---:|---:|---:|
| deepseek | -0.0058–3.3213 | -0.0058–3.3213 | -0.0024–3.3211 | -0.0024–3.3211 |
| gpt-5.6-luna | -0.0172–3.3277 | -0.0172–3.3277 | -0.0065–3.3216 | -0.0065–3.3216 |
| ox-alpha | -0.0075–3.3123 | -0.0075–3.3123 | -0.0027–3.3093 | -0.0027–3.3093 |

At settled active-clock sample points, all three models produce complementary outputs: for negative differential input, `OUTP` is low and `OUTN` is high; for positive differential input, `OUTP` is high and `OUTN` is low. Deepseek and ox-alpha switch between the -60 mV and +20 mV sampled points. GPT-5.6-luna remains in the negative-input state at +20 mV and switches by the +100 mV sampled point, indicating a larger positive input-referred offset or slower regeneration in this simplified model. During the low-clock reset phase, both outputs return high by design.

The pad-side traces closely follow their corresponding core nodes, so `io_secondary_3p3` is not the primary cause of the logic-level problem. Its maximum transient core-to-pad differences were approximately 56 mV (deepseek), 63 mV (gpt-5.6-luna), and 34 mV (ox-alpha). The larger issue is that these supplied cells are bare dynamic strong-arm latches with differential `OUTP/OUTN` nodes and no output buffer. The top-level netlist exports only `OUTP` and leaves `OUTN` internal; therefore a single exported waveform can look stuck high during reset or fail to show the valid complementary decision. Both outputs should be routed/probed and interpreted only after the active clock edge, or followed by an explicit single-ended sense/buffer stage.

The standalone result plot is [cmp_io_simulation_plot.png](/foss/designs/mbg-toplevel/cmp_debug/cmp_io_simulation_plot.png). The individual testbenches and logs are [deepseek_cmp_io_tb.spice](/foss/designs/mbg-toplevel/cmp_debug/deepseek_cmp_io_tb.spice), [gpt_luna_cmp_io_tb.spice](/foss/designs/mbg-toplevel/cmp_debug/gpt_luna_cmp_io_tb.spice), [oxa_cmp_io_tb.spice](/foss/designs/mbg-toplevel/cmp_debug/oxa_cmp_io_tb.spice), [deepseek_cmp_io.log](/foss/designs/mbg-toplevel/cmp_debug/deepseek_cmp_io.log), [gpt_luna_cmp_io.log](/foss/designs/mbg-toplevel/cmp_debug/gpt_luna_cmp_io.log), and [oxa_cmp_io.log](/foss/designs/mbg-toplevel/cmp_debug/oxa_cmp_io.log). All three standalone ngspice runs completed with exit code 0 and no fatal/convergence errors.

## Post-layout extraction

Magic was rerun in coupled-capacitance mode (`m=2`, subcircuit output enabled). The extracted file is [post_sim/mbg-d08.pex.spice](/foss/designs/mbg-toplevel/post_sim/mbg-d08.pex.spice), which now includes the `temp_sensor` MOS devices, 35 kΩ resistor, MIM capacitor, and `temp_out` pad parasitics. It contains the physical-unit output from `ext2spice scale off`; this is required for correct extracted diode area/perimeter values in ngspice. The extraction log is [post_sim/pex_run.log](/foss/designs/mbg-toplevel/post_sim/pex_run.log). Magic completed extraction but logged that a duplicate `via_dev$8` placement was ignored while reading the GDS.

## DRC

KLayout GF180MCU-D DRC was run with variant `C` (`metal_top=9K`, `metal_level=5LM`, MIM option B), deep mode, and two worker threads. The aggregate log is [drc_run/drc_run.log](/foss/designs/mbg-toplevel/drc_run/drc_run.log).

The run generated 51 `.lyrdb` databases. XML inspection found zero `<items>` in all completed databases. The driver reported `Klayout DRC run is clean. GDS has no DRC violations.` The `mslot` exception noted above is recorded in the same log.

## LVS

KLayout LVS used the GF180MCU-D 5LM/9K runset and explicit cell mappings for the three OTA, comparator, voltage-reference, and new `temp_sensor` variants. The source topology file is [mbg-d08_lvs.spice](/foss/designs/mbg-toplevel/mbg-d08_lvs.spice); it is an LVS-only native-MOS representation of the supplied module topologies. The mapped sensor comparison contains 18 MOS devices and the 35 kΩ poly resistor. The GF180 LVS runset extracts the MIM-cap geometry but does not emit that device into the comparison netlist, so the LVS source follows the runset representation.

The LVS log is [lvs_run/mbg-d08_lvs.log](/foss/designs/mbg-toplevel/lvs_run/mbg-d08_lvs.log), the extracted comparison netlist is [lvs_run/mbg-d08_lvs_extracted.cir](/foss/designs/mbg-toplevel/lvs_run/mbg-d08_lvs_extracted.cir), and the KLayout database is [lvs_run/mbg-d08_lvs.lvsdb](/foss/designs/mbg-toplevel/lvs_run/mbg-d08_lvs.lvsdb). The log ends with `INFO : Congratulations! Netlists match.`

## Simulation artifacts

- [mbg-d08_pre_tb.log](/foss/designs/mbg-toplevel/mbg-d08_pre_tb.log)
- [mbg-d08_pre_tr.dat](/foss/designs/mbg-toplevel/mbg-d08_pre_tr.dat)
- [mbg-d08_post_tb.log](/foss/designs/mbg-toplevel/mbg-d08_post_tb.log)
- [mbg-d08_post_tr.dat](/foss/designs/mbg-toplevel/mbg-d08_post_tr.dat)
- [temp_sensor_simulation_plot.png](/foss/designs/mbg-toplevel/temp_sensor_simulation_plot.png)
- [post_sim/mbg-d08.pex.spice](/foss/designs/mbg-toplevel/post_sim/mbg-d08.pex.spice)
- [cmp_debug/cmp_io_simulation_plot.png](/foss/designs/mbg-toplevel/cmp_debug/cmp_io_simulation_plot.png)
- [cmp_debug/deepseek_cmp_io_tr.dat](/foss/designs/mbg-toplevel/cmp_debug/deepseek_cmp_io_tr.dat)
- [cmp_debug/gpt_luna_cmp_io_tr.dat](/foss/designs/mbg-toplevel/cmp_debug/gpt_luna_cmp_io_tr.dat)
- [cmp_debug/oxa_cmp_io_tr.dat](/foss/designs/mbg-toplevel/cmp_debug/oxa_cmp_io_tr.dat)
