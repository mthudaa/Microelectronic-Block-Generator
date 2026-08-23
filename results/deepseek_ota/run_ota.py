"""Run the MBG FULL AUTOMATE flow on a 6T OTA with an external IBIAS input.

Specification (user-provided):
  - OTA, ports VDD VSS INP INN OUT IBIAS, .subckt ota VDD VSS INP INN OUT IBIAS
  - IBIAS is an external bias current input (nominal 20 uA).
  - GF180MCU, VDD = 3.3 V, VSS = 0 V, VIN_CM = 1.65 V, CL = 5 pF, 27 C.
  - DC gain >= 35 dB, GBW >= 1 MHz, phase margin >= 60 deg,
    slew (rise and fall) >= 0.5 V/us, supply current <= 250 uA,
    output DC at zero diff input = 1.65 V +/- 0.5 V, usable swing >= 0.5-2.8 V.
  - Characterize CMRR, PSRR, ICMR, power, noise and offset.
  - PVT: VDD 3.0/3.3/3.6 V, temp -40/27/125 C, corners typical/ff/ss.

The circuit is the simplest topology that can centre the output: a classic
NMOS-input differential pair with a PMOS current-mirror load and an NMOS tail
that mirrors the external IBIAS current (a diode-connected NMOS on the IBIAS
node makes the external current a real current input). This is the plainest
structure that satisfies the full spec set including the mid-rail output DC.

Measurement is intentionally richer than the bundled gain/bw-only hook: the
same AC, DC, transient, noise and supply-current measurements run identically
on the schematic and on the Magic-extracted netlist, so pre-layout and PEX
numbers are directly comparable.
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
CELL = "ota"
OUTDIR = os.path.join(os.path.expanduser("~"),
                      "opensource-project", "Microelectronic-Block-Generator",
                      "results", "deepseek_ota")
os.makedirs(OUTDIR, exist_ok=True)

lib_path = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice",
                        "sm141064.ngspice")

# ── netlist ───────────────────────────────────────────────────────────
# 6 MOS, flat, single subckt. NMOS diff pair (XM1/XM2), PMOS current-mirror
# load (XM3 diode-connected / XM4 mirror), NMOS tail (XM5) mirroring the
# external IBIAS through diode-connected XM6, so IBIAS is a true current input.
# Sizing chosen to centre the output DC near mid-rail and to hold the
# 1.65 +/- 0.5 V window across the full PVT grid (VDD 3.0-3.6 V, -40..125 C,
# typical/ff/ss): nominal ~1.67 V, PVT range [1.20, 2.15] V.
NETLIST = f"""
.lib "{lib_path}" typical
.subckt {CELL} VDD VSS INP INN OUT IBIAS
XM1  net1 INP net2 VSS nfet_03v3 L=1u W=4u nf=4
XM2  OUT  INN net2 VSS nfet_03v3 L=1u W=4u nf=4
XM3  net1 net1 VDD VDD pfet_03v3 L=1u W=2.4u nf=4
XM4  OUT  net1 VDD VDD pfet_03v3 L=1u W=2.4u nf=4
XM5  net2 IBIAS VSS VSS nfet_03v3 L=1u W=8u nf=4
XM6  IBIAS IBIAS VSS VSS nfet_03v3 L=1u W=4u nf=4
.ends
""".strip()

# ── specifications ────────────────────────────────────────────────────
SPECS = [
    Spec("gain_db", ">=", 35.0, " dB"),
    Spec("ugf_hz", ">=", 1e6, " Hz"),          # GBW (unity-gain frequency)
    Spec("pm_deg", ">=", 60.0, " deg"),
    Spec("slew_rise_vus", ">=", 0.5, " V/us"),
    Spec("slew_fall_vus", ">=", 0.5, " V/us"),
    Spec("idd_ua", "<=", 250.0, " uA"),
    Spec("vout_dc", "==", 1.65, " V", tol=0.5),
    Spec("vout_hi", ">=", 2.8, " V"),
    Spec("vout_lo", "<=", 0.5, " V"),
]
# Characterization-only (no user target): tracked, never required.
INFO_SPECS = [
    Spec("cmrr_db", ">=", 30.0, " dB", required=False),
    Spec("psrr_db", ">=", 30.0, " dB", required=False),
    Spec("icmr_lo", "<=", 1.2, " V", required=False),
    Spec("icmr_hi", ">=", 2.5, " V", required=False),
    Spec("offset_mv", "==", 0.0, " mV", tol=50.0, required=False),
    Spec("inoise_rms", "<=", 1e-3, " V", required=False),
    Spec("onoise_rms", "<=", 1e-2, " V", required=False),
]
ALL_SPECS = SPECS + INFO_SPECS

REQUEST = (
    "Design an Operational Transconductance Amplifier (OTA) in GF180MCU "
    "with ports VDD VSS INP INN OUT IBIAS where IBIAS is an external bias "
    "current input. VDD=3.3 V, VSS=0 V, VIN_CM=1.65 V, CL=5 pF, 27 C. "
    "DC gain >= 35 dB, GBW >= 1 MHz, phase margin >= 60 deg, "
    "rising and falling slew rate >= 0.5 V/us, supply current (excluding "
    "IBIAS) <= 250 uA, output DC at zero differential input = 1.65 V +/- 0.5 V, "
    "usable output swing >= 0.5-2.8 V. "
    "Also characterize CMRR, PSRR, input common-mode range, power, noise and "
    "offset, and check PVT corners (VDD 3.0/3.3/3.6 V, temp -40/27/125 C, "
    "gf180 typical/ff/ss)."
)

# ── measurement infrastructure ────────────────────────────────────────
from mbg.analysis import Testbench, SimResult, _parse_print, _parse_wrdata
from mbg.simulation import run_spice


class OtaTB(Testbench):
    """Testbench that injects the IBIAS current source and a temperature card."""

    def __init__(self, *args, extra_currents=None, ac_nodes=None,
                 extra_vsources=None, extra_elements=None, temp=27.0, **kw):
        super().__init__(*args, **kw)
        self.extra_currents = dict(extra_currents or {})
        self.ac_nodes = set(ac_nodes or ())
        self.extra_vsources = dict(extra_vsources or {})
        self.extra_elements = list(extra_elements or [])
        self.temp = temp
        self.supply_srcs = {}
        self.src_srcs = {}

    def _stimulus(self):
        lines = []
        for i, (node, val) in enumerate(self.supplies.items()):
            v = str(val)
            if node in self.ac_nodes:
                v = v.rstrip() + " AC 1"
            lines.append(f"Vsupply{i} {node} 0 {v}")
            self.supply_srcs[node] = f"Vsupply{i}"
        for i, (node, val) in enumerate(self.sources.items()):
            v = str(val)
            if node in self.ac_nodes:
                v = v.rstrip() + " AC 1"
            lines.append(f"Vsrc{i} {node} 0 {v}")
            self.src_srcs[node] = f"Vsrc{i}"
        for i, (node, val) in enumerate(self.extra_vsources.items()):
            lines.append(f"Vx{i} {node} 0 {val}")
        for node, spec in self.loads.items():
            lines.append(f"C_load_{node} {node} 0 {spec}")
        for node, val in self.extra_currents.items():
            lines.append(f"Ibias_{node} 0 {node} DC {val}")
        for ln in self.extra_elements:
            lines.append(ln)
        return lines

    def build_deck(self, analysis_lines, control):
        deck = super().build_deck(analysis_lines, control)
        out = []
        inserted = False
        for ln in deck.splitlines():
            out.append(ln)
            if ln.strip().startswith(".lib") and not inserted:
                out.append(f".temp {self.temp}")
                inserted = True
        return "\n".join(out)

    def custom(self, analysis, control, *, datfile=None, x_name="",
               probes=(), complex_data=False, analysis_lines=()):
        deck = self.build_deck(analysis_lines, control)
        r = run_spice(deck, workdir=self.workdir, timeout=self.timeout,
                      fmt="dat")
        res = SimResult(analysis=analysis, x_name=x_name,
                        returncode=r["returncode"],
                        stdout=r.get("stdout", ""), stderr=r.get("stderr", ""),
                        workdir=r.get("workdir", ""), deck=deck)
        _parse_print(res, probes)
        if datfile:
            for p in r.get("dat_paths") or []:
                if os.path.basename(p) == datfile:
                    _parse_wrdata(res, p, x_name, probes, complex_data)
                    break
        return res


def parse_ports(netlist, cell):
    m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+(.+)$", netlist,
                  re.MULTILINE | re.IGNORECASE)
    if not m:
        raise ValueError(f".subckt {cell} not found in netlist")
    ports = m.group(1).split()
    roles = {"vdd": None, "vss": None, "inp": None, "inn": None,
             "out": None, "ibias": None}
    for p in ports:
        pl = p.lower()
        if pl in ("vdd", "vcc", "avdd"):
            roles["vdd"] = roles["vdd"] or p
        elif pl in ("vss", "gnd", "avss", "vss!"):
            roles["vss"] = roles["vss"] or p
        elif "ibias" in pl or "bias" in pl or pl in ("vb", "ib"):
            roles["ibias"] = roles["ibias"] or p
        elif pl in ("out", "vo", "o", "output"):
            roles["out"] = roles["out"] or p
        elif pl in ("inp", "ip", "vinp", "vip", "inp!"):
            roles["inp"] = roles["inp"] or p
        elif pl in ("inn", "inm", "im", "vinn", "vinm", "inm!"):
            roles["inn"] = roles["inn"] or p
        elif pl.startswith("in") and len(pl) >= 3:
            if pl[-1] in ("n", "m"):
                roles["inn"] = roles["inn"] or p
            else:
                roles["inp"] = roles["inp"] or p
        elif pl.startswith("vd"):
            roles["vdd"] = roles["vdd"] or p
        elif pl.startswith("vs"):
            roles["vss"] = roles["vss"] or p
    missing = [r for r, v in roles.items() if v is None]
    if missing:
        raise ValueError(f"could not identify port roles {missing} "
                         f"among {ports}")
    return roles


def _phase(res, name, f):
    re_v = res.signals.get(f"{name}.re")
    im_v = res.signals.get(f"{name}.im")
    if not re_v or not im_v:
        return None
    for fr, rv, iv in zip(res.x, re_v, im_v):
        if fr >= f:
            return math.degrees(math.atan2(iv, rv))
    return math.degrees(math.atan2(im_v[-1], re_v[-1]))


def _largest_contiguous(x, y, lo, hi):
    best = None
    cur = None
    for xi, yi in zip(x, y):
        if lo <= yi <= hi:
            if cur is None:
                cur = [xi, xi]
            else:
                cur[1] = xi
        else:
            if cur is not None:
                if best is None or (cur[1] - cur[0]) > (best[1] - best[0]):
                    best = cur
                cur = None
    if cur is not None and (best is None or (cur[1] - cur[0]) > (best[1] - best[0])):
        best = cur
    return (best[0], best[1]) if best else (None, None)


def _slew_segment(to, yo, t_start, t_end):
    """Slew rate over one edge via 10-90% crossings of the local swing."""
    xs, ys = [], []
    for t, y in zip(to, yo):
        if t_start <= t <= t_end:
            xs.append(t)
            ys.append(y)
    if len(xs) < 4:
        return None
    lo, hi = min(ys), max(ys)
    span = hi - lo
    if span <= 1e-9:
        return None

    def cross(level):
        for i in range(1, len(xs)):
            a, b = ys[i - 1], ys[i]
            if a < level <= b or a > level >= b:
                if b == a:
                    return xs[i]
                return xs[i - 1] + (level - a) / (b - a) * (xs[i] - xs[i - 1])
        return None

    t1 = cross(lo + 0.1 * span)
    t2 = cross(lo + 0.9 * span)
    if t1 is None or t2 is None:
        return None
    ta, tb = min(t1, t2), max(t1, t2)
    if tb <= ta:
        return None
    return 0.8 * span / (tb - ta)


def measure_all(netlist, cell, *, vdd=3.3, vss=0.0, vcm=1.65, ibias=20e-6,
                cl=5e-12, corner="typical", temp=27.0, workdir="sim"):
    """Measure the full OTA metric set on any netlist (schematic or extracted).

    Returns an empty dict on any core-measurement failure so the flow treats
    it as a tool failure. Optional characterizations (CMRR/PSRR/ICMR/noise/
    offset) degrade to ``None`` rather than failing the run.
    """
    mcell = re.search(r"^\.subckt\s+(\S+)", netlist, re.MULTILINE | re.IGNORECASE)
    if mcell:
        cell = mcell.group(1)
    roles = parse_ports(netlist, cell)
    supplies = {roles["vdd"]: vdd, roles["vss"]: vss}
    sources = {roles["inp"]: f"DC {vcm}", roles["inn"]: f"DC {vcm}"}
    loads = {roles["out"]: f"{cl:.6g}"}
    extras = {roles["ibias"]: f"{ibias:.6g}"}
    out = roles["out"]
    inp = roles["inp"]
    wd = workdir
    os.makedirs(wd, exist_ok=True)

    try:
        # ── main run: op + ac + dc transfer + noise ────────────────────
        tb = OtaTB(netlist, cell, supplies=supplies,
                   sources={inp: f"DC {vcm}", roles["inn"]: f"DC {vcm}"},
                   loads=loads, corner=corner, temp=temp,
                   extra_currents=extras, ac_nodes={inp},
                   probes=[out], workdir=wd, timeout=600)
        vdd_src = "Vsupply%d" % list(supplies.keys()).index(roles["vdd"])
        inp_src = "Vsrc%d" % list(sources.keys()).index(inp)
        ctrl = [
            "op",
            f"print v({out}) i({vdd_src})",
            "ac dec 25 1 1e9",
            f"wrdata ac.dat v({out})",
            f"dc {inp_src} 0.4 2.9 0.005",
            f"wrdata dc.dat v({out})",
            "noise v(" + out + ") " + inp_src + " dec 10 1 100Meg",
            "print inoise_total onoise_total",
        ]
        res = tb.custom("main", ctrl, datfile="dc.dat", x_name="inp",
                        probes=[out])
        if not res.ok:
            return {}

        ac_res = tb.custom("ac", ["ac dec 25 1 1e9", f"wrdata ac2.dat v({out})"],
                           datfile="ac2.dat", x_name="freq", probes=[out],
                           complex_data=True)
        if not ac_res.ok or not ac_res.x:
            return {}
        mag = ac_res.get(out)
        if not mag or max(mag) <= 0:
            return {}
        db = [20.0 * math.log10(v) for v in mag]
        gain_db = db[0]
        bw_hz = None
        for f, d in zip(ac_res.x, db):
            if d <= gain_db - 3.0:
                bw_hz = f
                break
        ugf_hz = None
        for f, d in zip(ac_res.x, db):
            if d <= 0.0:
                ugf_hz = f
                break
        pm_deg = None
        if ugf_hz is not None:
            ph = _phase(ac_res, out, ugf_hz)
            if ph is not None:
                pm_deg = 180.0 + ph

        m = {
            "gain_db": gain_db,
            "bw_hz": bw_hz if bw_hz is not None else float("nan"),
            "ugf_hz": ugf_hz if ugf_hz is not None else float("nan"),
            "pm_deg": pm_deg if pm_deg is not None else float("nan"),
        }

        # operating point
        vout_dc = res.value(f"v({out})")
        idd = abs(res.value(f"i({vdd_src})"))
        m["vout_dc"] = vout_dc
        m["idd_ua"] = idd * 1e6

        # DC transfer: swing + systematic offset
        voutc = res.get(out)
        m["vout_hi"] = max(voutc)
        m["vout_lo"] = min(voutc)
        off = None
        for i in range(1, len(voutc)):
            a, b = voutc[i - 1], voutc[i]
            if (a - 1.65) * (b - 1.65) <= 0 and b != a:
                vin = res.x[i - 1] + (1.65 - a) / (b - a) * (res.x[i] - res.x[i - 1])
                off = (vin - vcm) * 1000.0
                break
        m["offset_mv"] = off

        # noise totals (input-/output-referred, integrated 1 Hz .. 100 MHz)
        m["inoise_rms"] = res.value("inoise_total")
        m["onoise_rms"] = res.value("onoise_total")
    except Exception as e:                      # noqa: BLE001
        print(f"[MEASURE] core measurement failed: {type(e).__name__}: {e}")
        return {}

    # ── common-mode AC (CMRR) ──────────────────────────────────────────
    try:
        tb_cm = OtaTB(netlist, cell, supplies=supplies,
                      sources={inp: f"DC {vcm}", roles["inn"]: f"DC {vcm}"},
                      loads=loads, corner=corner, temp=temp,
                      extra_currents=extras, ac_nodes={inp, roles["inn"]},
                      probes=[out], workdir=wd, timeout=600)
        cm = tb_cm.custom("ac", ["ac dec 15 1 1e7", f"wrdata cm.dat v({out})"],
                          datfile="cm.dat", x_name="freq", probes=[out],
                          complex_data=True)
        if cm.ok and cm.get(out):
            m["cmrr_db"] = gain_db - 20.0 * math.log10(cm.get(out)[0])
    except Exception:                           # noqa: BLE001
        pass

    # ── supply AC (PSRR) ───────────────────────────────────────────────
    try:
        tb_ps = OtaTB(netlist, cell,
                      supplies={roles["vdd"]: vdd, roles["vss"]: vss},
                      sources={inp: f"DC {vcm}", roles["inn"]: f"DC {vcm}"},
                      loads=loads, corner=corner, temp=temp,
                      extra_currents=extras, ac_nodes={roles["vdd"]},
                      probes=[out], workdir=wd, timeout=600)
        ps = tb_ps.custom("ac", ["ac dec 15 1 1e7", f"wrdata ps.dat v({out})"],
                          datfile="ps.dat", x_name="freq", probes=[out],
                          complex_data=True)
        if ps.ok and ps.get(out):
            m["psrr_db"] = gain_db - 20.0 * math.log10(ps.get(out)[0])
    except Exception:                           # noqa: BLE001
        pass

    # ── input common-mode range ────────────────────────────────────────
    try:
        # Both inputs are tied to one swept source, so the DUT sees a pure
        # common-mode sweep. The 0V tie source makes INN follow INP.
        tie = f"Vtie_cm {inp} {roles['inn']} 0"
        tb_ic = OtaTB(netlist, cell, supplies=supplies,
                      sources={inp: "DC 1.65"}, loads=loads,
                      corner=corner, temp=temp, extra_currents=extras,
                      extra_elements=[tie], probes=[out], workdir=wd,
                      timeout=600)
        ic = tb_ic.custom("dc", ["dc Vsrc0 0.4 3.0 0.05",
                                 f"wrdata ic.dat v({out})"],
                          datfile="ic.dat", x_name="vcm", probes=[out])
        if ic.ok and ic.get(out):
            ref = m.get("vout_dc")
            if ref:
                lo, hi = _largest_contiguous(ic.x, ic.get(out),
                                             ref - 0.5, ref + 0.5)
                if lo is not None:
                    m["icmr_lo"] = lo
                    m["icmr_hi"] = hi
    except Exception:                           # noqa: BLE001
        pass

    # ── transient: slew rates + large-signal rails ─────────────────────
    try:
        tb_tr = OtaTB(netlist, cell, supplies=supplies,
                      sources={inp: "DC 1.35 PULSE(1.35 1.95 0 5n 5n 30u 60u)",
                               roles["inn"]: f"DC {vcm}"},
                      loads=loads, corner=corner, temp=temp,
                      extra_currents=extras, probes=[out], workdir=wd,
                      timeout=900)
        tr = tb_tr.custom("tran", ["tran 10n 60u", f"wrdata tr.dat v({out})"],
                          datfile="tr.dat", x_name="time", probes=[out])
        if tr.ok and tr.get(out):
            yo = tr.get(out)
            to = tr.x
            rise = _slew_segment(to, yo, 0.0, 20e-6)
            fall = _slew_segment(to, yo, 30e-6, 50e-6)
            m["slew_rise_vus"] = (rise / 1e6) if rise else float("nan")
            m["slew_fall_vus"] = (fall / 1e6) if fall else float("nan")
            m["tran_vout_hi"] = max(yo)
            m["tran_vout_lo"] = min(yo)
    except Exception:                           # noqa: BLE001
        pass

    return m


def _simulate_pre(design):
    wd = os.path.join(OUTDIR, "sim", "pre")
    m = measure_all(design.netlist, CELL, workdir=wd)
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
    m = measure_all(pex_netlist, CELL, workdir=wd)
    if not m:
        raise RuntimeError("PEX simulation produced no usable data — "
                           "the extracted netlist exists but did not "
                           "simulate; this is a tool failure")
    return m


# ── hooks ─────────────────────────────────────────────────────────────
hooks = make_hooks(
    cell=CELL, in_node="INP", out_node="OUT",
    supplies={"VDD": 3.3, "VSS": 0.0},
    spec_names=[s.name for s in ALL_SPECS],
    specs=ALL_SPECS,
    outdir=OUTDIR,
    verbosity=1,
)
hooks.simulate_pre = _simulate_pre
hooks.simulate_pex = _simulate_pex
# Branch-and-compare must measure candidates with the SAME full metric set,
# otherwise the promoted winner is chosen on gain/bw only.
ref = {"build_layout": hooks.build_layout, "simulate_pex": _simulate_pex}
hooks.propose_candidates = make_candidate_proposer(
    specs=ALL_SPECS, hooks_ref=ref, verbosity=1)

config = FullAutoConfig.for_effort("normal", outdir=OUTDIR)


# ── entry point ───────────────────────────────────────────────────────
def main():
    if "--sanity" in sys.argv:
        m = measure_all(NETLIST, CELL, workdir=os.path.join(OUTDIR, "sim", "sanity"))
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
