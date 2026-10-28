"""High-level SPICE analyses: operating point, DC, AC, transient, Monte Carlo, FFT.

``mbg.simulation`` is the transport layer — it hands a deck to ngspice and gives
back files. This module is the part a person (or an agent) actually wants to
call: describe the circuit's supplies, stimulus and probes, pick an analysis,
and get structured numbers back.

    from mbg.analysis import Testbench

    tb = Testbench(netlist, cell="ota_5t",
                   supplies={"vdd": 3.3, "vss": 0.0},
                   sources={"inp": 1.65, "inm": 1.65, "vb": 0.8},
                   probes=["out"])

    tb.op()                          # operating point
    tb.dc("inp", 0, 3.3, 0.01)       # DC sweep
    tb.ac(1, 1e9, points=50)         # AC sweep
    tb.tran("1n", "1u")              # transient
    tb.monte_carlo("op", runs=50)    # mismatch spread

Two things this module handles that are easy to get wrong by hand:

* GF180 models need ``design.ngspice`` included BEFORE the model library, or
  ngspice fails with an unhelpful "Formula() error".
* ngspice frequently exits non-zero even when the analysis succeeded, so a
  result is judged by whether it produced data, never by the exit code.
"""

from __future__ import annotations

import math
import os
import re
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

from mbg.simulation import run_spice

__all__ = ["Testbench", "SimResult", "MonteCarloResult", "fft"]


# ── results ────────────────────────────────────────────────────────────

@dataclass
class SimResult:
    """One analysis run, parsed into columns."""
    analysis: str
    x_name: str = ""
    x: List[float] = field(default_factory=list)
    signals: Dict[str, List[float]] = field(default_factory=dict)
    scalars: Dict[str, float] = field(default_factory=dict)
    returncode: int = 0
    stdout: str = ""
    stderr: str = ""
    workdir: str = ""
    deck: str = ""

    @property
    def ok(self) -> bool:
        """True when the run produced data.

        Deliberately not `returncode == 0`: ngspice exits non-zero after a
        `.control` block even on success, so the exit code says nothing.
        """
        return bool(self.scalars) or any(len(v) for v in self.signals.values())

    def get(self, name: str) -> List[float]:
        """Column for a probe, tolerant about v(out) vs out."""
        for key in (name, f"v({name})", name.strip("v()"), name.lower(), f"v({name.lower()})"):
            if key in self.signals:
                return self.signals[key]
        raise KeyError(f"{name!r} not in {sorted(self.signals)}")

    def value(self, name: str) -> float:
        """Single number for an operating point or a measured quantity."""
        for key in (name, f"v({name})", name.lower(), f"v({name.lower()})"):
            if key in self.scalars:
                return self.scalars[key]
        col = self.get(name)
        if len(col) == 1:
            return col[0]
        raise KeyError(f"{name!r} is not a scalar; it has {len(col)} points")

    def min(self, name): return min(self.get(name))
    def max(self, name): return max(self.get(name))

    def peak_to_peak(self, name) -> float:
        c = self.get(name)
        return max(c) - min(c)

    def cross(self, name: str, level: float, edge: str = "either") -> Optional[float]:
        """First x where the signal crosses `level`, linearly interpolated."""
        y = self.get(name)
        for i in range(1, len(y)):
            a, b = y[i - 1], y[i]
            if (a < level <= b and edge in ("either", "rise")) or \
               (a > level >= b and edge in ("either", "fall")):
                if b == a:
                    return self.x[i]
                t = (level - a) / (b - a)
                return self.x[i - 1] + t * (self.x[i] - self.x[i - 1])
        return None

    def gain_db(self, name: str) -> List[float]:
        """20*log10|signal| — for an AC sweep."""
        return [20 * math.log10(abs(v)) if v else -300.0 for v in self.get(name)]

    def bandwidth_3db(self, name: str) -> Optional[float]:
        """Frequency where the response falls 3 dB below its low-frequency value."""
        if self.analysis != "ac":
            return None
        db = self.gain_db(name)
        if not db:
            return None
        target = db[0] - 3.0
        for i in range(1, len(db)):
            if db[i] <= target:
                a, b = db[i - 1], db[i]
                t = 0.0 if b == a else (target - a) / (b - a)
                return self.x[i - 1] + t * (self.x[i] - self.x[i - 1])
        return None

    def summary(self) -> str:
        head = f"{self.analysis} | {'ok' if self.ok else 'NO DATA'}"
        if self.scalars:
            head += " | " + ", ".join(f"{k}={v:.6g}" for k, v in list(self.scalars.items())[:6])
        if self.signals:
            head += f" | {len(self.signals)} signal(s) x {len(self.x)} points"
        return head


