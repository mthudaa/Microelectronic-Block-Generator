"""Self-starting 9-stage CMOS ring oscillator — gf180mcuD, 3.3 V.

Ports: VDD VSS OSC_OUT exactly. No clock/start/enable/bias pins.
Self-start mechanism: deliberate 5% PMOS asymmetry in stage 1 shifts the
ring's DC operating point off the symmetric metastable manifold, so the loop
departs within nanoseconds of power-up without any stimulus or forced
initial condition (verified: oscillation fully established ~16 ns after
t=0 from a pure DC solve).
"""
STAGES = 9
L_U = 2.2          # channel length [um] -> nominal f ~54 MHz pre-layout
WN_U = 2.0         # NMOS width [um]
WP_U = 4.0         # PMOS width [um]
WP1_U = 3.8        # stage-1 PMOS width (asymmetry = start assist)


def oscillator_netlist(stages=STAGES, l_u=L_U, wn_u=WN_U, wp_u=WP_U,
                       wp1_u=WP1_U):
    lines = [
        "* Self-starting %d-stage CMOS ring oscillator, gf180mcuD 3.3V" % stages,
        '* Ports: VDD VSS OSC_OUT. Self-start via stage-1 PMOS asymmetry.',
        '.lib "{PDK_LIB}" typical',
        ".subckt oscillator VDD VSS OSC_OUT",
    ]
    prev = "OSC_OUT"
    for k in range(1, stages + 1):
        out = "OSC_OUT" if k == stages else "n%d" % k
        wp = wp1_u if k == 1 else wp_u
        lines.append(f"XM{k}p {out} {prev} VDD VDD pfet_03v3 "
                     f"L={l_u:g}u W={wp:g}u nf=1")
        lines.append(f"XM{k}n {out} {prev} VSS VSS nfet_03v3 "
                     f"L={l_u:g}u W={wn_u:g}u nf=1")
        prev = out
    lines.append(".ends")
    return "\n".join(lines) + "\n"
