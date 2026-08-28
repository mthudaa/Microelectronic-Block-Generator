"""Measurement + tuning library for the temp_sensor full-auto run.

``simulate_ts_netlist()`` replaces ``mbg.flow_runtime.simulate_netlist`` so
both pre-layout and PEX simulations measure oscillator/temperature-sensor
metrics (frequency, duty cycle, swing, start-up time, average supply current,
sustained cycles) instead of the bundled small-signal AC metrics.

Modelling notes — all of these are decisions a reader has to be able to audit
-----------------------------------------------------------------------------
* **MOSFET models** come from ``pdk_flat/sm141064.ngspice``: the stock gf180
  library re-evaluates ~1000 quoted parameter expressions inside its .model
  cards at every Newton iteration, which turns a 250 us transient into hours.
  The flattened copy pre-evaluates them to the same IEEE doubles under the
  nominal ``sw_stat_global=0`` / ``sw_stat_mismatch=0`` switches.  Equivalence
  is re-checked by ``check_flat_lib.py`` in this directory.
* **Passives** are taken from the *stock* PDK, not the flattened copy: the
  resistor and MIM corner sections carry their own ``.param`` blocks
  (``rsh_ppolyf_u``, ``mim_corner_2p0ff``) that must come from the corner
  library, and they are cheap to evaluate.  ``.lib res``/``.lib cap_mim_new``
  on their own are *not* sufficient — they define the subcircuits but leave
  ``rsh_ppolyf_u`` and ``mim_corner_2p0ff`` undefined and ngspice aborts.
  The corner wrappers ``res_typical|res_ss|res_ff`` and
  ``mimcap_typical|mimcap_ss|mimcap_ff`` are the sections that define them.
* **Netlist form.** MBG's layout parser wants the two-terminal ``W=/L=`` form
  for ``XR``/``XC`` (that is the form ``tests/netlists/rc_filter.spice`` uses
  and the form the placer understands).  ngspice wants ``ppolyf_u``'s third
  (substrate) terminal and the ``r_width``/``r_length``, ``c_width``/
  ``c_length`` parameter names.  ``_normalise_passives`` translates the layout
  form into the simulation form; it is idempotent, so a Magic-extracted PEX
  netlist (already in the ngspice form) passes through untouched.
* **PEX substrate node.** Magic emits the poly resistor as
  ``X0 a b VSUBS ppolyf_u`` and hangs the extracted substrate parasitics on
  ``VSUBS``, which is not a subcircuit port, so it would float and make the
  matrix singular.  ``_tie_vsubs`` shorts it to the cell's ground port, which
  is what it physically is.
* **Stimulus.** The supply is an ideal DC source applied at t=0 (normal
  power-up).  There is no source on any signal node, no ``.ic``, and no
  ``.nodeset`` anywhere in the deck: start-up comes from the circuit's own
  XMS1/XMS2/XMS3 branch.
* TEMP_OUT is loaded with a 10 fF probe capacitance.
"""
import math
import os
import re

_HERE = os.path.dirname(os.path.abspath(__file__))
FLAT_LIB = os.path.join(_HERE, "pdk_flat", "sm141064.ngspice")

# corner name -> (mosfet section, resistor section, MIM section)
CORNER_LIBS = {
    "typical": ("typical", "res_typical", "mimcap_typical"),
    "ss":      ("ss",      "res_ss",      "mimcap_ss"),
    "ff":      ("ff",      "res_ff",      "mimcap_ff"),
    "sf":      ("sf",      "res_typical", "mimcap_typical"),
    "fs":      ("fs",      "res_typical", "mimcap_typical"),
}

_RES_MODELS = ("ppolyf_u", "npolyf_u", "nplus_u", "pplus_u", "nwell",
               "rm1", "rm2", "rm3")


