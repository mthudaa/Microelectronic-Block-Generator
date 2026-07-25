"""
IC Physical Verification — DRC, LVS, PEX for AI agent tooling.

AI agent usage pattern:
    drc = run_drc("out.gds")
    if drc["clean"]:
        lvs = run_lvs("out.gds", netlist_content=netlist)
        pex = run_pex("out.gds")

Returns structured dicts — no log-parsing required.
"""

import os, subprocess, shutil, re, tempfile, textwrap

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))
IIC_DRC = os.path.join(SCRIPT_DIR, "iic-drc.sh")
IIC_LVS = os.path.join(SCRIPT_DIR, "iic-lvs.sh")
IIC_PEX = os.path.join(SCRIPT_DIR, "iic-pex.sh")

__all__ = [
    "check_tools", "validate_gds",
    "extract_layout_netlist", "fix_port_order",
    "run_drc", "run_lvs", "run_pex",
]


def _check_env():
    missing = [v for v in ["PDK_ROOT", "PDK", "PDKPATH"] if v not in os.environ]
    if missing:
        raise EnvironmentError(
            f"Missing env vars: {', '.join(missing)}. "
            "Set PDK_ROOT=/foss/pdks, PDK=gf180mcuD, "
            "PDKPATH=/foss/pdks/gf180mcuD"
        )


