.include '/home/huda/.volare/gf180mcuD/libs.tech/ngspice/design.ngspice'
.lib '/home/huda/opensource-project/Microelectronic-Block-Generator/results/claude-opus-5_temp_sensor/pdk_flat/sm141064.ngspice' fs
.lib '/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice' res_typical
.lib '/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice' mimcap_typical
.options reltol=1e-4 vntol=1e-8 abstol=1e-15 chgtol=1e-16 trtol=1
.temp -15

* PEX produced on Fri Aug 28 10:19:36 PM CST 2026 using /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D/scripts/iic-pex.sh with m=2 and s=1
* NGSPICE file created from temp_sensor.ext - technology: gf180mcuD

.option scale=5n

.subckt temp_sensor TEMP_OUT VSS VDD
X0 a_14_27788# VSS cap_mim_2f0_m4m5_noshield c_width=3.4e-05 c_length=3.4e-05
X1 a_n4870_24770# VSS VSS ppolyf_u r_width=1e-06 r_length=0.0001
X2 a_n5902_27790# VSS VDD VDD pfet_03v3 ad=14.4n pd=0.48m as=14.4n ps=0.48m w=120 l=1900
X3 TEMP_OUT a_686_21744# VDD VDD pfet_03v3 ad=0.144u pd=2.64m as=0.144u ps=2.64m w=1200 l=200
X4 a_14_27788# a_n4530_27580# VDD VDD pfet_03v3 ad=96n pd=1.84m as=96n ps=1.84m w=800 l=800
X5 a_n5902_27790# a_n6522_24563# VSS VSS nfet_03v3 ad=96n pd=1.84m as=96n ps=1.84m w=800 l=120
X6 a_n2178_24770# a_n6522_24563# VSS VSS nfet_03v3 ad=48n pd=1.04m as=48n ps=1.04m w=400 l=800
X7 VSS a_686_21744# a_3758_27788# VDD pfet_03v3 ad=96n pd=1.84m as=96n ps=1.84m w=800 l=800
X8 TEMP_OUT a_686_21744# VSS VSS nfet_03v3 ad=72n pd=1.44m as=72n ps=1.44m w=600 l=200
X9 a_n4530_27580# a_n4530_27580# VDD VDD pfet_03v3 ad=96n pd=1.84m as=96n ps=1.84m w=800 l=800
X10 a_2578_24771# a_14_27788# VSS VSS nfet_03v3 ad=24n pd=0.64m as=24n ps=0.64m w=200 l=800
X11 a_686_21744# a_14_27788# a_2578_24771# VSS nfet_03v3 ad=24n pd=0.64m as=24n ps=0.64m w=200 l=800
X12 a_n6522_24563# a_n4530_27580# VDD VDD pfet_03v3 ad=96n pd=1.84m as=96n ps=1.84m w=800 l=800
X13 a_n4530_27580# a_n6522_24563# a_n4870_24770# VSS nfet_03v3 ad=96n pd=1.84m as=96n ps=1.84m w=800 l=800
X14 a_686_21744# a_14_27788# a_3758_27788# VDD pfet_03v3 ad=48n pd=1.04m as=48n ps=1.04m w=400 l=800
X15 a_3758_27788# a_14_27788# VDD VDD pfet_03v3 ad=48n pd=1.04m as=48n ps=1.04m w=400 l=800
X16 a_n4530_27580# a_n5902_27790# VSS VSS nfet_03v3 ad=24n pd=0.64m as=24n ps=0.64m w=200 l=200
X17 a_n6522_24563# a_n6522_24563# VSS VSS nfet_03v3 ad=24n pd=0.64m as=24n ps=0.64m w=200 l=800
X18 a_14_27788# TEMP_OUT a_n2178_24770# VSS nfet_03v3 ad=96n pd=1.84m as=96n ps=1.84m w=800 l=120
X19 VDD a_686_21744# a_2578_24771# VSS nfet_03v3 ad=48n pd=1.04m as=48n ps=1.04m w=400 l=800
C0 VDD a_686_21744# 5.39256f
C1 a_2578_24771# a_14_27788# 0.48479f
C2 TEMP_OUT a_686_21744# 0.40132f
C3 a_14_27788# a_686_21744# 1.04749f
C4 VDD a_n6522_24563# 2.41128f
C5 a_n5902_27790# a_n6522_24563# 0.61741f
C6 a_n5902_27790# VDD 2.96508f
C7 VDD TEMP_OUT 2.76181f
C8 a_n4530_27580# a_n2178_24770# 0.0476f
C9 VDD a_14_27788# 8.64551f
C10 a_n4870_24770# a_n6522_24563# 0.85674f
C11 TEMP_OUT a_14_27788# 1.44818f
C12 a_n5902_27790# a_n4870_24770# 0.18828f
C13 a_n4530_27580# a_n6522_24563# 1.22898f
C14 VDD a_n4530_27580# 10.7114f
C15 a_n5902_27790# a_n4530_27580# 0.80509f
C16 a_n4530_27580# TEMP_OUT 0.03471f
C17 a_n4530_27580# a_14_27788# 0.26656f
C18 a_n4870_24770# a_n4530_27580# 0.63482f
C19 a_686_21744# a_3758_27788# 1.4225f
C20 VDD a_3758_27788# 3.72699f
C21 a_14_27788# a_3758_27788# 0.50803f
C22 a_2578_24771# a_686_21744# 1.69852f
C23 a_n6522_24563# a_n2178_24770# 0.18157f
C24 a_n5902_27790# a_n2178_24770# 0.44392f
C25 TEMP_OUT a_n2178_24770# 0.12645f
C26 VDD a_2578_24771# 0.71418f
C27 a_n2178_24770# a_14_27788# 0.7544f
C28 TEMP_OUT VSS 4.15849f
C29 VDD VSS 93.3724f
C30 a_2578_24771# VSS 4.4566f ; **FLOATING
C31 a_n2178_24770# VSS 3.64413f ; **FLOATING
C32 a_n4870_24770# VSS 2.83985f ; **FLOATING
C33 a_3758_27788# VSS 1.96604f ; **FLOATING
C34 a_686_21744# VSS 10.489f ; **FLOATING
C35 a_14_27788# VSS 32.168f ; **FLOATING
C36 a_n6522_24563# VSS 11.8841f ; **FLOATING
C37 a_n4530_27580# VSS 5.3867f ; **FLOATING
C38 a_n5902_27790# VSS 6.34937f ; **FLOATING
.ends

Vsfix VSS 0 0
Vsup VDD 0 PWL(0 0 1e-06 3.3)
Cprobe TEMP_OUT 0 10f
Xdut TEMP_OUT VSS VDD temp_sensor

.control
tran 7.5546e-09 0.000151092 uic
wrdata ts.dat v(TEMP_OUT) i(Vsup)
.endc
.end
