"""Physical LEF and interface-only Liberty/Verilog views; no system integration."""
from __future__ import annotations

import json
import math
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
    from mbg.config import magic_bin, ToolError
    try:
        magic = magic_bin()
    except ToolError:
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
    cmd = [magic, "-dnull", "-noconsole"]
    if os.path.isfile(rcfile):
        cmd += ["-rcfile", rcfile]
    cmd.append(script)
    try:
        completed = subprocess.run(cmd, capture_output=True, text=True,
                                   timeout=timeout, cwd=outdir)
        if completed.returncode:
            return None
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
              library_name: Optional[str] = None, default_cap: Optional[float] = None) -> str:
    """Interface-only Liberty: no invented timing, voltage or capacitance."""
    from mbg.macro import validate_identifier
    validate_identifier(cell, 'cell')
    lib = validate_identifier(library_name or cell+'_lib', 'library')
    lines = ['/* Interface abstract; timing is NOT RUN. */', 'library ('+lib+') {',
             '  delay_model : table_lookup;', '  time_unit : "1ns";',
             '  voltage_unit : "1V";', '  capacitive_load_unit (1, pf);',
             '  cell ('+cell+') {', '    is_macro_cell : true;', '    dont_touch : true;']
    for pin in ports:
        validate_identifier(pin.name, 'pin')
        if pin.direction in ('power','ground'):
            role = 'primary_power' if pin.direction=='power' else 'primary_ground'
            lines += ['    pg_pin('+pin.name+') {', '      voltage_name : '+pin.name+';',
                      '      pg_type : '+role+';', '    }']
        else:
            lines += ['    pin('+pin.name+') {', '      direction : '+pin.liberty_dir+';']
            if default_cap is not None:
                if not math.isfinite(default_cap) or default_cap < 0:
                    raise ValueError('explicit pin capacitance must be nonnegative and finite')
                lines.append('      capacitance : '+str(default_cap)+';')
            lines.append('    }')
    lines += ['  }','}']
    os.makedirs(outdir,exist_ok=True)
    path = os.path.join(outdir,cell+'.lib')
    with open(path,'w') as f:
        f.write('\n'.join(lines)+'\n')
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

    interface = result.get("macro_interface") or {}
    lef = (write_macro_lef(result, outdir) if interface.get("pins") else
           write_lef(out.files["gds"], cell, outdir) if out.files["gds"] else None)
    out.files["lef"] = lef
    if lef is None:
        out.notes.append("LEF not generated (Magic unavailable or the write failed)")

    manifest = os.path.join(outdir, f"{cell}.views.json")
    with open(manifest, "w") as f:
        json.dump({"cell": cell,
                   "ports": [{"name": p.name, "direction": p.direction} for p in specs],
                   "files": {k: (os.path.relpath(v, outdir) if v else None)
                             for k, v in out.files.items()},
                   "notes": out.notes,
                   "interface": interface},
                  f, indent=2, sort_keys=True)
        f.write("\n")
    out.files["manifest"] = manifest

    if verbosity:
        print(f"  [OUTPUTS] {out.summary()}")
        for n in out.notes:
            print(f"  [OUTPUTS] note: {n}")
    return out


def write_macro_lef(result: Dict, outdir: str) -> str:
    """Write an ordinary macro abstract from its actual physical pin contract."""
    from mbg.macro import validate_identifier
    interface = result.get('macro_interface') or getattr(result.get('context'), 'macro_interface', None)
    if not interface or not interface.get('pins'):
        raise ValueError('macro LEF requires physical pin geometry')
    cell = validate_identifier(result.get('cell_name') or interface['cell'], 'cell')
    x0,y0,x1,y1 = interface['bounds']
    if x1 <= x0 or y1 <= y0:
        raise ValueError('macro bounds must be positive')
    lines = ['VERSION 5.8 ;','BUSBITCHARS "[]" ;','DIVIDERCHAR "/" ;',
             'MACRO '+cell, '  CLASS BLOCK ;','  ORIGIN 0 0 ;',
             f'  SIZE {x1-x0:.6f} BY {y1-y0:.6f} ;','  SYMMETRY X Y ;']
    for pin in interface['pins']:
        name = validate_identifier(pin['name'], 'pin')
        a,b,c,d = pin['rect']
        if not (x0 <= a < c <= x1 and y0 <= b < d <= y1):
            raise ValueError('macro pin escapes the declared bounds')
        direction = 'INPUT' if pin['direction']=='input' else 'OUTPUT' if pin['direction']=='output' else 'INOUT'
        use = 'POWER' if pin['direction']=='power' else 'GROUND' if pin['direction']=='ground' else 'SIGNAL'
        lines += ['  PIN '+name,'    DIRECTION '+direction+' ;','    USE '+use+' ;',
                  '    PORT','      LAYER Metal'+pin['layer'][3:]+' ;',
                  f'        RECT {a-x0:.6f} {b-y0:.6f} {c-x0:.6f} {d-y0:.6f} ;',
                  '    END','  END '+name]
    # Preserve actual internal metal as obstructions, subtracting this
    # layer's published physical pin rectangles so pins remain accessible.
    ctx = result.get('context')
    component = result.get('component') or getattr(ctx,'component',None)
    if component is not None and getattr(ctx,'rules',None) is not None:
        import gdstk
        geometry = component.get_polygons(by_spec=True)
        lines.append('  OBS')
        for layer in ctx.rules.metals:
            metal = geometry.get(ctx.rules.layer_tuple(layer),[])
            cuts = [gdstk.rectangle((p['rect'][0],p['rect'][1]),(p['rect'][2],p['rect'][3]))
                    for p in interface['pins'] if p['layer']==layer]
            pieces = gdstk.boolean(metal,cuts,'not',precision=ctx.rules.manufacturing_grid()) if metal else []
            if not pieces:
                continue
            from mbg.geometry import rect_decompose
            lines.append('    LAYER Metal'+layer[3:]+' ;')
            for polygon in pieces:
                for a,b,c,d in rect_decompose([tuple(pt) for pt in polygon.points]):
                    lines.append(f'      RECT {a-x0:.6f} {b-y0:.6f} {c-x0:.6f} {d-y0:.6f} ;')
        lines.append('  END')
    lines += ['END '+cell,'END LIBRARY']
    os.makedirs(outdir,exist_ok=True)
    path = os.path.join(outdir,cell+'.lef')
    with open(path,'w') as f:
        f.write('\n'.join(lines)+'\n')
    return path