def _pdk_root():
    return os.environ.get("PDKPATH") or os.path.join(
        os.environ.get("PDK_ROOT", os.path.expanduser("~/.volare")),
        os.environ.get("PDK", "gf180mcuD"))


def _pdk_file(name):
    return os.path.join(_pdk_root(), "libs.tech", "ngspice", name)


# ── netlist normalisation ─────────────────────────────────────────────

def _split_line(line):
    """-> (tokens_before_params, {k: v}) for an X-instance line."""
    parts = line.split()
    head, params = [], {}
    for tok in parts:
        if "=" in tok:
            k, v = tok.split("=", 1)
            params[k.lower()] = v
        else:
            head.append(tok)
    return head, params


def _normalise_passives(netlist: str, gnd: str) -> str:
    """Layout-form XR/XC -> ngspice-form.  Idempotent."""
    out = []
    for line in netlist.splitlines():
        s = line.strip()
        if not s or not s[0] in "Xx" or "=" not in s:
            out.append(line)
            continue
        head, params = _split_line(s)
        if len(head) < 3:
            out.append(line)
            continue
        model = head[-1]
        nodes = head[1:-1]
        low = model.lower()
        if low in _RES_MODELS:
            if "r_width" not in params:
                params["r_width"] = params.pop("w", "1u")
            if "r_length" not in params:
                params["r_length"] = params.pop("l", "4u")
            params.pop("w", None)
            params.pop("l", None)
            if len(nodes) == 2:            # add the substrate terminal
                nodes = nodes + [gnd]
        elif low.startswith("cap_mim"):
            if "c_width" not in params:
                params["c_width"] = params.pop("w", "5u")
            if "c_length" not in params:
                params["c_length"] = params.pop("l", "5u")
            params.pop("w", None)
            params.pop("l", None)
            nodes = nodes[:2]
        else:
            out.append(line)
            continue
        out.append(" ".join([head[0]] + nodes + [model]
                            + [f"{k}={v}" for k, v in params.items()]))
    return "\n".join(out)


_SCALE_OPT = re.compile(r"^\s*\.options?\s+.*\bscale\s*=\s*([0-9.eE+-]+)([a-zA-Z]*)",
                        re.IGNORECASE)
_UNIT = {"": 1.0, "m": 1e-3, "u": 1e-6, "n": 1e-9, "p": 1e-12, "f": 1e-15,
         "k": 1e3, "meg": 1e6}


def _num(text: str) -> float:
    m = re.match(r"^([0-9.eE+-]+)([a-zA-Z]*)$", text.strip())
    if not m:
        return float(text)
    unit = m.group(2).lower()
    for suffix in ("meg", "m", "u", "n", "p", "f", "k"):
        if unit.startswith(suffix):
            return float(m.group(1)) * _UNIT[suffix]
    return float(m.group(1))


def _descale_passive_params(netlist: str) -> str:
    """Undo ``.option scale`` for native-passive geometry parameters.

    Magic's PEX netlist writes every dimension in internal units and puts
    ``.option scale=5n`` at the top.  ngspice's ``scale`` applies to *device*
    geometry, so the MOSFETs inside ``pfet_03v3``/``nfet_03v3`` come out right
    — but ``c_width``/``c_length`` are plain subcircuit parameters feeding a
    ``.param c_area='c_length*c_width'`` expression, and ngspice never scales
    those.  The extracted 34 um MIM was therefore evaluated as c_width=6800
    *metres*, i.e. about 9e4 F, and the timing node could not charge at all:
    the post-layout netlist simulated as a dead circuit for a reason that had
    nothing to do with the layout.

    The fix rewrites only the passive width/length parameters into explicit
    absolute units and leaves ``.option scale`` in place for the transistors.
    The resistor is rewritten too: its resistance depends only on the
    length/width *ratio* so it was already right, but making it absolute also
    makes the r_dw edge correction correct instead of negligible-by-accident.
    """
    m = None
    for line in netlist.splitlines():
        m = _SCALE_OPT.match(line) or m
    if not m:
        return netlist
    scale = _num(m.group(1) + m.group(2))
    if scale == 1.0:
        return netlist
    keys = ("c_width", "c_length", "r_width", "r_length")
    out = []
    for line in netlist.splitlines():
        s = line.strip()
        if not s or s[0] not in "Xx" or "=" not in s:
            out.append(line)
            continue
        head, params = _split_line(s)
        model = head[-1].lower() if head else ""
        if not (model in _RES_MODELS or model.startswith("cap_mim")):
            out.append(line)
            continue
        for k in keys:
            if k in params:
                params[k] = f"{_num(params[k]) * scale:.6g}"
        out.append(" ".join(head[:-1] + [head[-1]]
                            + [f"{k}={v}" for k, v in params.items()]))
    return "\n".join(out)


