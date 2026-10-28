"""Declarative PDK profiles: one JSON file per supported process variant.

Everything the flow needs to know about a process *beyond* what gLayout
already models (layers, design rules, via stacks) lives in
``src/mbg/pdks/<name>.json``: the supply, the device catalogue with the
terminal order and the sizes the layout engine accepts, which ngspice model
sections a device kind needs per corner, and which DRC/LVS decks sign off.

The profiles are data on purpose. An agent can read one with
``mbg pdk info`` and know exactly what is legal before it writes a netlist,
and adding a variant is a new JSON file rather than a hunt for hard-coded
``gf180`` strings. This module is pure Python — it never imports gLayout —
so the agent tools that use it start instantly.

    from mbg import pdk_profile
    p = pdk_profile.resolve("gf180")         # -> gf180mcuD (the default)
    p.device("pnp_10p00x10p00").terminals    # ['c', 'b', 'e']
    p.lib_sections({"mos", "bjt"}, "ss")     # ['ss', 'bjt_ss']
    with p.env():                            # PDK, PDKPATH, ... for the tools
        ...
"""
from __future__ import annotations

import contextlib
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Iterator, List, Optional

_PROFILE_DIR = Path(__file__).resolve().parent / "pdks"

#: Device kinds the flow distinguishes. ``sim`` kinds select model sections.
KINDS = ("nmos", "pmos", "res", "cap", "bjt")


class ProfileError(ValueError):
    """An unknown PDK, or a request the profile cannot satisfy."""


@dataclass(frozen=True)
class DeviceSpec:
    model: str
    kind: str
    terminals: tuple
    layout: bool
    sim: str
    w_min_um: Optional[float] = None
    w_max_um: Optional[float] = None
    l_min_um: Optional[float] = None
    l_max_um: Optional[float] = None
    body_net: Optional[str] = None
    substrate_terminals: tuple = ()
    fixed_cell: Optional[str] = None
    sheet_ohm_sq: Optional[float] = None
    params: tuple = ()
    note: str = ""

    def as_dict(self) -> dict:
        d = {"model": self.model, "kind": self.kind,
             "terminals": list(self.terminals), "layout": self.layout,
             "sim": self.sim}
        for k in ("w_min_um", "w_max_um", "l_min_um", "l_max_um", "body_net",
                  "fixed_cell", "sheet_ohm_sq", "note"):
            v = getattr(self, k)
            if v not in (None, ""):
                d[k] = v
        if self.substrate_terminals:
            d["substrate_terminals"] = list(self.substrate_terminals)
        if self.params:
            d["params"] = list(self.params)
        return d


