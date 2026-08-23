# PVT Characterization — self-starting ring oscillator (ox-alpha)

Final design, nominal pre-layout `f=53.8 MHz`; extracted (PEX) `f=45.3 MHz`. Each cell: frequency, duty cycle; `*FLAG` marks a specification miss (window: 10-100 MHz, duty 40-60%, VOH>2.97 V, VOL<0.33 V, Iavg<1 mA, >=100 cycles, startup<5 us).

## Pre-layout (schematic) netlist

| corner | 3.0 V, -40 °C | 3.0 V, 27 °C | 3.0 V, 125 °C | 3.3 V, -40 °C | 3.3 V, 27 °C | 3.3 V, 125 °C | 3.6 V, -40 °C | 3.6 V, 27 °C | 3.6 V, 125 °C |
|---|---|---|---|---|---|---|---|---|---|
| typical | 60.4MHz d48.7% | 48.1MHz d48.8% | 37.2MHz d48.9% | 67.7MHz d48.7% | 53.8MHz d48.8% | 41.6MHz d48.9% | 74.4MHz d48.7% | 59.2MHz d48.8% | 45.7MHz d48.9% |
| ss | 53.1MHz d48.7% | 42.5MHz d48.8% | 33.1MHz d48.9% | 60.4MHz d48.7% | 48.2MHz d48.8% | 37.4MHz d48.9% | 67.2MHz d48.7% | 53.6MHz d48.8% | 41.5MHz d49.0% |
| ff | 67.8MHz d48.7% | 53.8MHz d48.8% | 41.5MHz d48.9% | 75.0MHz d48.7% | 59.5MHz d48.8% | 45.8MHz d48.9% | 81.6MHz d48.7% | 64.8MHz d48.8% | 49.9MHz d48.9% |
| sf | 60.8MHz d49.2% | 48.3MHz d49.2% | 37.3MHz d49.3% | 67.8MHz d49.1% | 53.9MHz d49.2% | 41.5MHz d49.3% | 74.4MHz d49.1% | 59.1MHz d49.2% | 45.6MHz d49.3% |
| fs | 59.4MHz d48.2% | 47.4MHz d48.3% | 36.9MHz d48.5% | 66.9MHz d48.3% | 53.3MHz d48.4% | 41.3MHz d48.5% | 73.9MHz d48.3% | 58.9MHz d48.4% | 45.6MHz d48.5% |

## Extracted (PEX) netlist

| corner | 3.0 V, -40 °C | 3.0 V, 27 °C | 3.0 V, 125 °C | 3.3 V, -40 °C | 3.3 V, 27 °C | 3.3 V, 125 °C | 3.6 V, -40 °C | 3.6 V, 27 °C | 3.6 V, 125 °C |
|---|---|---|---|---|---|---|---|---|---|
| typical | 50.6MHz d48.6% | 40.4MHz d48.7% | 31.4MHz d48.8% | 56.9MHz d48.6% | 45.3MHz d48.7% | 35.1MHz d48.8% | 62.7MHz d48.6% | 50.0MHz d48.7% | 38.7MHz d48.8% |
| ss | 44.1MHz d48.6% | 35.4MHz d48.7% | 27.6MHz d48.8% | 50.3MHz d48.6% | 40.2MHz d48.7% | 31.3MHz d48.8% | 56.1MHz d48.6% | 44.8MHz d48.7% | 34.8MHz d48.8% |
| ff | 57.4MHz d48.6% | 45.7MHz d48.7% | 35.3MHz d48.8% | 63.6MHz d48.5% | 50.6MHz d48.7% | 39.0MHz d48.8% | 69.3MHz d48.5% | 55.2MHz d48.7% | 42.6MHz d48.8% |
| sf | 51.1MHz d49.1% | 40.7MHz d49.1% | 31.5MHz d49.3% | 57.2MHz d49.0% | 45.5MHz d49.1% | 35.1MHz d49.3% | 62.8MHz d49.0% | 50.0MHz d49.1% | 38.6MHz d49.2% |
| fs | 49.7MHz d48.1% | 39.8MHz d48.2% | 31.0MHz d48.3% | 56.2MHz d48.1% | 44.8MHz d48.2% | 34.8MHz d48.4% | 62.2MHz d48.1% | 49.6MHz d48.2% | 38.5MHz d48.4% |

**Result:** schematic 45/45 points pass all specs; extracted 45/45 points pass.
PEX frequency range across the full grid: 27.6 - 69.3 MHz.

Simulation model: flattened GF180MCU ngspice parameter library (value-identical, see pdk_flat/); ideal DC power-up, no stimulus, no forced initial conditions anywhere.
