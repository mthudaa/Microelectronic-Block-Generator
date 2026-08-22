"""Centralised environment, PDK and EDA-tool configuration for MBG.

Everything that used to be resolved ad hoc — in shell scripts, in
``checks.py``, in notebooks — is decided here once, so there is exactly one
answer to "which Magic am I running?" and one place to change it.

Two rules drive the design:

**PDK variables must exist before gLayout is imported.** gLayout reads the
PDK environment at *import* time and calls ``Path()`` on it, so an unset
``PDK_ROOT`` surfaces as ``TypeError: expected str, bytes or os.PathLike
object, not NoneType`` from deep inside a third-party package — a traceback
that says nothing about the real problem. :func:`ensure_pdk_env` runs from
``mbg/__init__`` before any such import.

**An executable's name proves nothing.** A system Magic that cannot read the
GF180 techfile is worse than no Magic at all: it produces empty extractions
and DRC reports that say ``COUNT: 0``. Tools are therefore accepted only
after a version check *and* a functional probe against the real PDK.

Resolution order for every tool (first hit wins):

1. ``MBG_MAGIC`` / ``MBG_NETGEN`` / ``MBG_KLAYOUT`` — explicit executable
2. ``MBG_MAGIC_ROOT`` / ``MBG_NETGEN_ROOT`` — a prefix; ``<prefix>/bin/<tool>``
3. ``MBG_TOOLS_ROOT`` (default ``~/.local/mbg-tools``) — MBG's own builds
4. ``PATH`` — accepted only if it passes the compatibility probe
5. otherwise a :class:`ToolError` naming what to run

Nothing here writes to the filesystem or installs anything; that is
``scripts/setup_env.sh``.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "repo_root", "tools_root", "PDKConfig", "pdk_config", "ensure_pdk_env",
    "ToolInfo", "ToolError", "resolve_magic", "resolve_netgen",
    "resolve_klayout", "resolve_ngspice", "tool_timeout", "log_dir",
    "describe_environment", "MIN_MAGIC_VERSION", "MIN_NETGEN_VERSION",
]

# ── version policy ────────────────────────────────────────────────────
# The floor is the PDK's own requirement, read from the techfile when it is
# available ("requires magic-8.3.411" in gf180mcuD.tech). This constant is
# only the fallback for when the techfile cannot be read: pinning an exact
# build would reject working installations for no reason — 8.3.669 and
# 8.3.681 both run this flow correctly.
MIN_MAGIC_VERSION = (8, 3, 411)
MIN_NETGEN_VERSION = (1, 5, 200)

DEFAULT_PDK = "gf180mcuD"
DEFAULT_STD_CELL_LIBRARY = "gf180mcu_fd_sc_mcu7t5v0"

_DEFAULT_TIMEOUTS = {"magic": 900, "netgen": 900, "ngspice": 600, "klayout": 600}


# ── repository / tool locations ───────────────────────────────────────

def repo_root() -> Path:
    """The repository root, found by walking up from this file.

    Never a hard-coded path: the package is imported from a checkout that
    may live anywhere, and from a virtualenv that may live elsewhere again.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src").is_dir():
            return parent
    return here.parents[2]


def tools_root() -> Path:
    """Where MBG keeps EDA tools it built itself.

    Configurable through ``MBG_TOOLS_ROOT``; defaults under the user's home
    so that installing a toolchain never needs root and never touches
    ``/usr`` or the system package manager.
    """
    return Path(os.environ.get("MBG_TOOLS_ROOT",
                               Path.home() / ".local" / "mbg-tools")).expanduser()


def log_dir(workdir: str | os.PathLike, create: bool = True) -> Path:
    """Per-run log directory: ``<workdir>/logs``."""
    d = Path(workdir) / "logs"
    if create:
        d.mkdir(parents=True, exist_ok=True)
    return d


def tool_timeout(tool: str, default: Optional[int] = None) -> int:
    """Seconds before an external tool is killed.

    ``MBG_<TOOL>_TIMEOUT`` overrides one tool, ``MBG_TOOL_TIMEOUT`` overrides
    all of them. A bounded timeout is not a nicety: an unbounded netgen that
    waits for input hangs the whole regression, which is how one inverter
    once prevented three other circuits from ever being tested.
    """
    for var in (f"MBG_{tool.upper()}_TIMEOUT", "MBG_TOOL_TIMEOUT"):
        val = os.environ.get(var)
        if val:
            try:
                return int(val)
            except ValueError:
                pass
    return default if default is not None else _DEFAULT_TIMEOUTS.get(tool, 600)


