"""
@Owner: Ahmad Jabar Ilmi (Physical Verification & Automation Engineer)
@Role: Physical Verification Engineer
@Responsibility: Python wrapper for executing DRC, LVS, and PEX using Magic and netgen.
"""
import os
import subprocess
import shutil

SCRIPT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "scripts"))

IIC_DRC = os.path.join(SCRIPT_DIR, "iic-drc.sh")
IIC_LVS = os.path.join(SCRIPT_DIR, "iic-lvs.sh")
IIC_PEX = os.path.join(SCRIPT_DIR, "iic-pex.sh")


def _check_env():
    missing = []
    for var in ["PDK_ROOT", "PDK", "PDKPATH"]:
        if var not in os.environ:
            missing.append(var)
    if missing:
        raise EnvironmentError(
            f"Missing environment variables: {', '.join(missing)}. "
            "Set PDK_ROOT (e.g. /foss/pdks), PDK (e.g. gf180mcuD), "
            "and PDKPATH (e.g. $PDK_ROOT/$PDK)."
        )


def _check_script(path):
    if not os.path.isfile(path):
        raise FileNotFoundError(f"Script not found: {path}")


def _pdk_variant():
    pdk = os.environ.get("PDK", "")
    if "gf180" in pdk.lower():
        return "gf180"
    if "sky130" in pdk.lower():
        return "sky130"
    return pdk


def run_drc(
    gds_path,
    cell_name=None,
    engine="magic",
    workdir=None,
    clean=False,
    timeout=600,
):
    """Run DRC via iic-drc.sh.

    Args:
        gds_path: Path to GDS file.
        cell_name: Top cell name (auto from filename if None).
        engine: 'magic' (default), 'klayout', or 'both'.
        workdir: Working directory for results (default: cwd).
        clean: Remove previous result files before running.
        timeout: Timeout in seconds.

    Returns:
        dict with keys: clean (bool), report_path (str|None), log (str).
    """
    _check_env()
    _check_script(IIC_DRC)

    gds_path = os.path.abspath(gds_path)
    if not os.path.isfile(gds_path):
        raise FileNotFoundError(f"GDS not found: {gds_path}")

    if cell_name is None:
        cell_name = os.path.splitext(os.path.basename(gds_path))[0]

    cmd = ["bash", IIC_DRC]
    if engine == "klayout":
        cmd += ["-k"]
    elif engine == "both":
        cmd += ["-b"]
    else:
        cmd += ["-m"]

    if clean:
        cmd += ["-c"]

    if workdir:
        cmd += ["-w", os.path.abspath(workdir)]

    cmd.append(gds_path)

    env = os.environ.copy()

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        return {"clean": False, "report_path": None, "log": "DRC timed out"}

    log = result.stdout + "\n" + result.stderr

    resdir = os.path.abspath(workdir) if workdir else os.getcwd()
    report = os.path.join(resdir, f"{cell_name}.magic.drc.rpt")
    if not os.path.isfile(report):
        report = None

    is_clean = "No DRC errors" in log or "CONGRATULATIONS" in log

    return {"clean": is_clean, "report_path": report, "log": log.strip()}


def run_lvs(
    gds_path,
    netlist_path=None,
    netlist_content=None,
    cell_name=None,
    workdir=None,
    timeout=600,
):
    """Run LVS via iic-lvs.sh.

    Args:
        gds_path: Path to GDS layout.
        netlist_path: Path to SPICE netlist file (schematic).
        netlist_content: SPICE netlist as a string (saved to temp file
            if netlist_path is None). Takes priority over netlist_path.
        cell_name: Top cell name (auto from GDS filename if None).
        workdir: Working directory for results.
        timeout: Timeout in seconds.

    Returns:
        dict with keys: match (bool), report_path (str), log (str).
    """
    _check_env()
    _check_script(IIC_LVS)

    gds_path = os.path.abspath(gds_path)
    if not os.path.isfile(gds_path):
        raise FileNotFoundError(f"GDS not found: {gds_path}")

    if netlist_content is not None:
        wd = os.path.abspath(workdir) if workdir else os.path.dirname(gds_path)
        cell = cell_name or os.path.splitext(os.path.basename(gds_path))[0]
        netlist_path = os.path.join(wd, f"{cell}.spice")
        with open(netlist_path, "w") as f:
            f.write(netlist_content)
    elif netlist_path is not None:
        netlist_path = os.path.abspath(netlist_path)
    else:
        raise ValueError("Either netlist_path or netlist_content must be provided")

    if not os.path.isfile(netlist_path):
        raise FileNotFoundError(f"Netlist not found: {netlist_path}")

    if cell_name is None:
        cell_name = os.path.splitext(os.path.basename(gds_path))[0]

    cmd = ["bash", IIC_LVS]
    if workdir:
        cmd += ["-w", os.path.abspath(workdir)]
    cmd += ["-s", netlist_path, "-l", gds_path, "-c", cell_name]

    env = os.environ.copy()

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        return {"match": False, "report_path": None, "log": "LVS timed out"}

    log = result.stdout + "\n" + result.stderr

    resdir = os.path.abspath(workdir) if workdir else os.getcwd()
    report = os.path.join(resdir, f"{cell_name}.lvs.out")
    if not os.path.isfile(report):
        report = None

    match = "Circuits match uniquely" in log or "LVS is OK" in log

    return {"match": match, "report_path": report, "log": log.strip()}


def run_pex(
    gds_path,
    cell_name=None,
    mode=2,
    subcircuit=True,
    pex_name=None,
    workdir=None,
    timeout=600,
):
    """Run PEX via iic-pex.sh.

    Args:
        gds_path: Path to GDS layout.
        cell_name: Top cell name (auto from filename if None).
        mode: 1=C-decoupled, 2=C-coupled, 3=full-RC.
        subcircuit: Include .subckt definition in output.
        pex_name: Name of the PEX subcircuit (default: cell_name).
        workdir: Working directory for results.
        timeout: Timeout in seconds.

    Returns:
        dict with keys: pex_path (str), mode (str), log (str).
    """
    _check_env()
    _check_script(IIC_PEX)

    gds_path = os.path.abspath(gds_path)
    if not os.path.isfile(gds_path):
        raise FileNotFoundError(f"GDS not found: {gds_path}")

    if cell_name is None:
        cell_name = os.path.splitext(os.path.basename(gds_path))[0]

    cmd = ["bash", IIC_PEX]
    cmd += ["-m", str(mode)]
    cmd += ["-s", "1" if subcircuit else "0"]
    if pex_name:
        cmd += ["-n", pex_name]
    if workdir:
        cmd += ["-w", os.path.abspath(workdir)]
    cmd.append(gds_path)

    env = os.environ.copy()

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, env=env
        )
    except subprocess.TimeoutExpired:
        return {"pex_path": None, "mode": str(mode), "log": "PEX timed out"}

    log = result.stdout + "\n" + result.stderr

    resdir = os.path.abspath(workdir) if workdir else os.getcwd()
    basename = pex_name if pex_name else cell_name
    pex_path = os.path.join(resdir, f"{basename}.pex.spice")
    if not os.path.isfile(pex_path):
        pex_path = None

    mode_labels = {1: "C-decoupled", 2: "C-coupled", 3: "full-RC"}

    return {
        "pex_path": pex_path,
        "mode": mode_labels.get(mode, str(mode)),
        "log": log.strip(),
    }
