# PVT characterisation — temp_sensor

48 simulated operating points sch: 48.

Every point is an independent transient from a 0 V power-up ramp with `uic`; no point reuses another point's state, and none uses a forced initial condition.


## F(T) curve — schematic (pre-layout)

Frequency in kHz at every characterised temperature point.


**VDD = 3.0 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 825.9 | 935.7 | 1048.1 | 1125.8 | 1232.5 | 1349.7 | 1464.4 | 1569.3 | rising | +3890 | +4095 |
| ss | 555.0 | 629.5 | 706.7 | 760.3 | 833.8 | 915.0 | 996.6 | 1076.2 | rising | +4013 | +4180 |
| ff | — | — | — | — | — | — | — | — | — | — | — |
| sf | — | — | — | — | — | — | — | — | — | — | — |
| fs | — | — | — | — | — | — | — | — | — | — | — |

**VDD = 3.3 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 791.5 | 897.7 | 1006.8 | 1082.0 | 1184.5 | 1297.1 | 1409.7 | 1518.6 | rising | +3949 | +4106 |
| ss | 533.1 | 605.5 | 680.6 | 732.7 | 804.1 | 882.2 | 960.8 | 1038.9 | rising | +4044 | +4213 |
| ff | — | — | — | — | — | — | — | — | — | — | — |
| sf | — | — | — | — | — | — | — | — | — | — | — |
| fs | — | — | — | — | — | — | — | — | — | — | — |

**VDD = 3.6 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 756.2 | 859.0 | 964.9 | 1038.0 | 1137.6 | 1246.3 | 1355.2 | 1462.5 | rising | +3997 | +4161 |
| ss | 511.9 | 581.7 | 654.3 | 704.8 | 774.1 | 849.9 | 925.7 | 1001.2 | rising | +4065 | +4250 |
| ff | — | — | — | — | — | — | — | — | — | — | — |
| sf | — | — | — | — | — | — | — | — | — | — | — |
| fs | — | — | — | — | — | — | — | — | — | — | — |

## Monotonicity and sensitivity, per supply

| netlist | VDD | corners monotonic | TC_mean min | TC_mean max | TC_27 min | TC_27 max |
|---|---:|---|---:|---:|---:|---:|
| sch | 3.0 | 2/2 | +3890 | +4013 | +4095 | +4180 |
| sch | 3.3 | 2/2 | +3949 | +4044 | +4106 | +4213 |
| sch | 3.6 | 2/2 | +3997 | +4065 | +4161 | +4250 |

## Worst case across the whole grid

| netlist | metric | worst value | limit | verdict |
|---|---|---:|---:|---|
| sch | TEMP_OUT high (min) | 3.001 V | >= 2.97 V | PASS |
| sch | TEMP_OUT low (max) | -0.001305 V | <= 0.33 V | PASS |
| sch | duty cycle (min) | 45.28 % | >= 40 % | PASS |
| sch | duty cycle (max) | 49.31 % | <= 60 % | PASS |
| sch | avg supply current (max) | 59.54 uA | <= 200 uA | PASS |
| sch | sustained cycles (min) | 117  | >= 100  | PASS |
| sch | start-up time (max) | 1.981 us | <= 10 us | PASS |

## Points failing any per-corner limit

None — all 48 simulated points meet every limit.

