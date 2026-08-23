"""Oscillator measurement + tuning library for the MBG full-auto flow.

simulate_osc_netlist() replaces mbg.flow_runtime.simulate_netlist so both
pre-layout and PEX simulations measure oscillator metrics (frequency, duty
cycle, swing levels, startup time, average supply current, sustained cycles)
instead of the bundled small-signal AC metrics.

Simulation model notes:
- The GF180MCU ngspice model file ships ~1000 quoted parameter expressions
  inside .model cards that ngspice re-interprets at every Newton iteration;
  a 9-stage transient then takes hours instead of seconds. pdk_flat/ holds
  sm141064.ngspice with those expressions pre-evaluated to the same IEEE
  doubles (statistical terms fold to their exact zero under the nominal
  sw_stat_global=0 / sw_stat_mismatch=0 switches). Equivalence was verified:
  operating points match to all printed digits and a 20 ns device transient
  is bit-identical to the unflattened library.
- Supply is an ideal DC source tied at t=0 (normal power-up). There is no
  stimulus on any signal node and no .ic/.nodeset anywhere: startup comes
  from the circuit's own stage-1 asymmetry.
- OSC_OUT sees a 5 fF probe capacitance.
"""
import math
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
FLAT_LIB = os.path.join(_HERE, "pdk_flat", "sm141064.ngspice")


def _pdk_design():
    root = os.environ.get("PDKPATH") or os.path.join(
        os.environ.get("PDK_ROOT", os.path.expanduser("~/.volare")),
        os.environ.get("PDK", "gf180mcuD"))
    return os.path.join(root, "libs.tech", "ngspice", "design.ngspice")


def _subckt_ports(netlist: str, cell: str):
    """Declared port order of the DUT subckt (PEX files may reorder)."""
    m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+(.+)$", netlist,
                  re.MULTILINE | re.IGNORECASE)
    if not m:
        return ["VDD", "VSS", "OSC_OUT"]
    return [p for p in m.group(1).split() if "=" not in p]


def _top_net_for(port: str) -> str:
    lp = port.lower()
    if lp == "vdd":
        return "VDD"
    if lp == "vss":
        return "VSS"
    if "osc" in lp or "out" in lp:
        return "OSC_OUT"
    raise ValueError(f"unexpected DUT port {port!r}")


def build_deck(core_netlist: str, cell: str, *, vdd=3.3, temp=27,
               corner="typical", stop="12.5u", step="100p",
               cprobe="5f") -> str:
    keep = [l for l in core_netlist.splitlines()
            if not l.strip().lower().startswith((".lib", ".include", ".temp"))]
    head = []
    design = _pdk_design()
    if os.path.isfile(design):
        head.append(f".include '{design}'")
    head.append(f".lib '{FLAT_LIB}' {corner}")
    dut_nodes = " ".join(_top_net_for(p)
                         for p in _subckt_ports(core_netlist, cell))
    return "\n".join(
        head + [f".temp {temp}", "", "\n".join(keep).strip(), "",
                "Vsfix VSS 0 0",
                f"Vsup VDD 0 {vdd}",
                f"Cprobe OSC_OUT 0 {cprobe}",
                f"Xdut {dut_nodes} {cell}", "",
                ".control",
                f"tran {step} {stop}",
                "wrdata osc.dat v(OSC_OUT) i(Vsup)",
                ".endc", ".end", ""])


# ── waveform → metrics ────────────────────────────────────────────────

def _load_dat(path):
    ts, vs, isup = [], [], []
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) < 4 or ln[0] in "#*@":
                continue
            try:
                ts.append(float(p[0])); vs.append(float(p[1]))
                isup.append(float(p[3]))
            except ValueError:
                pass
    return ts, vs, isup


def _interp(x0, y0, x1, y1, y):
    return x0 + (y - y0) * (x1 - x0) / (y1 - y0)