# ── PDK ───────────────────────────────────────────────────────────────

@dataclass
class PDKConfig:
    root: Path
    pdk: str
    path: Path
    std_cell_library: str

    @property
    def magic_techfile(self) -> Path:
        return self.path / "libs.tech" / "magic" / f"{self.pdk}.tech"

    @property
    def magicrc(self) -> Path:
        return self.path / "libs.tech" / "magic" / f"{self.pdk}.magicrc"

    @property
    def netgen_setup(self) -> Path:
        return self.path / "libs.tech" / "netgen" / f"{self.pdk}_setup.tcl"

    @property
    def ngspice_models(self) -> Path:
        return self.path / "libs.tech" / "ngspice" / "sm141064.ngspice"

    def missing(self) -> List[str]:
        """Required PDK files that are not present."""
        out = []
        for label, p in (("PDKPATH", self.path),
                         ("magic techfile", self.magic_techfile),
                         ("magicrc", self.magicrc),
                         ("netgen setup", self.netgen_setup)):
            if not p.exists():
                out.append(f"{label}: {p}")
        return out

    def as_env(self) -> Dict[str, str]:
        return {"PDK_ROOT": str(self.root), "PDK": self.pdk,
                "PDKPATH": str(self.path),
                "STD_CELL_LIBRARY": self.std_cell_library}


def _default_pdk_root() -> Path:
    """Where to look for a PDK when nothing is configured.

    Volare's default (``~/.volare``) first, then the container location the
    project used historically, so an IIC-OSIC-TOOLS shell still works.
    """
    for cand in (Path.home() / ".volare", Path("/foss/pdks")):
        if cand.is_dir():
            return cand
    return Path.home() / ".volare"


def pdk_config() -> PDKConfig:
    """Resolve the PDK from the environment, filling in sane defaults."""
    pdk = os.environ.get("PDK") or DEFAULT_PDK
    root = Path(os.environ.get("PDK_ROOT") or _default_pdk_root()).expanduser()
    path_env = os.environ.get("PDKPATH")
    path = Path(path_env).expanduser() if path_env else root / pdk
    std = os.environ.get("STD_CELL_LIBRARY") or DEFAULT_STD_CELL_LIBRARY
    return PDKConfig(root=root, pdk=pdk, path=path, std_cell_library=std)


def ensure_pdk_env(strict: bool = False) -> PDKConfig:
    """Populate the PDK environment variables, and say so plainly if we can't.

    Called from ``mbg/__init__`` *before* anything imports gLayout. Without
    it, an unset ``PDK_ROOT`` becomes a ``TypeError`` about ``NoneType``
    raised inside a third-party package, which tells the user nothing.

    With ``strict``, a PDK that is missing or incomplete raises here — where
    the message can name the file and the command that installs it.
    """
    cfg = pdk_config()
    for key, value in cfg.as_env().items():
        os.environ.setdefault(key, value)
    if strict:
        missing = cfg.missing()
        if missing:
            raise ToolError(
                "The GF180MCU PDK is missing or incomplete.\n"
                + "".join(f"  not found: {m}\n" for m in missing)
                + f"\n  PDK_ROOT = {cfg.root}\n  PDK      = {cfg.pdk}\n"
                + "\nInstall it with:\n"
                + "  ./scripts/setup_env.sh --pdk\n"
                + "\nor point PDK_ROOT at an existing installation.")
    return cfg


def required_magic_version(cfg: Optional[PDKConfig] = None) -> Tuple[int, int, int]:
    """The minimum Magic the *installed techfile* asks for.

    gf180mcuD.tech opens with ``requires magic-8.3.411``. Reading it means the
    check tracks whatever PDK the user actually has, instead of a number
    frozen into this file.
    """
    cfg = cfg or pdk_config()
    try:
        with open(cfg.magic_techfile) as f:
            for _ in range(80):
                line = f.readline()
                if not line:
                    break
                m = re.search(r"requires\s+magic-(\d+)\.(\d+)\.(\d+)", line)
                if m:
                    return tuple(int(g) for g in m.groups())  # type: ignore
    except OSError:
        pass
    return MIN_MAGIC_VERSION


# ── tools ─────────────────────────────────────────────────────────────

class ToolError(RuntimeError):
    """A required tool is missing, unusable, or incompatible."""


