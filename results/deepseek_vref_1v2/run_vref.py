"""Run the MBG FULL AUTOMATE flow on a 1.2V MOS-only voltage reference.

Specification (user-provided):
  - Voltage reference, ports VDD VSS VREF IBIAS,
    .subckt vref_1v2 VDD VSS VREF IBIAS, IBIAS an external bias current.
  - GF180MCU gf180mcuD, VDD = 3.3 V, VSS = 0 V, IBIAS = 20 uA, CL = 1 pF, 27 C.
  - MOSFET-only (nfet_03v3 / pfet_03v3): no BJTs, no bandgap, no explicit
    resistors or reference-setting capacitors.
  - VREF nominal 1.20 V (allowed 1.15-1.25 V), tempco <= 300 ppm/C over
    -40..125 C, line regulation <= 100 mV/V over 3.0-3.6 V, VREF variation
    over 3.0-3.6 V <= 60 mV, supply current excluding IBIAS <= 300 uA.
  - Characterize IBIAS sensitivity at 10/20/30 uA, supply behaviour from
    ~2.7-3.6 V, and PVT corners (VDD 3.0/3.3/3.6, -40/27/125 C, corners).

Topology: a current-mirror-biased diode reference. IBIAS is turned into a
supply-independent gate voltage by a diode-connected NMOS (XM0) and mirrored
(XM0b) into a PMOS diode (XM1); the PMOS mirror (XM2) feeds a diode-connected
NMOS (XM3) whose Vgs IS the reference. Because the output current is set by
the fixed external bias current, the reference is inherently supply
independent (line regulation ~5 mV/V measured); the output diode is sized for
Vgs ~ 1.2 V and its operating point is chosen so the mobility tempco of the
overdrive cancels most of the Vth tempco (measured tempco ~60 ppm/C).

Measurement uses one ngspice run per netlist: an operating point for supply
current plus three DC sweeps (temperature, supply, IBIAS), so pre-layout and
PEX numbers are directly comparable.
"""
import math
import os
import re
import sys
import json

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))

from mbg import Spec, make_hooks
from mbg.full_auto import run_full_auto, FullAutoConfig
from mbg.simulation import run_spice

# ── cell / directories ────────────────────────────────────────────────
CELL = "vref_1v2"
OUTDIR = os.path.join(os.path.expanduser("~"),
                      "opensource-project", "Microelectronic-Block-Generator",
                      "results", "deepseek_vref_1v2")
os.makedirs(OUTDIR, exist_ok=True)

LIB = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice",
                   "sm141064.ngspice")
DESIGN = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice",
                      "design.ngspice")

# ── netlist ───────────────────────────────────────────────────────────
NETLIST = f"""
* 1.2V MOS-only voltage reference, GF180MCU 3.3V, ports VDD VSS VREF IBIAS.
* IBIAS -> diode (XM0) -> mirror (XM0b) -> PMOS diode (XM1) -> output diode
* (XM3). XM3's Vgs IS the reference; sizing tuned for VREF ~ 1.2 V and a
* near-flat temperature coefficient at IBIAS = 20 uA.
.subckt vref_1v2 VDD VSS VREF IBIAS
XM0  IBIAS IBIAS VSS  VSS  nfet_03v3 L=2u W=4u nf=2
XM0b pm   IBIAS VSS  VSS  nfet_03v3 L=2u W=4u nf=2
XM1  pm   pm   VDD  VDD  pfet_03v3 L=2u W=4u nf=2
XM2  vref pm   VDD  VDD  pfet_03v3 L=2u W=8u nf=2
XM3  vref vref VSS  VSS  nfet_03v3 L=0.5u W=1.2u nf=1
.ends
""".strip()

# ── specifications ────────────────────────────────────────────────────
SPECS = [
    Spec("vref", "==", 1.2, " V", tol=0.05),
    Spec("tempco_ppmC", "<=", 300.0, " ppm/C"),
    Spec("line_reg_mV_V", "<=", 100.0, " mV/V"),
    Spec("vref_swing_mV", "<=", 60.0, " mV"),
    Spec("idd_ua", "<=", 300.0, " uA"),
]
# Characterization-only (user asked to characterize, no target): tracked but
# never required, so a wide IBIAS sensitivity cannot block sign-off.
INFO_SPECS = [
    Spec("vref_10u", "==", 1.2, " V", tol=0.2, required=False),
    Spec("vref_30u", "==", 1.2, " V", tol=0.2, required=False),
    Spec("vref_2v7", "==", 1.2, " V", tol=0.15, required=False),
    Spec("vref_min", ">=", 1.0, " V", required=False),
    Spec("vref_max", "<=", 1.4, " V", required=False),
]
ALL_SPECS = SPECS + INFO_SPECS