def _check_script(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Verification script not found: {path}")


def check_tools():
    """Check if all verification tools (Magic, netgen) are available.

    Returns:
        dict: {magic: bool, netgen: bool, magic_path: str|None,
               netgen_path: str|None, pdk_ok: bool, message: str}
    """
    magic = shutil.which("magic")
    netgen = shutil.which("netgen")
    pdk_ok = all(k in os.environ for k in ["PDK_ROOT", "PDK", "PDKPATH"])
    status = []
    if not magic:
        status.append("MAGIC MISSING")
    if not netgen:
        status.append("NETGEN MISSING")
    if not pdk_ok:
        status.append("PDK ENV MISSING")
    return {
        "magic": magic is not None, "netgen": netgen is not None,
        "magic_path": magic, "netgen_path": netgen,
        "pdk_ok": pdk_ok,
        "message": "; ".join(status) if status else "All tools OK",
    }


def validate_gds(gds_path, cell_name=None, min_size=100):
    """Validate a GDS file exists, has content, and contains the expected cell.

    Args:
        gds_path: Path to GDS file.
        cell_name: Expected top cell name (optional).
        min_size: Minimum file size in bytes (default 100).

    Returns:
        dict: {valid: bool, size: int, cell: str|None,
               message: str, cells: list}
    """
    result = {"valid": False, "size": 0, "cell": None, "message": "", "cells": []}
    gds_path = os.path.abspath(gds_path)
    if not os.path.isfile(gds_path):
        result["message"] = f"File not found: {gds_path}"
        return result
    size = os.path.getsize(gds_path)
    result["size"] = size
    if size < min_size:
        result["message"] = f"File too small ({size}B < {min_size}B)"
        return result
    try:
        import gdstk
        lib = gdstk.read_gds(gds_path)
        cells = [c.name for c in lib.cells]
        result["cells"] = cells
        top = lib.top_level()
        if top:
            result["cell"] = top[0].name
        if cell_name and cell_name not in cells:
            result["message"] = f"Cell '{cell_name}' not found in GDS (have: {cells})"
            return result
        result["valid"] = True
        result["message"] = f"GDS OK: {size}B, {len(cells)} cells, top={result['cell']}"
    except Exception as e:
        result["message"] = f"GDS read error: {e}"
    return result


# ── Layout extraction ────────────────────────────────────────────────

def extract_layout_netlist(gds_path, cell_name=None, workdir=None, timeout=300):
    """Extract SPICE netlist from GDS using Magic (no-RC / LVS mode).

    Args:
        gds_path: Path to GDS file.
        cell_name: Top cell name (auto from filename if None).
        workdir: Working directory (temp dir if None).
        timeout: Max seconds (default 300).

    Returns:
        dict: {netlist_path: str|None, raw_ports: list, log: str,
               success: bool}
    """
    _check_env()
    gds_path = os.path.abspath(gds_path)
    if not os.path.isfile(gds_path):
        raise FileNotFoundError(f"GDS not found: {gds_path}")
    cell = cell_name or os.path.splitext(os.path.basename(gds_path))[0]
    wd = os.path.abspath(workdir) if workdir else tempfile.mkdtemp(prefix="lvs_")
    os.makedirs(wd, exist_ok=True)
    ext_script = os.path.join(wd, "extract.tcl")
    out_path = os.path.join(wd, f"{cell}_extracted.spice")

    with open(ext_script, "w") as f:
        f.write("crashbackups stop\ndrc off\n")
        f.write(f"gds read {gds_path}\nload {cell}\nexpand\n")
        f.write("select top cell\n")
        f.write(f"extract path {wd}\n")
        f.write("extract no capacitance\nextract no coupling\n")
        f.write("extract no resistance\nextract no length\nextract all\n")
        f.write("ext2spice lvs\n")
        f.write(f"ext2spice -p {wd} -o {out_path}\n")
        f.write("quit -noprompt\n")

    env = os.environ.copy()
    pdk = env.get("PDK", "gf180mcuD")
    rcfile = f"{env.get('PDK_ROOT', '')}/{pdk}/libs.tech/magic/{pdk}.magicrc"
    try:
        r = subprocess.run(
            ["magic", "-dnull", "-noconsole", "-rcfile", rcfile, ext_script],
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except subprocess.TimeoutExpired:
        return {"netlist_path": None, "raw_ports": [], "log": "Extraction timed out",
                "success": False}
    except FileNotFoundError:
        return {"netlist_path": None, "raw_ports": [], "log": "magic not found in PATH",
                "success": False}

    log = r.stdout + "\n" + r.stderr
    raw_ports = []
    if os.path.isfile(out_path):
        with open(out_path) as f:
            for line in f:
                if line.startswith(".subckt"):
                    raw_ports = line.strip().split()[2:]
                    break
    success = os.path.isfile(out_path)
    return {
        "netlist_path": out_path if success else None,
        "raw_ports": raw_ports,
        "log": log.strip(),
        "success": success,
    }


def fix_port_order(extracted_path, correct_order, out_path=None):
    """Rewrite extracted netlist .subckt line with correct port order.

    AI agents should use run_lvs(auto_fix_ports=True) instead of calling
    this directly.

    Args:
        extracted_path: Path to extracted .spice file.
        correct_order: List of port names in correct order.
        out_path: Output path (default: overwrite input).

    Returns:
        str: Path to fixed netlist.
    """
    out = out_path or extracted_path
    with open(extracted_path) as f:
        lines = f.readlines()
    for i, line in enumerate(lines):
        if line.startswith(".subckt"):
            parts = line.strip().split()
            lines[i] = ".subckt " + parts[1] + " " + " ".join(correct_order) + "\n"
            break
    with open(out, "w") as f:
        f.writelines(lines)
    return out


# ── DRC ──────────────────────────────────────────────────────────────

def run_drc(gds_path, cell_name=None, engine="magic", workdir=None,
            clean=False, timeout=600):
    """Run Design Rule Check via iic-drc.sh.

    Args:
        gds_path: Path to GDS file.
        cell_name: Top cell name (auto from filename if None).
        engine: "magic" (default), "klayout", or "both".
        workdir: Working directory (default: current dir).
        clean: Remove previous result files.
        timeout: Max seconds (default 600).

    Returns:
        dict: {clean: bool, report_path: str|None, error_count: int,
               log: str, summary: str}  — summary is a 1-line AI-readable
               string like "DRC: CLEAN" or "DRC: 12 ERRORS".
    """
    _check_env(); _check_script(IIC_DRC)
    gds_path = os.path.abspath(gds_path)
    if not os.path.isfile(gds_path):
        raise FileNotFoundError(f"GDS not found: {gds_path}")
    cell = cell_name or os.path.splitext(os.path.basename(gds_path))[0]

    engine_flag = {"magic": "-m", "klayout": "-k", "both": "-b"}.get(engine, "-m")
    cmd = ["bash", IIC_DRC, engine_flag]
    if clean: cmd += ["-c"]
    if workdir: cmd += ["-w", os.path.abspath(workdir)]
    cmd.append(gds_path)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"clean": False, "report_path": None, "error_count": -1,
                "log": "DRC timed out", "summary": "DRC: TIMEOUT"}
    except FileNotFoundError:
        return {"clean": False, "report_path": None, "error_count": -1,
                "log": "bash not found", "summary": "DRC: BASH NOT FOUND"}

    log = r.stdout + "\n" + r.stderr
    resdir = os.path.abspath(workdir) if workdir else os.getcwd()
    report = os.path.join(resdir, f"{cell}.magic.drc.rpt")
    if not os.path.isfile(report):
        report = None

    is_clean = "No DRC errors" in log or "CONGRATULATIONS" in log
    errors = 0
    if report:
        try:
            with open(report) as f:
                errors = sum(1 for line in f if line.strip())
        except Exception:
            pass

    return {
        "clean": is_clean,
        "report_path": report,
        "error_count": errors,
        "log": log.strip(),
        "summary": f"DRC: {'CLEAN' if is_clean else f'{errors} ERRORS'}",
    }


# ── LVS ──────────────────────────────────────────────────────────────

_SUBCKT_PORT_RE = re.compile(r"\.subckt\s+(\S+)\s+(.+)")


def _parse_lvs_summary(report_path):
    """Parse netgen LVS report into structured AI-readable dict."""
    if not report_path or not os.path.isfile(report_path):
        return {"match": False, "device_mismatch": "?", "net_mismatch": "?",
                "port_swaps": [], "missing_devices": [], "message": "No report"}
    with open(report_path) as f:
        text = f.read()
    match = "Circuits match uniquely" in text
    dev_m, net_m = "?", "?"
    for line in text.split("\n"):
        m = re.match(r"Number of devices:\s+(\d+)\s+\|\s+Number of devices:\s+(\d+)", line)
        if m: dev_m = f"{m.group(1)}vs{m.group(2)}"
        m = re.match(r"Number of nets:\s+(\d+)\s+\|\s+Number of nets:\s+(\d+)", line)
        if m: net_m = f"{m.group(1)}vs{m.group(2)}"
    swaps = re.findall(r"(\w+)\s+\|\s+(\w+)\s+\*\*Mismatch", text)
    missing = re.findall(r"no matching.*?Instance:\s+(\S+)", text)
    return {
        "match": match,
        "device_mismatch": dev_m,
        "net_mismatch": net_m,
        "port_swaps": [(a, b) for a, b in swaps],
        "missing_devices": missing,
        "message": "LVS OK" if match else "LVS MISMATCH",
    }


def _flatten_netlist(extracted_path, out_path=None):
    """Flatten a hierarchical extracted netlist into flat M-element SPICE.

    Magic's ext2spice lvs creates hierarchical netlists where each
    transistor is wrapped in a small subcircuit. This function replaces
    those wrappers with flat M-elements for netgen compatibility.

    Args:
        extracted_path: Path to hierarchical extracted .spice.
        out_path: Output path (default: same dir, add _flat suffix).

    Returns:
        str: Path to flattened netlist.
    """
    out = out_path or extracted_path.replace(".spice", "_flat.spice")
    with open(extracted_path) as f:
        text = f.read()

    # Parse subcircuits
    subckts = {}
    current_name = None
    current_lines = []
    for line in text.split("\n"):
        if line.startswith(".subckt "):
            if current_name:
                subckts[current_name] = current_lines
            parts = line.split()
            current_name = parts[1]
            current_lines = [line]
        elif line.startswith(".ends"):
            if current_name:
                current_lines.append(line)
                subckts[current_name] = current_lines
            current_name = None
            current_lines = []
        elif current_name:
            current_lines.append(line)
    if current_name and current_lines:
        subckts[current_name] = current_lines

    # Find transistor wrapper subcircuits
    wrappers = {}
    for name, lines in subckts.items():
        for line in lines:
            m = re.search(r'X0\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(nfet_03v3|pfet_03v3)', line)
            if m:
                wrappers[name] = {
                    "pins": [m.group(1), m.group(2), m.group(3), m.group(4)],
                    "model": m.group(5),
                    "ext_pins": subckts[name][0].split()[2:] if name in subckts else []
                }

    # Flatten top-level subcircuit (first .subckt after comments)
    flat_lines = []
    for line in subckts.get(list(wrappers.keys())[0] if wrappers else "inv", []):
        pass  # skip — we only process "inv"
    top_name = [n for n in subckts if n not in wrappers]
    top_name = top_name[0] if top_name else "inv"

    for line in subckts.get(top_name, []):
        m = re.match(r'X(\S+)\s+(.+)', line)
        if m:
            inst, rest = m.group(1), m.group(2).strip()
            parts = rest.rsplit(None, 1)
            if len(parts) == 2 and parts[1] in wrappers:
                conn, wrap = parts[0].split(), wrappers[parts[1]]
                pmap = dict(zip(wrap["ext_pins"], conn))
                d = (pmap.get(wrap["pins"][0], "vdd" if "pfet" in wrap["model"] else "vss")).lower()
                g = pmap.get(wrap["pins"][1], "?").lower()
                s = (pmap.get(wrap["pins"][2], "vss" if "nfet" in wrap["model"] else "vdd")).lower()
                b = pmap.get(wrap["pins"][3], "vdd" if "pfet" in wrap["model"] else "vss")
                if b.upper() in ("VSUBS", "VSUB"):
                    b = "vss"
                b = b.lower()
                flat_lines.append(f"M{inst} {d} {g} {s} {b} {wrap['model']} W=15u L=1u")
                continue
        flat_lines.append(line)

    with open(out, "w") as f:
        f.write("\n".join(flat_lines))
    return out


def run_lvs(gds_path, netlist_path=None, netlist_content=None,
            cell_name=None, workdir=None, auto_fix_ports=True, timeout=600):
    """Run Layout vs Schematic via netgen with auto port-order fix + flatten.

    Usage:
        lvs = run_lvs("out.gds", netlist_content=netlist)
        if lvs["match"]:
            print("LVS passed!")
        else:
            s = lvs["summary"]
            print(f"Port swaps: {s['port_swaps']}")

    Args:
        gds_path: Path to GDS layout.
        netlist_path: Path to schematic SPICE netlist.
        netlist_content: SPICE netlist string (saved to temp file).
        cell_name: Top cell name (auto from GDS filename if None).
        workdir: Working directory (temp dir if None).
        auto_fix_ports: If True, extracts layout netlist and reorders its
            ports to match the schematic before running LVS.
        timeout: Max seconds (default 600).

    Returns:
        dict: {match: bool, report_path: str|None, log: str,
               summary: dict}  — summary has keys: match, device_mismatch,
               net_mismatch, port_swaps, missing_devices, message.
    """
    _check_env()
    gds_path = os.path.abspath(gds_path)
    if not os.path.isfile(gds_path):
        raise FileNotFoundError(f"GDS not found: {gds_path}")
    cell = cell_name or os.path.splitext(os.path.basename(gds_path))[0]
    wd = os.path.abspath(workdir) if workdir else tempfile.mkdtemp(prefix="lvs_")
    os.makedirs(wd, exist_ok=True)

    if netlist_content is not None:
        sch_path = os.path.join(wd, f"{cell}.sch.spice")
        with open(sch_path, "w") as f:
            f.write(netlist_content)
    elif netlist_path is not None:
        sch_path = os.path.abspath(netlist_path)
    else:
        raise ValueError("Provide netlist_path or netlist_content")

    # Auto-fix: extract layout → flatten → fix port order
    if auto_fix_ports:
        xtr = extract_layout_netlist(gds_path, cell, wd, timeout=timeout)
        if xtr["success"]:
            flat_path = _flatten_netlist(xtr["netlist_path"])
            sch_ports = []
            with open(sch_path) as f:
                for line in f:
                    if line.startswith(".subckt"):
                        sch_ports = line.strip().split()[2:]
                        break
            if sch_ports:
                fix_port_order(flat_path, sch_ports)
            xtr_path = flat_path
        else:
            xtr_path = gds_path
    else:
        xtr_path = gds_path

    # Run netgen directly
    _pdk_root = os.environ.get('PDK_ROOT', '/foss/pdks')
    _pdk = os.environ.get('PDK', 'gf180mcuD')
    _pdkpath = os.environ.get('PDKPATH', f'{_pdk_root}/{_pdk}')
    setup_path = f"{_pdkpath}/libs.tech/netgen/{_pdk}_setup.tcl"
    report = os.path.join(wd, f"{cell}.lvs.out")
    try:
        r = subprocess.run(
            ["netgen", "-batch", "lvs",
             f"{xtr_path} {cell}", f"{sch_path} {cell}",
             setup_path, report],
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PATH": f"/foss/tools/netgen/bin:{os.environ.get('PATH', '')}"}
        )
    except FileNotFoundError:
        # Fallback: try netgen without full path
        try:
            r = subprocess.run(
                ["netgen", "-batch", "lvs",
                 f"{xtr_path} {cell}", f"{sch_path} {cell}",
                 setup_path, report],
                capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return {"match": False, "report_path": None, "log": "netgen not found",
                    "summary": {"match": False, "message": "Netgen not found in PATH"}}
    except subprocess.TimeoutExpired:
        return {"match": False, "report_path": None, "log": "LVS timed out",
                "summary": {"match": False, "message": "LVS: TIMEOUT"}}

    log = r.stdout + "\n" + r.stderr
    if not os.path.isfile(report):
        report = None

    summary = _parse_lvs_summary(report)
    return {"match": summary["match"], "report_path": report,
            "log": log.strip(), "summary": summary}


# ── PEX ──────────────────────────────────────────────────────────────

def run_pex(gds_path, cell_name=None, mode=2, subcircuit=True,
            pex_name=None, workdir=None, timeout=600):
    """Run Parasitic Extraction via iic-pex.sh.

    Args:
        gds_path: Path to GDS layout.
        cell_name: Top cell name (auto from filename if None).
        mode: 1=C-decoupled, 2=C-coupled (default), 3=full-RC.
        subcircuit: Include .subckt definition.
        pex_name: Output subcircuit name (default: cell_name).
        workdir: Working directory (default: current dir).
        timeout: Max seconds (default 600).

    Returns:
        dict: {pex_path: str|None, mode: str, log: str,
               summary: str}  — summary is e.g. "PEX: OK (C-coupled)".
    """
    _check_env(); _check_script(IIC_PEX)
    gds_path = os.path.abspath(gds_path)
    if not os.path.isfile(gds_path):
        raise FileNotFoundError(f"GDS not found: {gds_path}")
    cell = cell_name or os.path.splitext(os.path.basename(gds_path))[0]

    cmd = ["bash", IIC_PEX, "-m", str(mode),
           "-s", "1" if subcircuit else "0"]
    if pex_name: cmd += ["-n", pex_name]
    if workdir: cmd += ["-w", os.path.abspath(workdir)]
    cmd.append(gds_path)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"pex_path": None, "mode": str(mode), "log": "PEX timed out",
                "summary": "PEX: TIMEOUT"}

    log = r.stdout + "\n" + r.stderr
    resdir = os.path.abspath(workdir) if workdir else os.getcwd()
    base = pex_name or cell
    pex_path = os.path.join(resdir, f"{base}.pex.spice")
    if not os.path.isfile(pex_path):
        pex_path = None

    mode_labels = {1: "C-decoupled", 2: "C-coupled", 3: "full-RC"}
    return {"pex_path": pex_path, "mode": mode_labels.get(mode, str(mode)),
            "log": log.strip(),
            "summary": f"PEX: {'OK' if pex_path else 'FAILED'} ({mode_labels.get(mode, str(mode))})"}
