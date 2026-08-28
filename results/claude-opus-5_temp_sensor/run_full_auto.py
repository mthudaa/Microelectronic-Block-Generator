"""Drive /mbg-full-auto for the self-starting temperature sensor.

Run from the repository root:
    cd "$MBG_ROOT" && python3 results/claude-opus-5_temp_sensor/run_full_auto.py

The bundled ``mbg.flow_runtime.simulate_netlist`` measures small-signal AC
metrics; this run replaces it so every pre-layout and PEX evaluation measures
the sensor instead.

Why the measurement is a three-temperature sweep, not one point
---------------------------------------------------------------
For a temperature sensor the temperature coefficient *is* the specification —
a design that passed at 27 C alone could be perfectly dead as a sensor.  Each
evaluation therefore simulates -40 / +27 / +125 C and returns

  * the 27 C frequency, against the 100 kHz - 2 MHz nominal window;
  * ``tc_ppm_per_c`` and ``f_monotonic``, so sensitivity and monotonicity are
    gate conditions rather than after-the-fact commentary;
  * every other metric aggregated to its **worst case** over the three points
    (min swing-high, max swing-low, max current, min sustained cycles, max
    start-up time, min/max duty).

The exhaustive 8-temperature x 3-VDD x 5-corner characterisation is run
separately by ``pvt_run.py``; this in-loop sweep is what keeps the optimiser
honest while it searches.
"""
import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("MBG_ROOT") or os.path.abspath(
    os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "src"))
sys.path.insert(0, HERE)

import mbg.flow_runtime as fr                                   # noqa: E402
from mbg import Spec                                            # noqa: E402
from ts_design import temp_sensor_netlist, CELL                 # noqa: E402
from ts_sim import (simulate_ts_netlist, scale_cap,             # noqa: E402
                    scale_resistor, scale_hysteresis,
                    scale_discharge, scale_widths)

OUTDIR = HERE
TC_TEMPS = (-40, 27, 125)
NOMINAL_T = 27


# ── measurement override ──────────────────────────────────────────────

def measure_sensor(netlist, cell=CELL, workdir=None, corner="typical",
                   vdd=3.3, temps=TC_TEMPS):
    """Simulate at each temperature and fold into one spec-able metric set."""
    per = {}
    for t in temps:
        per[t] = simulate_ts_netlist(
            netlist, cell, workdir=workdir or os.path.join(HERE, "simwork"),
            corner=corner, temp=t, vdd=vdd)
    nom = per[NOMINAL_T]
    if not nom or not nom.get("freq_hz"):
        return {}
    fs = [per[t].get("freq_hz") or 0.0 for t in temps]
    if all(f > 0 for f in fs):
        rising = all(b > a for a, b in zip(fs, fs[1:]))
        falling = all(b < a for a, b in zip(fs, fs[1:]))
        mono = 1.0 if (rising or falling) else 0.0
        # Mean log-slope over the characterised span; the sign is kept so a
        # CTAT design is not flattered by an absolute value.
        tc = (math.log(fs[-1]) - math.log(fs[0])) / (temps[-1] - temps[0]) * 1e6
    else:
        mono, tc = 0.0, 0.0

    def worst(key, how):
        vals = [per[t].get(key) for t in temps if per[t].get(key) is not None]
        return how(vals) if vals else None

    return {
        "freq_hz": nom["freq_hz"],
        "tc_ppm_per_c": tc,
        "f_monotonic": mono,
        "startup_time_s": worst("startup_time_s", max),
        "duty_min_pct": worst("duty_cycle_pct", min),
        "duty_max_pct": worst("duty_cycle_pct", max),
        "duty_cycle_pct": nom.get("duty_cycle_pct"),
        "volt_high_v": worst("volt_high_v", min),
        "volt_low_v": worst("volt_low_v", max),
        "i_avg_a": worst("i_avg_a", max),
        "cycles_sustained": worst("cycles_sustained", min),
        "_per_temp": {str(t): per[t] for t in temps},
    }


def _measure(netlist, cell, spec_names, **kw):
    m = measure_sensor(netlist, cell)
    m.pop("_per_temp", None)
    return m


fr.simulate_netlist = _measure


# ── specifications (exactly the user's targets, nothing invented) ─────

SPECS = [
    Spec("freq_hz", ">=", 100e3, " Hz"),
    Spec("freq_hz", "<=", 2e6, " Hz"),
    Spec("tc_ppm_per_c", ">=", 2000.0, " ppm/C"),
    Spec("tc_ppm_per_c", "<=", 6000.0, " ppm/C"),
    Spec("f_monotonic", ">=", 1.0, ""),
    Spec("startup_time_s", "<=", 10e-6, " s"),
    Spec("duty_min_pct", ">=", 40.0, " %"),
    Spec("duty_max_pct", "<=", 60.0, " %"),
    Spec("volt_high_v", ">=", 2.97, " V"),
    Spec("volt_low_v", "<=", 0.33, " V"),
    Spec("i_avg_a", "<=", 200e-6, " A"),
    Spec("cycles_sustained", ">=", 100.0, ""),
]