@dataclass
class ToolInfo:
    name: str
    path: Optional[str] = None
    version: Optional[Tuple[int, ...]] = None
    version_string: str = ""
    ok: bool = False
    optional: bool = False
    reason: str = ""
    source: str = ""          # which resolution rule produced this
    notes: List[str] = field(default_factory=list)

    def __str__(self) -> str:
        state = "OK" if self.ok else ("OPTIONAL" if self.optional else "FAIL")
        return f"{self.name}: {state} {self.path or '-'} {self.version_string}"

    def require(self) -> str:
        """The executable path, or a ToolError explaining how to get one."""
        if not self.ok or not self.path:
            raise ToolError(self.reason or f"{self.name} is not usable")
        return self.path


def _run(cmd: Sequence[str], timeout: int = 60,
         stdin: str = "") -> Tuple[int, str, str]:
    try:
        r = subprocess.run(list(cmd), capture_output=True, text=True,
                           timeout=timeout, input=stdin)
        return r.returncode, r.stdout or "", r.stderr or ""
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout}s"
    except (OSError, ValueError) as e:
        return 127, "", f"{type(e).__name__}: {e}"


def _parse_version(text: str, pattern: str) -> Tuple[Optional[Tuple[int, ...]], str]:
    m = re.search(pattern, text)
    if not m:
        return None, ""
    parts = tuple(int(g) for g in m.groups() if g and g.isdigit())
    return parts, ".".join(str(p) for p in parts)


def _candidates(name: str, env_exe: str, env_root: str,
                subdirs: Sequence[str] = ()) -> List[Tuple[str, str]]:
    """(path, source) pairs to try, in priority order."""
    out: List[Tuple[str, str]] = []

    # Explicit configuration is authoritative. If the user names a binary and
    # it turns out to be unusable, that is an error to report — not a licence
    # to go and quietly run a different one.
    exe = os.environ.get(env_exe)
    if exe:
        out.append((os.path.expanduser(exe), f"${env_exe}"))

    root = os.environ.get(env_root)
    if root:
        out.append((str(Path(root).expanduser() / "bin" / name), f"${env_root}"))

    tr = tools_root()
    if tr.is_dir():
        # any <tools_root>/<name>-<version>/bin/<name>, newest name last
        for d in sorted(tr.glob(f"{name}-*"), reverse=True):
            cand = d / "bin" / name
            if cand.exists():
                out.append((str(cand), "MBG_TOOLS_ROOT"))
        cand = tr / "bin" / name
        if cand.exists():
            out.append((str(cand), "MBG_TOOLS_ROOT"))
    for sub in subdirs:
        out.append((sub, "conventional"))

    found = shutil.which(name)
    if found:
        out.append((found, "PATH"))

    seen, uniq = set(), []
    for p, src in out:
        if p not in seen:
            seen.add(p)
            uniq.append((p, src))
    return uniq


def resolve_magic(cfg: Optional[PDKConfig] = None,
                  probe: bool = True) -> ToolInfo:
    """Find a Magic that can actually drive this PDK.

    Two gates. The version must satisfy what the techfile asks for — an older
    Magic reports ``Magic version 8.3.411 is required by this techfile, but
    this version of magic is 0.0.0`` and then produces an empty ``cifinput``
    section, so GDS reads fail and extraction silently yields nothing. Then,
    unless ``probe`` is off, Magic must load the GF180 techfile for real.
    """
    cfg = cfg or pdk_config()
    need = required_magic_version(cfg)
    info = ToolInfo(name="magic")
    tried: List[str] = []

    explicit = {"$MBG_MAGIC", "$MBG_MAGIC_ROOT"}
    for path, source in _candidates("magic", "MBG_MAGIC", "MBG_MAGIC_ROOT"):
        pinned = source in explicit
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            if pinned:
                info.reason = (f"MBG_MAGIC/MBG_MAGIC_ROOT points at {path}, which is "
                               f"not an executable file.")
                return info
            continue
        rc, out, err = _run([path, "--version"], timeout=30)
        ver, vs = _parse_version(out + err, r"(\d+)\.(\d+)\.(\d+)")
        if ver is None:
            tried.append(f"  {path} ({source}): version could not be determined")
            if pinned:
                break
            continue
        if ver < need:
            tried.append(f"  {path} ({source}): version {vs} < required "
                         f"{'.'.join(map(str, need))}")
            if pinned:
                break
            continue
        if probe and not cfg.magicrc.is_file():
            tried.append(f"  {path} ({source}): PDK magicrc not found at "
                         f"{cfg.magicrc}")
            if pinned:
                break
            continue
        if probe:
            ok, why = _probe_magic(path, cfg)
            if not ok:
                tried.append(f"  {path} ({source}): {why}")
                if pinned:
                    break
                continue
        info.path, info.version, info.version_string = path, ver, vs
        info.ok, info.source = True, source
        return info

    info.reason = _tool_error_text("Magic", tried, "--eda")
    return info


