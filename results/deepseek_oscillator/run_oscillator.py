"""Run the MBG FULL AUTOMATE flow on a self-starting CMOS ring oscillator.

Specification (user-provided):
  - oscillator, ports VDD VSS OSC_OUT, .subckt oscillator VDD VSS OSC_OUT
  - self-starting from normal power-up (VDD ramp, no forced initial condition)
  - GF180MCU (nfet_03v3 / pfet_03v3), VDD = 3.3 V, VSS = 0 V, 27 C
  - Frequency 10-100 MHz
  - Startup time < 5 us
  - Duty cycle 40-60%
  - OSC_OUT high > 2.97 V, low < 0.33 V
  - Average supply current < 1 mA
  - Sustained oscillation >= 100 cycles
  - Characterize PVT: VDD 3.0/3.3/3.6 V, temp -40/27/125 C, corners.

Topology: 3-stage CMOS ring oscillator (three inverters in a loop). Odd
number of stages guarantees no latching state; the loop starts from the
power-up edge and the exponential growth of any asymmetry carries it to
full swing — no START/ENABLE/reset port, no bias input. This is the
simplest self-starting topology.

Measurement is a transient run: VDD is ramped from 0 to 3.3 V (normal
power-up, no .ic, no uic) and the output waveform is analysed for
frequency, startup time, duty cycle, VOH/VOL and average supply current.
The same measurement runs identically on the schematic and the
Magic-extracted netlist.
"""
import math
import os
import re
import sys

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))

from mbg import Spec, make_hooks
from mbg.full_auto import run_full_auto, FullAutoConfig
from mbg.flow_runtime import make_candidate_proposer

# ── cell / directories ────────────────────────────────────────────────
CELL = "oscillator"
OUTDIR = os.path.join(os.path.expanduser("~"),
                      "opensource-project", "Microelectronic-Block-Generator",
                      "results", "deepseek_oscillator")
os.makedirs(OUTDIR, exist_ok=True)

lib_path = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice",
                        "sm141064.ngspice")

# ── netlist ───────────────────────────────────────────────────────────
# 3-stage ring oscillator, 6 MOS, flat single subckt. Identical inverters;
# Wp/Wn = 2:1 for ~50% duty at the output. Sizing target: pre-layout
# frequency comfortably inside 10-100 MHz (~40-70 MHz) so that post-PEX
# (parasitic caps slow the ring down) stays inside the band.
# L=4u chosen from an empirical sweep: L=2u -> ~143 MHz, L=10u -> ~9 MHz,
# so L=4u lands near ~50 MHz with room for PEX and PVT.
NETLIST = f"""
.lib "{lib_path}" typical
.subckt {CELL} VDD VSS OSC_OUT
XM1  n1 OSC_OUT VSS VSS nfet_03v3 L=4u W=2u nf=1
XM1P n1 OSC_OUT VDD VDD pfet_03v3 L=4u W=4u nf=1
XM2  n2 n1 VSS VSS nfet_03v3 L=4u W=2u nf=1
XM2P n2 n1 VDD VDD pfet_03v3 L=4u W=4u nf=1
XM3  OSC_OUT n2 VSS VSS nfet_03v3 L=4u W=2u nf=1
XM3P OSC_OUT n2 VDD VDD pfet_03v3 L=4u W=4u nf=1
.ends
""".strip()

# ── specifications ────────────────────────────────────────────────────
SPECS = [
    Spec("freq_mhz", ">=", 10.0, " MHz"),
    Spec("freq_mhz", "<=", 100.0, " MHz"),
    Spec("startup_us", "<=", 5.0, " us"),
    Spec("duty_pct", ">=", 40.0, " %"),
    Spec("duty_pct", "<=", 60.0, " %"),
    Spec("voh_v", ">=", 2.97, " V"),
    Spec("vol_v", "<=", 0.33, " V"),
    Spec("i_avg_ua", "<=", 1000.0, " uA"),
    Spec("sustained", ">=", 100.0, " cycles"),
]
ALL_SPECS = SPECS

