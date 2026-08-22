Design a **self-starting oscillator** using the Microelectronic-Block-Generator framework with the **GF180MCU `gf180mcuD` PDK**.

Follow the existing MBG SKILL for the complete workflow.

## Result Directory

Store all results in:

```text
results/{model_name}_oscillator
```

Examples: `deepseek_oscillator`, `ox_alpha_oscillator`, `chatgpt_oscillator`.

## Ports

Use exactly:

```text
VDD VSS OSC_OUT
```

Top-level:

```spice
.subckt oscillator VDD VSS OSC_OUT
```

Do not add CLK, START, ENABLE, RESET, IBIAS, or VBIAS.

The oscillator must start automatically from normal power-up.

## Technology

```text
PDK : gf180mcuD
VDD : 3.3 V
VSS : 0 V
```

Use MOSFET devices supported by GF180MCU, preferably `nfet_03v3` and `pfet_03v3`.

## Nominal Conditions

```text
VDD  = 3.3 V
TEMP = 27 °C
```

## Specifications

| Parameter | Target |
|---|---:|
| Autonomous startup | Required |
| Frequency | 10–100 MHz |
| Startup time | < 5 µs |
| Duty cycle | 40–60% |
| OSC_OUT high | > 2.97 V |
| OSC_OUT low | < 0.33 V |
| Average supply current | < 1 mA |
| Sustained oscillation | ≥ 100 cycles |

The final acceptance simulation must not depend on an external startup pulse or forced internal initial condition.

## PVT

Characterize at:

```text
VDD  = 3.0, 3.3, 3.6 V
TEMP = -40, 27, 125 °C
```

and meaningful available process corners.

A CMOS ring oscillator is preferred, but independently choose the stage count and sizing. Prefer the simplest topology that remains self-starting after PEX.