def _probe_magic(path: str, cfg: PDKConfig) -> Tuple[bool, str]:
    """Load the real techfile and confirm Magic is happy with it."""
    script = "puts MBG_TECH_OK\nquit -noprompt\n"
    rc, out, err = _run([path, "-dnull", "-noconsole", "-rcfile",
                         str(cfg.magicrc)], timeout=tool_timeout("magic", 120),
                        stdin=script)
    blob = out + err
    if "MBG_TECH_OK" not in blob:
        head = "; ".join(l.strip() for l in blob.splitlines() if l.strip())[:200]
        return False, f"could not load {cfg.pdk} techfile ({head or 'no output'})"
    if re.search(r"is required by this techfile", blob):
        return False, "techfile rejected this Magic version"
    if re.search(r"[Nn]othing in \"?cifinput", blob):
        return False, "techfile loaded without a cifinput section (GDS reads will fail)"
    return True, ""


def resolve_netgen(probe: bool = True) -> ToolInfo:
    """Find a netgen that runs in batch mode and terminates.

    The failure this guards against is not a crash but a hang: some builds
    sit waiting on stdin under ``-batch``, and an LVS that never returns
    stops the whole regression at the first circuit.
    """
    info = ToolInfo(name="netgen")
    tried: List[str] = []

    explicit = {"$MBG_NETGEN", "$MBG_NETGEN_ROOT"}
    for path, source in _candidates("netgen", "MBG_NETGEN", "MBG_NETGEN_ROOT"):
        pinned = source in explicit
        if not (os.path.isfile(path) and os.access(path, os.X_OK)):
            if pinned:
                info.reason = (f"MBG_NETGEN/MBG_NETGEN_ROOT points at {path}, which is "
                               f"not an executable file.")
                return info
            continue
        rc, out, err = _run([path, "-batch"], timeout=30, stdin="quit\n")
        blob = out + err
        ver, vs = _parse_version(blob, r"Netgen\s+(\d+)\.(\d+)\.(\d+)")
        if ver is None:
            tried.append(f"  {path} ({source}): not a netgen LVS binary "
                         f"(no version banner; the Netgen *mesh generator* "
                         f"shares this name on some distributions)")
            if pinned:
                break
            continue
        if ver < MIN_NETGEN_VERSION:
            tried.append(f"  {path} ({source}): version {vs} < required "
                         f"{'.'.join(map(str, MIN_NETGEN_VERSION))}")
            if pinned:
                break
            continue
        if probe:
            ok, why = _probe_netgen(path)
            if not ok:
                tried.append(f"  {path} ({source}): {why}")
                if pinned:
                    break
                continue
        info.path, info.version, info.version_string = path, ver, vs
        info.ok, info.source = True, source
        return info

    info.reason = _tool_error_text("netgen", tried, "--eda")
    return info


def _probe_netgen(path: str) -> Tuple[bool, str]:
    """Batch mode must complete on its own, without input and without hanging."""
    rc, out, err = _run([path, "-batch"], timeout=30, stdin="quit\n")
    if rc == 124:
        return False, "batch mode did not terminate (this build hangs under -batch)"
    return True, ""


def resolve_klayout() -> ToolInfo:
    """KLayout, which is optional for the GF180 Magic + netgen flow.

    The Python module and the standalone executable are different things: the
    module being importable does not give you a ``klayout`` command. Only the
    executable matters for the DRC engine, and only when it is selected.
    """
    info = ToolInfo(name="klayout", optional=True)
    # Same resolution order as the other tools: explicit config, then an
    # MBG-managed build, then PATH. A distro that ships no klayout package
    # (Fedora) or a binary living outside PATH (nix store) is common, so
    # MBG_KLAYOUT must be honoured.
    # Explicit configuration is authoritative, exactly as for Magic and
    # netgen: if the user names a binary and it is unusable, that is an error
    # to report — not permission to quietly run a different one.
    path = source = None
    explicit = {"$MBG_KLAYOUT", "$MBG_KLAYOUT_ROOT"}
    for cand, src in _candidates("klayout", "MBG_KLAYOUT", "MBG_KLAYOUT_ROOT"):
        if os.path.isfile(cand) and os.access(cand, os.X_OK):
            path, source = cand, src
            break
        if src in explicit:
            info.reason = (f"MBG_KLAYOUT/MBG_KLAYOUT_ROOT points at {cand}, "
                           f"which is not an executable file.")
            return info
    if path:
        rc, out, err = _run([path, "-v"], timeout=30)
        ver, vs = _parse_version(out + err, r"(\d+)\.(\d+)\.?(\d+)?")
        info.path, info.version, info.version_string = path, ver, vs or ""
        info.ok = True
        # Report where it actually came from. Saying "PATH" for a binary found
        # under MBG_TOOLS_ROOT misleads: it suggests the resolution depends on
        # PATH order when it does not.
        info.source = source or "PATH"
        return info
    try:
        import klayout  # noqa: F401
        info.notes.append("the `klayout` Python module is installed, but the "
                          "standalone executable is not on PATH")
    except ImportError:
        pass
    info.reason = ("klayout executable not found. It is OPTIONAL: the default "
                   "GF180 flow uses Magic for DRC and netgen for LVS. It is "
                   "needed only for run_drc(engine='klayout') or engine='both'.")
    return info


