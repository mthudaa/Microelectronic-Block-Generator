"""PVT characterization of the final oscillator (schematic + PEX netlists).

Grid: corner x VDD x TEMP as requested by the design prompt.
Writes pvt_summary.json + pvt_summary.md incrementally.
"""
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

from osc_sim import simulate_osc_netlist  # noqa: E402

SCH = os.path.join(HERE, "generated_netlist.spice")
PEX = os.path.join(HERE, "final", "oscillator.pex.spice")

CORNERS = ["typical", "ss", "ff", "sf", "fs"]
VDDS = [3.0, 3.3, 3.6]
TEMPS = [-40, 27, 125]

SPEC = dict(freq=(10e6, 100e6), duty=(40.0, 60.0), voh=(2.97, None),
            vol=(None, 0.33), iavg=(None, 1e-3))


def evaluate(m):
    flags = []
    f = m.get("freq_hz")
    if not m:
        return ["NO_DATA"]
    if f is None or not (10e6 <= f <= 100e6):
        flags.append("FREQ")
    d = m.get("duty_cycle_pct")
    if d is None or not (40.0 <= d <= 60.0):
        flags.append("DUTY")
    if (m.get("volt_high_v") or 0) < 2.97:
        flags.append("VOH")
    if (m.get("volt_low_v") or 1) > 0.33:
        flags.append("VOL")
    if (m.get("i_avg_a") or 1) > 1e-3:
        flags.append("IAVG")
    if (m.get("cycles_sustained") or 0) < 100:
        flags.append("CYCLES")
    if (m.get("startup_time_s") or 1) > 5e-6:
        flags.append("TSTART")
    return flags


def main():
    results = []
    out_json = os.path.join(HERE, "pvt_summary.json")
    total = len(CORNERS) * len(VDDS) * len(TEMPS) * 2
    done = 0
    t00 = time.time()
    for src_name, path in (("sch", SCH), ("pex", PEX)):
        netlist = open(path).read()
        for corner in CORNERS:
            for vdd in VDDS:
                for temp in TEMPS:
                    t0 = time.time()
                    try:
                        m = simulate_osc_netlist(netlist, "oscillator", [],
                                                 corner=corner, temp=temp,
                                                 vdd=vdd)
                        err = ""
                    except Exception as e:      # noqa: BLE001
                        m, err = {}, str(e)[:200]
                    row = {"netlist": src_name, "corner": corner,
                           "vdd": vdd, "temp": temp,
                           "metrics": m, "fail_flags": evaluate(m),
                           "wall_s": round(time.time() - t0, 1), "err": err}
                    results.append(row)
                    done += 1
                    ok = "PASS" if not row["fail_flags"] else ",".join(
                        row["fail_flags"])
                    print(f"[{done}/{total}] {src_name} {corner:>7} "
                          f"{vdd:.1f}V {temp:>4}C -> {ok} "
                          f"f={m.get('freq_hz', 0)/1e6:7.2f}MHz "
                          f"duty={m.get('duty_cycle_pct', 0):5.2f}% "
                          f"({row['wall_s']}s)", flush=True)
                    with open(out_json, "w") as f:
                        json.dump(results, f, indent=1)
    print(f"total wall: {round(time.time()-t00, 1)}s")
    npass = sum(1 for r in results if r["netlist"] == "pex"
                and not r["fail_flags"])
    print(f"PEX points passing all specs: {npass}/{len(CORNERS)*len(VDDS)*len(TEMPS)}")


if __name__ == "__main__":
    main()