def _tie_vsubs(netlist: str, cell: str, gnd: str) -> str:
    """Short Magic's floating VSUBS node to the cell's ground port."""
    if not re.search(r"\bVSUBS\b", netlist):
        return netlist
    out, inside = [], False
    for line in netlist.splitlines():
        s = line.strip()
        if re.match(rf"^\.subckt\s+{re.escape(cell)}\b", s, re.I):
            inside = True
        elif inside and s.lower().startswith(".ends"):
            out.append(f"RVSUBSTIE VSUBS {gnd} 1m")
            inside = False
        out.append(line)
    return "\n".join(out)


def _subckt_ports(netlist: str, cell: str):
    m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+(.+)$", netlist,
                  re.MULTILINE | re.IGNORECASE)
    if not m:
        return ["VDD", "VSS", "TEMP_OUT"]
    return [p for p in m.group(1).split() if "=" not in p]


def _classify_port(port: str) -> str:
    lp = port.lower()
    if lp in ("vdd", "vcc", "vdda"):
        return "VDD"
    if lp in ("vss", "gnd", "vssa", "0"):
        return "VSS"
    return "TEMP_OUT"


VRAMP_S = 1e-6          # supply rise time of the modelled power-up

# Integration accuracy.  ``trtol`` is the load-bearing one: at its ngspice
# default of 7 the local truncation error accumulated into the *voltage-source
# branch current* of this deck, so i(Vsup) drifted from 41 uA to 520 uA over
# 40 us while every node voltage, the frequency and the duty cycle stayed
# correct, and the drift changed when unrelated vectors were added to wrdata.
# With trtol=1 the measurement is stable in time and identical across those
# variants (41.3 -> 42.7 uA).  The remaining tolerances are tightened so the
# average-supply-current figure is a real number rather than an artefact.
SIM_OPTIONS = (".options reltol=1e-4 vntol=1e-8 abstol=1e-15 "
               "chgtol=1e-16 trtol=1")