@dataclass
class MonteCarloResult:
    """A set of runs plus the spread of each measured quantity."""
    runs: List[SimResult] = field(default_factory=list)
    measure: str = ""

    def values(self, name: str) -> List[float]:
        out = []
        for r in self.runs:
            try:
                out.append(r.value(name))
            except KeyError:
                continue
        return out

    def stats(self, name: str) -> Dict[str, float]:
        v = self.values(name)
        if not v:
            return {"n": 0}
        n = len(v)
        mean = sum(v) / n
        var = sum((x - mean) ** 2 for x in v) / (n - 1) if n > 1 else 0.0
        sd = math.sqrt(var)
        return {"n": n, "mean": mean, "sigma": sd, "min": min(v), "max": max(v),
                "sigma_over_mean": (sd / abs(mean)) if mean else float("nan")}

    def summary(self, name: str) -> str:
        s = self.stats(name)
        if not s.get("n"):
            return f"{name}: no data"
        return (f"{name}: n={s['n']} mean={s['mean']:.6g} sigma={s['sigma']:.3g} "
                f"({100 * s['sigma_over_mean']:.2f}%) range=[{s['min']:.6g}, {s['max']:.6g}]")


# ── FFT ────────────────────────────────────────────────────────────────

def fft(result: SimResult, signal: str, *, window: str = "hann",
        drop_dc: bool = True) -> Tuple[List[float], List[float]]:
    """Single-sided amplitude spectrum of a transient signal.

    Returns (frequencies_hz, magnitudes). The transient is resampled onto a
    uniform grid first, because ngspice uses adaptive time steps and an FFT of
    unevenly spaced samples is meaningless.
    """
    if result.analysis != "tran":
        raise ValueError(f"fft needs a transient result, got {result.analysis!r}")
    import numpy as np

    t = np.asarray(result.x, dtype=float)
    y = np.asarray(result.get(signal), dtype=float)
    if t.size < 4:
        raise ValueError("not enough transient points for an FFT")

    n = int(2 ** math.floor(math.log2(t.size)))          # power of two
    tu = np.linspace(t[0], t[-1], n)
    yu = np.interp(tu, t, y)
    dt = float(tu[1] - tu[0])

    if window == "hann":
        w = np.hanning(n)
    elif window in (None, "none", "rect"):
        w = np.ones(n)
    else:
        raise ValueError(f"unknown window {window!r}")
    coherent_gain = w.mean()

    spec = np.fft.rfft((yu - yu.mean()) * w)
    mag = np.abs(spec) / (n * coherent_gain) * 2.0
    freq = np.fft.rfftfreq(n, dt)
    if drop_dc:
        freq, mag = freq[1:], mag[1:]
    return freq.tolist(), mag.tolist()


# ── testbench ──────────────────────────────────────────────────────────

_NUM = r"[-+]?[0-9]*\.?[0-9]+(?:[eE][-+]?[0-9]+)?"


