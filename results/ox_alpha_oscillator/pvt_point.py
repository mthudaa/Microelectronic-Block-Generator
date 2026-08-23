"""One-shot PVT point: args corner vdd temp netlist(sch|pex). Appends to JSON."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

from osc_sim import simulate_osc_netlist  # noqa: E402
from pvt_run import evaluate  # noqa: E402

corner, vdd, temp, src = (sys.argv[1], float(sys.argv[2]), int(sys.argv[3]),
                          sys.argv[4])
path = os.path.join(HERE, "generated_netlist.spice" if src == "sch"
                    else "final", "oscillator.pex.spice")
if src == "sch":
    path = os.path.join(HERE, "generated_netlist.spice")
netlist = open(path).read()
t0 = __import__("time").time()
try:
    m = simulate_osc_netlist(netlist, "oscillator", [], corner=corner,
                             temp=temp, vdd=vdd)
    err = ""
except Exception as e:                                  # noqa: BLE001
    m, err = {}, str(e)[:200]
row = {"netlist": src, "corner": corner, "vdd": vdd, "temp": temp,
       "metrics": m, "fail_flags": evaluate(m),
       "wall_s": round(__import__("time").time() - t0, 1), "err": err}

out_json = os.path.join(HERE, "pvt_summary.json")
rows = json.load(open(out_json)) if os.path.exists(out_json) else []
rows = [r for r in rows if not (r["netlist"] == src and r["corner"] == corner
                                and r["vdd"] == vdd and r["temp"] == temp)]
rows.append(row)
json.dump(rows, open(out_json, "w"), indent=1)
ok = "PASS" if not row["fail_flags"] else ",".join(row["fail_flags"])
print(f"{src} {corner} {vdd}V {temp}C -> {ok} "
      f"f={m.get('freq_hz', 0)/1e6:.2f}MHz duty={m.get('duty_cycle_pct', 0):.2f}%")