@dataclass
class PDKProfile:
    name: str
    family: str
    data: dict = field(repr=False)

    # ── identity / process ────────────────────────────────────────────
    @property
    def aliases(self) -> List[str]:
        return list(self.data.get("aliases", []))

    @property
    def description(self) -> str:
        return self.data.get("description", "")

    @property
    def supply_v(self) -> float:
        return float(self.data["supply"]["nominal_v"])

    @property
    def supply_range(self) -> tuple:
        s = self.data["supply"]
        return float(s["min_v"]), float(s["max_v"])

    @property
    def glayout_pdk(self) -> str:
        """Attribute name of the mapped PDK in ``glayout`` (``gf180``/``sky130``)."""
        return self.data["glayout_pdk"]

    @property
    def std_cell_library(self) -> str:
        return self.data.get("std_cell_library", "")

    @property
    def conventions(self) -> dict:
        return self.data.get("conventions", {})

    @property
    def tested_ceiling(self) -> dict:
        return self.data.get("tested_ceiling", {})

    # ── devices ───────────────────────────────────────────────────────
    @property
    def devices(self) -> Dict[str, DeviceSpec]:
        out = {}
        for model, d in self.data.get("devices", {}).items():
            out[model] = DeviceSpec(
                model=model, kind=d["kind"], terminals=tuple(d["terminals"]),
                layout=bool(d.get("layout", False)), sim=d.get("sim", d["kind"]),
                w_min_um=d.get("w_min_um"), w_max_um=d.get("w_max_um"),
                l_min_um=d.get("l_min_um"), l_max_um=d.get("l_max_um"),
                body_net=d.get("body_net"),
                substrate_terminals=tuple(d.get("substrate_terminals", ())),
                fixed_cell=d.get("fixed_cell"), sheet_ohm_sq=d.get("sheet_ohm_sq"),
                params=tuple(d.get("params", ())), note=d.get("note", ""))
        return out

    def device(self, model: str) -> Optional[DeviceSpec]:
        if not model:
            return None
        devs = self.devices
        if model in devs:
            return devs[model]
        low = model.lower()
        for name, spec in devs.items():
            if name.lower() == low:
                return spec
        return None

    def kind_of(self, model: str) -> Optional[str]:
        spec = self.device(model)
        return spec.kind if spec else None

    def models(self, kind: Optional[str] = None,
               layout_only: bool = False) -> List[str]:
        return [m for m, s in self.devices.items()
                if (kind is None or s.kind == kind)
                and (s.layout or not layout_only)]

    # ── filesystem ────────────────────────────────────────────────────
    def path(self, root: Optional[os.PathLike] = None) -> Path:
        """Installed location of this variant.

        ``PDKPATH`` wins when it names this variant, then ``<root>/<name>``
        with ``root`` defaulting to ``PDK_ROOT`` / the config default.
        """
        env_path = os.environ.get("PDKPATH")
        if root is None and env_path and Path(env_path).name == self.name:
            return Path(env_path).expanduser()
        if root is None:
            from mbg import config
            root = os.environ.get("PDK_ROOT") or config._default_pdk_root()
        return Path(root).expanduser() / self.name

    def installed(self, root: Optional[os.PathLike] = None) -> bool:
        p = self.path(root)
        return (p / "libs.tech" / "magic" / f"{self.name}.tech").is_file()

    @property
    def model_file_rel(self) -> str:
        return self.data["ngspice"]["model_file"]

    @property
    def design_file_rel(self) -> Optional[str]:
        return self.data["ngspice"].get("design_file")

    def model_file(self, root=None) -> Path:
        return self.path(root) / self.model_file_rel

    def design_file(self, root=None) -> Optional[Path]:
        rel = self.design_file_rel
        return self.path(root) / rel if rel else None

    # ── simulation ────────────────────────────────────────────────────
    @property
    def corners(self) -> List[str]:
        return list(self.data["ngspice"]["corners"])

    @property
    def default_corner(self) -> str:
        return self.data["ngspice"]["default_corner"]

    @property
    def spiceinit(self) -> List[str]:
        return list(self.data["ngspice"].get("spiceinit", []))

    def canonical_corner(self, corner: Optional[str]) -> str:
        if not corner:
            return self.default_corner
        aliases = self.data["ngspice"].get("corner_aliases", {})
        return aliases.get(corner, corner)

    def lib_sections(self, kinds: Iterable[str],
                     corner: Optional[str] = None) -> List[str]:
        """Model-library sections to load for these device kinds at a corner.

        MOS always comes first, so a MOS-only deck is unchanged by the
        multi-section support. A kind with no section at this corner (gf180
        has no ``bjt_fs``) falls back to the profile's ``fallback_corner``.
        Duplicates are dropped — sky130 loads every kind from one section.
        """
        corner = self.canonical_corner(corner)
        secs = self.data["ngspice"]["sections"]
        fallback = self.data["ngspice"].get("fallback_corner", self.default_corner)
        sim_kinds = {"nmos": "mos", "pmos": "mos"}
        wanted = {sim_kinds.get(k, k) for k in kinds} | {"mos"}
        out: List[str] = []
        for kind in ("mos", "bjt", "res", "cap"):
            if kind not in wanted or kind not in secs:
                continue
            spec = secs[kind]
            c = corner if corner in spec["corners"] else fallback
            name = spec["pattern"].format(corner=c)
            if name not in out:
                out.append(name)
        return out

    # ── verification ──────────────────────────────────────────────────
    @property
    def verification(self) -> dict:
        return self.data.get("verification", {})

    @property
    def drc_engines(self) -> List[str]:
        return list(self.verification.get("drc_engines", ["magic"]))

    @property
    def drc_primary(self) -> str:
        return self.verification.get("drc_primary", self.drc_engines[0])

    @property
    def klayout_variant(self) -> Optional[str]:
        return self.verification.get("klayout_variant")

    def klayout_deck(self, root=None) -> Optional[Path]:
        rel = self.verification.get("klayout_deck")
        return self.path(root) / rel if rel else None

    @property
    def lvs_permute_models(self) -> List[str]:
        return list(self.verification.get("lvs_permute_models", []))

    # ── environment ───────────────────────────────────────────────────
    def env_vars(self, root=None) -> Dict[str, str]:
        p = self.path(root)
        return {"PDK_ROOT": str(p.parent), "PDK": self.name,
                "PDKPATH": str(p), "STD_CELL_LIBRARY": self.std_cell_library}

    @contextlib.contextmanager
    def env(self, root=None) -> Iterator["PDKProfile"]:
        """Point PDK/PDKPATH/PDK_ROOT/STD_CELL_LIBRARY at this variant.

        ``config.ensure_pdk_env`` only fills variables that are unset, so a
        process that started on gf180mcuD would otherwise verify a sky130
        layout against the gf180 techfile. This *overrides*, and restores
        the previous values on exit.
        """
        new = self.env_vars(root)
        old = {k: os.environ.get(k) for k in new}
        os.environ.update(new)
        try:
            yield self
        finally:
            for k, v in old.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    # ── reporting ─────────────────────────────────────────────────────
    def summary(self, section: Optional[str] = None, root=None) -> dict:
        """A compact, JSON-ready description — what ``mbg pdk info`` prints."""
        full = {
            "name": self.name, "family": self.family,
            "description": self.description,
            "installed": self.installed(root), "path": str(self.path(root)),
            "supply": self.data["supply"], "units": self.data.get("units", ""),
            "conventions": self.conventions,
            "devices": {m: s.as_dict() for m, s in self.devices.items()},
            "sim": {"model_file": self.model_file_rel,
                    "corners": self.corners,
                    "default_corner": self.default_corner,
                    "sections": self.data["ngspice"]["sections"]},
            "verification": self.verification,
            "tested_ceiling": self.tested_ceiling,
        }
        if section is None:
            return full
        if section not in full:
            raise ProfileError(f"unknown section {section!r}; choose from "
                               f"{sorted(full)}")
        return {"name": self.name, section: full[section]}


