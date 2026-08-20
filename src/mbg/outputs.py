"""Per-module deliverables: LEF, Liberty, Verilog, and a manifest of everything.

The layout flow already produces GDS, SVG, the schematic and extracted netlists,
and the DRC / LVS / PEX reports. Integrating a block into a larger chip with
LibreLane needs three more views:

    LEF      abstract footprint and pin shapes, for the placer
    LIB      Liberty timing/power abstract, for the synthesiser
    Verilog  a black-box module declaration, so RTL can instantiate it

An analog macro has no timing arcs to characterise, so the Liberty view here is
a hard-macro abstract: correct pin directions and capacitances, no arcs. That is
what LibreLane needs to place and route around the block, and it is honest about
what it is — it does not claim characterisation that was never run.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

__all__ = ["PortSpec", "classify_ports", "write_lef", "write_verilog",
           "write_lib", "write_all", "OutputSet"]

_POWER = {"vdd", "vcc", "vpwr", "vdda", "vddio", "avdd"}
_GROUND = {"vss", "gnd", "vgnd", "vssa", "vssio", "agnd"}


@dataclass
class PortSpec:
    name: str
    direction: str          # "inout" | "input" | "output" | "power" | "ground"

    @property
    def is_supply(self) -> bool:
        return self.direction in ("power", "ground")

    @property
    def verilog_dir(self) -> str:
        return {"power": "inout", "ground": "inout"}.get(self.direction, self.direction)

    @property
    def liberty_dir(self) -> str:
        return {"power": "inout", "ground": "inout"}.get(self.direction, self.direction)


def classify_ports(ports: Sequence[str],
                   directions: Optional[Dict[str, str]] = None) -> List[PortSpec]:
    """Label each subcircuit port.

    Supplies are recognised by name. Everything else defaults to `inout`,
    which is the correct and honest choice for an analog macro: the netlist
    records connectivity, not signal direction, and guessing input/output from
    a name would be inventing information. Pass `directions` to override.
    """
    out = []
    for p in ports:
        low = p.lower()
        if directions and p in directions:
            d = directions[p]
        elif low in _POWER:
            d = "power"
        elif low in _GROUND:
            d = "ground"
        else:
            d = "inout"
        out.append(PortSpec(p, d))
    return out


@dataclass
class OutputSet:
    """Where each generated view ended up. Missing views are recorded as None."""
    cell: str
    outdir: str
    files: Dict[str, Optional[str]] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)

    def present(self) -> Dict[str, str]:
        return {k: v for k, v in self.files.items() if v and os.path.isfile(v)}

    def missing(self) -> List[str]:
        return sorted(k for k, v in self.files.items()
                      if not v or not os.path.isfile(v))

    def summary(self) -> str:
        have = self.present()
        return (f"{self.cell}: {len(have)}/{len(self.files)} views "
                f"[{', '.join(sorted(have))}]"
                + (f" missing: {', '.join(self.missing())}" if self.missing() else ""))


# ── LEF ────────────────────────────────────────────────────────────────

def write_lef(gds_path: str, cell: str, outdir: str, *,
              tech: Optional[str] = None, timeout: int = 300) -> Optional[str]:
    """Generate an abstract LEF with Magic.

    Returns the path, or None with the reason recorded by the caller.
    """
    if shutil.which("magic") is None:
        return None
    gds_path = os.path.abspath(gds_path)
    outdir = os.path.abspath(outdir)
    os.makedirs(outdir, exist_ok=True)
    lef_path = os.path.join(outdir, f"{cell}.lef")
    tech = tech or os.environ.get("PDK", "gf180mcuD")

    script = os.path.join(outdir, "_write_lef.tcl")
    with open(script, "w") as f:
        # `gds readonly true` and `gds rescale false` make Magic emit an empty
        # macro (SIZE 0.005 BY 0.005, no pins). A plain read gives the real
        # abstract, so do not "optimise" those flags back in.
        f.write(
            "drc off\n"
            f"gds read {gds_path}\n"
            f"load {cell}\n"
            "select top cell\n"
            f"lef write {lef_path} -hide\n"
            "quit -noprompt\n")
    pdkpath = os.environ.get("PDKPATH") or os.path.join(
        os.environ.get("PDK_ROOT", os.path.expanduser("~/.volare")), tech)
    rcfile = os.path.join(pdkpath, "libs.tech", "magic", f"{tech}.magicrc")
    cmd = ["magic", "-dnull", "-noconsole"]
    if os.path.isfile(rcfile):
        cmd += ["-rcfile", rcfile]
    cmd.append(script)
    try:
        subprocess.run(cmd, capture_output=True, text=True,
                       timeout=timeout, cwd=outdir)
    except Exception:
        return None
    if not os.path.isfile(lef_path):
        return None
    # An abstract with no pins means Magic loaded an empty cell; report that
    # as a failure rather than shipping a LEF the placer cannot use.
    text = open(lef_path).read()
    if "PIN " not in text:
        return None
    return lef_path


# ── Verilog ────────────────────────────────────────────────────────────

def write_verilog(cell: str, ports: Sequence[PortSpec], outdir: str) -> str:
    """Black-box module declaration for RTL integration."""
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{cell}.v")
    width = max((len(p.name) for p in ports), default=1)
    decls = "\n".join(f"    {p.verilog_dir:<6} {p.name};" for p in ports)
    plist = ",\n".join(f"    {p.name}" for p in ports)
    supplies = [p.name for p in ports if p.is_supply]
    with open(path, "w") as f:
        f.write(
            f"// Black-box declaration for the analog macro `{cell}`.\n"
            f"// Generated by mbg.outputs — there is no behavioural model here;\n"
            f"// the implementation is the GDS, and this exists so RTL and\n"
            f"// LibreLane can instantiate the block.\n"
            f"//\n"
            f"// Supplies ({len(supplies)}): {', '.join(supplies) or 'none'}\n"
            f"// Signal pins are declared `inout`: a SPICE netlist records\n"
            f"// connectivity, not direction, so anything else would be a guess.\n"
            f"\n"
            f"`timescale 1ns / 1ps\n"
            f"`default_nettype none\n\n"
            f"(* blackbox *)\n"
            f"module {cell} (\n{plist}\n);\n\n{decls}\n\n"
            f"endmodule\n\n"
            f"`default_nettype wire\n")
    return path


# ── Liberty ────────────────────────────────────────────────────────────

def write_lib(cell: str, ports: Sequence[PortSpec], outdir: str, *,
              library_name: Optional[str] = None,
              default_cap: float = 0.005) -> str:
    """Minimal Liberty abstract for a hard analog macro.

    No timing arcs: none were characterised, and inventing them would make a
    synthesiser trust numbers nobody measured. Pin directions and a nominal
    capacitance are enough for LibreLane to treat the block as a hard macro.
    """
    os.makedirs(outdir, exist_ok=True)
    path = os.path.join(outdir, f"{cell}.lib")
    lib = library_name or f"{cell}_lib"
    pin_blocks = []
    for p in ports:
        if p.direction == "power":
            pin_blocks.append(
                f'    pg_pin({p.name}) {{\n'
                f'      voltage_name : VDD;\n'
                f'      pg_type : primary_power;\n'
                f'    }}')
        elif p.direction == "ground":
            pin_blocks.append(
                f'    pg_pin({p.name}) {{\n'
                f'      voltage_name : VSS;\n'
                f'      pg_type : primary_ground;\n'
                f'    }}')
        else:
            pin_blocks.append(
                f'    pin({p.name}) {{\n'
                f'      direction : {p.liberty_dir};\n'
                f'      capacitance : {default_cap};\n'
                f'    }}')
    with open(path, "w") as f:
        f.write(
            f'/*\n'
            f' * Liberty abstract for the analog macro `{cell}`.\n'
            f' * Generated by mbg.outputs.\n'
            f' *\n'
            f' * This is a HARD MACRO abstract, not a characterised cell: it carries\n'
            f' * pin directions, supply pins and a nominal input capacitance so a\n'
            f' * synthesiser and floorplanner can work around the block. It contains\n'
            f' * no timing arcs, because none were characterised.\n'
            f' */\n'
            f'library ({lib}) {{\n'
            f'  technology (cmos);\n'
            f'  delay_model : table_lookup;\n'
            f'  time_unit : "1ns";\n'
            f'  voltage_unit : "1V";\n'
            f'  current_unit : "1mA";\n'
            f'  capacitive_load_unit (1, pf);\n'
            f'  pulling_resistance_unit : "1kohm";\n'
            f'  leakage_power_unit : "1nW";\n'
            f'  default_max_transition : 1.0;\n\n'
            f'  voltage_map (VDD, 3.3);\n'
            f'  voltage_map (VSS, 0.0);\n\n'
            f'  operating_conditions (typical) {{\n'
            f'    process : 1.0;\n    temperature : 25.0;\n    voltage : 3.3;\n'
            f'    tree_type : balanced_tree;\n  }}\n'
            f'  default_operating_conditions : typical;\n\n'
            f'  cell ({cell}) {{\n'
            f'    is_macro_cell : true;\n'
            f'    dont_touch : true;\n'
            f'    dont_use : true;\n'
            f'    interface_timing : true;\n\n'
            + "\n".join(pin_blocks) + "\n"
            f'  }}\n'
            f'}}\n')
    return path


# ── orchestration ──────────────────────────────────────────────────────

def write_all(result: Dict, *, outdir: Optional[str] = None,
              directions: Optional[Dict[str, str]] = None,
              verbosity: int = 1) -> OutputSet:
    """Produce every view for a completed pipeline result.

    `result` is what spice_to_gds_with_checks() returned. Views already written
    by the flow (GDS, SVG, netlists, reports) are recorded rather than redone.
    """
    cell = result.get("cell_name") or "top"
    outdir = os.path.abspath(outdir or result.get("outdir") or ".")
    os.makedirs(outdir, exist_ok=True)
    out = OutputSet(cell=cell, outdir=outdir)

    ctx = result.get("context")
    ports = list(getattr(ctx, "top_ports", []) or [])
    if not ports:
        out.notes.append("no subcircuit ports found; LEF/LIB/Verilog pins will be empty")
    specs = classify_ports(ports, directions)

    def _find(*names):
        for n in names:
            p = os.path.join(outdir, n)
            if os.path.isfile(p):
                return p
        return None

    out.files["gds"] = result.get("gds_path") or _find(f"{cell}.gds")
    out.files["svg"] = result.get("svg_path") or _find(f"{cell}.svg")
    out.files["sch_spice"] = _find(f"{cell}.spice")
    out.files["pex_spice"] = (result.get("pex", {}) or {}).get("pex_path") or \
        _find(f"{cell}.pex.spice")
    out.files["lvs_report"] = (result.get("lvs", {}) or {}).get("report_path") or \
        _find(f"{cell}.lvs.out")
    out.files["drc_report"] = (result.get("drc", {}) or {}).get("report_path") or \
        _find(f"{cell}.magic.drc.rpt", f"{cell}.drc.rpt")
    out.files["extracted_spice"] = _find(f"{cell}_extracted.spice")

    out.files["verilog"] = write_verilog(cell, specs, outdir)
    out.files["lib"] = write_lib(cell, specs, outdir)

    lef = write_lef(out.files["gds"], cell, outdir) if out.files["gds"] else None
    out.files["lef"] = lef
    if lef is None:
        out.notes.append("LEF not generated (Magic unavailable or the write failed)")

    manifest = os.path.join(outdir, f"{cell}.views.json")
    with open(manifest, "w") as f:
        json.dump({"cell": cell,
                   "ports": [{"name": p.name, "direction": p.direction} for p in specs],
                   "files": {k: (os.path.relpath(v, outdir) if v else None)
                             for k, v in out.files.items()},
                   "notes": out.notes},
                  f, indent=2, sort_keys=True)
        f.write("\n")
    out.files["manifest"] = manifest

    if verbosity:
        print(f"  [OUTPUTS] {out.summary()}")
        for n in out.notes:
            print(f"  [OUTPUTS] note: {n}")
    return out