def resolve_ngspice() -> ToolInfo:
    """ngspice, required only for simulation, not for layout or signoff."""
    info = ToolInfo(name="ngspice", optional=True)
    path = shutil.which(os.environ.get("MBG_NGSPICE", "ngspice"))
    if not path:
        info.reason = ("ngspice not found. Required for mbg.analysis / "
                       "mbg.simulation only; layout and DRC/LVS do not use it.")
        return info
    rc, out, err = _run([path, "-v"], timeout=30)
    ver, vs = _parse_version(out + err, r"ngspice-(\d+)")
    info.path, info.version, info.version_string = path, ver, vs or ""
    info.ok, info.source = True, "PATH"
    return info


_WHY_NOT_ENOUGH = {
    "Magic": ("An executable being present is not enough — it must satisfy the "
              "version the PDK techfile asks for and actually load that "
              "techfile."),
    "netgen": ("An executable being present is not enough — it must be the "
               "netgen LVS tool (not the mesh generator of the same name) and "
               "must terminate in batch mode."),
}


def _tool_error_text(label: str, tried: Sequence[str], flag: str) -> str:
    body = "\n".join(tried) if tried else "  (no candidate executables found)"
    why = _WHY_NOT_ENOUGH.get(label, "")
    return (f"No usable {label} was found.\n\n"
            f"Checked, in order:\n{body}\n\n"
            + (f"{why}\n\n" if why else "")
            + f"Install a known-good build under $MBG_TOOLS_ROOT with:\n"
              f"  ./scripts/setup_env.sh {flag}\n\n"
              f"or point MBG_{label.upper()}_ROOT at an existing prefix.")


# ── cached accessors used by the pipeline ─────────────────────────────

_CACHE: Dict[str, ToolInfo] = {}
_ANNOUNCED: set = set()


def _announce(info: ToolInfo) -> None:
    """Say once, out loud, which binary is about to be used.

    Silence here is how a run ends up using an unexpected Magic and nobody
    notices until the results are wrong. Set MBG_QUIET_TOOLS=1 to suppress.
    """
    if info.name in _ANNOUNCED or os.environ.get("MBG_QUIET_TOOLS"):
        return
    _ANNOUNCED.add(info.name)
    if info.ok:
        print(f"[TOOLS] {info.name}: {info.path} "
              f"({info.version_string}, via {info.source})")


def magic_bin(probe: bool = True) -> str:
    """Path to the Magic MBG will run. Raises ToolError if there isn't one."""
    if "magic" not in _CACHE:
        _CACHE["magic"] = resolve_magic(probe=probe)
    _announce(_CACHE["magic"])
    return _CACHE["magic"].require()


def netgen_bin(probe: bool = True) -> str:
    """Path to the netgen MBG will run. Raises ToolError if there isn't one."""
    if "netgen" not in _CACHE:
        _CACHE["netgen"] = resolve_netgen(probe=probe)
    _announce(_CACHE["netgen"])
    return _CACHE["netgen"].require()


def clear_tool_cache() -> None:
    _CACHE.clear()
    _ANNOUNCED.clear()


def describe_environment(probe: bool = True) -> Dict[str, object]:
    """Everything the preflight check reports, as data."""
    cfg = pdk_config()
    return {
        "repo_root": str(repo_root()),
        "tools_root": str(tools_root()),
        "pdk": {**cfg.as_env(), "missing": cfg.missing(),
                "required_magic": ".".join(map(str, required_magic_version(cfg)))},
        "tools": {t.name: t for t in (resolve_magic(cfg, probe=probe),
                                      resolve_netgen(probe=probe),
                                      resolve_klayout(),
                                      resolve_ngspice())},
    }
