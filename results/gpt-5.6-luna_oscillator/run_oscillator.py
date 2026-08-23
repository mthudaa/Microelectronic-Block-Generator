"""Run the MBG FULL AUTOMATE flow for a self-starting GF180 ring oscillator.

The transient evaluator is deliberately kept in the result directory because
the stock runtime measures AC gain/bandwidth only.  The supply ramp is the
normal power-up waveform; there is no startup pulse or forced internal state.
"""
import math
import os
import re
import statistics
import sys

os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.expanduser("~/.volare/gf180mcuD"))

from mbg import Spec, make_hooks
from mbg.analysis import SimResult, Testbench, _parse_wrdata
from mbg.full_auto import FullAutoConfig, run_full_auto
from mbg.simulation import run_spice


CELL = "oscillator"
OUTDIR = os.path.join(os.path.dirname(__file__))
LIB = os.path.join(os.environ["PDKPATH"], "libs.tech", "ngspice", "sm141064.ngspice")

NETLIST = f""".lib \"{LIB}\" typical
.subckt oscillator VDD VSS OSC_OUT
XM1p n1 OSC_OUT VDD VDD pfet_03v3 L=2.5u W=4u nf=1
XM1n n1 OSC_OUT VSS VSS nfet_03v3 L=2.5u W=2u nf=1
XM2p n2 n1 VDD VDD pfet_03v3 L=2.5u W=4u nf=1
XM2n n2 n1 VSS VSS nfet_03v3 L=2.5u W=2u nf=1
XM3p n3 n2 VDD VDD pfet_03v3 L=2.5u W=4u nf=1
XM3n n3 n2 VSS VSS nfet_03v3 L=2.5u W=2u nf=1
XM4p n4 n3 VDD VDD pfet_03v3 L=2.5u W=4u nf=1
XM4n n4 n3 VSS VSS nfet_03v3 L=2.5u W=2u nf=1
XM5p OSC_OUT n4 VDD VDD pfet_03v3 L=2.5u W=4u nf=1
XM5n OSC_OUT n4 VSS VSS nfet_03v3 L=2.5u W=2u nf=1
.ends oscillator"""

SPECS = [
    Spec("autonomous_startup", ">=", 1.0),
    Spec("frequency_hz", ">=", 10e6, " Hz"),
    Spec("frequency_hz", "<=", 100e6, " Hz"),
    Spec("startup_time_us", "<=", 5.0, " us"),
    Spec("duty_cycle", ">=", 0.40),
    Spec("duty_cycle", "<=", 0.60),
    Spec("osc_high_v", ">=", 2.97, " V"),
    Spec("osc_low_v", "<=", 0.33, " V"),
    Spec("idd_ma", "<=", 1.0, " mA"),
    Spec("sustained_cycles", ">=", 100.0),
]

REQUEST = (
    "Design a self-starting CMOS ring oscillator in GF180MCU gf180mcuD. "
    "Use exactly VDD VSS OSC_OUT and .subckt oscillator VDD VSS OSC_OUT. "
    "Use gf180mcuD 3.3 V nfet_03v3 and pfet_03v3 devices. Nominal VDD=3.3 V, "
    "VSS=0 V, TEMP=27 C. It must start automatically on normal power-up, "
    "oscillate at 10-100 MHz, start in under 5 us, have 40-60 percent duty "
    "cycle, OSC_OUT high above 2.97 V and low below 0.33 V, average supply "
    "current below 1 mA, and sustain at least 100 cycles. Characterize VDD "
    "at 3.0/3.3/3.6 V, TEMP at -40/27/125 C, and meaningful gf180 corners. "
    "The final acceptance transient must not use a startup pulse or forced "
    "internal initial condition."
)


class OscillatorTB(Testbench):
    """Transient testbench with a normal ramped supply and temperature."""

    def __init__(self, *args, temp=27.0, **kwargs):
        super().__init__(*args, **kwargs)
        self.temp = temp

    def build_deck(self, analysis_lines, control):
        deck = super().build_deck(analysis_lines, control)
        lines = deck.splitlines()
        for i, line in enumerate(lines):
            if line.strip().startswith(".lib"):
                lines.insert(i + 1, f".temp {self.temp:g}")
                break
        return "\n".join(lines)

    def transient(self, step="1n", stop="1.6u"):
        probes = ["OSC_OUT"]
        deck = self.build_deck(
            [], [f"tran {step} {stop}", "wrdata tran.dat v(OSC_OUT) i(Vsupply0)"]
        )
        raw = run_spice(deck, workdir=self.workdir, timeout=self.timeout, fmt="dat")
        result = SimResult(
            analysis="tran", x_name="time", returncode=raw["returncode"],
            stdout=raw.get("stdout", ""), stderr=raw.get("stderr", ""),
            workdir=raw.get("workdir", ""), deck=deck,
        )
        for path in raw.get("dat_paths") or []:
            if os.path.basename(path) == "tran.dat":
                _parse_wrdata(result, path, "time", probes + ["i(Vsupply0)"])
                break
        return result


