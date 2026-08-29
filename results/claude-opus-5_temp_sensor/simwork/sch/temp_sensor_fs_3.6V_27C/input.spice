.include '/home/huda/.volare/gf180mcuD/libs.tech/ngspice/design.ngspice'
.lib '/home/huda/opensource-project/Microelectronic-Block-Generator/results/claude-opus-5_temp_sensor/pdk_flat/sm141064.ngspice' fs
.lib '/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice' res_typical
.lib '/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice' mimcap_typical
.options reltol=1e-4 vntol=1e-8 abstol=1e-15 chgtol=1e-16 trtol=1
.temp 27

* Self-starting relaxation-oscillator temperature sensor, gf180mcuD 3.3V
* Ports: VDD VSS TEMP_OUT.  Internal PTAT beta-multiplier reference,
* native ppolyf_u degeneration resistor + metal4/metal5 MIM timing cap.
* Self-start: XMS1/XMS2/XMS3, self-extinguishing.  No .ic, no stimulus.
.subckt temp_sensor VDD VSS TEMP_OUT
* --- beta-multiplier PTAT current reference ---
XMP1 nb1 nbp VDD VDD pfet_03v3 L=4u W=4u nf=1
XMP2 nbp nbp VDD VDD pfet_03v3 L=4u W=4u nf=1
XMN1 nb1 nb1 VSS VSS nfet_03v3 L=4u W=1u nf=1
XMN2 nbp nb1 nrs VSS nfet_03v3 L=4u W=4u nf=1
XR1 nrs VSS VSS ppolyf_u r_width=1u r_length=100u
* --- self-extinguishing start-up branch ---
XMS1 nsu VSS VDD VDD pfet_03v3 L=9.5u W=0.6u nf=1
XMS2 nsu nb1 VSS VSS nfet_03v3 L=0.6u W=4u nf=1
XMS3 nbp nsu VSS VSS nfet_03v3 L=1u W=1u nf=1
* --- native-passive relaxation timing core ---
XMPC ncap nbp VDD VDD pfet_03v3 L=4u W=4u nf=1
XMNS ncap TEMP_OUT nsk VSS nfet_03v3 L=0.6u W=4u nf=1
XMNC nsk nb1 VSS VSS nfet_03v3 L=4u W=2u nf=1
XC1 ncap VSS cap_mim_2f0_m4m5_noshield c_width=34u c_length=34u
* --- hysteresis comparator (6T CMOS Schmitt trigger) ---
XMSP1 npa ncap VDD VDD pfet_03v3 L=4u W=2u nf=1
XMSP2 nst ncap npa VDD pfet_03v3 L=4u W=2u nf=1
XMSP3 VSS nst npa VDD pfet_03v3 L=4u W=4u nf=1
XMSN1 nnb ncap VSS VSS nfet_03v3 L=4u W=1u nf=1
XMSN2 nst ncap nnb VSS nfet_03v3 L=4u W=1u nf=1
XMSN3 VDD nst nnb VSS nfet_03v3 L=4u W=2u nf=1
* --- output buffer, closes the loop and drives TEMP_OUT ---
XMB1 TEMP_OUT nst VDD VDD pfet_03v3 L=1u W=6u nf=1
XMB2 TEMP_OUT nst VSS VSS nfet_03v3 L=1u W=3u nf=1
.ends

Vsfix VSS 0 0
Vsup VDD 0 PWL(0 0 1e-06 3.6)
Cprobe TEMP_OUT 0 10f
Xdut VDD VSS TEMP_OUT temp_sensor

.control
tran 6.04047e-09 0.000120809 uic
wrdata ts.dat v(TEMP_OUT) i(Vsup) v(Xdut.ncap)
.endc
.end