def build_deck(core_netlist: str, cell: str, *, vdd=3.3, temp=27,
               corner="typical", stop="250u", step="4n",
               cprobe="10f", power_up=True) -> str:
    """Assemble the simulation deck.

    ``power_up=True`` (the acceptance configuration) models a real power-up:
    the supply is a 1 us ramp from 0 V and the transient runs with ``uic``, so
    every node starts at 0 V and ngspice never solves a DC operating point.
    That is the *least* favourable initial state, not a forced one — there is
    no ``.ic``/``.nodeset`` in the deck and no source on any signal node.  It
    is a strictly stronger start-up test than the default DC-op start, which
    would hand the circuit its settled bias for free.

    ``power_up=False`` starts from the DC operating point instead, and is kept
    only as a cross-check that the design also runs from that state.
    """
    ports = _subckt_ports(core_netlist, cell)
    gnd = next((p for p in ports if _classify_port(p) == "VSS"), "VSS")
    core = _tie_vsubs(_normalise_passives(
        _descale_passive_params(core_netlist), gnd), cell, gnd)
    keep = [l for l in core.splitlines()
            if not l.strip().lower().startswith((".lib", ".include", ".temp"))]
    mos_lib, res_lib, mim_lib = CORNER_LIBS.get(corner,
                                                CORNER_LIBS["typical"])
    stock = _pdk_file("sm141064.ngspice")
    head = []
    design = _pdk_file("design.ngspice")
    if os.path.isfile(design):
        head.append(f".include '{design}'")
    head.append(f".lib '{FLAT_LIB}' {mos_lib}")
    head.append(f".lib '{stock}' {res_lib}")
    head.append(f".lib '{stock}' {mim_lib}")
    dut_nodes = " ".join(_classify_port(p) for p in ports)
    if power_up:
        supply = f"Vsup VDD 0 PWL(0 0 {VRAMP_S:g} {vdd})"
        analysis = f"tran {step} {stop} uic"
    else:
        supply = f"Vsup VDD 0 {vdd}"
        analysis = f"tran {step} {stop}"
    return "\n".join(
        head + [SIM_OPTIONS, f".temp {temp}", "", "\n".join(keep).strip(), "",
                "Vsfix VSS 0 0",
                supply,
                f"Cprobe TEMP_OUT 0 {cprobe}",
                f"Xdut {dut_nodes} {cell}", "",
                ".control",
                analysis,
                # The ramp node only exists by name in the pre-layout netlist;
                # Magic renames it (a_14_27788#) in the extracted one, so the
                # diagnostic probe is added only when it is really there.
                "wrdata ts.dat v(TEMP_OUT) i(Vsup)"
                + (" v(Xdut.ncap)" if re.search(r"\bncap\b", core) else ""),
                ".endc", ".end", ""])


# ── waveform -> metrics ───────────────────────────────────────────────

def _load_dat(path):
    ts, vs, isup = [], [], []
    with open(path) as f:
        for ln in f:
            p = ln.split()
            if len(p) < 4 or ln[0] in "#*@":
                continue
            try:
                ts.append(float(p[0]))
                vs.append(float(p[1]))
                isup.append(float(p[3]))
            except ValueError:
                pass
    return ts, vs, isup


def _interp(x0, y0, x1, y1, y):
    if y1 == y0:
        return x1
    return x0 + (y - y0) * (x1 - x0) / (y1 - y0)


def ts_metrics_from_dat(dat_path, vdd=3.3):
    """Frequency / duty / swing / start-up / current from the TEMP_OUT trace.

    Start-up time is the instant TEMP_OUT first rises through 0.9*VDD, i.e.
    the first valid output HIGH after power-up.  Everything else is measured
    on the settled waveform after that instant.
    """
    ts, vs, isup = _load_dat(dat_path)
    n = len(ts)
    if n < 50:
        return {}
    i0 = int(n * 0.5)
    hi, lo = max(vs[i0:]), min(vs[i0:])
    mid, amp = (hi + lo) / 2.0, (hi - lo) / 2.0
    if amp < 0.5 * 0.5 or hi <= lo:
        return {"startup_time_s": float("inf"), "freq_hz": 0.0,
                "duty_cycle_pct": 0.0, "volt_high_v": hi, "volt_low_v": lo,
                "i_avg_a": sum(abs(i) for i in isup) / n,
                "cycles_sustained": 0.0}

    thr_hi = 0.9 * vdd
    t_start = None
    for i in range(1, n):
        if vs[i] >= thr_hi and vs[i - 1] < thr_hi:
            t_start = _interp(ts[i - 1], vs[i - 1], ts[i], vs[i], thr_hi)
            break
    if t_start is None:
        return {"startup_time_s": float("inf"), "freq_hz": 0.0,
                "duty_cycle_pct": 0.0, "volt_high_v": hi, "volt_low_v": lo,
                "i_avg_a": sum(abs(i) for i in isup) / n,
                "cycles_sustained": 0.0}

    j = next((i for i in range(n) if ts[i] >= t_start), n - 1)
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
                "i_avg_a": sum(abs(i) for i in isup[j:]) / max(n - j, 1),
                "cycles_sustained": float(max(len(rises) - 1, 0))}

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
    # Time-weighted (trapezoidal) mean.  A plain sample mean would be wrong:
    # ngspice clusters timepoints around the fast output edges, exactly where
    # the crowbar current spikes, so an unweighted average over-reports the
    # supply current by a factor that depends on the timestep controller.
    num = den = 0.0
    for i in range(w0 + 1, n):
        dt = ts[i] - ts[i - 1]
        num += 0.5 * (abs(isup[i]) + abs(isup[i - 1])) * dt
        den += dt
    i_avg = num / den if den > 0 else 0.0
    return {"startup_time_s": t_start, "freq_hz": freq,
            "duty_cycle_pct": duty, "volt_high_v": voh, "volt_low_v": vol,
            "i_avg_a": i_avg, "cycles_sustained": float(len(rises) - 1)}


