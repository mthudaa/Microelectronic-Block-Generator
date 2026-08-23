Design a **Strong-Arm clocked comparator** using the Microelectronic-Block-Generator framework with the **GF180MCU `gf180mcuD` PDK**.

Follow the existing MBG SKILL for the complete design, optimization, layout, verification, PEX, and reporting workflow.

## Result Directory

Store all results in:

```text
results/{model_name}_strongarm_comparator
```

Examples:

```text
results/deepseek_strongarm_comparator
results/ox_alpha_strongarm_comparator
results/chatgpt_strongarm_comparator
```

## Ports

Use exactly:

```text
VDD VSS INP INN CLK OUTP OUTN
```

Top-level:

```spice
.subckt strongarm_comparator VDD VSS INP INN CLK OUTP OUTN
```

`CLK` is the comparator evaluation clock.

The comparator must provide fully differential outputs `OUTP` and `OUTN`.

## Technology

```text
PDK : gf180mcuD
VDD : 3.3 V
VSS : 0 V
```

Use **MOSFET-only circuitry**, preferably GF180MCU `nfet_03v3` and `pfet_03v3`.

Do not use:

- BJTs;
- explicit resistors;
- explicit capacitors inside the comparator core;
- ideal/behavioral comparator elements.

## Nominal Conditions

```text
VDD     = 3.3 V
VCM     = 1.65 V
TEMP    = 27 °C
CLK     = 10 MHz
CL_OUTP = 20 fF
CL_OUTN = 20 fF
```

The output loads are testbench components only.

## Specifications

| Parameter | Target |
|---|---:|
| Architecture | Strong-Arm dynamic latch comparator |
| Minimum differential input | ≤ 5 mV |
| Decision correctness at ±5 mV input | Required |
| Decision time | ≤ 5 ns |
| Output differential swing | ≥ 90% of VDD |
| Static current between comparisons | Approximately 0 |
| Average current @ 10 MHz | ≤ 500 µA |
| Input common-mode range | At least 1.0–2.3 V |
| Reset/precharge operation | Required |
| Regenerative evaluation | Required |

Characterize comparator delay versus differential input for at least:

```text
|VIN_DIFF| = 5 mV
             10 mV
             25 mV
             50 mV
             100 mV
```

Test both input polarities:

```text
INP > INN
INP < INN
```

## Offset and Monte Carlo

Where supported by the GF180 simulation flow, characterize input-referred offset using mismatch Monte Carlo simulation.

Target:

```text
1σ input-referred offset ≤ 10 mV
```

Report:

```text
mean offset
1σ offset
3σ offset
number of Monte Carlo runs
```

If mismatch Monte Carlo is unavailable, clearly report it as not verified rather than estimating the value.

## PVT

Characterize at:

```text
VDD  = 3.0, 3.3, 3.6 V
TEMP = -40, 27, 125 °C
```

and meaningful GF180 process corners available in the PDK.

At each tested condition verify:

- correct reset/precharge;
- correct regeneration;
- correct decision polarity;
- decision delay;
- output swing.

Choose and size the **Strong-Arm topology independently** for reliable post-layout operation. Pay particular attention to differential-pair matching, regenerative latch symmetry, clock-device sizing, parasitic imbalance, and post-PEX decision delay.

Do not simply copy an existing comparator example from the repository.