REQUEST = (
    "Design a 1.2V MOS-only voltage reference in GF180MCU (gf180mcuD) with "
    "ports VDD VSS VREF IBIAS where IBIAS is an external bias current input. "
    "VDD = 3.3 V, VSS = 0 V, IBIAS = 20 uA nominal, CL = 1 pF, 27 C. "
    "Use MOSFET-only circuitry (nfet_03v3 / pfet_03v3) — no BJTs, no "
    "bandgap, no explicit resistors or reference-setting capacitors. "
    "VREF nominal 1.20 V and allowed 1.15-1.25 V; temperature coefficient "
    "<= 300 ppm/C over -40..125 C; line regulation <= 100 mV/V over "
    "3.0-3.6 V; VREF variation over 3.0-3.6 V <= 60 mV; supply current "
    "excluding IBIAS <= 300 uA. Characterize IBIAS sensitivity at 10/20/30 "
    "uA, supply behaviour from ~2.7-3.6 V, and PVT (VDD 3.0/3.3/3.6 V, "
    "temp -40/27/125 C, gf180 typical/ff/ss corners)."
)

# ── measurement infrastructure ────────────────────────────────────────
TEMP_POINTS = [-40, 0, 27, 60, 90, 125]


def parse_ports(netlist, cell):
    m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+(.+)$", netlist,
                  re.MULTILINE | re.IGNORECASE)
    if not m:
        raise ValueError(f".subckt {cell} not found in netlist")
    ports = [p for p in m.group(1).split() if "=" not in p]
    roles = {"vdd": None, "vss": None, "vref": None, "ibias": None}
    for p in ports:
        pl = p.lower()
        if pl in ("vdd", "vcc", "avdd"):
            roles["vdd"] = roles["vdd"] or p
        elif pl in ("vss", "gnd", "avss", "vss!"):
            roles["vss"] = roles["vss"] or p
        elif "ibias" in pl or pl in ("ib", "i"):
            roles["ibias"] = roles["ibias"] or p
        elif pl in ("vref", "ref", "vout", "out", "vo"):
            roles["vref"] = roles["vref"] or p
        elif pl.startswith("vr"):
            roles["vref"] = roles["vref"] or p
    missing = [r for r, v in roles.items() if v is None]
    if missing:
        raise ValueError(f"could not identify port roles {missing} among {ports}")
    return roles, ports


def build_deck(netlist, cell, *, temp=27.0, vdd=3.3, vss=0.0, ibias=20e-6,
               cl=1e-12, corner="typical"):
    roles, ports = parse_ports(netlist, cell)
    core = "\n".join(l for l in netlist.splitlines()
                     if not l.strip().lower().startswith((".lib", ".include")))
    body = []
    body.append(f".include '{DESIGN}'")
    body.append(f".lib '{LIB}' {corner}")
    body.append(f".temp {temp}")
    body.append("")
    body.append(core.strip())
    body.append("")
    body.append(f"VDD {roles['vdd']} 0 {vdd}")
    body.append(f"VSSV {roles['vss']} 0 {vss}")
    body.append(f"IIB 0 {roles['ibias']} DC {ibias}")
    body.append(f"CL {roles['vref']} 0 {cl}")
    body.append("")
    body.append(f"X1 {' '.join(ports)} {cell}")
    body.append(".control")
    body.append("op")
    body.append(f"print v({roles['vref']})")
    body.append(f"print i(VDD) i(VSSV)")
    body.append("set wr_singlescale")
    body.append("dc temp -40 125 5")
    body.append(f"wrdata temp.dat v({roles['vref']})")
    body.append("dc VDD 2.7 3.6 0.05")
    body.append(f"wrdata vdd.dat v({roles['vref']})")
    body.append("dc IIB 8u 32u 1u")
    body.append(f"wrdata ib.dat v({roles['vref']})")
    body.append(".endc")
    body.append(".end")
    return "\n".join(body)