# ── driver ────────────────────────────────────────────────────────────

MIN_CYCLES = 100
PROBE_STOP = 20e-6          # first pass: only has to measure the period
MAX_STOP = 900e-6           # hard bound so a dead design cannot run forever


def _run_once(netlist, cell, wd, corner, temp, vdd, stop_s, power_up=True):
    from mbg.simulation import run_spice
    # Keep the point count roughly constant instead of scaling it with the
    # run length: a 250 us slow-corner run does not need 8x the samples of a
    # 30 us one.  ngspice still refines internally under trtol=1, so this is
    # the *maximum* step, not the integration step.  Verified: 3 ns, 10 ns
    # and 40 ns caps on a 145 us slow-corner run agree on frequency to
    # 0.01 %, on duty cycle to 3 decimals and on average current to 0.03 %.
    step_s = min(max(stop_s / 20000.0, 1e-9), 1e-8)
    stale = os.path.join(wd, "ts.dat")
    if os.path.exists(stale):
        os.remove(stale)
    deck = build_deck(netlist, cell, vdd=vdd, temp=temp, corner=corner,
                      stop=f"{stop_s:g}", step=f"{step_s:g}", power_up=power_up)
    with open(os.path.join(wd, "deck.sp"), "w") as f:
        f.write(deck)
    r = run_spice(deck, workdir=wd, fmt="dat", timeout=3600)
    dats = [p for p in r["dat_paths"] if os.path.basename(p) == "ts.dat"]
    if not dats:
        raise RuntimeError(
            f"ngspice produced no waveform data (rc={r['returncode']}) "
            f"— see {wd}")
    return ts_metrics_from_dat(dats[0], vdd=vdd)


def simulate_ts_netlist(netlist: str, cell: str, spec_names=None,
                        out_node=None, in_node=None, supplies=None,
                        bias=None, workdir=None, corner="typical",
                        temp=27, vdd=3.3, stop=None, step=None,
                        power_up=True):
    """Measure the sensor.  Two-pass: probe, then extend to >=100 cycles.

    The stop time is chosen from the *measured* frequency rather than assumed,
    so the 100-cycle sustained-oscillation criterion is evaluated on real
    cycles at every corner instead of being extrapolated from a short run.
    """
    wd = workdir or os.path.join(_HERE, "simwork")
    tag = re.sub(r"[^A-Za-z0-9_.-]+", "_", f"{cell}_{corner}_{vdd}V_{temp}C")
    wd = os.path.join(wd, tag)
    os.makedirs(wd, exist_ok=True)

    stop_s = float(stop) if stop else PROBE_STOP
    m = _run_once(netlist, cell, wd, corner, temp, vdd, stop_s, power_up)
    f = m.get("freq_hz") or 0.0
    cyc = m.get("cycles_sustained") or 0.0
    if stop is None and f > 0 and cyc < MIN_CYCLES + 5:
        need = (m.get("startup_time_s") or 0.0) + (MIN_CYCLES + 8) / f
        need = min(need * 1.1, MAX_STOP)
        if need > stop_s * 1.05:
            m = _run_once(netlist, cell, wd, corner, temp, vdd, need,
                          power_up)
    return m


