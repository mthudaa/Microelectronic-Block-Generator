# PVT characterisation — temp_sensor

240 simulated operating points pex: 120, sch: 120.

Every point is an independent transient from a 0 V power-up ramp with `uic`; no point reuses another point's state, and none uses a forced initial condition.


## F(T) curve — extracted (PEX)

Frequency in kHz at every characterised temperature point.


**VDD = 3.0 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 790.1 | 892.7 | 997.6 | 1070.1 | 1169.7 | 1279.0 | 1385.6 | 1482.7 | rising | +3815 | +4022 |
| ss | 532.2 | 602.2 | 674.6 | 724.6 | 793.4 | 869.4 | 945.5 | 1019.6 | rising | +3941 | +4099 |
| ff | 1259.2 | 1418.1 | 1581.0 | 1694.4 | 1848.6 | 2010.1 | 2140.2 | 2156.0 | rising | +3259 | +3948 |
| sf | 822.0 | 929.1 | 1038.1 | 1113.0 | 1215.9 | 1328.5 | 1437.5 | 1532.6 | rising | +3775 | +3995 |
| fs | 760.4 | 858.7 | 959.4 | 1029.4 | 1126.0 | 1231.8 | 1335.1 | 1427.8 | rising | +3818 | +4045 |

**VDD = 3.3 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 759.3 | 858.9 | 960.8 | 1030.8 | 1126.4 | 1231.4 | 1336.2 | 1437.4 | rising | +3868 | +4015 |
| ss | 512.7 | 581.0 | 651.5 | 700.3 | 767.0 | 839.9 | 913.4 | 986.2 | rising | +3965 | +4121 |
| ff | 1205.9 | 1360.6 | 1517.5 | 1626.1 | 1775.3 | 1936.6 | 2089.7 | 2218.0 | rising | +3693 | +3963 |
| sf | 790.6 | 894.7 | 1000.8 | 1073.4 | 1172.1 | 1280.2 | 1387.8 | 1491.0 | rising | +3845 | +3989 |
| fs | 729.4 | 824.8 | 922.6 | 990.1 | 1082.6 | 1184.6 | 1286.6 | 1385.1 | rising | +3887 | +4039 |

**VDD = 3.6 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 727.3 | 823.9 | 923.1 | 991.4 | 1084.1 | 1185.3 | 1286.8 | 1386.5 | rising | +3911 | +4060 |
| ss | 493.6 | 559.7 | 628.1 | 675.5 | 740.4 | 811.1 | 881.8 | 952.2 | rising | +3982 | +4156 |
| ff | 1152.1 | 1303.0 | 1456.1 | 1561.0 | 1704.8 | 1862.2 | 2016.0 | 2159.1 | rising | +3807 | +3983 |
| sf | 758.4 | 859.3 | 962.6 | 1033.5 | 1129.5 | 1233.6 | 1337.5 | 1439.4 | rising | +3884 | +4035 |
| fs | 697.5 | 790.0 | 885.2 | 950.9 | 1040.5 | 1138.8 | 1237.8 | 1335.3 | rising | +3935 | +4083 |

## F(T) curve — schematic (pre-layout)

Frequency in kHz at every characterised temperature point.


**VDD = 3.0 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 825.9 | 935.7 | 1048.1 | 1125.8 | 1232.5 | 1349.7 | 1464.4 | 1569.3 | rising | +3890 | +4095 |
| ss | 555.0 | 629.5 | 706.7 | 760.3 | 833.8 | 915.0 | 996.6 | 1076.2 | rising | +4013 | +4180 |
| ff | 1321.8 | 1492.6 | 1667.4 | 1789.1 | 1954.7 | 2128.8 | 2270.0 | 2289.2 | rising | +3328 | +4014 |
| sf | 859.9 | 974.6 | 1091.7 | 1172.1 | 1282.4 | 1403.0 | 1520.2 | 1622.9 | rising | +3850 | +4067 |
| fs | 794.3 | 899.2 | 1007.0 | 1081.9 | 1185.2 | 1298.6 | 1409.8 | 1510.0 | rising | +3894 | +4116 |

