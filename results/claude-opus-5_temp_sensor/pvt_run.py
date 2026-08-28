"""PVT characterisation of the final temperature sensor (schematic + PEX).

Grid: {schematic, PEX} x 5 process corners x 3 supplies x 8 temperatures
= 240 transient simulations, each run long enough to contain at least 100
oscillation cycles at that corner's own frequency (the stop time is chosen
from a measured probe run, never assumed).

Process corners are real corners of *all three* device classes, not the MOSFET
corner alone.  The GF180 library carries separate corner sections for the poly
resistor (rsh_ppolyf_u = 350 / 420 / 280 ohm/sq) and for the MIM capacitor
(x1.0 / x1.1 / x0.9), and for this design those matter more than the MOSFET
skew does: the reference current goes as 1/R^2 and the frequency as 1/C.

  typical  MOS typical, res_typical, mimcap_typical
  ss       MOS slow,    res_ss  (high R -> low current), mimcap_ss (high C)
  ff       MOS fast,    res_ff  (low R  -> high current), mimcap_ff (low C)
  sf, fs   MOS skew only, passives typical

Writes pvt_summary.json incrementally so a long run can be inspected while it
is still going.  Re-running is safe: existing rows for a point are replaced.
"""
import json
import multiprocessing as mp
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("MBG_ROOT") or os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

from ts_sim import simulate_ts_netlist                          # noqa: E402
from ts_design import CELL                                      # noqa: E402

SCH = os.path.join(HERE, "generated_netlist.spice")
PEX = os.path.join(HERE, "final", f"{CELL}.pex.spice")

CORNERS = (os.environ.get("PVT_CORNERS", "").split(",")
           if os.environ.get("PVT_CORNERS")
           else ["typical", "ss", "ff", "sf", "fs"])
VDDS = [3.0, 3.3, 3.6]
TEMPS = [-40, -15, 10, 27, 50, 75, 100, 125]

# The user's acceptance table.  freq is bounded only at the nominal point
# (27 C, typical, 3.3 V); everywhere else the requirement is that the sensor
# keeps oscillating, stays monotonic and keeps its output levels and duty.
LIMITS = dict(duty=(40.0, 60.0), voh=2.97, vol=0.33, iavg=200e-6,
              cycles=100.0, tstart=10e-6, fnom=(100e3, 2e6))


def evaluate(m, nominal=False):
    if not m or not m.get("freq_hz"):
        return ["NO_OSC"]
    flags = []
    if nominal:
        lo, hi = LIMITS["fnom"]
        if not (lo <= m["freq_hz"] <= hi):
            flags.append("FNOM")
    d = m.get("duty_cycle_pct")
    if d is None or not (LIMITS["duty"][0] <= d <= LIMITS["duty"][1]):
        flags.append("DUTY")
    if (m.get("volt_high_v") or 0.0) < LIMITS["voh"]:
        flags.append("VOH")
    if (m.get("volt_low_v") or 1.0) > LIMITS["vol"]:
        flags.append("VOL")
    if (m.get("i_avg_a") or 1.0) > LIMITS["iavg"]:
        flags.append("IAVG")
    if (m.get("cycles_sustained") or 0.0) < LIMITS["cycles"]:
        flags.append("CYCLES")
    if (m.get("startup_time_s") or 1.0) > LIMITS["tstart"]:
        flags.append("TSTART")
    return flags


MIN_CYCLES = 100


def _one(job):
    """One grid point.  ``stop`` may be pre-computed; see main()."""
    src, path, corner, vdd, temp, stop = job
    netlist = open(path).read()
    t0 = time.time()
    try:
        m = simulate_ts_netlist(netlist, CELL, corner=corner, temp=temp,
                                vdd=vdd, stop=stop,
                                workdir=os.path.join(HERE, "simwork", src))
        # A predicted stop time is a scheduling hint, never an assumption
        # about the result: if the window did not actually contain 100
        # cycles, the point is re-run long enough that it does.
        if stop and (m.get("cycles_sustained") or 0) < MIN_CYCLES:
            f = m.get("freq_hz") or 0.0
            if f > 0:
                need = ((m.get("startup_time_s") or 0.0)
                        + (MIN_CYCLES + 10) / f) * 1.2
                m = simulate_ts_netlist(
                    netlist, CELL, corner=corner, temp=temp, vdd=vdd,
                    stop=min(need, 1.5e-3),
                    workdir=os.path.join(HERE, "simwork", src))
        err = ""
    except Exception as e:                                     # noqa: BLE001
        m, err = {}, f"{type(e).__name__}: {e}"[:300]
    nominal = (corner == "typical" and vdd == 3.3 and temp == 27)
    return {"netlist": src, "corner": corner, "vdd": vdd, "temp": temp,
            "metrics": m, "fail_flags": evaluate(m, nominal),
            "nominal_point": nominal, "stop_s": stop,
            "wall_s": round(time.time() - t0, 1), "err": err}