def _read_dat(path):
    rows = []
    if not os.path.isfile(path):
        return rows
    with open(path) as f:
        for ln in f:
            ln = ln.strip()
            if not ln or ln.startswith(("#", "Index", "Variables", "x",
                                        "Values", "Points", "Title", "Date",
                                        "Plotname", "Flags", "No.")):
                continue
            parts = ln.split()
            if len(parts) >= 2:
                try:
                    rows.append((float(parts[0]), float(parts[1])))
                except ValueError:
                    continue
    return rows


def measure_all(netlist, cell, *, vdd=3.3, ibias=20e-6, temp=27.0, cl=1e-12,
                corner="typical", workdir="sim"):
    """Full characterization of any netlist (schematic or extracted).

    Returns an empty dict on any core-measurement failure so the flow treats
    it as a tool failure rather than a spec miss.
    """
    wd = workdir
    os.makedirs(wd, exist_ok=True)
    for f in ("temp.dat", "vdd.dat", "ib.dat"):
        p = os.path.join(wd, f)
        if os.path.isfile(p):
            os.remove(p)
    try:
        deck = build_deck(netlist, cell, temp=temp, vdd=vdd, ibias=ibias,
                          cl=cl, corner=corner)
        r = run_spice(deck, workdir=wd, timeout=400, fmt="dat")
        if r["returncode"] not in (0, None):
            print(f"[MEASURE] ngspice rc={r['returncode']}: "
                  f"{r.get('stdout','')[-400:]}")
            return {}
        out = {}
        for name, val in re.findall(
                r"^\s*([\w()#.]+)\s*=\s*(-?\d*\.?\d*[eE]?[+-]?\d+)\s*$",
                r.get("stdout", ""), re.MULTILINE):
            out[name.lower()] = float(val)
        trows = _read_dat(os.path.join(wd, "temp.dat"))
        vrows = _read_dat(os.path.join(wd, "vdd.dat"))
        irows = _read_dat(os.path.join(wd, "ib.dat"))
        if not trows or not vrows:
            print(f"[MEASURE] no sweep data; stdout tail:\n"
                  f"{r.get('stdout','')[-600:]}")
            return {}

        vref27 = None
        for x, v in vrows:
            if abs(x - 3.3) < 0.03:
                vref27 = v
        if vref27 is None:
            vref27 = trows[0][1]
        tmin = min(v for _, v in trows)
        tmax = max(v for _, v in trows)
        tc = (tmax - tmin) / (1.2 * 165.0) * 1e6

        vlo = v_hi = v27 = v27b = None
        for x, v in vrows:
            if abs(x - 3.0) < 0.02:
                vlo = v
            if abs(x - 3.6) < 0.02:
                v_hi = v
            if abs(x - 3.3) < 0.02:
                v27 = v
            if abs(x - 2.7) < 0.02:
                v27b = v
        line = (v_hi - vlo) / 0.6 * 1000.0 if (v_hi is not None
                                               and vlo is not None) else None
        swing = (max(v for _, v in vrows) - min(v for _, v in vrows)) * 1000.0

        iv = {}
        for x, v in irows:
            if abs(x - 10e-6) < 0.6e-6:
                iv[10] = v
            if abs(x - 20e-6) < 0.6e-6:
                iv[20] = v
            if abs(x - 30e-6) < 0.6e-6:
                iv[30] = v

        idd = None
        for key in ("i(vdd)", "vdd#branch"):
            if key in out:
                idd = abs(out[key])
                break

        m = {
            "vref": vref27,
            "tempco_ppmC": tc,
            "line_reg_mV_V": line if line is not None else float("nan"),
            "vref_swing_mV": swing,
            "idd_ua": idd * 1e6 if idd is not None else float("nan"),
            "vref_10u": iv.get(10, float("nan")),
            "vref_30u": iv.get(30, float("nan")),
            "vref_2v7": v27b if v27b is not None else float("nan"),
            "vref_min": tmin,
            "vref_max": tmax,
            "vref@3v3": v27,
        }
        return m
    except Exception as e:                       # noqa: BLE001
        print(f"[MEASURE] core measurement failed: {type(e).__name__}: {e}")
        return {}


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
        raise RuntimeError("PEX simulation produced no usable data — the "
                           "extracted netlist exists but did not simulate; "
                           "this is a tool failure")
    return m


