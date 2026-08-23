import sys, os, time
os.chdir("/home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator")
sys.path.insert(0, ".")
from offset_probe import run_variant, netlist

variants = {
    "slow_inL1u":  netlist(inp_w="10u", inp_nf=5, inp_l="1u", tail_w="8u", tail_nf=4),
    "slow_tail2u": netlist(inp_w="10u", inp_nf=5, inp_l="0.6u", tail_w="2u", tail_nf=1),
    "slow_both":   netlist(inp_w="10u", inp_nf=5, inp_l="1u", tail_w="2u", tail_nf=1),
    "fast_latch":  netlist(inp_w="10u", inp_nf=5, inp_l="0.6u", tail_w="8u", tail_nf=4),
}
# fast_latch uses default netlist; modify netlist() call already default.
for name, nl in variants.items():
    t0 = time.time()
    print(f"\n### {name}", flush=True)
    try:
        run_variant(name, nl)
    except Exception as e:
        print(f"### {name} ERROR {e}", flush=True)
    print(f"### {name} total {round(time.time()-t0,1)}s", flush=True)
