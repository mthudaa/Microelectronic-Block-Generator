import sys, os, time
os.chdir("/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator")
sys.path.insert(0, ".")
from offset_probe import run_variant, netlist

BASE = netlist()  # default: input pair 10u/5f/0.6u, tail 8u/4f

variants = [
    ("rc_wm2",   {},                  "--router W=2.0"),
    ("rc_hi",    {},                  "--router LAY=met4,met5"),
    ("rc_m34",   {},                  "--router LAY=met3,met4"),
    ("rc_acc4",  {},                  "--router ACC=met4"),
    ("rc_wm2_hi", {},                 "--router W=2.0 LAY=met4,met5"),
]
from offset_probe import parse_spec
for name, _p, rc in variants:
    t0 = time.time()
    # rebuild router_kw from rc string
    router_kw = {}
    for kv in rc[len("--router "):].split():
        k, _, v = kv.partition("=")
        if k == "W": router_kw["width_multiplier"] = float(v)
        elif k == "PW": router_kw["power_width_multiplier"] = float(v)
        elif k == "LAY": router_kw["routing_layers"] = v.split(",")
        elif k == "ACC": router_kw["access_layer"] = v
    from mbg.router import RouterConfig
    rcfg = RouterConfig(**router_kw) if router_kw else None
    print(f"\n### {name} {rc}", flush=True)
    run_variant(name, BASE, router_cfg=rcfg)
    print(f"### {name} total {round(time.time()-t0,1)}s", flush=True)
