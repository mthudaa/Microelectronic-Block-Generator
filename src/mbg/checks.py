"""
IC Physical Verification — DRC, LVS, PEX for AI agent tooling.

AI agent usage pattern:
    drc = run_drc("out.gds")
    if drc["clean"]:
        lvs = run_lvs("out.gds", netlist_content=netlist)
        pex = run_pex("out.gds")

Returns structured dicts — no log-parsing required.
"""

import os, subprocess, shutil, re, tempfile, textwrap, signal, time

from mbg import config as _config
from mbg.config import ToolError

# ── stage results ─────────────────────────────────────────────────────
# Verification is a dependency chain, not a set of independent checks:
#
#     GDS -> DRC
#     GDS -> extraction -> extracted SPICE -> validate -> LVS -> PEX
#
# Every stage reports one of these states. SKIP is the important one: when
# extraction fails, LVS must not run at all. The previous code fell back to
# handing the raw .gds to netgen as though it were a netlist, which is not a
# wrong answer so much as an unbounded wait for one.
PASS, FAIL, SKIP, ERROR, TIMEOUT = "PASS", "FAIL", "SKIP", "ERROR", "TIMEOUT"

_ERROR_HINTS = (
    "is required by this techfile", "couldn't be read", "cifinput",
    "nothing here to extract", "no such file", "can't read", "error",
    "cannot open", "not found", "abort",
)


def _stage(stage, status, **kw):
    d = {"stage": stage, "status": status, "tool": kw.pop("tool", ""),
         "log": kw.pop("log", ""), "output": kw.pop("output", "")}
    d.update(kw)
    return d


def _relevant_lines(text, limit=6):
    """The lines a human actually needs out of several hundred of tool output."""
    hits = [l.strip() for l in (text or "").splitlines()
            if l.strip() and any(h in l.lower() for h in _ERROR_HINTS)]
    seen, out = set(), []
    for l in hits:
        if l not in seen:
            seen.add(l)
            out.append(l)
        if len(out) >= limit:
            break
    if not out:
        tail = [l.strip() for l in (text or "").splitlines() if l.strip()]
        out = tail[-limit:]
    return out