# ── tuners ────────────────────────────────────────────────────────────
#
# The knobs, and what each one actually does to  f = I / (2 C dV):
#
#   cap        C          pure frequency knob, temperature-neutral
#   resistor   I ~ 1/R^2  frequency knob that ALSO moves the inversion level
#                         of XMN1 and therefore the temperature coefficient
#   hysteresis dV         frequency knob via the Schmitt trip spacing
#   mn1 width  I and Vov  the temperature-coefficient knob: a narrower XMN1
#                         raises the current density until I tracks 1/mu_n
#                         (ute = -1.568 -> +5200 ppm/C) instead of the weaker
#                         moderate-inversion PTAT
#   discharge  I_sink     duty cycle only

def _tune(design, report, prefix):
    failing = {r.name for r in report.failures}
    vals = {r.name: r.value for r in report.results if r.value is not None}
    net, moves = design.netlist, []

    tc = vals.get("tc_ppm_per_c")
    if "tc_ppm_per_c" in failing and tc is not None:
        if tc < 2000.0:
            net = scale_widths(net, 0.8, ["MN1"])
            moves.append("MN1 W x0.8 (deeper strong inversion, raise TC)")
        elif tc > 6000.0:
            net = scale_widths(net, 1.25, ["MN1"])
            moves.append("MN1 W x1.25 (back toward moderate inversion)")

    f = vals.get("freq_hz")
    if "freq_hz" in failing and f is not None:
        if f > 2e6:
            net = scale_cap(net, min(f / 1.2e6, 3.0))
            moves.append("C up (slow the ramp)")
        elif f < 100e3:
            net = scale_cap(net, max(f / 8e5, 0.34))
            moves.append("C down (speed the ramp)")

    if ("duty_min_pct" in failing or "duty_max_pct" in failing):
        d = vals.get("duty_cycle_pct") or 50.0
        k = 1.12 if d < 50.0 else 0.9
        net = scale_discharge(net, k)
        moves.append(f"discharge sink x{k}")

    step = int(design.circuit.get(f"_{prefix}_step", 0)) + 1
    circ = {**design.circuit, f"_{prefix}_step": step}
    note = f"{prefix}_tune_{step}"
    if not moves:
        return design.evolve(note=note + "(no move)")
    return design.evolve(netlist=net, circuit=circ,
                         note=note + "(" + "; ".join(moves) + ")")


def tune_pre(design, report):
    return _tune(design, report, "pre")


def tune_post(design, report, degradation):
    layout = dict(design.layout)
    layout["critical_net_width"] = round(
        min(float(layout.get("critical_net_width", 0.28)) * 1.25, 1.0), 4)
    layout["tighten_matched_groups"] = True
    worst = [d.name for d in degradation if d.worsened][:3]
    if worst:
        layout["parasitic_sensitive"] = worst
    stepped = _tune(design, report, "pex")
    return stepped.evolve(layout={**layout, **stepped.layout})


# ── branch-and-compare strategy ───────────────────────────────────────

