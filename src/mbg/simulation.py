"""
@Owner: Huda
@Role: ngspice command wrapper — run, parse, convert.
Free-form: AI agent provides any SPICE netlist, we run it and return results.
"""

import os, re, subprocess, tempfile, shutil, csv, struct
import numpy as np

# ── PDK path resolution ──────────────────────────────────
def pdk_path(subpath=""):
    pdk = os.environ.get("PDK", "gf180mcuD")
    for base in [
        os.environ.get("PDKPATH"),
        os.path.join(os.environ.get("PDK_ROOT", "/foss/pdks"), pdk),
        os.path.join(os.path.expanduser("~/.volare"), pdk),
        "/foss/pdks/gf180mcuD",
    ]:
        if base is None: continue
        p = os.path.join(base, subpath)
        if os.path.exists(p):
            return p
    return os.path.join("/foss/pdks", pdk, subpath)


# ── Run ngspice ──────────────────────────────────────────
def run_spice(netlist_content, *, workdir=None, timeout=300, fmt="raw"):
    """Run any ngspice netlist.

    Args:
        netlist_content: Full SPICE netlist as string.
        workdir: If None, uses temp dir (auto-cleaned).
        timeout: Max seconds.
        fmt: 'raw' for binary, 'dat' for wrdata text, or 'both'.

    Returns:
        {"stdout": str, "stderr": str, "returncode": int,
         "raw_path": str|None, "dat_paths": [str],
         "workdir": str}
    """
    wd = os.path.abspath(workdir) if workdir else tempfile.mkdtemp(prefix="ngspice_")
    os.makedirs(wd, exist_ok=True)
    # Absolute: the subprocess runs with cwd=wd, so a relative path here made
    # ngspice look for <wd>/<wd>/input.spice and fail with "No such file".
    inp = os.path.join(wd, "input.spice")
    with open(inp, "w") as f:
        f.write(netlist_content)

    try:
        r = subprocess.run(["ngspice", "-b", inp], capture_output=True, text=True,
                           timeout=timeout, cwd=wd)
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] ngspice timed out after {timeout}s — workdir kept: {wd}")
        return {"stdout": "", "stderr": "", "returncode": -1,
                "raw_path": None, "dat_paths": [], "workdir": wd}

    # Find output files
    raw_path = None
    dat_paths = []
    for f in os.listdir(wd):
        if f.endswith(".raw"):
            raw_path = os.path.join(wd, f)
        elif f.endswith(".dat"):
            dat_paths.append(os.path.join(wd, f))

    if r.returncode != 0:
        print(f"[WARN] ngspice returned {r.returncode} — workdir kept: {wd}")

    return {
        "stdout": r.stdout,
        "stderr": r.stderr,
        "returncode": r.returncode,
        "raw_path": raw_path,
        "dat_paths": dat_paths,
        "workdir": wd,
    }


# ── Raw file to CSV ──────────────────────────────────────
def raw_to_csv(raw_path, csv_path=None, max_rows=None):
    """Convert ngspice binary raw file to CSV.

    Returns list of dicts, and writes csv_path if given.
    Returns empty list on parse failure.
    """
    try:
        with open(raw_path, "rb") as f:
            blob = f.read()
    except Exception as e:
        print(f"[ERROR] Cannot read raw file: {e}")
        return []

    # Split header from binary
    bin_marker = b"Binary:\n"
    bin_idx = blob.find(bin_marker)
    if bin_idx < 0:
        print(f"[ERROR] Raw file has no Binary: marker — text-mode output?")
        return []
    header = blob[:bin_idx].decode("utf-8", errors="replace")
    bin_start = bin_idx + len(bin_marker)

    # Parse header fields
    n_vars_m = re.search(r"No\. Variables:\s*(\d+)", header)
    n_pts_m = re.search(r"No\. Points:\s*(\d+)", header)
    if not n_vars_m or not n_pts_m:
        print(f"[ERROR] Raw header missing Variables/Points: {header[:200]}")
        return []
    n_vars = int(n_vars_m.group(1))
    n_pts = int(n_pts_m.group(1))

    # Parse variable names and types
    var_names, var_types = [], []
    in_vars = False
    for line in header.split("\n"):
        if line.startswith("Variables:"):
            in_vars = True; continue
        if in_vars and line.strip() and "\t" in line:
            parts = line.strip().split("\t")
            var_names.append(parts[1].strip())
            var_types.append(parts[2].strip() if len(parts) > 2 else "")

    if len(var_names) != n_vars:
        print(f"[WARN] Parsed {len(var_names)} vars, header says {n_vars}")

    try:
        is_complex = any("grid" in t or t in ("notype", "complex") for t in var_types)
        if is_complex:
            vals = struct.unpack_from(f"<{n_vars * 2 * n_pts}d", blob, bin_start)
            arr = np.array(vals).reshape((n_pts, n_vars, 2))
            data = {vn: arr[:, i, 0] for i, vn in enumerate(var_names)}
            for i, vn in enumerate(var_names):
                data[f"{vn}_mag"] = np.sqrt(arr[:, i, 0]**2 + arr[:, i, 1]**2)
                data[f"{vn}_db"] = 20 * np.log10(np.abs(data[f"{vn}_mag"]) + 1e-30)
        else:
            vals = struct.unpack_from(f"<{n_vars * n_pts}d", blob, bin_start)
            arr = np.array(vals).reshape((n_pts, n_vars))
            data = {vn: arr[:, i] for i, vn in enumerate(var_names)}
    except (struct.error, ValueError) as e:
        print(f"[ERROR] Binary data parse failed: {e}")
        return []

    # Build row list
    rows = []
    n_out = min(n_pts, max_rows) if max_rows else n_pts
    keys = sorted(data.keys())
    for i in range(n_out):
        row = {k: float(data[k][i]) for k in keys}
        rows.append(row)

    # Write CSV
    if csv_path:
        os.makedirs(os.path.dirname(csv_path) or ".", exist_ok=True)
        with open(csv_path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=keys)
            w.writeheader()
            w.writerows(rows)

    return rows


# ── Quick .dat (wrdata) parser ───────────────────────────
def parse_dat(dat_path):
    """Parse ngspice wrdata text file into list of dicts."""
    rows = []
    with open(dat_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("*") or line.startswith("@"):
                continue
            parts = line.split()
            if len(parts) >= 2:
                try:
                    row = {"index": int(parts[0])} if parts[0].isdigit() else {}
                    row["freq(Hz)"] = float(parts[0])
                    for j, p in enumerate(parts[1:], 1):
                        row[f"col{j}"] = float(p)
                    rows.append(row)
                except ValueError:
                    pass
    return rows