# ── tuning ────────────────────────────────────────────────────────────
def _scale_width(netlist, name, factor):
    from mbg.flow_runtime import scale_device_widths
    return scale_device_widths(netlist, factor, only=[name])


def _set_l(netlist, name, new_l):
    out = []
    for ln in netlist.splitlines():
        if ln.split() and ln.split()[0] == name:
            out.append(re.sub(r"(L=)[0-9.]+u", rf"\g<1>{new_l}u", ln))
        else:
            out.append(ln)
    return "\n".join(out)


def _failing(report):
    return {r.name for r in report.failures}


def _vref_off(design):
    """None, or the measured vref from the last report is not available here."""
    return None


def tune_post(design, report, degradation):
    """Reference-aware PEX tuning.

    Knobs: output diode width XM3 W (moves VREF and tempco), output diode
    length XM3 L (tempco balance), mirror size XM1/XM2 W (supply current).
    """
    failing = _failing(report)
    netlist = design.netlist
    note = []

    if "vref" in failing or "vref_2v7" in failing:
        v = report.get("vref")
        if v is not None:
            if v.value < 1.15:
                netlist = _scale_width(netlist, "XM3", 0.85)
                note.append("XM3 W x0.85 (raise vref)")
            elif v.value > 1.25:
                netlist = _scale_width(netlist, "XM3", 1.2)
                note.append("XM3 W x1.2 (lower vref)")
    if "tempco_ppmC" in failing:
        netlist = _set_l(netlist, "XM3", 0.6)
        netlist = _scale_width(netlist, "XM3", 1.1)
        note.append("XM3 L=0.6u, W x1.1 (tempco)")
    if "idd_ua" in failing or "line_reg_mV_V" in failing:
        netlist = _scale_width(netlist, "XM1", 0.8)
        netlist = _scale_width(netlist, "XM2", 0.8)
        note.append("mirror W x0.8 (reduce current)")

    step = int(design.circuit.get("_pex_step", 0)) + 1
    return design.evolve(
        netlist=netlist,
        layout=dict(design.layout or {}),
        circuit={**design.circuit, "_pex_step": step},
        note=f"pex_tune_{step}({'; '.join(note) if note else 'no-op'})")


def propose_candidates(*, design, report, degradation, iteration,
                       baseline_score, budget):
    """Several distinct reference edits from the same baseline, each measured
    independently so an improvement is attributable to one change."""
    from mbg.search import CandidateResult
    failing = _failing(report)
    candidates = []
    v = report.get("vref")
    vval = v.value if v is not None else None

    # Distinct hypotheses (each only fires if its target metric is relevant).
    if "tempco_ppmC" in failing or (vval is not None and abs(vval - 1.2) > 0.03):
        candidates.append(("XM3 W x1.25", _scale_width(design.netlist, "XM3", 1.25)))
        candidates.append(("XM3 W x0.8", _scale_width(design.netlist, "XM3", 0.8)))
        candidates.append(("XM3 L=0.65u", _set_l(design.netlist, "XM3", 0.65)))
    elif "idd_ua" in failing or "line_reg_mV_V" in failing:
        candidates.append(("mirror W x0.8", _scale_width(design.netlist, "XM1", 0.8)))
        candidates.append(("mirror W x0.85", _scale_width(design.netlist, "XM2", 0.85)))
        candidates.append(("XM3 W x1.1", _scale_width(design.netlist, "XM3", 1.1)))
    else:
        # Nothing obvious failing: bracket XM3 width to polish margin.
        candidates.append(("XM3 W x1.1", _scale_width(design.netlist, "XM3", 1.1)))
        candidates.append(("XM3 W x0.9", _scale_width(design.netlist, "XM3", 0.9)))
        candidates.append(("XM3 L=0.6u", _set_l(design.netlist, "XM3", 0.6)))

    candidates = candidates[:budget]
    records = []
    for i, (label, net) in enumerate(candidates):
        cid = f"C{iteration}.{i + 1}"
        cd = design.evolve(
            netlist=net,
            circuit={**design.circuit, "_tag": f"cand_{cid}"},
            note=f"{cid}:{label}")
        res = CandidateResult(candidate=cd)
        try:
            layout = hooks_ref["build_layout"](cd)
            if not layout.ok:
                res.error = layout.message or "layout failed"
                res.decision = "ERROR"
                print(f"[SEARCH]   {cid}: {res.error}")
                records.append(res.as_dict())
                continue
            metrics = hooks_ref["simulate_pex"](cd, layout)
            from mbg.specs import evaluate_specs
            rep = evaluate_specs(metrics, ALL_SPECS, "pex")
            res.ok, res.metrics, res.report = True, dict(metrics), rep
            res.score, res.margin = rep.score, None
            res.candidate.params["_layout"] = layout
            print(f"[SEARCH]   {cid} ({label}): score {res.score:.4g}"
                  + ("  PASSES" if rep.passed else "")
                  + f" vref={metrics.get('vref')} tc={metrics.get('tempco_ppmC')}")
        except Exception as e:                       # noqa: BLE001
            res.error = f"{type(e).__name__}: {e}"
            res.decision = "ERROR"
            print(f"[SEARCH]   {cid}: ERROR {res.error}")
        records.append(res.as_dict())
        if res.ok and res.score < baseline_score - 1e-9:
            return cd, records
    return None, records