def osc_metrics_from_dat(dat_path):
    ts, vs, isup = _load_dat(dat_path)
    n = len(ts)
    if n < 50:
        return {}
    i0 = int(n * 0.6)
    hi, lo = max(vs[i0:]), min(vs[i0:])
    mid, amp = (hi + lo) / 2.0, (hi - lo) / 2.0
    if amp < 0.5 or hi <= lo:
        return {}

    t_start = None
    for i in range(n):
        if abs(vs[i] - mid) >= 0.8 * amp:
            t_start = ts[i]
            break
    if t_start is None:
        return {"startup_time_s": float("inf"), "freq_hz": 0.0,
                "duty_cycle_pct": 0.0, "volt_high_v": hi, "volt_low_v": lo,
                "i_avg_a": 0.0, "cycles_sustained": 0}

    j = 0
    while j < n and ts[j] < t_start + 3e-9:
        j += 1
    rises, falls = [], []
    above = vs[j] >= mid
    for k in range(j + 1, n):
        now = vs[k] >= mid
        if now != above:
            tc = _interp(ts[k - 1], vs[k - 1], ts[k], vs[k], mid)
            (rises if now else falls).append(tc)
        above = now
    if len(rises) < 3:
        return {"startup_time_s": t_start, "freq_hz": 0.0,
                "duty_cycle_pct": 0.0, "volt_high_v": hi, "volt_low_v": lo,
                "i_avg_a": 0.0, "cycles_sustained": 0}

    freq = (len(rises) - 1) / (rises[-1] - rises[0])
    duties, fi = [], 0
    for r0, r1 in zip(rises, rises[1:]):
        while fi < len(falls) and falls[fi] < r0:
            fi += 1
        if fi < len(falls) and falls[fi] < r1:
            duties.append((falls[fi] - r0) / (r1 - r0))
    duty = sum(duties) / len(duties) * 100.0 if duties else float("nan")

    w0 = next(i for i in range(n) if ts[i] >= rises[0])
    idx = range(w0, n)
    voh = max(vs[i] for i in idx)
    vol = min(vs[i] for i in idx)
    i_avg = sum(abs(isup[i]) for i in idx) / len(idx)
    return {"startup_time_s": t_start, "freq_hz": freq,
            "duty_cycle_pct": duty, "volt_high_v": voh, "volt_low_v": vol,
            "i_avg_a": i_avg, "cycles_sustained": float(len(rises) - 1)}


def simulate_osc_netlist(netlist: str, cell: str, spec_names,
                         out_node=None, in_node=None, supplies=None,
                         bias=None, workdir=None, corner="typical",
                         temp=27, vdd=3.3, stop="12.5u", step="100p"):
    from mbg.simulation import run_spice
    wd = workdir or os.path.join(_HERE, "simwork")
    os.makedirs(wd, exist_ok=True)
    tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{cell}_{corner}_{vdd}V_{temp}C")
    wd = os.path.join(wd, tag)
    os.makedirs(wd, exist_ok=True)
    # never let a previous analysis's waveform masquerade as this run's
    stale = os.path.join(wd, "osc.dat")
    if os.path.exists(stale):
        os.remove(stale)
    deck = build_deck(netlist, cell, vdd=vdd, temp=temp, corner=corner,
                      stop=stop, step=step)
    r = run_spice(deck, workdir=wd, fmt="dat", timeout=1200)
    dats = [p for p in r["dat_paths"] if os.path.basename(p) == "osc.dat"]
    if not dats:
        raise RuntimeError(
            f"ngspice produced no waveform data (rc={r['returncode']}) "
            f"— see {wd}")
    return osc_metrics_from_dat(dats[0])


# ── sizing knobs ──────────────────────────────────────────────────────

_DEV_L = re.compile(
    r"^(?P<head>\s*X\w+\s+(?:\S+\s+){3,4}\S*(?:fet|FET)\S*\s+.*?)"
    r"\bL\s*=\s*(?P<l>[0-9.eE+-]+)(?P<unit>[a-zA-Z]*)(?P<tail>.*)$")
_DEV_WP = re.compile(
    r"^(?P<head>\s*X\w+\s+(?:\S+\s+){3,4}(?P<model>\S*p\S*FET\S*|\S*pfet\S*)\s+.*?)"
    r"\bW\s*=\s*(?P<w>[0-9.eE+-]+)(?P<unit>[a-zA-Z]*)(?P<tail>.*)$", re.I)


def scale_device_lengths(netlist: str, factor: float,
                         l_max: float = 10.0) -> str:
    out = []
    for line in netlist.splitlines():
        m = _DEV_L.match(line)
        if not m:
            out.append(line)
            continue
        unit = m.group("unit") or ""
        l = float(m.group("l"))
        new_l = l * factor
        if unit.lower().startswith("u") and new_l >= l_max:
            new_l = l_max - 0.05
        out.append(f"{m.group('head')}L={new_l:g}{unit}{m.group('tail')}")
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")


def scale_pmos_widths(netlist: str, factor: float,
                      w_max: float = 10.0) -> str:
    out = []
    for line in netlist.splitlines():
        m = _DEV_WP.match(line)
        if not m:
            out.append(line)
            continue
        unit = m.group("unit") or ""
        w = float(m.group("w"))
        new_w = w * factor
        if unit.lower().startswith("u") and new_w >= w_max:
            new_w = w_max - 0.01
        out.append(f"{m.group('head')}W={new_w:g}{unit}{m.group('tail')}")
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")
