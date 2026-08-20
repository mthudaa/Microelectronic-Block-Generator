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

def _find_eda_scripts():
    """Locate the iic-*.sh verification scripts.

    The package lives at <repo>/src/mbg while the EDA shell scripts stay with
    the Chipathon design directory, so the path is discovered rather than
    assumed. Honours MBG_SCRIPTS_DIR for unusual layouts.
    """
    override = os.environ.get("MBG_SCRIPTS_DIR")
    if override and os.path.isfile(os.path.join(override, "iic-drc.sh")):
        return os.path.abspath(override)
    here = os.path.dirname(os.path.abspath(__file__))
    root = here
    for _ in range(6):                      # walk up looking for the repo root
        root = os.path.dirname(root)
        if os.path.isdir(os.path.join(root, ".git")):
            break
    for cand in (
        os.path.join(root, "designs", "notebooks", "chipathon2026-D", "scripts"),
        os.path.join(root, "scripts"),
        os.path.join(here, "..", "..", "scripts"),
    ):
        if os.path.isfile(os.path.join(cand, "iic-drc.sh")):
            return os.path.abspath(cand)
    return os.path.abspath(os.path.join(root, "designs", "notebooks",
                                        "chipathon2026-D", "scripts"))


SCRIPT_DIR = _find_eda_scripts()
IIC_DRC = os.path.join(SCRIPT_DIR, "iic-drc.sh")
IIC_LVS = os.path.join(SCRIPT_DIR, "iic-lvs.sh")
IIC_PEX = os.path.join(SCRIPT_DIR, "iic-pex.sh")