# ── loading ───────────────────────────────────────────────────────────

_CACHE: Dict[str, PDKProfile] = {}


def available() -> List[str]:
    """Names of every profile shipped with the package."""
    return sorted(p.stem for p in _PROFILE_DIR.glob("*.json"))


def _load_file(name: str) -> PDKProfile:
    if name not in _CACHE:
        data = json.loads((_PROFILE_DIR / f"{name}.json").read_text())
        _CACHE[name] = PDKProfile(name=data["name"], family=data["family"],
                                  data=data)
    return _CACHE[name]


def all_profiles() -> List[PDKProfile]:
    return [_load_file(n) for n in available()]


def load(name: str) -> PDKProfile:
    """A profile by exact name or alias (case-insensitive)."""
    if not name:
        raise ProfileError("empty PDK name")
    low = name.lower()
    for prof in all_profiles():
        if low == prof.name.lower() or low in (a.lower() for a in prof.aliases):
            if low == prof.family.lower():
                # A bare family name: prefer the variant the environment names.
                return resolve(prof.family)
            return prof
    raise ProfileError(f"unknown PDK {name!r}; supported: {available()}")


def family_default(family: str) -> PDKProfile:
    cands = [p for p in all_profiles() if p.family == family]
    if not cands:
        raise ProfileError(f"unknown PDK family {family!r}")
    for p in cands:
        if p.data.get("default"):
            return p
    return cands[0]


def resolve(spec: Optional[str] = None) -> PDKProfile:
    """Turn a variant name, an alias, a family, or nothing into a profile.

    * a variant name (``sky130A``) or alias -> that profile;
    * a family (``gf180``, as the netlist parser reports it) -> the variant
      ``$PDK`` names if it belongs to that family, else the family default;
    * ``None`` -> ``$PDK`` if it is a known variant, else the project default.
    """
    env_pdk = os.environ.get("PDK", "")
    if spec is None:
        if env_pdk and env_pdk in available():
            return _load_file(env_pdk)
        for p in all_profiles():
            if p.data.get("default"):
                return p
        return all_profiles()[0]
    families = {p.family for p in all_profiles()}
    if spec in families:
        if env_pdk in available() and _load_file(env_pdk).family == spec:
            return _load_file(env_pdk)
        return family_default(spec)
    return load(spec)


def for_netlist(text: str, requested: Optional[str] = None) -> PDKProfile:
    """The profile a netlist targets, checked against an explicit request.

    The parser infers the family from ``.lib`` lines or model names. When the
    caller also names a PDK, the two must agree — laying out ``nfet_03v3``
    with the sky130 rules is never what anyone meant.
    """
    from mbg.spice_parser import parse_netlist_with_pdk
    fam = parse_netlist_with_pdk(text)["metadata"]["pdk"]
    detected = fam if fam in {p.family for p in all_profiles()} else None
    if requested:
        prof = resolve(requested)
        if detected and detected != prof.family:
            raise ProfileError(
                f"netlist models belong to {detected!r} but PDK "
                f"{prof.name!r} ({prof.family}) was requested")
        return prof
    if detected is None:
        raise ProfileError(
            "could not tell which PDK this netlist targets: no .lib/.include "
            "and no recognised device model. Pass a PDK explicitly.")
    return resolve(detected)


_LIB_RE = re.compile(r"^\s*\.lib\s+(\S+)\s*$", re.IGNORECASE)


def scan_lib_sections(model_file: os.PathLike) -> List[str]:
    """Section names a SPICE model library defines (``.lib <name>`` lines)."""
    names = []
    with open(model_file, errors="replace") as f:
        for line in f:
            m = _LIB_RE.match(line)
            if m:
                names.append(m.group(1))
    return names