def main():
    workers = int(os.environ.get("PVT_WORKERS", "2"))
    for src, path in (("sch", SCH), ("pex", PEX)):
        if not os.path.isfile(path):
            raise SystemExit(f"missing {src} netlist: {path}")
    out_json = os.path.join(HERE, "pvt_summary.json")
    # Resume.  This sweep is long and shares the machine with other jobs, so
    # points already on disk are reloaded rather than re-simulated.  A point
    # counts as done only if it actually produced a frequency, so a crashed
    # or non-oscillating point is retried rather than silently accepted.
    results = []
    if os.path.exists(out_json):
        for r in json.load(open(out_json)):
            if (r.get("metrics") or {}).get("freq_hz"):
                results.append(r)
    have = {(r["netlist"], r["corner"], r["vdd"], r["temp"]) for r in results}
    if have:
        print(f"resuming: {len(have)} point(s) already on disk", flush=True)
    grid = [(c, v, t) for c in CORNERS for v in VDDS for t in TEMPS]

    def flush():
        with open(out_json, "w") as f:
            json.dump(results, f, indent=1)

    def run_phase(src, path, stops, label):
        jobs = [(src, path, c, v, t, stops.get((c, v, t)))
                for c, v, t in grid if (src, c, v, t) not in have]
        n = 0
        if not jobs:
            print(f"[{label}] all points already on disk", flush=True)
            return
        with mp.Pool(workers) as pool:
            for row in pool.imap_unordered(_one, jobs):
                results.append(row)
                n += 1
                m = row["metrics"]
                ok = ("PASS" if not row["fail_flags"]
                      else ",".join(row["fail_flags"]))
                print(f"[{label} {n}/{len(jobs)}] {row['corner']:>7} "
                      f"{row['vdd']:.1f}V {row['temp']:>4}C -> {ok:<12} "
                      f"f={(m.get('freq_hz') or 0)/1e3:8.1f}kHz "
                      f"duty={m.get('duty_cycle_pct') or 0:5.2f}% "
                      f"i={(m.get('i_avg_a') or 0)*1e6:6.1f}uA "
                      f"cyc={m.get('cycles_sustained') or 0:.0f} "
                      f"({row['wall_s']}s)", flush=True)
                flush()

    t00 = time.time()
    # Phase 1 -- schematic.  Cheap, and each point discovers its own stop
    # time with a short probe run.
    run_phase("sch", SCH, {}, "sch")

    # Phase 2 -- extracted.  The PEX netlist is several times more expensive
    # per simulated microsecond, so its stop time is taken from the matching
    # schematic point instead of being rediscovered by a second probe
    # transient.  Pre-layout and post-layout frequencies agree to well under
    # a percent here, and _one() re-runs any point whose window turned out to
    # hold fewer than 100 cycles, so this costs accuracy nothing.
    stops = {}
    for r in list(results):
        if r["netlist"] != "sch":
            continue
        f = (r["metrics"] or {}).get("freq_hz") or 0.0
        t0 = (r["metrics"] or {}).get("startup_time_s") or 0.0
        if f > 0:
            stops[(r["corner"], r["vdd"], r["temp"])] = (
                t0 + (MIN_CYCLES + 12) / f) * 1.15
    run_phase("pex", PEX, stops, "pex")

    print(f"total wall: {round(time.time() - t00, 1)}s")
    for src in ("sch", "pex"):
        sub = [r for r in results if r["netlist"] == src]
        npass = sum(1 for r in sub if not r["fail_flags"])
        print(f"{src}: {npass}/{len(sub)} points meet every per-corner limit")


if __name__ == "__main__":
    main()