__all__ = [
    "check_tools", "validate_gds",
    "extract_layout_netlist", "fix_port_order",
    "permute_mosfet_sd",
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


# ── MOSFET Drain-Source permute ───────────────────────────────────────

_MOSFET_MODELS = {"nfet_03v3", "pfet_03v3", "nfet_06v0", "pfet_06v0"}


def _swap_ad_as_pd_ps(rest):
    """Swap ad↔as and pd↔ps in a parameter string (used on X-lines)."""
    rest = re.sub(r'\b(ad)=(\S+)', r'_AD_=\2', rest, flags=re.IGNORECASE)
    rest = re.sub(r'\b(as)=(\S+)', r'ad=\2', rest, flags=re.IGNORECASE)
    rest = re.sub(r'_AD_=', 'as=', rest)
    rest = re.sub(r'\b(pd)=(\S+)', r'_PD_=\2', rest, flags=re.IGNORECASE)
    rest = re.sub(r'\b(ps)=(\S+)', r'pd=\2', rest, flags=re.IGNORECASE)
    rest = re.sub(r'_PD_=', 'ps=', rest)
    return rest


def permute_mosfet_sd(spice_content, models=None, swap_params=True):
    """Align drain↔source across multi-finger MOSFET instances.

    For **nf > 1** Magic extraction produces multiple X-instances per
    device with *alternating* D/S (interdigitated fingers).  Permuting
    **all** of them would just swap both and leave them mismatched.

    This function groups instances by device (model + gate + body) and
    permutes *every other* instance within each group so that all
    instances of the same device share the same D/S orientation.

    For **nf = 1** (single instances) no permutation is applied — the
    netgen ``permute 1 3`` rule already handles single-finger D/S
    swapping during LVS.

    Handles both **X-instances** (extracted) and **M-instances**
    (schematic).  For X-instances the ``ad``↔``as`` and ``pd``↔``ps``
    parameters are also swapped on permuted lines.

    Example (nf=2, before → after)::

        X0 a_n676_4419# VBN vss vss nfet_03v3 ad=1.4p … as=3p …
        X1 vss VBN a_n676_4419# vss nfet_03v3 ad=3p … as=1.4p …

        X0 a_n676_4419# VBN vss vss nfet_03v3 ad=1.4p … as=3p …   ← kept
        X1 a_n676_4419# VBN vss vss nfet_03v3 as=1.4p … ad=3p …   ← permuted

    Usage::

        fixed = permute_mosfet_sd(extracted_spice)
        # or only NMOS:
        fixed = permute_mosfet_sd(spice, models=["nfet_03v3"])

    Args:
        spice_content: SPICE netlist as a string.
        models: Model names to align.  Defaults to all recognised
            MOSFET models (nfet_03v3, pfet_03v3, nfet_06v0, pfet_06v0).
        swap_params: If True, also swap ad↔as and pd↔ps on X-lines.

    Returns:
        str: Netlist with D/S aligned across finger instances.
    """
    target = set(models) if models else _MOSFET_MODELS
    alt = "|".join(re.escape(m) for m in sorted(target, key=len, reverse=True))
    if not alt:
        return spice_content

    # Pattern for both X… and M… MOSFET lines:
    #   X0  d g s b  nfet_03v3  ad=… as=… …
    #   MM1 d g s b  pfet_03v3  W=… L=… …
    mos_re = re.compile(
        r'^([XM]\S+)\s+'          # device name  (group 1)
        r'(\S+)\s+'               # drain node   (group 2)
        r'(\S+)\s+'               # gate node    (group 3)
        r'(\S+)\s+'               # source node  (group 4)
        r'(\S+)\s+'               # body node    (group 5)
        r'(' + alt + r')\b'       # model name   (group 6)
        r'(.*)$',                  # rest of line (group 7)
        re.IGNORECASE,
    )

    lines = spice_content.split('\n')

    # ── First pass: group instances by device ──
    #  key = (model, gate, body)  →  list of line indices
    from collections import defaultdict
    groups = defaultdict(list)
    parsed = {}   # line_index → (dev, drain, gate, source, body, model, rest)

    for i, line in enumerate(lines):
        m = mos_re.match(line.strip())
        if not m:
            continue
        dev, drain, gate, source, body, model, rest = m.groups()
        key = (model.upper(), gate.upper(), body.upper())
        groups[key].append(i)
        parsed[i] = (dev, drain, gate, source, body, model, rest)

    # ── Mark every-other instance within each group for permute ──
    permute_set = set()
    for indices in groups.values():
        indices.sort()
        # Permute instances at positions 1, 3, 5… (0-based) within the group
        for j in range(1, len(indices), 2):
            permute_set.add(indices[j])

    # ── Second pass: rebuild, permuting only marked lines ──
    out = []
    for i, line in enumerate(lines):
        if i not in permute_set or i not in parsed:
            out.append(line)
            continue

        dev, drain, gate, source, body, model, rest = parsed[i]
        # Swap drain ↔ source
        new_line = f"{dev} {source} {gate} {drain} {body} {model}"

        if swap_params and dev.upper().startswith('X'):
            rest = _swap_ad_as_pd_ps(rest)

        new_line += " " + rest.lstrip()
        out.append(new_line)

    return '\n'.join(out)


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

    # iic-drc.sh names the report after the GDS FILE, which is not always the
    # cell name.  Looking only for "<cell>.magic.drc.rpt" silently found no
    # report and then reported 0 errors regardless of what Magic said.
    gds_stem = os.path.splitext(os.path.basename(gds_path))[0]
    report = None
    for stem in (gds_stem, cell):
        cand = os.path.join(resdir, f"{stem}.magic.drc.rpt")
        if os.path.isfile(cand):
            report = cand
            break

    # The report ends with "[INFO] COUNT: <n>" — the number of error tiles.
    # Counting non-blank lines (the old behaviour) counted Magic's banner too.
    errors = None
    rules_hit = []
    if report:
        try:
            with open(report) as f:
                for line in f:
                    m = re.search(r"COUNT:\s*(\d+)", line)
                    if m:
                        errors = int(m.group(1))
                    elif (line.strip() and not line.startswith(" ")
                          and not line.startswith("-") and "COUNT" not in line
                          and "[INFO]" not in line and line.strip() != cell
                          and line.strip() != gds_stem):
                        rules_hit.append(line.strip())
        except Exception:
            pass

    if errors is None:
        is_clean = "No DRC errors" in log or "CONGRATULATIONS" in log
        errors = 0 if is_clean else -1
        summary = "DRC: CLEAN" if is_clean else "DRC: NO REPORT PARSED"
    else:
        is_clean = errors == 0
        summary = "DRC: CLEAN" if is_clean else f"DRC: {errors} ERROR TILES"

    return {
        "clean": is_clean,
        "report_path": report,
        "error_count": errors,
        "rules_violated": rules_hit,
        "log": log.strip(),
        "summary": summary,
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
    # "Circuits match uniquely" alone is NOT a pass: netgen prints it even
    # when it also reports property errors (e.g. a device built at twice the
    # netlist width) or when top-level pin matching failed.  Reporting those
    # as "LVS OK" is exactly the false pass this flow must not produce.
    topology_ok = "Circuits match uniquely" in text
    property_errors = "Property errors were found" in text
    pin_failure = "failed pin matching" in text
    match = topology_ok and not property_errors and not pin_failure
    dev_m, net_m = "?", "?"
    for line in text.split("\n"):
        m = re.match(r"Number of devices:\s+(\d+)\s+\|\s+Number of devices:\s+(\d+)", line)
        if m: dev_m = f"{m.group(1)}vs{m.group(2)}"
        m = re.match(r"Number of nets:\s+(\d+)\s+\|\s+Number of nets:\s+(\d+)", line)
        if m: net_m = f"{m.group(1)}vs{m.group(2)}"
    swaps = re.findall(r"(\w+)\s+\|\s+(\w+)\s+\*\*Mismatch", text)
    missing = re.findall(r"no matching.*?Instance:\s+(\S+)", text)
    if match:
        message = "LVS OK"
    elif pin_failure:
        message = "LVS FAIL: top-level pin matching failed"
    elif property_errors and topology_ok:
        message = "LVS FAIL: topology matches but device properties differ"
    else:
        message = "LVS MISMATCH"

    props = re.findall(r"^\s*(\w+) circuit1:\s*(\S+)\s+circuit2:\s*(\S+)",
                       text, re.MULTILINE)
    return {
        "match": match,
        "topology_match": topology_ok,
        "property_errors": property_errors,
        "pin_matching_failed": pin_failure,
        "property_mismatches": [{"param": a, "layout": b, "schematic": c}
                                for a, b, c in props[:20]],
        "device_mismatch": dev_m,
        "net_mismatch": net_m,
        "port_swaps": [(a, b) for a, b in swaps],
        "missing_devices": missing,
        "message": message,
    }


def _flatten_netlist(extracted_path, out_path=None):
    """Pass-through: extracted netlist with port-order fix only.

    Magic's ``ext2spice lvs`` produces X-instances (e.g.
    ``X0 d g s b nfet_03v3 ...``) which netgen compares directly against
    the schematic's M-elements using the PDK setup file for pin mapping.
    """
    out = out_path or extracted_path.replace(".spice", "_flat.spice")
    import shutil
    shutil.copy2(extracted_path, out)
    return out


def _match_extracted_to_schematic(xtr_lines, xtr_ports, sch_lines, sch_ports):
    """Match extracted X-instances to schematic M-instances by topology.

    Returns:
        (merged_map, xtr_node_to_sch_net): 
            merged_map: dict mapping internal node → set of merged schematic net names
            xtr_node_to_sch_net: dict mapping internal node → single merged net name
    """
    xtr_devs = []
    sch_devs = []

    for line in xtr_lines:
        m = re.match(r'X(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(pfet_03v3|nfet_03v3)\s', line)
        if m:
            idx, d, g, s, b, model = m.groups()
            wm = re.search(r'\bw=(\S+)', line, re.IGNORECASE)
            w = wm.group(1) if wm else "?"
            xtr_devs.append((int(idx), model, d, g, s, b, w))

    for line in sch_lines:
        m = re.match(r'XM(\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(pfet_03v3|nfet_03v3)\s', line)
        if m:
            idx, d, g, s, b, model = m.groups()
            wm = re.search(r'W=(\S+)', line)
            w = wm.group(1) if wm else "?"
            sch_devs.append((int(idx), model, d, g, s, b, w))

    node_to_sch_net = {}
    used_sch = set()

    for xd in xtr_devs:
        xi, xm, xdrain, xgate, xsrc, xbody, xw = xd
        best_match = None
        best_score = -1
        for sd in sch_devs:
            si, sm, sdrain, sgate, ssrc, sbody, sw = sd
            if si in used_sch:
                continue
            score = 0
            if xm == sm:
                score += 10
            if sdrain in sch_ports:
                if xdrain == sdrain:
                    score += 8
                elif xdrain not in xtr_ports:
                    score -= 5
            if sgate in sch_ports:
                if xgate == sgate:
                    score += 8
                elif xgate not in xtr_ports:
                    score -= 5
            if xw != "?" and sw != "?" and xw.upper() == sw.upper():
                score += 5
            if xsrc.upper() in ("VDD", "VSS") and ssrc.upper() in ("VDD", "VSS"):
                score += 2
            if xbody.upper() in ("VDD", "VSS") and sbody.upper() in ("VDD", "VSS"):
                score += 2
            if score > best_score:
                best_score = score
                best_match = sd
        if best_match:
            si, sm, sdrain, sgate, ssrc, sbody, sw = best_match
            used_sch.add(si)
            pins_xtr = [xdrain, xgate, xsrc, xbody]
            pins_sch = [sdrain, sgate, ssrc, sbody]
            for pxtr, psch in zip(pins_xtr, pins_sch):
                if pxtr not in xtr_ports:
                    if pxtr not in node_to_sch_net:
                        node_to_sch_net[pxtr] = set()
                    node_to_sch_net[pxtr].add(psch)
                elif psch not in sch_ports:
                    # Port pin reused for internal connection — track it
                    if pxtr not in node_to_sch_net:
                        node_to_sch_net[pxtr] = set()
                    node_to_sch_net[pxtr].add(psch)

    merged_map = {}
    for node, nets in node_to_sch_net.items():
        if len(nets) > 1:
            merged_map[node] = nets
    return merged_map, node_to_sch_net


def _merge_schematic_nets(sch_content, merge_map):
    """Rewrite schematic netlist merging nets listed in merge_map.

    merge_map: dict mapping internal_node → set of schematic nets to merge.
    The function picks a canonical name for each merged set and rewrites
    all device lines to use it.
    """
    lines = sch_content.split('\n')
    port_nets = set()
    for line in lines:
        if line.startswith('.subckt '):
            port_nets.update(line.split()[2:])
            break

    all_nets_to_merge = set()
    for nets in merge_map.values():
        all_nets_to_merge.update(nets)

    if not all_nets_to_merge:
        return sch_content

    chosen = {}
    for nets in merge_map.values():
        if nets & port_nets:
            target = min(nets & port_nets)
        else:
            target = min(nets)
        for n in nets:
            chosen[n] = target

    out_lines = []
    for line in lines:
        if line.startswith('.subckt '):
            parts = line.split()
            ports = parts[2:]
            new_ports = []
            for p in ports:
                p2 = chosen.get(p, p)
                if p2 not in new_ports:
                    new_ports.append(p2)
            out_lines.append(' '.join([parts[0], parts[1]] + new_ports))
        elif line.startswith('+') or line.startswith('.lib') or line.startswith('.ends'):
            out_lines.append(line)
        else:
            tokens = line.split()
            new_tokens = [chosen.get(t, t) for t in tokens]
            out_lines.append(' '.join(new_tokens))
    return '\n'.join(out_lines)


def run_lvs(gds_path, netlist_path=None, netlist_content=None,
            cell_name=None, workdir=None, auto_fix_ports=True,
            auto_permute_sd=False, timeout=600):
    """Run Layout vs Schematic via netgen with auto port-order fix + flatten.

    Detects and adapts to net merges caused by the auto-router (e.g.,
    net1↔net2 shorts) by merging corresponding nets in the schematic
    before comparison.

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
        auto_permute_sd: If True and the first LVS attempt mismatches,
            also tries a drain↔source-permuted version of the extracted
            netlist and returns the better result.
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

    with open(sch_path) as f:
        sch_text = f.read()
    with open(sch_path, "w") as f:
        f.write(sch_text)

    sch_ports = []
    for line in sch_text.split('\n'):
        if line.startswith('.subckt'):
            sch_ports = line.strip().split()[2:]
            break

    # Extract layout
    xtr = extract_layout_netlist(gds_path, cell, wd, timeout=timeout)
    if xtr["success"]:
        with open(xtr["netlist_path"]) as f:
            xtr_text = f.read()
        xtr_lines = [l for l in xtr_text.split('\n') if l.strip() and not l.startswith('*')]
        xtr_ports = set()
        for l in xtr_lines:
            if l.startswith('.subckt'):
                xtr_ports = set(l.split()[2:])
                break

        # NOTE: auto net-merge is DISABLED — it corrupts the schematic
        # by incorrectly merging internal nets (e.g. n1→VDD, VIN_N→VDD).
        # Netgen's permute 1 3 handles D/S swapping natively.
        # merge_map, _ = _match_extracted_to_schematic(
        #     xtr_lines, xtr_ports, sch_text.split('\n'), sch_ports)
        # if merge_map:
        #     modified = _merge_schematic_nets(sch_text, merge_map)
        #     with open(sch_path, "w") as f:
        #         f.write(modified)
        #     with open(sch_path) as f:
        #         for line in f:
        #             if line.startswith('.subckt'):
        #                 sch_ports = line.strip().split()[2:]
        #                 break

        flat_path = _flatten_netlist(xtr["netlist_path"])
        if sch_ports:
            fix_port_order(flat_path, sch_ports)
        xtr_path = flat_path
    else:
        xtr_path = gds_path

    # ── Prepare netgen TCL setup ──
    _pdk_root = os.environ.get('PDK_ROOT', '/foss/pdks')
    _pdk = os.environ.get('PDK', 'gf180mcuD')
    _pdkpath = os.environ.get('PDKPATH', f'{_pdk_root}/{_pdk}')
    setup_path = os.path.join(_pdkpath, 'libs.tech', 'netgen', f'{_pdk}_setup.tcl')
    # Resolve symlinks (volare uses relative symlinks that may break)
    if not os.path.isfile(setup_path):
        setup_path = os.path.realpath(setup_path)
    if not os.path.isfile(setup_path):
        # Fallback: search under PDK_ROOT
        import glob as _glob
        candidates = _glob.glob(
            f'{_pdk_root}/**/{_pdk}/libs.tech/netgen/{_pdk}_setup.tcl',
            recursive=True)
        if candidates:
            setup_path = candidates[0]
    if not os.path.isfile(setup_path):
        raise FileNotFoundError(
            f"PDK netgen setup not found: {setup_path}. "
            f"Check PDK_ROOT={_pdk_root}, PDK={_pdk}, PDKPATH={_pdkpath}")
    # Custom setup: no permute default (prevents top-cell port reordering),
    # but add unconditional drain-source permute for MOSFETs
    custom_setup = os.path.join(wd, "lvs_custom_setup.tcl")
    with open(setup_path) as f:
        setup_text = f.read()
    setup_text = setup_text.replace("permute default\n", "")
    setup_text += (
        '\n# Unconditional drain-source permute for MOSFETs\n'
        'permute "-circuit1 pfet_03v3" 1 3\n'
        'permute "-circuit2 pfet_03v3" 1 3\n'
        'permute "-circuit1 nfet_03v3" 1 3\n'
        'permute "-circuit2 nfet_03v3" 1 3\n'
    )
    with open(custom_setup, "w") as f:
        f.write(setup_text)

    # ── Helper: invoke netgen once ──
    def _invoke_netgen(xtr_file, report_file):
        """Run netgen LVS.  Returns (subprocess_run, report_path_or_None)."""
        try:
            r = subprocess.run(
                ["netgen", "-batch", "lvs",
                 f"{xtr_file} {cell}", f"{sch_path} {cell}",
                 custom_setup, report_file],
                capture_output=True, text=True, timeout=timeout,
                env={**os.environ, "PATH": f"/foss/tools/netgen/bin:{os.environ.get('PATH', '')}"}
            )
            return r, (report_file if os.path.isfile(report_file) else None)
        except FileNotFoundError:
            try:
                r = subprocess.run(
                    ["netgen", "-batch", "lvs",
                     f"{xtr_file} {cell}", f"{sch_path} {cell}",
                     custom_setup, report_file],
                    capture_output=True, text=True, timeout=timeout)
                return r, (report_file if os.path.isfile(report_file) else None)
            except FileNotFoundError:
                return None, None
        except subprocess.TimeoutExpired:
            return None, None

    # ── First attempt: original extracted netlist ──
    report = os.path.join(wd, f"{cell}.lvs.out")
    r, report_path = _invoke_netgen(xtr_path, report)

    if r is None:
        return {"match": False, "report_path": None,
                "log": "netgen not found or LVS timed out",
                "summary": {"match": False, "message": "Netgen not found or LVS timed out"}}

    log = r.stdout + "\n" + r.stderr
    summary = _parse_lvs_summary(report_path)

    # ── Fallback: permute D/S and retry ──
    if not summary["match"] and auto_permute_sd and xtr.get("success"):
        print("  [LVS] mismatch — retrying with permuted D/S…")
        try:
            perm_path = os.path.join(wd, f"{cell}_permuted_flat.spice")
            with open(xtr_path) as f:
                perm_content = permute_mosfet_sd(f.read())
            with open(perm_path, "w") as f:
                f.write(perm_content)
            report2 = os.path.join(wd, f"{cell}.lvs_permuted.out")
            r2, report_path2 = _invoke_netgen(perm_path, report2)
            if r2 is not None:
                log2 = r2.stdout + "\n" + r2.stderr
                summary2 = _parse_lvs_summary(report_path2)
                if summary2["match"]:
                    print("  [LVS] permuted D/S → MATCH ✓")
                    report_path = report_path2
                    log = log2
                    summary = summary2
                else:
                    print("  [LVS] permuted D/S still MISMATCH — issue is NOT D/S ordering")
                    log += "\n\n--- permuted retry ---\n" + log2
            else:
                print("  [LVS] permuted retry failed (netgen error)")
        except Exception as e:
            print(f"  [LVS] permute fallback error: {e}")

    return {"match": summary["match"], "report_path": report_path,
            "log": log.strip(), "summary": summary}


# ── PEX ──────────────────────────────────────────────────────────────

def run_pex(gds_path, cell_name=None, mode=2, subcircuit=True,
            pex_name=None, workdir=None, permute_sd=False, timeout=600):
    """Run Parasitic Extraction via iic-pex.sh.

    Args:
        gds_path: Path to GDS layout.
        cell_name: Top cell name (auto from filename if None).
        mode: 1=C-decoupled, 2=C-coupled (default), 3=full-RC.
        subcircuit: Include .subckt definition.
        pex_name: Output subcircuit name (default: cell_name).
        workdir: Working directory (default: current dir).
        permute_sd: If True, apply drain↔source permutation to the
            output PEX netlist so that D/S assignment matches the
            schematic (safe for symmetric MOSFETs).
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

    resdir = os.path.abspath(workdir) if workdir else os.getcwd()
    os.makedirs(resdir, exist_ok=True)

    # iic-pex.sh derives cell name from filename, so copy GDS to match cell name
    gds_for_pex = os.path.join(resdir, f"{cell}.gds")
    if os.path.abspath(gds_path) != os.path.abspath(gds_for_pex):
        import shutil
        shutil.copy2(gds_path, gds_for_pex)

    cmd = ["bash", IIC_PEX, "-m", str(mode),
           "-s", "1" if subcircuit else "0"]
    if pex_name: cmd += ["-n", pex_name]
    if workdir: cmd += ["-w", resdir]
    cmd.append(gds_for_pex)

    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"pex_path": None, "mode": str(mode), "log": "PEX timed out",
                "summary": "PEX: TIMEOUT"}

    log = r.stdout + "\n" + r.stderr
    base = pex_name or cell
    pex_path = os.path.join(resdir, f"{base}.pex.spice")
    if not os.path.isfile(pex_path):
        pex_path = None

    # ── Post-process: permute D/S if requested ──
    if pex_path and permute_sd:
        try:
            with open(pex_path) as f:
                original = f.read()
            permuted = permute_mosfet_sd(original)
            with open(pex_path, "w") as f:
                f.write(permuted)
        except Exception:
            pass  # keep original on any error

    mode_labels = {1: "C-decoupled", 2: "C-coupled", 3: "full-RC"}
    return {"pex_path": pex_path, "mode": mode_labels.get(mode, str(mode)),
            "log": log.strip(),
            "summary": f"PEX: {'OK' if pex_path else 'FAILED'} ({mode_labels.get(mode, str(mode))})"}