REQUEST = (
    "Design a self-starting CMOS ring oscillator in GF180MCU with ports "
    "VDD VSS OSC_OUT only. VDD=3.3 V, VSS=0 V, 27 C. It must start "
    "automatically from normal power-up without any external startup pulse "
    "or forced initial condition. Frequency 10-100 MHz, startup time < 5 us, "
    "duty cycle 40-60%, OSC_OUT high > 2.97 V, OSC_OUT low < 0.33 V, "
    "average supply current < 1 mA, sustained oscillation >= 100 cycles. "
    "Characterize PVT: VDD 3.0/3.3/3.6 V, temp -40/27/125 C, gf180 "
    "typical/ff/ss corners."
)


# ── oscillator transient measurement ──────────────────────────────────
def parse_ports(netlist, cell):
    m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+(.+)$", netlist,
                  re.MULTILINE | re.IGNORECASE)
    if not m:
        raise ValueError(f".subckt {cell} not found in netlist")
    return [p for p in m.group(1).split()]


def measure_osc(netlist, cell, *, vdd=3.3, temp=27.0, corner="typical",
                workdir="sim", stop="12u"):
    """Run a power-up transient and measure the oscillator metric set.

    VDD ramps 0 -> vdd over a finite edge (normal power-up, no .ic / no uic).
    Returns an empty dict on any core-measurement failure so the flow treats
    it as a tool failure.
    """
    mcell = re.search(r"^\.subckt\s+(\S+)", netlist, re.MULTILINE | re.IGNORECASE)
    if mcell:
        cell = mcell.group(1)
    ports = parse_ports(netlist, cell)

    # Map ports: VDD/VSS by name, everything else is the output under test.
    vdd_port = next((p for p in ports if p.lower() in ("vdd", "vcc", "avdd")), None)
    vss_port = next((p for p in ports if p.lower() in ("vss", "gnd", "vss!")), None)
    if vdd_port is None:
        vdd_port = next((p for p in ports if p.lower().startswith("vd")), None)
    if vss_port is None:
        vss_port = next((p for p in ports if p.lower().startswith("vs")), None)
    out_port = next((p for p in ports if p not in (vdd_port, vss_port)), None)
    if not (vdd_port and vss_port and out_port):
        raise ValueError(f"could not identify VDD/VSS/OUT among {ports}")

    extra_ports = [p for p in ports if p not in (vdd_port, vss_port, out_port)]
    # then supplies + DUT + analysis.
    core = "\n".join(
        l for l in netlist.splitlines()
        if not l.strip().lower().startswith((".lib", ".include")))
    lines = [
        f".include '{os.path.join(os.environ['PDKPATH'], 'libs.tech', 'ngspice', 'design.ngspice')}'",
        f".lib '{lib_path}' {corner}",
        f".temp {temp}",
        "",
        core,
        "",
        f"Xosc {' '.join(ports)} {cell}",
        f"Vvdd {vdd_port} 0 PULSE(0 {vdd} 0 1u 1u 100u 100u)",
        f"Vvss {vss_port} 0 0",
    ]
    for ep in extra_ports:
        if any(k in ep.lower() for k in ("vss", "gnd", "sub")):
            lines.append(f"Vext_{ep} {ep} 0 0")
        elif any(k in ep.lower() for k in ("vdd", "nw", "well", "bulk")):
            lines.append(f"Vext_{ep} {ep} 0 {vdd}")
        else:
            lines.append(f"R{ep} {ep} 0 1G")
    lines += [
        ".control",
        f"tran 5n {stop} 0 5n",
        f"wrdata osc.dat v({out_port}) v(vdd) i(Vvdd)",
        ".endc",
        ".end",
        "",
    ]
    deck = "\n".join(lines)

    os.makedirs(workdir, exist_ok=True)
    from mbg.simulation import run_spice
    r = run_spice(deck, workdir=workdir, timeout=1800, fmt="dat")
    dat = os.path.join(workdir, "osc.dat")
    if not os.path.isfile(dat):
        return {}

    # ngspice wrdata emits one time column PER probe, so a 3-probe write
    # produces [t0 v0 t1 v1 t2 v2].
    t, v, vddv, ivdd = [], [], [], []
    for line in open(dat):
        line = line.strip()
        if not line or line.startswith(("#", "*", "@", "Index", "---")):
            continue
        parts = line.split()
        if len(parts) >= 6:
            try:
                t.append(float(parts[0])); v.append(float(parts[1]))
                vddv.append(float(parts[3])); ivdd.append(float(parts[5]))
            except ValueError:
                pass
    if len(t) < 200 or max(v) - min(v) < 0.5:
        return {}

    import numpy as np
    t = np.array(t); v = np.array(v); ivdd = np.array(ivdd)

    # Threshold crossings at mid-rail (VDD/2, so it stays valid across PVT).
    th = vdd / 2.0
    up = np.flatnonzero((v[:-1] < th) & (v[1:] >= th))
    down = np.flatnonzero((v[:-1] > th) & (v[1:] <= th))
    if len(up) < 30 or len(down) < 30:
        return {}

    # Startup time: time of the first rising crossing that begins a
    # sustained run (take the 5th crossing to skip the initial ramp blip).
    t_first = t[up[4]] if len(up) > 4 else t[up[0]]
    startup_us = t_first * 1e6

    # Steady state: last 20% of the crossings.
    n_ss = max(20, len(up) // 5)
    up_ss = up[-n_ss:]
    t_up_ss = t[up_ss]
    freq = (len(up_ss) - 1) / (t_up_ss[-1] - t_up_ss[0])
    freq_mhz = freq / 1e6

    # Duty cycle: use falling crossings paired to the same cycles.
    period = 1.0 / freq
    t_hi = []
    for ru in up_ss:
        for rd in down:
            if t[rd] > t[ru]:
                t_hi.append(t[rd] - t[ru])
                break
    duty = 100.0 * (np.mean(t_hi) / period) if t_hi else None

    # VOH/VOL and average supply current in steady state.
    t0 = t_up_ss[0]
    t1 = t_up_ss[-1]
    sel = (t >= t0) & (t <= t1)
    voh = float(v[sel].max())
    vol = float(v[sel].min())
    # ngspice i(Vvdd) convention: negative = current drawn from the supply.
    i_avg_ua = float(-ivdd[sel].mean()) * 1e6

    sustained = len(up) - 5

    m = {
        "freq_mhz": round(freq_mhz, 4),
        "startup_us": round(startup_us, 4),
        "duty_pct": round(duty, 3) if duty else float("nan"),
        "voh_v": round(voh, 4),
        "vol_v": round(vol, 4),
        "i_avg_ua": round(i_avg_ua, 4),
        "sustained": float(sustained),
    }
    return m


def _simulate_pre(design):
    wd = os.path.join(OUTDIR, "sim", "pre")
    m = measure_osc(design.netlist, CELL, workdir=wd)
    if not m:
        raise RuntimeError("pre-layout simulation produced no usable data — "
                           "check the ngspice log; this is a tool failure")
    return m


def _simulate_pex(design, layout):
    if not layout.pex_netlist or not os.path.isfile(layout.pex_netlist):
        raise RuntimeError("no extracted netlist to simulate")
    with open(layout.pex_netlist) as f:
        pex_netlist = f.read()
    wd = os.path.join(OUTDIR, "sim", "pex")
    m = measure_osc(pex_netlist, CELL, workdir=wd)
    if not m:
        raise RuntimeError("PEX simulation produced no usable data — "
                           "the extracted netlist exists but did not "
                           "simulate; this is a tool failure")
    return m


# ── tuners ────────────────────────────────────────────────────────────
from mbg.flow_runtime import scale_device_widths


def _scale_length(netlist, factor):
    """Multiply transistor lengths by ``factor`` (slow/speed the ring)."""
    out = []
    for line in netlist.splitlines():
        m = re.match(r"^(\s*X\S+\s+(?:\S+\s+){3,4}\S*fet_03v3\s+.*?)\bL\s*=\s*([0-9.eE+-]+)([a-zA-Z]*)(\s+.*)$", line)
        if not m:
            out.append(line)
            continue
        try:
            l = float(m.group(2))
        except ValueError:
            out.append(line)
            continue
        new_l = l * factor
        out.append(f"{m.group(1)}L={new_l:g}{m.group(3)}{m.group(4)}")
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")


def tune_pre(design, report):
    failing = {r.name for r in report.failures}
    f = design.circuit.get("freq_mhz")
    if "freq_mhz" in failing and f is not None:
        if f < 10.0:
            step = design.circuit.get("_l_pre", 0) + 1
            return design.evolve(
                netlist=_scale_length(design.netlist, 0.75),
                circuit={**design.circuit, "_l_pre": step},
                note=f"pre_speedup_{step}(L x0.75)")
        if f > 100.0:
            step = design.circuit.get("_l_pre", 0) + 1
            return design.evolve(
                netlist=_scale_length(design.netlist, 1.35),
                circuit={**design.circuit, "_l_pre": step},
                note=f"pre_slow_{step}(L x1.35)")
    if "i_avg_ua" in failing:
        step = design.circuit.get("_w_pre", 0) + 1
        return design.evolve(
            netlist=scale_device_widths(design.netlist, 0.8),
            circuit={**design.circuit, "_w_pre": step},
            note=f"pre_current_{step}(W x0.8)")
    return design


def tune_post(design, report, degradation):
    failing = {r.name for r in report.failures}
    layout = dict(design.layout)
    width = float(layout.get("critical_net_width", 0.28))
    layout["critical_net_width"] = round(min(width * 1.25, 1.0), 4)
    f = design.circuit.get("freq_mhz")
    if "freq_mhz" in failing and f is not None:
        if f < 10.0:
            step = design.circuit.get("_l_pex", 0) + 1
            return design.evolve(
                netlist=_scale_length(design.netlist, 0.8), layout=layout,
                circuit={**design.circuit, "_l_pex": step},
                note=f"pex_speedup_{step}(L x0.8)")
        if f > 100.0:
            step = design.circuit.get("_l_pex", 0) + 1
            return design.evolve(
                netlist=_scale_length(design.netlist, 1.3), layout=layout,
                circuit={**design.circuit, "_l_pex": step},
                note=f"pex_slow_{step}(L x1.3)")
    if "i_avg_ua" in failing:
        step = design.circuit.get("_w_pex", 0) + 1
        return design.evolve(
            netlist=scale_device_widths(design.netlist, 0.85), layout=layout,
            circuit={**design.circuit, "_w_pex": step},
            note=f"pex_current_{step}(W x0.85)")
    return design


# ── hooks ─────────────────────────────────────────────────────────────
hooks = make_hooks(
    cell=CELL, in_node="OSC_OUT", out_node="OSC_OUT",
    supplies={"VDD": 3.3, "VSS": 0.0},
    spec_names=[s.name for s in ALL_SPECS],
    specs=ALL_SPECS,
    outdir=OUTDIR,
    verbosity=1,
)
hooks.simulate_pre = _simulate_pre
hooks.simulate_pex = _simulate_pex
hooks.tune_pre = tune_pre
hooks.tune_post = tune_post
# Branch-and-compare must measure candidates with the SAME metric set.
ref = {"build_layout": hooks.build_layout, "simulate_pex": _simulate_pex}
hooks.propose_candidates = make_candidate_proposer(
    specs=ALL_SPECS, hooks_ref=ref, verbosity=1)

config = FullAutoConfig.for_effort("normal", outdir=OUTDIR)


# ── entry point ───────────────────────────────────────────────────────
def main():
    if "--sanity" in sys.argv:
        m = measure_osc(NETLIST, CELL, workdir=os.path.join(OUTDIR, "sim", "sanity"))
        print("SANITY MEASUREMENT:")
        for k, v in sorted(m.items()):
            print(f"  {k:16s} = {v}")
        return 0

    res = run_full_auto(REQUEST, hooks, cell=CELL, specs=ALL_SPECS,
                        netlist=NETLIST, config=config)

    print("\n" + "=" * 80)
    if hasattr(res, "summary"):
        print(res.summary())
    print("STATUS:", res.status)
    print("TAPEOUT_READY:", res.tapeout_ready)
    print("Report:", res.report_path)
    return 0 if res.tapeout_ready else 1


if __name__ == "__main__":
    sys.exit(main())
