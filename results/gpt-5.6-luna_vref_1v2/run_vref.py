"""Run FULL AUTOMATE for a MOS-only 1.2 V reference.

The reference uses a PMOS mirror driven by the external IBIAS port, a
short-channel diode-connected NMOS, and a long-channel common-gate NMOS.
The latter supplies the opposing temperature term needed to compensate the
diode-connected device. The hooks are local because stock MBG hooks measure
OTA AC metrics rather than voltage-reference DC/PVT metrics.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from typing import Dict, Iterable, Mapping, Sequence

from mbg import Spec, make_hooks
from mbg.analysis import Testbench
from mbg.flow import DesignPoint
from mbg.flow_runtime import make_candidate_proposer, scale_device_widths
from mbg.full_auto import FullAutoConfig, run_full_auto
from mbg.search import Candidate


ROOT = os.path.dirname(os.path.abspath(__file__))
CELL = "vref_1v2"
OUTDIR = ROOT
PDKPATH = os.environ.get("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))
LIB = os.path.join(PDKPATH, "libs.tech", "ngspice", "sm141064.ngspice")

NETLIST = f""".lib \"{LIB}\" typical
.subckt {CELL} VDD VSS VREF IBIAS
* External IBIAS sinks the PMOS mirror reference current.
XM1 IBIAS IBIAS VDD  VDD  pfet_03v3 L=8u    W=2u   nf=1
XM2 VREF  IBIAS VDD  VDD  pfet_03v3 L=8u    W=2u   nf=1
* XM3 is the CTAT diode-connected device; XM4 adds opposing TC in triode.
XM3 VREF  VREF  VMB  VSS  nfet_03v3 L=0.28u W=9.5u nf=1
XM4 VMB   VREF  VSS  VSS  nfet_03v3 L=8u    W=9.5u nf=1
.ends {CELL}
""".strip()

SPECS = [
    Spec("vref_low_limit", ">=", 1.15, " V"),
    Spec("vref_high_limit", "<=", 1.25, " V"),
    Spec("tempco_ppm", "<=", 300.0, " ppm/C"),
    Spec("line_reg_mv_per_v", "<=", 100.0, " mV/V"),
    Spec("vref_supply_span", "<=", 0.060, " V"),
    Spec("supply_current_ua", "<=", 300.0, " uA"),
]

_CACHE: Dict[tuple, Dict[str, float]] = {}


def _workdir(netlist: str, phase: str) -> str:
    tag = hashlib.sha256(netlist.encode()).hexdigest()[:12]
    path = os.path.join(OUTDIR, "simulation", phase, tag)
    os.makedirs(path, exist_ok=True)
    return path


def _op(netlist: str, *, vdd: float, ibias: float, temp: float,
        corner: str = "typical", phase: str = "pre") -> Dict[str, float]:
    tb = Testbench(
        netlist, CELL, supplies={"VDD": vdd, "VSS": 0.0},
        probes=["VREF"], corner=corner, workdir=_workdir(netlist, phase),
        timeout=600,
    )
    control = ["op", "print v(VREF) i(Vsupply0)"]
    deck = tb.build_deck([f".temp {temp}"], control)
    dut = f"Xdut {' '.join(tb.ports)} {tb.cell}"
    stimulus = f"I_BIAS IBIAS VSS {ibias:.12g}\nC_LOAD VREF VSS 1p"
    if dut not in deck:
        raise RuntimeError("testbench did not contain the DUT instance")
    deck = deck.replace(dut, stimulus + "\n" + dut, 1)
    res = tb._run("op", deck, "", ["VREF"])
    if not res.ok:
        raise RuntimeError(f"operating point failed for {corner} at {temp} C")
    try:
        vref = res.value("VREF")
        idd = abs(res.value("i(Vsupply0)")) * 1e6
    except KeyError as exc:
        raise RuntimeError(f"operating point omitted required value: {exc}") from exc
    return {"vref": vref, "supply_current_ua": idd}


def measure_vref(netlist: str, *, phase: str) -> Dict[str, float]:
    """Return all required metrics using identical pre/PEX measurements."""
    key = (hashlib.sha256(netlist.encode()).hexdigest(), phase)
    if key in _CACHE:
        return dict(_CACHE[key])

    nominal = _op(netlist, vdd=3.3, ibias=20e-6, temp=27.0, phase=phase)
    supply = {
        str(v): _op(netlist, vdd=v, ibias=20e-6, temp=27.0, phase=phase)
        for v in (3.0, 3.3, 3.6)
    }
    temps = {
        str(t): _op(netlist, vdd=3.3, ibias=20e-6, temp=t, phase=phase)["vref"]
        for t in (-40.0, -20.0, 0.0, 27.0, 75.0, 100.0, 125.0)
    }
    bias = {
        str(i): _op(netlist, vdd=3.3, ibias=i * 1e-6, temp=27.0, phase=phase)["vref"]
        for i in (10, 20, 30)
    }
    values = list(supply.values())
    span = max(x["vref"] for x in values) - min(x["vref"] for x in values)
    tspan = max(temps.values()) - min(temps.values())
    tempco = abs(tspan) / (125.0 - (-40.0)) / nominal["vref"] * 1e6
    metrics = {
        "vref_low_limit": nominal["vref"],
        "vref_high_limit": nominal["vref"],
        "tempco_ppm": tempco,
        "line_reg_mv_per_v": span / 0.6 * 1000.0,
        "vref_supply_span": span,
        "supply_current_ua": nominal["supply_current_ua"],
        # Characterization-only values are retained in the iteration history.
        "vref_nominal": nominal["vref"],
        "vref_at_10ua": bias["10"],
        "vref_at_20ua": bias["20"],
        "vref_at_30ua": bias["30"],
    }
    _CACHE[key] = dict(metrics)
    return metrics


def _scale_parameter(netlist: str, only: Iterable[str], parameter: str,
                     factor: float) -> str:
    selected = set(only)
    pattern = re.compile(rf"(\b{parameter}\s*=\s*)([0-9.eE+-]+)([a-zA-Z]*)")
    lines = []
    for line in netlist.splitlines():
        if line.split() and line.split()[0] in selected:
            def repl(match):
                return f"{match.group(1)}{float(match.group(2)) * factor:g}{match.group(3)}"
            line = pattern.sub(repl, line, count=1)
        lines.append(line)
    return "\n".join(lines) + ("\n" if netlist.endswith("\n") else "")


def tune_pre(design: DesignPoint, report) -> DesignPoint:
    value = next((r.value for r in report.results if r.name == "vref_low_limit"), None)
    if value is None:
        return design
    if value < 1.15:
        factor, action = 0.80, "raise VREF"
    elif value > 1.25:
        factor, action = 1.20, "lower VREF"
    else:
        # Length is a separate hypothesis when nominal voltage is in range but
        # the temperature coefficient remains the limiting specification.
        factor, action = 1.15, "sample stack-length sensitivity"
        return design.evolve(
            netlist=_scale_parameter(design.netlist, ("XM3", "XM4"), "L", factor),
            circuit={**design.circuit, "_pre_step": int(design.circuit.get("_pre_step", 0)) + 1},
            note=f"pre_tune_length_x{factor:g}",
        )
    return design.evolve(
        netlist=scale_device_widths(design.netlist, factor, only=("XM3", "XM4")),
        circuit={**design.circuit, "_pre_step": int(design.circuit.get("_pre_step", 0)) + 1},
        note=f"pre_tune_{action.replace(' ', '_')}_x{factor:g}",
    )


class VrefStrategy:
    name = "vref_mos_sweep"

    def propose(self, state, budget: int):
        failing = {r.name for r in state.report.results if r.required and r.status != "PASS"}
        value = next((r.value for r in state.report.results if r.name == "vref_low_limit"), None)
        if value is not None and value < 1.15:
            stack_factors = (0.70, 0.85)
        elif value is not None and value > 1.25:
            stack_factors = (1.15, 1.30)
        else:
            stack_factors = (0.85, 1.20)
        candidates = []
        for index, factor in enumerate(stack_factors[:budget]):
            candidates.append(Candidate(
                id=f"VREF{state.iteration}.{index + 1}",
                design=state.design.evolve(
                    netlist=scale_device_widths(state.design.netlist, factor,
                                                 only=("XM3", "XM4")),
                    note=f"stack_width_x{factor:g}"),
                hypothesis="measure the effect of NMOS stack width on VREF and TC",
                change=f"scale XM3/XM4 widths x{factor:g}",
                rationale="the diode-stack VGS sets the reference voltage",
                expected_effect="move VREF toward the 1.2 V window",
                risk="width changes also alter MOS temperature coefficient",
                target="circuit", params={"knob": "stack_width", "factor": factor,
                                            "step": (factor - 1.0) * 100},
                source=self.name,
            ))
        if len(candidates) < budget and "tempco_ppm" in failing:
            factor = 0.80
            candidates.append(Candidate(
                id=f"VREF{state.iteration}.L",
                design=state.design.evolve(
                    netlist=_scale_parameter(state.design.netlist, ("XM3", "XM4"), "L", factor),
                    note=f"stack_length_x{factor:g}"),
                hypothesis="sample a shorter stack channel length for TC",
                change=f"scale XM3/XM4 lengths x{factor:g}",
                rationale="channel-length dependence contributes to the VGS drift",
                expected_effect="reduce temperature coefficient",
                risk="shorter channels increase supply sensitivity",
                target="circuit", params={"knob": "stack_length", "factor": factor,
                                            "step": (factor - 1.0) * 100},
                source=self.name,
            ))
        return candidates[:budget]


def _simulate_pre(design: DesignPoint) -> Mapping[str, float]:
    return measure_vref(design.netlist, phase="pre")


def _simulate_pex(design: DesignPoint, layout) -> Mapping[str, float]:
    if not layout.pex_netlist or not os.path.isfile(layout.pex_netlist):
        raise RuntimeError("no extracted netlist to simulate")
    with open(layout.pex_netlist) as stream:
        return measure_vref(stream.read(), phase="pex")


def characterize(netlist: str, label: str) -> Dict[str, object]:
    def safe_op(**kwargs):
        try:
            return _op(netlist, **kwargs)
        except Exception as exc:  # retain the point as evidence, not a false pass
            return {"status": "NOT RUN", "error": f"{type(exc).__name__}: {exc}"}

    data: Dict[str, object] = {"label": label, "nominal": {}, "ibias_uA": {},
                               "supply_V": {}, "temperature_C": {}, "corners": {},
                               "pvt_grid": {}}
    data["nominal"] = safe_op(vdd=3.3, ibias=20e-6, temp=27.0)
    for current in (10, 20, 30):
        data["ibias_uA"][str(current)] = safe_op(
            vdd=3.3, ibias=current * 1e-6, temp=27.0)
    for supply in (2.7, 3.0, 3.3, 3.6):
        data["supply_V"][str(supply)] = safe_op(
            vdd=supply, ibias=20e-6, temp=27.0)
    for temp in (-40, -20, 0, 27, 75, 100, 125):
        data["temperature_C"][str(temp)] = safe_op(
            vdd=3.3, ibias=20e-6, temp=temp)
    for corner in ("typical", "ff", "ss", "fs", "sf"):
        data["corners"][corner] = {}
        for supply in (3.0, 3.3, 3.6):
            data["corners"][corner][str(supply)] = safe_op(
                vdd=supply, ibias=20e-6, temp=27.0, corner=corner)
        data["pvt_grid"][corner] = {}
        for temp in (-40, 27, 125):
            data["pvt_grid"][corner][str(temp)] = {}
            for supply in (3.0, 3.3, 3.6):
                data["pvt_grid"][corner][str(temp)][str(supply)] = safe_op(
                    vdd=supply, ibias=20e-6, temp=temp, corner=corner)
    return data


REQUEST = """Design a 1.2-V MOS-only voltage reference in GF180MCU gf180mcuD.
Use exactly the ports VDD VSS VREF IBIAS, with VDD=3.3 V and VSS=0 V;
IBIAS is an external bias-current input. Use only nfet_03v3 and pfet_03v3,
with no BJTs, parasitic bipolar devices, bandgap architecture, explicit
resistors, or reference-setting capacitors. At VDD=3.3 V, IBIAS=20 uA,
CL=1 pF and 27 C, require VREF=1.20 V within 1.15--1.25 V, temperature
coefficient <=300 ppm/C over -40--125 C, line regulation <=100 mV/V over
3.0--3.6 V, VREF span <=60 mV over that supply range, and supply current
excluding IBIAS <=300 uA. Characterize IBIAS at 10/20/30 uA, supply from
approximately 2.7--3.6 V, and PVT at VDD 3.0/3.3/3.6 V, -40/27/125 C,
and GF180 typical/ff/ss/fs/sf corners. Use the simplest MOS-only topology
and report non-convergence or missing verification evidence honestly."""


def main() -> int:
    hooks = make_hooks(
        cell=CELL, in_node="IBIAS", out_node="VREF",
        supplies={"VDD": 3.3, "VSS": 0.0},
        spec_names=[s.name for s in SPECS], specs=SPECS, outdir=OUTDIR,
        tune_pre=tune_pre,
        verbosity=1,
    )
    hooks.simulate_pre = _simulate_pre
    hooks.simulate_pex = _simulate_pex
    ref = {"build_layout": hooks.build_layout, "simulate_pex": _simulate_pex}
    hooks.propose_candidates = make_candidate_proposer(
        specs=SPECS, hooks_ref=ref, strategy=VrefStrategy(), verbosity=1)
    config = FullAutoConfig.for_effort("normal", outdir=OUTDIR)
    result = run_full_auto(REQUEST, hooks, cell=CELL, specs=SPECS,
                           netlist=NETLIST, config=config)

    with open(os.path.join(OUTDIR, "generated_netlist.spice"), "w") as stream:
        stream.write(NETLIST + "\n")
    with open(os.path.join(OUTDIR, "prompt.txt"), "w") as stream:
        stream.write(REQUEST + "\n")

    # Characterize the original circuit even when Loop A cannot reach layout;
    # this evidence is separate from the sign-off gate and is never promoted
    # to a PEX result.
    try:
        pvt_path = os.path.join(OUTDIR, "pvt_characterization.json")
        tmp_path = pvt_path + ".tmp"
        with open(tmp_path, "w") as stream:
            json.dump(characterize(NETLIST, "initial_schematic"), stream, indent=2)
            stream.write("\n")
        os.replace(tmp_path, pvt_path)
        error_path = os.path.join(OUTDIR, "pvt_characterization_error.txt")
        if os.path.isfile(error_path):
            os.remove(error_path)
    except Exception as exc:  # preserve the full-auto result if optional characterization fails
        with open(os.path.join(OUTDIR, "pvt_characterization_error.txt"), "w") as stream:
            stream.write(f"{type(exc).__name__}: {exc}\n")

    # Repeat the requested characterization on the exact PEX netlist selected
    # by the sign-off result. This is supplemental evidence; the full-auto
    # gate still reports PVT as NOT REQUIRED because it is not a configured
    # gate condition in the generic runtime.
    try:
        layout = getattr(result.flow, "best_pex_layout", None) if result.flow else None
        pex_path = layout.pex_netlist if layout else None
        if pex_path and os.path.isfile(pex_path):
            with open(pex_path) as stream:
                pex_data = characterize(stream.read(), "final_pex")
            with open(os.path.join(OUTDIR, "pvt_pex_characterization.json"), "w") as stream:
                json.dump(pex_data, stream, indent=2)
                stream.write("\n")
    except Exception as exc:
        with open(os.path.join(OUTDIR, "pvt_pex_characterization_error.txt"), "w") as stream:
            stream.write(f"{type(exc).__name__}: {exc}\n")

    print(f"STATUS: {result.status}")
    print(f"TAPEOUT_READY: {result.tapeout_ready}")
    print(f"REPORT: {result.report_path}")
    return 0 if result.tapeout_ready else 1


if __name__ == "__main__":
    sys.exit(main())
