import sys, os, time
os.chdir("/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator")
sys.path.insert(0, ".")
import numpy as np
import sa_measure as M
from offset_probe import run_variant, netlist, systematic_offset
from mbg.pipeline import spice_to_gds_with_checks

def net(inp_w, inp_nf, inp_l, tail_w, tail_nf):
    return netlist(inp_w=inp_w, inp_nf=inp_nf, inp_l=inp_l,
                   tail_w=tail_w, tail_nf=tail_nf)

variants = {
    "t2_i20_L1":  net("20u", 10, "1u",  "2u", 1),
    "t2_i16_L06": net("16u", 8,  "0.6u","2u", 1),
    "t1_i20_L1":  net("20u", 10, "1u",  "1u", 1),
    "t2_i20_L06": net("20u", 10, "0.6u","2u", 1),
}

def extra_checks(nl, tag):
    out = {}
    # nominal combined (10 cases) - decision time
    try:
        m = M.measure_comparator(nl, workdir=f"sim/{tag}_m", do_icmr=False, tstep="50p")
        out["t_dec_ns"] = m.get("t_dec_ns")
        out["n_correct"] = m.get("n_correct")
    except Exception as e:
        out["nom_err"] = str(e)
    # low VCM
    for vcm in (0.9, 1.0):
        try:
            res, cycles, _ = M.run_combined(nl, vcm=vcm, vd_list=[25e-3, -25e-3],
                                            workdir=f"sim/{tag}_v{vcm}", tstep="50p")
            ok = all(c["correct"] for c in cycles) and all(
                c["t_dec"] is not None and c["t_dec"] <= 5e-9 for c in cycles)
            out[f"vcm{vcm}_ok"] = bool(ok)
            out[f"vcm{vcm}_td"] = max((c["t_dec"] or 1e9) * 1e9 for c in cycles)
        except Exception as e:
            out[f"vcm{vcm}_err"] = str(e)
    return out

for name, nl in variants.items():
    t0 = time.time()
    print(f"\n### {name}", flush=True)
    try:
        off = run_variant(name, nl)
        # find the pex from the build (probe wrote to CWD strongarm_comparator)
        pex = "strongarm_comparator/strongarm_comparator.pex.spice"
        if os.path.isfile(pex):
            off = systematic_offset(open(pex).read(), f"sim/{name}_ramp")
            print(f"[{name}] offset = {off*1e3:+.2f} mV", flush=True)
        chk = extra_checks(nl, name)
        print(f"[{name}] checks = {chk}", flush=True)
    except Exception as e:
        print(f"### {name} ERROR {type(e).__name__}: {e}", flush=True)
    print(f"### {name} total {round(time.time()-t0,1)}s", flush=True)
