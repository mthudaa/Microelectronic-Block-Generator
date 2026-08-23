"""Build a comparator variant layout and measure its systematic post-layout
input-referred offset via a differential-input ramp on the extracted netlist.
"""
import sys
import os
import time

sys.path.insert(0, "/home/huda/opensource-project/Microelectronic-Block-Generator/src")
sys.path.insert(0, "/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator")

import numpy as np
import sa_measure as M

OUT = "/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/probe"


def netlist(inp_w="10u", inp_nf=5, inp_l="0.6u", tail_w="8u", tail_nf=4):
    return f"""
.subckt strongarm_comparator VDD VSS INP INN CLK OUTP OUTN
XM1  TAIL CLK VSS VSS nfet_03v3 L=0.5u W={tail_w} nf={tail_nf}
XM2  D1 INP TAIL VSS nfet_03v3 L={inp_l} W={inp_w} nf={inp_nf}
XM3  D2 INN TAIL VSS nfet_03v3 L={inp_l} W={inp_w} nf={inp_nf}
XM4  OUTN OUTP D1 VSS nfet_03v3 L=0.5u W=6u nf=3
XM5  OUTP OUTN D2 VSS nfet_03v3 L=0.5u W=6u nf=3
XM6  OUTN OUTP VDD VDD pfet_03v3 L=0.5u W=6u nf=3
XM7  OUTP OUTN VDD VDD pfet_03v3 L=0.5u W=6u nf=3
XM8  OUTN CLK VDD VDD pfet_03v3 L=0.5u W=2u nf=1
XM9  OUTP CLK VDD VDD pfet_03v3 L=0.5u W=2u nf=1
XM10 D1 CLK VDD VDD pfet_03v3 L=0.5u W=2u nf=1
XM11 D2 CLK VDD VDD pfet_03v3 L=0.5u W=2u nf=1
.ends
"""


def systematic_offset(pex_netlist, workdir):
    """Flip point of the extracted comparator on a +-30 mV ramp."""
    ramp = list(np.arange(-0.030, 0.030 + 1e-12, 0.005))
    res, cycles, _ = M.run_combined(pex_netlist, vd_list=ramp,
                                    workdir=workdir, tstep="0.5n")
    signs = [+1 if c["diff_settled"] > 0 else -1 for c in cycles]
    for k in range(1, len(signs)):
        if signs[k - 1] != signs[k]:
            return 0.5 * (ramp[k - 1] + ramp[k])
    return (ramp[-1] if signs[-1] == 1 else ramp[0])


def run_variant(name, nl, verbosity=0, router_cfg=None, placement_cfg=None):
    wd = os.path.join(OUT, name)
    os.makedirs(wd, exist_ok=True)
    t0 = time.time()
    from mbg.pipeline import spice_to_gds_with_checks
    r = spice_to_gds_with_checks(nl, verbosity=verbosity,
                                 router_config=router_cfg,
                                 placement_config=placement_cfg)
    print(f"[{name}] build elapsed {round(time.time()-t0,1)}s "
          f"all_pass={r['all_pass']} gds={os.path.basename(r['gds_path'])}")
    if not r["all_pass"]:
        print(f"[{name}] verification failed: {r.get('verification')}")
        return None
    pex_path = (r.get("pex") or {}).get("pex_path")
    if not pex_path or not os.path.isfile(pex_path):
        print(f"[{name}] no pex netlist")
        return None
    off = systematic_offset(open(pex_path).read(), os.path.join(wd, "ramp"))
    print(f"[{name}] systematic post-layout offset = {off*1e3:+.2f} mV")
    return off


def parse_spec(spec):
    parts = {}
    for tok in spec.split():
        k, _, v = tok.partition("=")
        parts[k] = v
    return parts


if __name__ == "__main__":
    variants = {}
    for arg in sys.argv[1:]:
        name, _, _ = arg.partition("=")
        variants[name] = arg.split("=", 1)[1]
    if not variants:
        print("usage: offset_probe.py name='W=20u nf=10 L=0.6u' [--router W=2 LAY=...]")
        sys.exit(2)
    router_kw = {}
    for tok in sys.argv:
        if tok.startswith("--router "):
            for kv in tok[len("--router "):].split():
                k, _, v = kv.partition("=")
                if k == "W":
                    router_kw["width_multiplier"] = float(v)
                elif k == "PW":
                    router_kw["power_width_multiplier"] = float(v)
                elif k == "LAY":
                    router_kw["routing_layers"] = v.split(",")
                elif k == "ACC":
                    router_kw["access_layer"] = v
    router_cfg = None
    placement_cfg = None
    if router_kw:
        from mbg.router import RouterConfig
        router_cfg = RouterConfig(**router_kw)
    for name, spec in variants.items():
        parts = parse_spec(spec)
        nl = netlist(inp_w=parts.get("W", "10u"), inp_nf=int(parts.get("nf", 5)),
                     inp_l=parts.get("L", "0.6u"),
                     tail_w=parts.get("TW", "8u"), tail_nf=int(parts.get("TNF", 4)))
        run_variant(name, nl, router_cfg=router_cfg,
                    placement_cfg=placement_cfg)
