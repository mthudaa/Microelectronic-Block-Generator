Design a **self-starting relaxation-oscillator-based temperature sensor** using the Microelectronic-Block-Generator framework with the **GF180MCU `gf180mcuD` PDK**.

Follow the existing MBG SKILL for the complete workflow.

## Result Directory

Store all results in:

```text
results/{model_name}_temp_sensor
```

Examples: `deepseek_temp_sensor`, `ox_alpha_temp_sensor`, `chatgpt_temp_sensor`.

## Ports

Use exactly:

```text
VDD VSS TEMP_OUT
```

Top-level:

```spice
.subckt temp_sensor VDD VSS TEMP_OUT
```

Do not add CLK, START, ENABLE, RESET, IBIAS, VBIAS, or TRIM.

The sensor must self-bias and self-start from normal power-up — no external reference current, no forced initial condition, no calibration input.

## Technology

```text
PDK : gf180mcuD
VDD : 3.3 V
VSS : 0 V
```

Use MOSFET devices supported by GF180MCU (`nfet_03v3` / `pfet_03v3`). Native passives (`ppolyf_u` resistor, metal4/metal5 MIM cap, or MOS cap) are expected for the timing element and/or bias generator — this is a required stress point for the framework's native-passive support, not optional.

## Nominal Conditions

```text
VDD  = 3.3 V
TEMP = 27 °C
```

## Specifications

| Parameter | Target |
|---|---:|
| Autonomous startup | Required (no external pulse or forced IC) |
| Nominal frequency @ 27 °C | 100 kHz – 2 MHz |
| Frequency vs. temperature | Strictly monotonic, −40 °C to 125 °C |
| Temperature sensitivity | 2000–6000 ppm/°C (uncalibrated, single-point) |
| Startup time | < 10 µs |
| Duty cycle | 40–60% |
| TEMP_OUT high | > 2.97 V |
| TEMP_OUT low | < 0.33 V |
| Average supply current | < 200 µA |
| Sustained oscillation | ≥ 100 cycles at every corner |

The final acceptance simulation must not depend on an external startup pulse or forced internal initial condition. The design report must include the measured **F(T) curve** — frequency at every characterized temperature point, per corner — not just a pass/fail at nominal.

## PVT

Characterize at:

```text
VDD  = 3.0, 3.3, 3.6 V
TEMP = -40, -15, 10, 27, 50, 75, 100, 125 °C
```

and meaningful available process corners. Report monotonicity and sensitivity (ppm/°C) at each VDD, not only at 3.3 V.

## Preferred Topology

A relaxation oscillator built from:

1. A PTAT/CTAT (or beta-multiplier-style) bias generator setting a temperature-dependent charge/discharge current — no external `IBIAS`/`VBIAS` pin; the reference is internal.
2. A native-passive RC (or MOS-cap) timing core charged/discharged by that current through switch devices.
3. A hysteresis comparator (Schmitt-trigger style) sensing the timing-cap voltage.
4. A cross-coupled latch / inverter buffer closing the feedback loop and driving `TEMP_OUT` rail-to-rail.

Independently choose stage sizing, comparator threshold spacing, and bias-generator topology. Keep the design flat (single `.subckt` — MBG does not flatten nested subcircuits). Prefer the simplest topology that remains self-starting and monotonic after PEX; do not over-optimize frequency stability at the expense of temperature sensitivity — unlike a clock-reference oscillator, drift-with-temperature here is the signal, not the error.