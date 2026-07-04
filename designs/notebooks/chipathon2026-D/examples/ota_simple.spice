
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt ota_simple vin_p vin_n vout vbias vdd vss
M1 n1 vin_p ntail vss nfet_03v3 W=10u L=1u
M2 vout vin_n ntail vss nfet_03v3 W=10u L=1u
M3 n1 n1 vdd vdd pfet_03v3 W=20u L=1u
M4 vout n1 vdd vdd pfet_03v3 W=20u L=1u
M5 ntail vbias vss vss nfet_03v3 W=15u L=1u
.ends