class Testbench:
    """Wraps a subcircuit with supplies, stimulus and probes."""

    def __init__(self, netlist: str, cell: str, *,
                 ports: Optional[Sequence[str]] = None,
                 supplies: Optional[Dict[str, float]] = None,
                 sources: Optional[Dict[str, object]] = None,
                 probes: Optional[Sequence[str]] = None,
                 loads: Optional[Dict[str, str]] = None,
                 pdk_root: Optional[str] = None,
                 corner: str = "typical",
                 workdir: str = "sim",
                 timeout: int = 600,
                 pdk: Optional[str] = None,
                 temp: Optional[float] = None,
                 isources: Optional[Dict[str, object]] = None,
                 extra_lines: Sequence[str] = (),
                 model_libs: Optional[Sequence[Tuple[str, str]]] = None):
        self.netlist = netlist
        self.cell = cell
        self.supplies = dict(supplies or {})
        self.sources = dict(sources or {})
        self.probes = list(probes or [])
        self.loads = dict(loads or {})
        self.corner = corner
        self.workdir = workdir
        self.timeout = timeout
        # GF180 gates device mismatch behind sw_stat_mismatch; the typical
        # corner leaves it at zero, so a Monte Carlo run on "typical" produces
        # identical samples. Set by monte_carlo(), not normally by hand.
        self.mismatch = False
        self.seed: Optional[int] = None
        self.ports = list(ports) if ports else self._ports_from_netlist(netlist, cell)

        # Optional extensions, all off by default so an existing call builds
        # exactly the deck it always did:
        #   temp        -> `.temp T`
        #   isources    -> {node: value} injects `value` amps INTO the node from
        #                  ground; {node: (from_node, value)} from another node
        #   extra_lines -> appended verbatim after the stimulus
        #   model_libs  -> [(path, section), ...] replaces the automatic choice
        self.temp = temp
        self.isources = dict(isources or {})
        self.extra_lines = list(extra_lines)
        self.model_libs = list(model_libs) if model_libs else None

        from mbg import pdk_profile
        self.profile = self._profile_for(pdk, netlist)
        self.corner = self.profile.canonical_corner(corner)
        env_root = os.environ.get("PDKPATH")
        if pdk_root:
            root = pdk_root
        elif env_root and os.path.basename(os.path.normpath(env_root)) == self.profile.name:
            root = env_root
        elif pdk is None and env_root and os.environ.get("PDK", self.profile.name) == self.profile.name:
            root = env_root
        else:
            root = str(self.profile.path())
        self.pdk_root = root
        self.pdk_models = os.path.join(root, self.profile.model_file_rel)
        design_rel = self.profile.design_file_rel
        self.pdk_design = os.path.join(root, design_rel) if design_rel else ""

    @staticmethod
    def _profile_for(pdk, netlist):
        """The PDK profile: explicit, else from the netlist's models, else env."""
        from mbg import pdk_profile
        if pdk:
            return pdk_profile.resolve(pdk)
        try:
            return pdk_profile.for_netlist(netlist)
        except Exception:
            return pdk_profile.resolve()

    # -- deck construction --
    @staticmethod
    def _ports_from_netlist(netlist: str, cell: str) -> List[str]:
        m = re.search(rf"^\.subckt\s+{re.escape(cell)}\s+(.+)$", netlist,
                      re.MULTILINE | re.IGNORECASE)
        if not m:
            raise ValueError(f".subckt {cell} not found in the netlist")
        return [p for p in m.group(1).split() if "=" not in p]

    def _core(self) -> str:
        """The subcircuit with any .lib line stripped — we add our own."""
        keep = [l for l in self.netlist.splitlines()
                if not l.strip().lower().startswith((".lib", ".include"))]
        return "\n".join(keep).strip()

    def _stimulus(self) -> List[str]:
        lines = []
        for i, (node, val) in enumerate(self.supplies.items()):
            lines.append(f"V{'supply%d' % i} {node} 0 {val}")
        for i, (node, val) in enumerate(self.sources.items()):
            if isinstance(val, str):                 # a full source expression
                lines.append(f"Vsrc{i} {node} 0 {val}")
            else:
                lines.append(f"Vsrc{i} {node} 0 {val}")
        for node, spec in self.loads.items():
            lines.append(f"C_load_{node} {node} 0 {spec}")
        for i, (node, val) in enumerate(self.isources.items()):
            src, value = (val if isinstance(val, (tuple, list)) else ("0", val))
            # ngspice: current flows from n+ through the source to n-, so
            # `I src node` pushes `value` amps into `node`.
            lines.append(f"Iisrc{i} {src} {node} {value}")
        lines.extend(self.extra_lines)
        return lines

    # -- model libraries --
    def device_kinds(self) -> List[str]:
        """Device kinds in the circuit, from the profile's device catalogue."""
        kinds = []
        for line in self._core().splitlines():
            parts = line.split()
            if not parts or parts[0].startswith((".", "*", "+")):
                continue
            for tok in parts[1:]:
                if "=" in tok:
                    break
                kind = self.profile.kind_of(tok)
                if kind and kind not in kinds:
                    kinds.append(kind)
        return kinds

    def lib_lines(self) -> List[str]:
        """`.lib` lines for this circuit: one section per device kind present.

        A MOS-only circuit gets exactly the single `.lib <models> <corner>`
        line this class always wrote. A bandgap with PNPs and poly resistors
        on gf180 additionally gets `bjt_<corner>` and `res_<corner>` — the
        sections that define those devices, which the MOS corners do not.
        """
        if self.model_libs:
            return [f".lib '{path}' {sec}" for path, sec in self.model_libs]
        sections = self.profile.lib_sections(self.device_kinds(), self.corner)
        available = self._available_sections()
        if available:
            missing = [sec for sec in sections if sec not in available]
            if missing:
                raise ValueError(
                    f"model library {self.pdk_models} has no section(s) "
                    f"{missing} for corner {self.corner!r}; available: "
                    f"{sorted(available)}")
        return [f".lib '{self.pdk_models}' {sec}" for sec in sections]

    _SECTION_CACHE: Dict[str, List[str]] = {}

    def _available_sections(self) -> List[str]:
        if not os.path.isfile(self.pdk_models):
            return []
        if self.pdk_models not in Testbench._SECTION_CACHE:
            from mbg.pdk_profile import scan_lib_sections
            Testbench._SECTION_CACHE[self.pdk_models] = scan_lib_sections(self.pdk_models)
        return Testbench._SECTION_CACHE[self.pdk_models]

    def build_deck(self, analysis_lines: Sequence[str], control: Sequence[str]) -> str:
        """Assemble a complete, runnable ngspice deck."""
        if not os.path.isfile(self.pdk_models):
            raise FileNotFoundError(
                f"PDK models not found at {self.pdk_models} — set PDK_ROOT/PDKPATH")
        head = []
        if self.pdk_design and os.path.isfile(self.pdk_design):
            # must come before the model library or the models fail to evaluate
            head.append(f".include '{self.pdk_design}'")
        head.extend(self.lib_lines())
        if self.mismatch:
            head.append(".param sw_stat_mismatch=1")
        if self.temp is not None:
            head.append(f".temp {self.temp}")

        inst = f"Xdut {' '.join(self.ports)} {self.cell}"
        body = head + ["", self._core(), ""] + self._stimulus() + [inst, ""]
        body += list(analysis_lines)
        pre = [f"set seed={self.seed}"] if self.seed is not None else []
        body += [".control"] + pre + list(control) + [".endc", ".end", ""]
        return "\n".join(body)

    # -- running --
    def _run(self, analysis: str, deck: str, x_name: str,
             probes: Sequence[str], workdir: Optional[str] = None,
             datfile: Optional[str] = None,
             complex_data: bool = False) -> SimResult:
        wd = workdir or self.workdir
        if self.profile.spiceinit:
            # ngspice reads .spiceinit from its working directory; sky130
            # needs `set ngbehavior=hsa` or its model library fails to parse.
            os.makedirs(wd, exist_ok=True)
            with open(os.path.join(wd, ".spiceinit"), "w") as f:
                f.write("\n".join(self.profile.spiceinit) + "\n")
        r = run_spice(deck, workdir=wd, timeout=self.timeout, fmt="dat")
        res = SimResult(analysis=analysis, x_name=x_name, returncode=r["returncode"],
                        stdout=r.get("stdout", ""), stderr=r.get("stderr", ""),
                        workdir=r.get("workdir", ""), deck=deck)
        _parse_print(res, probes)
        paths = list(r.get("dat_paths") or [])
        # Read the file THIS analysis wrote. Testbenches reuse one workdir, so
        # ac.dat/dc.dat/tran.dat pile up side by side and taking the first
        # path silently returned a previous analysis's data — the transient
        # came back holding the DC sweep, with the output node missing.
        if datfile:
            want = [p for p in paths if os.path.basename(p) == datfile]
            paths = want or ([] if any(
                os.path.basename(p) in _DAT_NAMES for p in paths) else paths)
        for path in paths:
            _parse_wrdata(res, path, x_name, probes, complex_data)
            break
        return res

    # -- analyses --
    def op(self) -> SimResult:
        """Operating point: one value per probe."""
        probes = self.probes or self.ports
        ctrl = ["op"] + [f"print {_vec(p)}" for p in probes]
        return self._run("op", self.build_deck([], ctrl), "", probes)

    def dc(self, source_node: str, start: float, stop: float, step: float) -> SimResult:
        """Sweep a source and record the probes.

        ``source_node`` is a node driven by ``sources`` or ``supplies`` (a
        supply sweep gives line regulation), a source name, or ``"temp"``
        for a temperature sweep in degrees C.
        """
        vname = self._source_name(source_node)
        # Default to every port, not just the swept source: recording only
        # the stimulus tells you what you already know and leaves the
        # response — the reason for the sweep — out of the result.
        probes = self.probes or self.ports or [source_node]
        ctrl = [f"dc {vname} {start} {stop} {step}",
                f"wrdata dc.dat {' '.join(_vec(p) for p in probes)}"]
        x_name = "temp" if vname == "temp" else "v_sweep"
        return self._run("dc", self.build_deck([], ctrl), x_name, probes,
                         datfile="dc.dat")

    def _source_name(self, node: str) -> str:
        """The ngspice source driving ``node`` (or ``temp``)."""
        if node.lower() == "temp":
            return "temp"
        if node in self.sources:
            return f"Vsrc{list(self.sources).index(node)}"
        if node in self.supplies:
            return f"Vsupply{list(self.supplies).index(node)}"
        return node

    def run(self, control: Sequence[str], *, analysis: str = "custom",
            x_name: str = "", probes: Sequence[str] = (),
            datfile: Optional[str] = None, complex_data: bool = False,
            workdir: Optional[str] = None) -> SimResult:
        """Run arbitrary ngspice control lines against this testbench.

        The public form of what the measurement recipes need: the deck is
        built exactly as for the canned analyses (models, stimulus, DUT), and
        ``print``/``wrdata`` output is parsed into the result.
        """
        return self._run(analysis, self.build_deck([], control), x_name,
                         list(probes), workdir=workdir, datfile=datfile,
                         complex_data=complex_data)

    def ac(self, fstart: float, fstop: float, points: int = 20,
           variation: str = "dec", ac_node: Optional[str] = None) -> SimResult:
        """AC sweep. The stimulus node is given an AC magnitude of 1."""
        node = ac_node or (list(self.sources)[0] if self.sources else None)
        if node is None:
            raise ValueError("ac() needs a source node to excite")
        probes = self.probes or self.ports or [node]
        deck = self.build_deck([], [f"ac {variation} {points} {fstart} {fstop}",
                                    f"wrdata ac.dat {' '.join(_vec(p) for p in probes)}"])
        # Give the chosen source an AC magnitude of 1. The old pattern only
        # matched a single-token value, so a source written "DC 1.2" kept an
        # AC magnitude of zero and the sweep came back all zeros — a silent
        # wrong answer. Match the line, not the value, and refuse to run if
        # the source is not there at all.
        # The excited node may be a supply as well as a source: AC on VDD,
        # read at the output, is the PSRR transfer function.
        vname = self._source_name(node)
        deck, n = re.subn(rf"^({re.escape(vname)}\s+{re.escape(node)}\s+0\s+.*)$",
                          r"\1 AC 1", deck, flags=re.MULTILINE)
        if n != 1:
            raise RuntimeError(
                f"ac(): could not attach an AC magnitude to source "
                f"'{vname}' on node '{node}'. Without it every result is "
                f"zero, so this fails instead of returning one.")
        return self._run("ac", deck, "frequency", probes, datfile="ac.dat",
                         complex_data=True)

    def tran(self, step: str, stop: str, start: str = "0") -> SimResult:
        """Transient analysis."""
        probes = self.probes or self.ports
        ctrl = [f"tran {step} {stop} {start}",
                f"wrdata tran.dat {' '.join(_vec(p) for p in probes)}"]
        return self._run("tran", self.build_deck([], ctrl), "time", probes,
                         datfile="tran.dat")

    def monte_carlo(self, analysis: str = "op", runs: int = 25,
                    corner: str = "statistical", mismatch: bool = True,
                    **kwargs) -> MonteCarloResult:
        """Repeat an analysis with fresh device-mismatch draws.

        GF180 expresses mismatch as `delvto = mis_vth * sw_stat_mismatch`, so
        two things are needed for the samples to actually differ: a corner that
        carries the statistical parameters, and sw_stat_mismatch enabled. Just
        re-seeding the typical corner returns the same number every run — the
        mismatch term is multiplied by zero.
        """
        out = MonteCarloResult(measure=analysis)
        fn = {"op": self.op, "dc": self.dc, "ac": self.ac, "tran": self.tran}[analysis]
        base_wd, base_corner, base_mm, base_seed = (
            self.workdir, self.corner, self.mismatch, self.seed)
        self.corner, self.mismatch = corner, mismatch
        try:
            for i in range(runs):
                self.workdir = os.path.join(base_wd, f"mc{i:03d}")
                self.seed = i + 1
                out.runs.append(fn(**kwargs))
        finally:
            self.workdir, self.corner = base_wd, base_corner
            self.mismatch, self.seed = base_mm, base_seed
        return out