def make_strategy():
    from mbg.search import SearchStrategy, Candidate

    class SensorStrategy(SearchStrategy):
        name = "temp_sensor"

        def propose(self, state, budget):
            failing = set(state.failing())
            m = state.metrics
            out = []

            def add(cid, fn, factor, change, hyp, effect, risk, extra=None):
                if len(out) >= budget:
                    return
                circ = {**state.design.circuit}
                circ.update(extra or {})
                out.append(Candidate(
                    id=cid,
                    design=state.design.evolve(
                        netlist=fn(state.design.netlist, factor), circuit=circ),
                    hypothesis=hyp, change=change,
                    rationale="f = I/(2 C dV); I ~ 1/(mu_n R^2) from the "
                              "beta-multiplier, so C and dV move frequency "
                              "alone while R and the XMN1 width also move the "
                              "temperature coefficient",
                    expected_effect=effect, risk=risk, target="circuit",
                    params={"factor": factor}, source=self.name))

            tc = m.get("tc_ppm_per_c")
            if "tc_ppm_per_c" in failing and tc is not None:
                if tc < 2000.0:
                    add("tc_up_s", lambda n, k: scale_widths(n, k, ["MN1"]),
                        0.85, "narrow XMN1 by 15%",
                        "raise the reference current density so I tracks 1/mu_n",
                        "raise tc_ppm_per_c toward the 2000-6000 window",
                        "also raises f; may need C compensation")
                    add("tc_up_l", lambda n, k: scale_widths(n, k, ["MN1"]),
                        0.7, "narrow XMN1 by 30%",
                        "push XMN1 further into strong inversion",
                        "larger TC increase", "overshoot past 6000 ppm/C")
                else:
                    add("tc_dn", lambda n, k: scale_widths(n, k, ["MN1"]),
                        1.2, "widen XMN1 by 20%",
                        "reduce current density back toward moderate inversion",
                        "lower tc_ppm_per_c", "may drop below 2000 ppm/C")

            f = m.get("freq_hz")
            if f is not None and ("freq_hz" in failing or not failing):
                if f > 2e6:
                    add("f_dn_c", scale_cap, min(f / 1.2e6, 3.0),
                        "enlarge the MIM timing capacitor",
                        "C sets the ramp slope and has ~15 ppm/C of its own",
                        "move f into the 100 kHz-2 MHz window",
                        "MIM area grows as the square of the edge")
                    add("f_dn_h", scale_hysteresis, 1.3,
                        "widen the Schmitt window",
                        "a wider dV lengthens both ramps equally",
                        "lower f, duty unchanged",
                        "a very wide window costs current-source headroom")
                elif f < 100e3:
                    add("f_up_c", scale_cap, max(f / 8e5, 0.34),
                        "shrink the MIM timing capacitor",
                        "smaller C, steeper ramp", "raise f",
                        "parasitics become a larger fraction of C")
                    add("f_up_h", scale_hysteresis, 0.77,
                        "narrow the Schmitt window",
                        "less dV per ramp", "raise f",
                        "too little hysteresis risks losing the snap")

            if "duty_min_pct" in failing or "duty_max_pct" in failing:
                d = m.get("duty_cycle_pct") or 50.0
                add("duty", scale_discharge, 1.12 if d < 50 else 0.9,
                    "trim the discharge sink against the charge source",
                    "duty is I_charge/(I_charge+I_net_discharge)",
                    "recentre the duty cycle on 50%",
                    "moves f slightly as well")

            if not out and f is not None:
                add("margin_c", scale_cap, 1.15,
                    "small capacitor increase",
                    "buy margin against the 2 MHz ceiling",
                    "lower f a little", "none material")
            return out[:budget]

    return SensorStrategy()


# ── main ──────────────────────────────────────────────────────────────

def main():
    from mbg.full_auto import run_full_auto, FullAutoConfig
    from mbg import make_hooks
    from mbg.flow_runtime import make_candidate_proposer

    netlist = temp_sensor_netlist()
    with open(os.path.join(HERE, "prompt.txt")) as f:
        request = f.read()
    with open(os.path.join(HERE, "generated_netlist.spice"), "w") as f:
        f.write(netlist)

    hooks = make_hooks(cell=CELL, in_node="TEMP_OUT", out_node="TEMP_OUT",
                       supplies={"vdd": 3.3, "vss": 0.0},
                       spec_names=[s.name for s in SPECS],
                       specs=SPECS, outdir=OUTDIR, verbosity=1,
                       tune_pre=tune_pre, tune_post=tune_post)
    hooks.propose_candidates = make_candidate_proposer(
        specs=SPECS,
        hooks_ref={"build_layout": hooks.build_layout,
                   "simulate_pex": hooks.simulate_pex},
        strategy=make_strategy(), verbosity=1)

    t0 = time.time()
    res = run_full_auto(request, hooks, cell=CELL, specs=SPECS,
                        netlist=netlist,
                        config=FullAutoConfig.for_effort("normal",
                                                         outdir=OUTDIR))
    print("\n=== FULL AUTO RESULT ===")
    print("status:", res.status, "| tapeout_ready:", res.tapeout_ready)
    print("elapsed:", round(time.time() - t0, 1), "s")
    if res.signoff:
        print(res.signoff.table())
    if res.flow and res.flow.best_pex:
        print("\nbest PEX metrics:")
        for r in res.flow.best_pex.results:
            v = "MISSING" if r.value is None else (
                f"{r.value:.5g}" if isinstance(r.value, float) else str(r.value))
            print(f"  {r.name:<20} {v:<12} {r.op} {r.target:<10g} -> {r.status}")
    if res.report_path:
        print("report:", res.report_path)
    with open(os.path.join(HERE, "full_auto_run_summary.json"), "w") as f:
        json.dump(res.as_dict(), f, indent=2, default=str)
    return 0 if res.tapeout_ready else 1


if __name__ == "__main__":
    sys.exit(main())