def _crossings(times, values, level, rising):
    out = []
    for i in range(1, len(values)):
        a, b = values[i - 1], values[i]
        crossed = a < level <= b if rising else a > level >= b
        if crossed:
            if b == a:
                out.append(times[i])
            else:
                out.append(times[i - 1] + (level - a) * (times[i] - times[i - 1]) / (b - a))
    return out


def _percentile(values, fraction):
    if not values:
        return float("nan")
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round(fraction * (len(ordered) - 1)))))
    return ordered[index]


def measure_oscillator(netlist, *, vdd=3.3, vss=0.0, temp=27.0,
                       corner="typical", workdir, stop="1.6u"):
    cell = re.search(r"^\.subckt\s+(\S+)", netlist, re.MULTILINE | re.IGNORECASE).group(1)
    tb = OscillatorTB(
        netlist, cell,
        supplies={"VDD": "PWL(0 0 10n 3.3)" if vdd == 3.3 else f"PWL(0 0 10n {vdd:g})", "VSS": vss},
        probes=["OSC_OUT"], workdir=workdir, temp=temp, corner=corner,
        timeout=900,
    )
    result = tb.transient(stop=stop)
    if not result.ok:
        return {}
    values = result.get("OSC_OUT")
    if len(values) < 20:
        return {}
    threshold = 0.5 * vdd
    rises = _crossings(result.x, values, threshold, True)
    falls = _crossings(result.x, values, threshold, False)
    if len(rises) < 2:
        return {"autonomous_startup": 0.0, "sustained_cycles": float(len(rises))}

    settled_start = max(0, min(len(result.x) - 1, int(0.2 * len(result.x))))
    settled_rises = [t for t in rises if t >= result.x[settled_start]]
    periods = [b - a for a, b in zip(settled_rises, settled_rises[1:])]
    if not periods:
        return {"autonomous_startup": 0.0, "sustained_cycles": float(len(rises))}
    period = statistics.median(periods)

    high_samples, low_samples = [], []
    for rise, fall in zip(rises, falls):
        if fall <= rise:
            continue
        samples = [v for t, v in zip(result.x, values) if rise <= t <= fall]
        high_samples.extend(samples)
        next_rise = next((t for t in rises if t > fall), None)
        if next_rise is not None:
            low_samples.extend(v for t, v in zip(result.x, values) if fall <= t <= next_rise)

    currents = result.signals.get("i(Vsupply0)", [])
    avg_idd = (sum(-i for i in currents) / len(currents) * 1e3) if currents else float("nan")
    startup = rises[0] * 1e6
    duty = statistics.mean(
        (fall - rise) / (next_rise - rise)
        for rise, fall, next_rise in zip(rises, falls, rises[1:])
        if rise < fall < next_rise
    )
    settled_values = values[settled_start:]
    return {
        "autonomous_startup": 1.0,
        "frequency_hz": 1.0 / period,
        "startup_time_us": startup,
        "duty_cycle": duty,
        "osc_high_v": max(settled_values),
        "osc_low_v": min(settled_values),
        "idd_ma": avg_idd,
        "sustained_cycles": float(len(rises)),
    }


def simulate_pre(design):
    metrics = measure_oscillator(design.netlist, workdir=os.path.join(OUTDIR, "sim", "pre"))
    if not metrics:
        raise RuntimeError("pre-layout transient simulation produced no usable data")
    return metrics


def simulate_pex(design, layout):
    if not layout.pex_netlist or not os.path.isfile(layout.pex_netlist):
        raise RuntimeError("no extracted netlist to simulate")
    with open(layout.pex_netlist) as stream:
        netlist = stream.read()
    metrics = measure_oscillator(netlist, workdir=os.path.join(OUTDIR, "sim", "pex"))
    if not metrics:
        raise RuntimeError("PEX transient simulation produced no usable data")
    return metrics


hooks = make_hooks(
    cell=CELL, in_node="OSC_OUT", out_node="OSC_OUT",
    supplies={"VDD": 3.3, "VSS": 0.0},
    spec_names=[s.name for s in SPECS], specs=SPECS, outdir=OUTDIR, verbosity=1,
)
hooks.simulate_pre = simulate_pre
hooks.simulate_pex = simulate_pex


def main():
    res = run_full_auto(
        REQUEST, hooks, cell=CELL, specs=SPECS, netlist=NETLIST,
        config=FullAutoConfig.for_effort("normal", outdir=OUTDIR),
    )
    print("STATUS:", res.status)
    print("TAPEOUT_READY:", res.tapeout_ready)
    print("REPORT:", res.report_path)
    return 0 if res.tapeout_ready else 1


if __name__ == "__main__":
    sys.exit(main())