# ── sizing knobs used by the tuners / search strategy ─────────────────

_RES_LINE = re.compile(r"^(?P<head>\s*X\w+\s+.*?\bppolyf_u\b.*?)"
                       r"\b(?P<key>[rR]_length|L)\s*=\s*"
                       r"(?P<v>[0-9.eE+-]+)(?P<unit>[a-zA-Z]*)(?P<tail>.*)$")
_CAP_LINE = re.compile(r"^(?P<head>\s*X\w+\s+.*?\bcap_mim\w*\b.*?)$")
_DEV_W = re.compile(
    r"^(?P<head>\s*X(?P<nm>\w+)\s+(?:\S+\s+){3,4}\S*(?:fet|FET)\S*\s+.*?)"
    r"\bW\s*=\s*(?P<w>[0-9.eE+-]+)(?P<unit>[a-zA-Z]*)(?P<tail>.*)$")


def scale_resistor(netlist: str, factor: float, l_max: float = 400.0) -> str:
    """Scale the beta-multiplier degeneration resistor length.

    I ~ 1/R^2, and f ~ I, so this is the dominant frequency knob.
    """
    out = []
    for line in netlist.splitlines():
        m = _RES_LINE.match(line)
        if not m:
            out.append(line)
            continue
        val = float(m.group("v")) * factor
        unit = m.group("unit") or ""
        if unit.lower().startswith("u"):
            val = min(max(val, 5.0), l_max)
        out.append(f"{m.group('head')}{m.group('key')}={val:g}{unit}"
                   f"{m.group('tail')}")
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")


def scale_cap(netlist: str, factor: float, s_min: float = 5.0,
              s_max: float = 60.0) -> str:
    """Scale the MIM timing capacitor edge length (area ~ edge^2)."""
    edge_f = math.sqrt(factor)
    out = []
    for line in netlist.splitlines():
        if "cap_mim" not in line:
            out.append(line)
            continue
        def _rep(mm):
            v = float(mm.group(2)) * edge_f
            return f"{mm.group(1)}={min(max(v, s_min), s_max):g}u"
        out.append(re.sub(r"\b([WLwl]|c_width|c_length)=([0-9.eE+-]+)u",
                          _rep, line))
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")


def scale_widths(netlist: str, factor: float, names, w_max: float = 9.9,
                 w_min: float = 0.22) -> str:
    """Scale W of the named devices (``XMSN3`` etc., without the leading X)."""
    want = {n.lower().lstrip("x") for n in names}
    out = []
    for line in netlist.splitlines():
        m = _DEV_W.match(line)
        if not m or m.group("nm").lower() not in want:
            out.append(line)
            continue
        unit = m.group("unit") or ""
        w = float(m.group("w")) * factor
        if unit.lower().startswith("u"):
            w = min(max(w, w_min), w_max)
        out.append(f"{m.group('head')}W={w:g}{unit}{m.group('tail')}")
    return "\n".join(out) + ("\n" if netlist.endswith("\n") else "")


def scale_hysteresis(netlist: str, factor: float) -> str:
    """Widen (>1) or narrow (<1) the Schmitt window via the feedback pair.

    Stronger feedback devices (XMSN3 / XMSP3) push the two trip points apart,
    which raises dV and therefore lowers f.
    """
    return scale_widths(netlist, factor, ["MSN3", "MSP3"])


def scale_discharge(netlist: str, factor: float) -> str:
    """Trim the discharge sink relative to the charge source -> duty cycle."""
    return scale_widths(netlist, factor, ["MNC"])