**VDD = 3.3 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 791.5 | 897.7 | 1006.8 | 1082.0 | 1184.5 | 1297.1 | 1409.7 | 1518.6 | rising | +3949 | +4106 |
| ss | 533.1 | 605.5 | 680.6 | 732.7 | 804.1 | 882.2 | 960.8 | 1038.9 | rising | +4044 | +4213 |
| ff | 1262.5 | 1428.5 | 1597.4 | 1714.0 | 1874.2 | 2047.7 | 2213.0 | 2352.2 | rising | +3771 | +4037 |
| sf | 824.8 | 935.9 | 1049.6 | 1127.7 | 1233.7 | 1349.7 | 1465.1 | 1576.2 | rising | +3925 | +4082 |
| fs | 759.7 | 861.3 | 965.8 | 1038.1 | 1137.2 | 1246.5 | 1355.9 | 1462.1 | rising | +3968 | +4127 |

**VDD = 3.6 V**

| corner | -40 C | -15 C | 10 C | 27 C | 50 C | 75 C | 100 C | 125 C | monotonic | TC_mean ppm/C | TC_27 ppm/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|---:|---:|
| typical | 756.2 | 859.0 | 964.9 | 1038.0 | 1137.6 | 1246.3 | 1355.2 | 1462.5 | rising | +3997 | +4161 |
| ss | 511.9 | 581.7 | 654.3 | 704.8 | 774.1 | 849.9 | 925.7 | 1001.2 | rising | +4065 | +4250 |
| ff | 1203.4 | 1365.0 | 1529.6 | 1642.5 | 1796.9 | 1966.1 | 2131.8 | 2286.3 | rising | +3890 | +4070 |
| sf | 789.2 | 896.7 | 1007.1 | 1083.1 | 1186.3 | 1298.2 | 1409.8 | 1519.3 | rising | +3969 | +4135 |
| fs | 724.7 | 823.0 | 924.4 | 994.7 | 1090.7 | 1196.1 | 1302.2 | 1407.1 | rising | +4021 | +4181 |

## Monotonicity and sensitivity, per supply

| netlist | VDD | corners monotonic | TC_mean min | TC_mean max | TC_27 min | TC_27 max |
|---|---:|---|---:|---:|---:|---:|
| pex | 3.0 | 5/5 | +3259 | +3941 | +3948 | +4099 |
| pex | 3.3 | 5/5 | +3693 | +3965 | +3963 | +4121 |
| pex | 3.6 | 5/5 | +3807 | +3982 | +3983 | +4156 |
| sch | 3.0 | 5/5 | +3328 | +4013 | +4014 | +4180 |
| sch | 3.3 | 5/5 | +3771 | +4044 | +4037 | +4213 |
| sch | 3.6 | 5/5 | +3890 | +4065 | +4070 | +4250 |

## Worst case across the whole grid

| netlist | metric | worst value | limit | verdict |
|---|---|---:|---:|---|
| pex | TEMP_OUT high (min) | 3.001 V | >= 2.97 V | PASS |
| pex | TEMP_OUT low (max) | -0.0009271 V | <= 0.33 V | PASS |
| pex | duty cycle (min) | 45.25 % | >= 40 % | PASS |
| pex | duty cycle (max) | 51.35 % | <= 60 % | PASS |
| pex | avg supply current (max) | 87.85 uA | <= 200 uA | PASS |
| pex | sustained cycles (min) | 120  | >= 100  | PASS |
| pex | start-up time (max) | 2.009 us | <= 10 us | PASS |
| sch | TEMP_OUT high (min) | 3.001 V | >= 2.97 V | PASS |
| sch | TEMP_OUT low (max) | -0.001092 V | <= 0.33 V | PASS |
| sch | duty cycle (min) | 45.28 % | >= 40 % | PASS |
| sch | duty cycle (max) | 51.13 % | <= 60 % | PASS |
| sch | avg supply current (max) | 87.17 uA | <= 200 uA | PASS |
| sch | sustained cycles (min) | 117  | >= 100  | PASS |
| sch | start-up time (max) | 1.981 us | <= 10 us | PASS |

## Points failing any per-corner limit

None — all 240 simulated points meet every limit.