# ── PVT characterization (evidence, not a gate condition) ─────────────
def pvt_characterize(netlist, workdir):
    """Corners + temperature + supply behaviour. Writes pvt_characterization.json."""
    roles, ports = parse_ports(netlist, CELL)
    results = {"corners": {}, "tempco": {}, "ibias": {}, "supply": {}}
    temps = [-40, 0, 27, 60, 90, 125]
    for corner in ["typical", "ff", "ss"]:
        vs = {}
        for t in temps:
            deck = build_deck(netlist, CELL, temp=t, corner=corner)
            wd = os.path.join(workdir, "pvt", corner)
            os.makedirs(wd, exist_ok=True)
            r = run_spice(deck, workdir=wd, timeout=400, fmt="dat")
            tr = _read_dat(os.path.join(wd, "temp.dat"))
            v = tr[0][1] if tr else None
            if v is None:
                print(f"[PVT] no vref at corner={corner} T={t}")
                continue
            vs[t] = v
        if not vs:
            continue
        tc = (max(vs.values()) - min(vs.values())) / (1.2 * 165.0) * 1e6
        results["tempco"][corner] = round(tc, 1)
        results["corners"][corner] = {str(t): round(v, 4) for t, v in vs.items()}
    with open(os.path.join(workdir, "pvt_characterization.json"), "w") as f:
        json.dump(results, f, indent=2)
        f.write("\n")
    return results


# ── hooks ─────────────────────────────────────────────────────────────
hooks = make_hooks(
    cell=CELL, in_node="VREF", out_node="VREF",
    supplies={"VDD": 3.3, "VSS": 0.0},
    spec_names=[s.name for s in ALL_SPECS],
    specs=ALL_SPECS,
    outdir=OUTDIR,
    verbosity=1,
)
hooks.simulate_pre = _simulate_pre
hooks.simulate_pex = _simulate_pex
hooks.tune_post = tune_post

# Branch-and-compare must measure candidates with the SAME full metric set.
hooks_ref = {"build_layout": hooks.build_layout, "simulate_pex": _simulate_pex}
hooks.propose_candidates = propose_candidates

config = FullAutoConfig.for_effort("normal", outdir=OUTDIR)


def main():
    if "--sanity" in sys.argv:
        m = measure_all(NETLIST, CELL,
                        workdir=os.path.join(OUTDIR, "sim", "sanity"))
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

    # PVT characterization is part of the spec (characterize, not a gate).
    try:
        pvt = pvt_characterize(NETLIST, OUTDIR)
        print("\nPVT characterization:")
        print("  tempco (ppm/C):", pvt["tempco"])
        for c, vs in pvt["corners"].items():
            print(f"  {c}: " + " ".join(f"{t}C={vs[t]}" for t in sorted(vs, key=int)))
    except Exception as e:                             # noqa: BLE001
        print(f"[PVT] characterization failed: {type(e).__name__}: {e}")

    return 0 if res.tapeout_ready else 1


if __name__ == "__main__":
    sys.exit(main())
