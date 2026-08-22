Design an **Operational Transconductance Amplifier (OTA)** using the Microelectronic-Block-Generator framework with the **GF180MCU `gf180mcuD` PDK**.

Follow the existing MBG SKILL for the full design, optimization, layout, verification, PEX, and reporting workflow.

## Result Directory

Store all results in:

```text
results/{model_name}_ota
```

Examples: `deepseek_ota`, `ox_alpha_ota`, `chatgpt_ota`.

## Ports

Use exactly:

```text
VDD VSS INP INN OUT IBIAS
```

Top-level:

```spice
.subckt ota VDD VSS INP INN OUT IBIAS
```

`IBIAS` is an external bias current input.

## Technology

```text
PDK  : gf180mcuD
VDD  : 3.3 V
VSS  : 0 V
```

Use MOSFET devices supported by GF180MCU, preferably `nfet_03v3` and `pfet_03v3`.

## Nominal Conditions

```text
VDD    = 3.3 V
IBIAS  = 20 µA
VIN_CM = 1.65 V
CL     = 5 pF
TEMP   = 27 °C
```

## Specifications

| Parameter | Target |
|---|---:|
| DC gain | ≥ 35 dB |
| GBW | ≥ 1 MHz |
| Phase margin | ≥ 60° |
| Rising slew rate | ≥ 0.5 V/µs |
| Falling slew rate | ≥ 0.5 V/µs |
| Supply current excluding IBIAS | ≤ 250 µA |
| Output DC at zero differential input | 1.65 V ± 0.5 V |
| Usable output swing | ≥ 0.5–2.8 V |
| Load | 5 pF |

Also characterize CMRR, PSRR, input common-mode range, power, noise, and offset where supported.

## PVT

Characterize at:

```text
VDD  = 3.0, 3.3, 3.6 V
TEMP = -40, 27, 125 °C
```

and meaningful GF180 process corners available in the PDK.

Choose the simplest OTA topology that can satisfy the specifications after post-layout extraction. Do not simply copy an existing repository example.