def run_tool(tool, argv, *, stage, workdir, timeout=None, stdin_text=None,
             env=None):
    """Run one external EDA command with a bounded timeout and full logging.

    Returns a stage dict. stdout and stderr are always written to
    ``<workdir>/logs/<stage>.log`` — never discarded, because the failure that
    matters ("Magic version ... is required by this techfile") only ever
    appears there. The console gets a summary; the log keeps everything.

    On timeout the whole process group is killed, so a hung netgen cannot
    outlive the call and stall the rest of the regression.
    """
    timeout = timeout or _config.tool_timeout(tool)
    logs = _config.log_dir(workdir)
    log_path = str(logs / f"{stage}.log")
    started = time.time()

    try:
        proc = subprocess.Popen(
            list(argv), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            stdin=subprocess.PIPE if stdin_text is not None else None,
            text=True, cwd=workdir, env=env or os.environ.copy(),
            start_new_session=True)
    except (OSError, ValueError) as e:
        with open(log_path, "w") as f:
            f.write(f"failed to launch {argv[0]}: {e}\n")
        return _stage(stage, ERROR, tool=tool, log=log_path,
                      message=f"could not launch {tool}: {e}")

    timed_out = False
    try:
        out, err = proc.communicate(input=stdin_text, timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            proc.wait(timeout=10)
        except Exception:
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except Exception:
                pass
        out, err = proc.communicate()

    elapsed = time.time() - started
    with open(log_path, "w") as f:
        f.write(f"$ {' '.join(argv)}\n")
        f.write(f"cwd: {workdir}\n")
        f.write(f"timeout: {timeout}s   elapsed: {elapsed:.1f}s\n")
        f.write(f"exit: {'TIMEOUT' if timed_out else proc.returncode}\n")
        f.write("\n--- stdout ---\n" + (out or ""))
        f.write("\n--- stderr ---\n" + (err or ""))

    blob = (out or "") + "\n" + (err or "")
    if timed_out:
        return _stage(stage, TIMEOUT, tool=tool, log=log_path, output=blob,
                      timeout=timeout, elapsed=elapsed, command=" ".join(argv),
                      message=(f"{tool} exceeded {timeout}s during {stage} and "
                               f"was terminated. Raise MBG_{tool.upper()}_TIMEOUT "
                               f"if the design is genuinely this large."),
                      relevant=_relevant_lines(blob))
    rc = proc.returncode
    sig = -rc if rc is not None and rc < 0 else None
    return _stage(stage, PASS if rc == 0 else FAIL, tool=tool, log=log_path,
                  output=blob, returncode=rc, signal=sig, elapsed=elapsed,
                  command=" ".join(argv), relevant=_relevant_lines(blob))


def validate_spice_netlist(path, *, require_subckt=True):
    """Confirm a file really is a SPICE netlist before netgen sees it.

    Guards the specific accident this project hit: passing a ``.gds`` to
    netgen as if it were an extracted netlist. netgen does not reject it — it
    sits there, and the regression stops at the first circuit.
    """
    if not path:
        return False, "no netlist path was produced"
    if not os.path.isfile(path):
        return False, f"file does not exist: {path}"
    if os.path.getsize(path) == 0:
        return False, f"file is empty: {path}"
    if os.path.splitext(path)[1].lower() in (".gds", ".gds2", ".gdsii",
                                             ".svg", ".png", ".oas"):
        return False, (f"{os.path.basename(path)} is layout/binary data, not a "
                       f"SPICE netlist — refusing to hand it to netgen")
    try:
        with open(path, "rb") as f:
            head = f.read(8192)
    except OSError as e:
        return False, f"cannot read {path}: {e}"
    if b"\x00" in head:
        return False, f"{os.path.basename(path)} is binary, not a SPICE netlist"
    try:
        text = head.decode("utf-8", errors="replace").lower()
    except Exception:
        return False, f"{os.path.basename(path)} is not decodable text"
    if require_subckt and ".subckt" not in text:
        return False, (f"{os.path.basename(path)} contains no .subckt "
                       f"definition — extraction produced nothing usable")
    return True, ""



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

    cfg = _config.pdk_config()
    try:
        magic = _config.magic_bin()
    except ToolError as e:
        return {"netlist_path": None, "raw_ports": [], "log": str(e),
                "success": False, "status": ERROR, "stage": "extraction",
                "message": str(e)}

    st = run_tool("magic",
                  [magic, "-dnull", "-noconsole", "-rcfile",
                   str(cfg.magicrc), ext_script],
                  stage="magic_extract", workdir=wd,
                  timeout=timeout or _config.tool_timeout("magic"))
    log = st.get("output", "").strip()

    # A file on disk is not a successful extraction. Magic writes a netlist
    # even when it never managed to read the cell — the result is a .subckt
    # with no devices, which LVS then "compares" against the real schematic.
    ok, why = validate_spice_netlist(out_path)
    if st["status"] in (TIMEOUT, ERROR):
        ok, why = False, st.get("message", st["status"])
    if ok and not _netlist_has_devices(out_path):
        ok, why = False, (f"{os.path.basename(out_path)} has a .subckt but no "
                          f"devices — Magic read no geometry")

    raw_ports = []
    if ok:
        with open(out_path) as f:
            for line in f:
                if line.startswith(".subckt"):
                    raw_ports = line.strip().split()[2:]
                    break

    return {
        "netlist_path": out_path if ok else None,
        "raw_ports": raw_ports,
        "log": log,
        "success": ok,
        "status": PASS if ok else (st["status"] if st["status"] in (TIMEOUT, ERROR)
                                   else FAIL),
        "stage": "extraction",
        "tool": magic,
        "log_path": st.get("log"),
        "message": "" if ok else why,
        "relevant": st.get("relevant", []),
    }


def _netlist_has_devices(path):
    """True if an extracted netlist contains at least one device instance."""
    try:
        with open(path) as f:
            for line in f:
                t = line.strip()
                if t and t[0] in "XxMmRrCcDdQq" and not t.lower().startswith(".s"):
                    return True
    except OSError:
        return False
    return False


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

def _drc_via_engine(gds_path, cell_name, engine, workdir, timeout):
    """Run KLayout (or both engines) through mbg.drc and adapt the result.

    Returns run_drc()'s dict shape so callers do not have to care which
    implementation answered. A verdict is only ever CLEAN when a report was
    actually parsed; NOT_CONFIGURED and ERROR stay distinct from FAIL,
    because "the checker did not run" is not "the layout is clean".
    """
    from mbg.drc import DRCStatus, SignoffVerdict, get_engine, run_dual_drc

    workdir = os.path.abspath(workdir) if workdir else os.getcwd()
    os.makedirs(workdir, exist_ok=True)

    def adapt(res, summary=None):
        clean = res.status == DRCStatus.CLEAN
        status = {DRCStatus.CLEAN: PASS, DRCStatus.FAIL: FAIL}.get(
            res.status, ERROR)
        return {
            "clean": clean,
            "status": status,
            "stage": "drc",
            "report_path": res.report_path,
            "error_count": res.violations if res.status in (
                DRCStatus.CLEAN, DRCStatus.FAIL) else -1,
            "rules_violated": sorted(res.rules or {}),
            "rule_counts": dict(res.rules or {}),
            "layout_load_errors": ([res.message]
                                   if res.status == DRCStatus.ERROR and res.message
                                   else []),
            "log": res.message or "",
            "log_path": res.log_path,
            "tool": res.tool,
            "engine": res.engine,
            "summary": summary or f"DRC: {res.summary()}",
        }

    if engine == "klayout":
        res = get_engine("klayout").run(gds_path, cell_name=cell_name,
                                        workdir=workdir, timeout=timeout)
        return adapt(res)

    signoff = run_dual_drc(gds_path, cell_name=cell_name, workdir=workdir,
                           verbosity=0)
    primary = signoff.get("klayout") or (signoff.results[0]
                                         if signoff.results else None)
    if primary is None:
        return {"clean": False, "status": ERROR, "stage": "drc",
                "report_path": None, "error_count": -1, "rules_violated": [],
                "layout_load_errors": ["no DRC engine produced a result"],
                "log": signoff.reason, "log_path": None, "tool": "",
                "engine": "both",
                "summary": "DRC: NO ENGINE AVAILABLE"}
    out = adapt(primary, summary=f"DRC: {signoff.verdict} — {signoff.reason}")
    # On "both", the reconciled verdict decides, not either engine alone.
    out["clean"] = signoff.verdict == SignoffVerdict.PASS
    out["status"] = PASS if out["clean"] else FAIL
    out["engine"] = "both"
    out["signoff"] = signoff.as_dict()
    return out


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
    if os.path.getsize(gds_path) == 0:
        raise ValueError(f"GDS is empty: {gds_path}")
    cell = cell_name or os.path.splitext(os.path.basename(gds_path))[0]

    if engine in ("klayout", "both"):
        # Delegate to mbg.drc, which is the real KLayout implementation.
        #
        # This used to shell out to iic-drc.sh with -k/-b, and every part of
        # that path was broken:
        #   * the script finds KLayout with `command -v klayout`, ignoring
        #     $MBG_KLAYOUT -- and the project pins KLayout by absolute path
        #     precisely because distributions ship no `klayout` package;
        #   * it reads the deck from libs.tech/klayout/drc/<pdk>_mr.drc,
        #     which this PDK does not contain (the deck is under
        #     libs.tech/klayout/tech/drc/gf180mcu.drc);
        #   * it writes <cell>.klayout.drc.{feol,beol,density}.xml, while
        #     this function only ever looked for <stem>.magic.drc.rpt, so a
        #     KLayout report was never read even when one existed;
        #   * with no report parsed, the verdict fell through to a log
        #     substring test for "No DRC errors"/"CONGRATULATIONS" -- Magic's
        #     phrases. On engine="both" a Magic-clean run could therefore
        #     report DRC: CLEAN while KLayout had failed or found violations.
        # mbg.drc.KLayoutDRC does it correctly: it honours the resolved
        # binary, uses the shipped deck, and reads the .lyrdb it produces.
        return _drc_via_engine(gds_path, cell, engine, workdir, timeout)

    engine_flag = "-m"
    cmd = ["bash", IIC_DRC, engine_flag]
    if clean: cmd += ["-c"]
    if workdir: cmd += ["-w", os.path.abspath(workdir)]
    cmd.append(gds_path)

    env = os.environ.copy()
    try:
        # Pin the exact verified binary; the script falls back to `magic` on
        # PATH only if this is unset, and PATH is precisely what we do not
        # want to trust here.
        env["MBG_MAGIC"] = _config.magic_bin()
    except ToolError as e:
        return {"clean": False, "status": ERROR, "stage": "drc",
                "report_path": None, "error_count": -1, "rules_violated": [],
                "layout_load_errors": [], "log": str(e),
                "summary": "DRC: NO USABLE MAGIC"}

    st = run_tool("magic", ["bash"] + cmd[1:] if cmd[0] == "bash" else cmd,
                  stage="magic_drc",
                  workdir=os.path.abspath(workdir) if workdir else os.getcwd(),
                  timeout=timeout or _config.tool_timeout("magic"), env=env)
    if st["status"] == TIMEOUT:
        return {"clean": False, "status": TIMEOUT, "stage": "drc",
                "report_path": None, "error_count": -1, "rules_violated": [],
                "layout_load_errors": [], "log": st.get("message", ""),
                "log_path": st.get("log"),
                "summary": f"DRC: TIMEOUT after {st.get('timeout')}s"}
    if st["status"] == ERROR:
        return {"clean": False, "status": ERROR, "stage": "drc",
                "report_path": None, "error_count": -1, "rules_violated": [],
                "layout_load_errors": [], "log": st.get("message", ""),
                "log_path": st.get("log"), "summary": "DRC: COULD NOT RUN"}

    log = st.get("output", "")
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

    # "COUNT: 0" on its own does NOT mean the layout is clean. Magic prints a
    # zero count just as happily when it never read the GDS at all — an
    # unreadable cell yields zero error tiles because there is no geometry to
    # check. A clean result therefore has to be corroborated: the run must
    # not have failed, and the log must not carry any of the signatures of a
    # layout that was never loaded.
    load_failures = [
        (r"is required by this techfile", "Magic is too old for this techfile"),
        (r"[Nn]othing in \"?cifinput", "techfile has no cifinput section — "
                                       "GDS cannot be read"),
        (r"[Cc]ell\s+\S+\s+couldn't be read", "the top cell could not be read"),
        (r"[Nn]othing here to extract", "Magic found no geometry"),
        (r"[Nn]o such file or directory", "an input file was missing"),
    ]
    blocked = [why for pat, why in load_failures if re.search(pat, log)]

    if blocked:
        is_clean = False
        errors = -1 if errors in (None, 0) else errors
        summary = f"DRC: FAILED TO READ LAYOUT ({blocked[0]})"
    elif errors is None:
        is_clean = "No DRC errors" in log or "CONGRATULATIONS" in log
        errors = 0 if is_clean else -1
        summary = "DRC: CLEAN" if is_clean else "DRC: NO REPORT PARSED"
    else:
        is_clean = errors == 0
        summary = "DRC: CLEAN" if is_clean else f"DRC: {errors} ERROR TILES"

    return {
        "clean": is_clean,
        "status": PASS if is_clean else FAIL,
        "stage": "drc",
        "report_path": report,
        "error_count": errors,
        "rules_violated": rules_hit,
        "layout_load_errors": blocked,
        "log": log.strip(),
        "log_path": st.get("log"),
        "tool": env.get("MBG_MAGIC", "magic"),
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
    """DISABLED — retained only to document why automatic net merging is off.

    This rewrote the *schematic* netlist to match whatever the layout
    extracted, which makes LVS compare the layout against itself: any
    router-induced short became "correct" instead of being reported.
    The only call site is commented out in run_lvs() and must stay that
    way. If LVS reports a merged net, fix the layout, not the netlist.
    """
    raise RuntimeError(
        "_merge_schematic_nets is disabled: it masks real shorts by editing the schematic to match the layout")
    # --- original implementation retained below, unreachable ---

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
        # LVS depends on extraction; without an extracted netlist there is
        # nothing to compare and the stage is SKIPPED, not failed-open.
        #
        # This branch used to read `xtr_path = gds_path`, handing netgen the
        # raw GDS as though it were a netlist. netgen does not reject binary
        # input — it waits, and the regression stopped dead at the first
        # circuit. Never substitute a different file for a missing one.
        msg = xtr.get("message") or "Magic extraction produced no usable netlist"
        detail = "\n".join(f"    {l}" for l in xtr.get("relevant", [])[:5])
        report_txt = (
            f"[ERROR][MAGIC_EXTRACTION]\n\n"
            f"Magic failed while extracting:\n"
            f"  design : {cell}\n"
            f"  GDS    : {gds_path}\n"
            f"  tool   : {xtr.get('tool', 'magic')}\n\n"
            f"  {msg}\n"
            + (f"\nRelevant output:\n{detail}\n" if detail else "")
            + f"\nLVS was SKIPPED because no valid extracted SPICE netlist "
              f"was generated.\n"
            + (f"\nFull log:\n  {xtr.get('log_path')}\n"
               if xtr.get("log_path") else ""))
        print(report_txt)
        return {
            "match": False,
            "status": SKIP,
            "stage": "lvs",
            "skipped_because": "extraction",
            "extraction": {k: xtr.get(k) for k in
                           ("status", "message", "log_path", "tool")},
            "report_path": None,
            "log": report_txt,
            "summary": {
                "match": False, "status": SKIP,
                "topology_match": False, "property_errors": False,
                "pin_matching_failed": False, "property_mismatches": [],
                "device_mismatch": "?", "net_mismatch": "?", "port_swaps": [],
                "missing_devices": [],
                "message": "LVS SKIPPED — Magic extraction did not produce a "
                           "valid netlist (see extraction log)",
            },
        }

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
        """Run netgen LVS. Returns (stage_dict, report_path_or_None).

        The netlist is re-validated here as well as at the call site. This is
        the last point before a file is handed to a tool that will happily
        block forever on the wrong kind of input, so it is worth checking
        twice rather than trusting a caller.
        """
        ok, why = validate_spice_netlist(xtr_file)
        if not ok:
            return _stage("lvs", ERROR, tool="netgen",
                          message=f"refusing to run netgen: {why}"), None
        try:
            netgen = _config.netgen_bin()
        except ToolError as e:
            return _stage("lvs", ERROR, tool="netgen", message=str(e)), None

        st = run_tool("netgen",
                      [netgen, "-batch", "lvs",
                       f"{xtr_file} {cell}", f"{sch_path} {cell}",
                       custom_setup, report_file],
                      stage="netgen_lvs", workdir=wd,
                      timeout=timeout or _config.tool_timeout("netgen"))
        return st, (report_file if os.path.isfile(report_file) else None)

    # ── First attempt: original extracted netlist ──
    report = os.path.join(wd, f"{cell}.lvs.out")
    r, report_path = _invoke_netgen(xtr_path, report)

    if r is None or r.get("status") in (ERROR, TIMEOUT):
        st = r or _stage("lvs", ERROR, tool="netgen", message="netgen unavailable")
        msg = st.get("message") or (
            f"netgen exceeded {st.get('timeout')}s and was terminated"
            if st.get("status") == TIMEOUT else "netgen could not be run")
        detail = "\n".join(f"    {l}" for l in st.get("relevant", [])[:5])
        text = (f"[ERROR][NETGEN_LVS]\n\n  design : {cell}\n"
                f"  tool   : {st.get('tool')}\n  {msg}\n"
                + (f"\nRelevant output:\n{detail}\n" if detail else "")
                + (f"\nFull log:\n  {st.get('log')}\n" if st.get("log") else ""))
        print(text)
        return {"match": False, "status": st.get("status", ERROR), "stage": "lvs",
                "report_path": None, "log": text,
                "summary": {"match": False, "status": st.get("status", ERROR),
                            "topology_match": False, "property_errors": False,
                            "pin_matching_failed": False,
                            "property_mismatches": [], "device_mismatch": "?",
                            "net_mismatch": "?", "port_swaps": [],
                            "missing_devices": [], "message": msg}}

    log = r.get("output", "")
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
            if r2 is not None and r2.get("status") not in (ERROR, TIMEOUT):
                log2 = r2.get("output", "")
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

    summary["status"] = PASS if summary["match"] else FAIL
    return {"match": summary["match"], "status": summary["status"],
            "stage": "lvs", "report_path": report_path,
            "log": log.strip(), "summary": summary,
            "tool": r.get("tool", "netgen"), "log_path": r.get("log")}


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