# ── parsing ────────────────────────────────────────────────────────────

def _vec(probe: str) -> str:
    """A node name as an ngspice vector; expressions like i(Vsupply0) pass through."""
    return probe if "(" in probe else f"v({probe})"


def _parse_print(res: SimResult, probes: Sequence[str]) -> None:
    """Pull `name = value` lines out of ngspice's stdout."""
    for m in re.finditer(rf"^\s*([\w()\.]+)\s*=\s*({_NUM})\s*$", res.stdout or "",
                         re.MULTILINE):
        res.scalars[m.group(1).lower()] = float(m.group(2))


_DAT_NAMES = {"dc.dat", "ac.dat", "tran.dat"}


def _parse_wrdata(res: SimResult, path: str, x_name: str,
                  probes: Sequence[str], complex_data: bool = False) -> None:
    """Read an ngspice `wrdata` file.

    wrdata repeats the sweep variable before every probe, so the stride
    depends on whether the data is real or complex:

        real (dc/tran)  x y   x y   x y    -> stride 2
        complex (ac)    x re im  x re im   -> stride 3

    Parsing an AC file with the real stride silently produced phantom signals
    (`col4`, `col5`) and put an imaginary part where a voltage belonged, so
    the two cases are handled separately. For AC the magnitude is stored under
    the probe name, with the real and imaginary parts kept alongside as
    `<name>.re` / `<name>.im` for anyone who needs phase.
    """
    if not os.path.isfile(path):
        return
    xs: List[float] = []
    cols: List[List[float]] = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line[0] in "#*@":
                continue
            try:
                vals = [float(v) for v in line.split()]
            except ValueError:
                continue
            if not vals:
                continue
            xs.append(vals[0])
            if complex_data and len(vals) >= 3:
                ys = [(vals[i], vals[i + 1])
                      for i in range(1, len(vals) - 1, 3)]
            elif len(vals) > 2:
                ys = vals[1::2]
            else:
                ys = vals[1:]
            while len(cols) < len(ys):
                cols.append([])
            for i, v in enumerate(ys):
                cols[i].append(v)
    if not xs:
        return
    res.x = xs
    res.x_name = x_name
    for i, col in enumerate(cols):
        name = probes[i] if i < len(probes) else f"col{i}"
        if complex_data:
            re_p = [c[0] for c in col]
            im_p = [c[1] for c in col]
            mag = [math.hypot(a, b) for a, b in col]
            res.signals[f"{name}.re"] = re_p
            res.signals[f"{name}.im"] = im_p
            col = mag
        res.signals[name] = col
        res.signals[f"v({name})"] = col
