#!/usr/bin/env python3
"""Assemble the three reference analog GDS blocks in a chip wrapper.

The source GDS files are selected from the repository's LVS configuration
files.  The generated wrapper is intentionally an assembly/layout container:
it imports the existing child cells, places them inside a 500 um x 1000 um
outline, and creates boundary pin allocation markers.  It does not claim to
route the child pins or to make the resulting wrapper LVS-clean.

Examples
--------
From the repository root::

    python3 scripts/integrate_modules.py
    python3 scripts/integrate_modules.py --output outputs/integration/chip.gds

The default output is ``outputs/integration/mbg_analog_wrapper.gds`` with a
sidecar ``integration_manifest.json``.
"""

from __future__ import annotations

import argparse
import os
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


WRAPPER_WIDTH_UM = 500.0
WRAPPER_HEIGHT_UM = 1000.0

# These are the eleven unique external nets documented in README.md.  The
# request specifies eleven right-side allocation slots, so these names are
# useful defaults for that side.  The README does not assign names to the five
# additional top-side slots; those remain explicit allocation placeholders.
DEFAULT_TOP_PINS = tuple(f"top_pin_{i}" for i in range(1, 6))
DEFAULT_RIGHT_PINS = (
    "vdd",
    "vss",
    "ota_inp",
    "ota_inm",
    "ota_out",
    "ota_vb",
    "cmp_inp",
    "cmp_inm",
    "cmp_out",
    "cmp_vb",
    "vref_out",
)


@dataclass(frozen=True)
class ModuleSpec:
    """One config-driven child GDS and its desired lower-left placement."""

    name: str
    config: Path
    lower_left: tuple[float, float]


MODULE_SPECS = (
    ModuleSpec("comparator_core", Path("lvs_config_comparator_core.json"), (50.0, 100.0)),
    ModuleSpec("ota_5t", Path("lvs_config_ota_5t.json"), (250.0, 100.0)),
    ModuleSpec("vref_1v2", Path("lvs_config_vref_1v2.json"), (150.0, 350.0)),
)


def repository_root() -> Path:
    """Return the worktree root without embedding a machine-specific path."""

    return Path(__file__).resolve().parents[1]


def _expand_config_path(value: str, root: Path) -> Path:
    """Expand config variables, including the repo-local ``UPRJ_ROOT``."""

    variables = {
        "UPRJ_ROOT": str(root),
        "PDK_ROOT": os.environ.get("PDK_ROOT", ""),
        "PDK": os.environ.get("PDK", "gf180mcuD"),
    }
    expanded = value
    for key, replacement in variables.items():
        expanded = expanded.replace(f"${key}", replacement)
    return Path(os.path.expandvars(expanded)).expanduser()


def _load_config(config_path: Path) -> dict[str, Any]:
    try:
        with config_path.open(encoding="utf-8") as handle:
            config = json.load(handle)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"LVS config not found: {config_path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in LVS config {config_path}: {exc}") from exc

    layout_file = config.get("LAYOUT_FILE")
    top_layout = config.get("TOP_LAYOUT")
    if not isinstance(layout_file, str) or not layout_file:
        raise ValueError(f"{config_path} does not define a usable LAYOUT_FILE")
    if not isinstance(top_layout, str) or not top_layout:
        raise ValueError(f"{config_path} does not define TOP_LAYOUT")
    return config


def _fallback_gds_candidates(config: dict[str, Any], root: Path) -> list[Path]:
    """Find preserved GDS alternatives when a historical config path is stale."""

    result_root = root / "AI-Generated-Design-Result"
    top = str(config["TOP_LAYOUT"])
    candidates = [result_root / top / f"{top}.gds"]
    if result_root.is_dir():
        candidates.extend(sorted(result_root.glob(f"*/{top}.gds")))

    # Prefer the original/generated result over a DesignContext regression
    # result when both exist.  This keeps a stale historical config tied to
    # the closest matching experiment while still making the choice visible.
    return sorted(
        dict.fromkeys(candidates),
        key=lambda path: ("designcontext" in path.parent.name.lower(), str(path)),
    )


def resolve_gds(config_path: Path, root: Path) -> tuple[Path, dict[str, Any]]:
    """Resolve the GDS named by an LVS config, with a documented fallback."""

    config = _load_config(config_path)
    configured = _expand_config_path(config["LAYOUT_FILE"], root)
    if configured.is_file():
        return configured.resolve(), {
            "configured_layout": str(configured),
            "resolved_layout": str(configured.resolve()),
            "fallback_used": False,
        }

    for candidate in _fallback_gds_candidates(config, root):
        if candidate.is_file():
            return candidate.resolve(), {
                "configured_layout": str(configured),
                "resolved_layout": str(candidate.resolve()),
                "fallback_used": True,
                "fallback_reason": "configured LAYOUT_FILE does not exist",
            }

    raise FileNotFoundError(
        f"No GDS found for {config_path}. Configured path: {configured}. "
        f"Checked fallbacks: {_fallback_gds_candidates(config, root)}"
    )


def _top_cell(lib: Any, requested_name: str, gds_path: Path) -> Any:
    """Return the configured top cell, rejecting ambiguous imports."""

    matches = [cell for cell in lib.cells if cell.name == requested_name]
    if len(matches) == 1:
        return matches[0]
    if not matches:
        tops = lib.top_level()
        if len(tops) == 1:
            return tops[0]
        names = [cell.name for cell in lib.cells]
        raise ValueError(
            f"TOP_LAYOUT={requested_name!r} is absent from {gds_path}; cells={names}"
        )
    raise ValueError(f"Duplicate top-cell name {requested_name!r} in {gds_path}")


def _bbox_size(cell: Any) -> tuple[float, float]:
    bbox = cell.bounding_box()
    if bbox is None:
        raise ValueError(f"Imported cell {cell.name!r} has no geometry")
    return (bbox[1][0] - bbox[0][0], bbox[1][1] - bbox[0][1])


def _place_at_lower_left(cell: Any, lower_left: tuple[float, float]) -> tuple[float, float]:
    bbox = cell.bounding_box()
    if bbox is None:
        raise ValueError(f"Imported cell {cell.name!r} has no geometry")
    return (lower_left[0] - bbox[0][0], lower_left[1] - bbox[0][1])


def _pdk_pin_layers() -> tuple[tuple[int, int], tuple[int, int]]:
    """Resolve GF180 metal-5 and pin-label layers from the active gLayout PDK."""

    try:
        from glayout import gf180

        return gf180.get_glayer("met5"), gf180.get_glayer("met5_label")
    except Exception as exc:  # pragma: no cover - depends on external PDK env
        raise RuntimeError(
            "GF180 gLayout PDK is required to create wrapper pins. "
            "Run this in the GLdev/IIC-OSIC-TOOLS environment."
        ) from exc


def _add_boundary_pins(
    wrapper: Any,
    top_pins: Iterable[str],
    right_pins: Iterable[str],
    pin_layer: tuple[int, int],
    label_layer: tuple[int, int],
    pin_width: float = 2.0,
    edge_depth: float = 10.0,
) -> list[dict[str, Any]]:
    """Add physical metal-5 edge stubs and labels for the requested slots."""

    import gdstk

    top = tuple(top_pins)
    right = tuple(right_pins)
    if len(top) != 5:
        raise ValueError(f"Expected exactly 5 top pins, got {len(top)}")
    if len(right) != 11:
        raise ValueError(f"Expected exactly 11 right pins, got {len(right)}")
    if len(set(top + right)) != len(top) + len(right):
        raise ValueError("Boundary pin names must be unique")

    allocations: list[dict[str, Any]] = []
    top_pitch = WRAPPER_WIDTH_UM / (len(top) + 1)
    for index, name in enumerate(top, start=1):
        x = top_pitch * index
        wrapper.add(
            gdstk.rectangle(
                (x - pin_width / 2, WRAPPER_HEIGHT_UM - edge_depth),
                (x + pin_width / 2, WRAPPER_HEIGHT_UM),
                layer=pin_layer[0],
                datatype=pin_layer[1],
            )
        )
        wrapper.add(gdstk.Label(name, (x, WRAPPER_HEIGHT_UM), layer=label_layer[0], texttype=label_layer[1]))
        allocations.append({"name": name, "side": "top", "position_um": [x, WRAPPER_HEIGHT_UM]})

    right_pitch = WRAPPER_HEIGHT_UM / (len(right) + 1)
    for index, name in enumerate(right, start=1):
        y = right_pitch * index
        wrapper.add(
            gdstk.rectangle(
                (WRAPPER_WIDTH_UM - edge_depth, y - pin_width / 2),
                (WRAPPER_WIDTH_UM, y + pin_width / 2),
                layer=pin_layer[0],
                datatype=pin_layer[1],
            )
        )
        wrapper.add(gdstk.Label(name, (WRAPPER_WIDTH_UM, y), layer=label_layer[0], texttype=label_layer[1]))
        allocations.append({"name": name, "side": "right", "position_um": [WRAPPER_WIDTH_UM, y]})
    return allocations


def build_wrapper(
    output_gds: Path,
    output_manifest: Path | None = None,
    *,
    root: Path | None = None,
    top_pins: Iterable[str] = DEFAULT_TOP_PINS,
    right_pins: Iterable[str] = DEFAULT_RIGHT_PINS,
) -> dict[str, Any]:
    """Build and write the integrated wrapper; return its manifest."""

    try:
        import gdstk
    except ImportError as exc:  # pragma: no cover - external EDA dependency
        raise RuntimeError("gdstk is required to assemble GDS files") from exc

    root = (root or repository_root()).resolve()
    output_gds = output_gds.resolve()
    output_gds.parent.mkdir(parents=True, exist_ok=True)
    if output_manifest is None:
        output_manifest = output_gds.with_name("integration_manifest.json")
    output_manifest = output_manifest.resolve()
    output_manifest.parent.mkdir(parents=True, exist_ok=True)

    pin_layer, label_layer = _pdk_pin_layers()
    library = gdstk.Library(name="mbg_analog_integration", unit=1e-6, precision=5e-9)
    wrapper = gdstk.Cell("mbg_analog_wrapper")
    library.add(wrapper)

    # Layer 0 is used only for a non-manufacturing outline annotation.  The
    # actual wrapper pin stubs below are resolved GF180 met5 geometry.
    wrapper.add(gdstk.rectangle((0, 0), (WRAPPER_WIDTH_UM, WRAPPER_HEIGHT_UM), layer=0, datatype=0))

    modules: list[dict[str, Any]] = []
    imported_names: set[str] = set()
    for spec in MODULE_SPECS:
        config_path = (root / spec.config).resolve()
        config = _load_config(config_path)
        gds_path, resolution = resolve_gds(config_path, root)
        source_lib = gdstk.read_gds(str(gds_path))
        source_top = _top_cell(source_lib, str(config["TOP_LAYOUT"]), gds_path)
        source_cells = list(source_lib.cells)
        duplicate_names = imported_names.intersection(cell.name for cell in source_cells)
        if duplicate_names:
            raise ValueError(
                f"Cell-name collision while importing {gds_path}: {sorted(duplicate_names)}"
            )
        library.add(*source_cells)
        imported_names.update(cell.name for cell in source_cells)

        origin = _place_at_lower_left(source_top, spec.lower_left)
        wrapper.add(gdstk.Reference(source_top, origin=origin))
        size = _bbox_size(source_top)
        max_x = spec.lower_left[0] + size[0]
        max_y = spec.lower_left[1] + size[1]
        if spec.lower_left[0] < 0 or spec.lower_left[1] < 0 or max_x > WRAPPER_WIDTH_UM or max_y > WRAPPER_HEIGHT_UM:
            raise ValueError(f"{spec.name} does not fit in the requested wrapper: bbox={(spec.lower_left, (max_x, max_y))}")
        modules.append(
            {
                "name": spec.name,
                "config": str(config_path),
                "configured_layout": resolution["configured_layout"],
                "resolved_layout": resolution["resolved_layout"],
                "fallback_used": resolution["fallback_used"],
                "top_cell": source_top.name,
                "lower_left_um": list(spec.lower_left),
                "size_um": list(size),
                "reference_origin_um": list(origin),
            }
        )

    allocations = _add_boundary_pins(wrapper, top_pins, right_pins, pin_layer, label_layer)
    library.write_gds(str(output_gds))

    # Re-open the output so the manifest records what was actually emitted.
    written = gdstk.read_gds(str(output_gds))
    written_wrapper = _top_cell(written, wrapper.name, output_gds)
    bbox = written_wrapper.bounding_box()
    if bbox is None:
        raise ValueError("Generated wrapper has no geometry")
    emitted_size = [bbox[1][0] - bbox[0][0], bbox[1][1] - bbox[0][1]]
    if emitted_size != [WRAPPER_WIDTH_UM, WRAPPER_HEIGHT_UM]:
        raise ValueError(f"Generated wrapper size is {emitted_size}, expected [500.0, 1000.0]")

    manifest: dict[str, Any] = {
        "wrapper_cell": wrapper.name,
        "wrapper_size_um": {"width": WRAPPER_WIDTH_UM, "height": WRAPPER_HEIGHT_UM},
        "gds_path": str(output_gds),
        "manifest_path": str(output_manifest),
        "pdk": "gf180mcuD",
        "pin_layers": {"metal": list(pin_layer), "label": list(label_layer)},
        "pin_allocations": allocations,
        "modules": modules,
        "electrical_routing": "NOT RUN",
        "lvs_status": "NOT RUN",
        "notes": [
            "Existing child GDS cells and labels were imported unchanged.",
            "The layer-0 rectangle is a wrapper-size annotation, not signoff geometry.",
            "Child-to-wrapper interconnect routing is not generated by this assembly script.",
        ],
    }
    output_manifest.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--librelane", action="store_true",
                        help="collect generated modules into a LibreLane macro "
                             "integration (Verilog, config.json, info.yaml, "
                             "lvs_config.json) instead of building a GDS wrapper")
    parser.add_argument("--top", default="mbg_top", help="top-level module name")
    parser.add_argument("--search", action="append",
                        help="directory to search for *.views.json (repeatable)")
    parser.add_argument("--outdir", help="where to write the integration files")
    parser.add_argument("--run", action="store_true",
                        help="invoke LibreLane after generating the configuration")
    parser.add_argument("--title", default="AI-generated analog blocks")
    parser.add_argument("--team", default="D08 Microelectronic Block Generator")
    parser.add_argument("--description", default="")
    parser.add_argument("--discord", default="")
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("outputs/integration/mbg_analog_wrapper.gds"),
        help="Output GDS path (default: %(default)s)",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Optional manifest path (default: beside the output GDS)",
    )
    parser.add_argument(
        "--top-pins",
        nargs=5,
        metavar="PIN",
        default=DEFAULT_TOP_PINS,
        help="Exactly five top allocation names",
    )
    parser.add_argument(
        "--right-pins",
        nargs=11,
        metavar="PIN",
        default=DEFAULT_RIGHT_PINS,
        help="Exactly eleven right allocation names",
    )
    return parser.parse_args(argv)


def _repo_src() -> str:
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, "src")
        if os.path.isdir(os.path.join(cand, "mbg")):
            return cand
        d = os.path.dirname(d)
    raise RuntimeError("could not locate src/mbg")


def _librelane_mode(args) -> int:
    """Collect generated modules into a LibreLane macro integration."""
    import sys as _sys
    _sys.path.insert(0, _repo_src())
    from mbg.integrate import integrate

    root = str(repository_root())
    roots = args.search or [os.path.join(root, "AI-Generated-Design-Result"),
                            os.path.join(root, "outputs")]
    outdir = args.outdir or os.path.join(root, "outputs", "integration")
    res = integrate(args.top, roots, outdir,
                    title=args.title, team=args.team,
                    description=args.description, discord=args.discord,
                    repo_root=root, run=args.run)
    if not res.get("modules"):
        print(f"[INTEGRATE] {res.get('reason')}")
        return 1
    print(f"\n[INTEGRATE] wrote {outdir}/")
    for key in ("top_verilog", "config", "info_yaml", "macros"):
        if res.get(key):
            print(f"    {os.path.basename(res[key])}")
    for c in res.get("lvs_configs", []):
        print(f"    {os.path.basename(c)}")
    ll = res.get("librelane", {})
    print(f"[INTEGRATE] LibreLane: {ll.get('status')}"
          + (f" — {ll.get('reason')}" if ll.get("reason") else ""))
    return 0 if ll.get("status") in ("PASS", "NOT RUN") else 1


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if getattr(args, "librelane", False):
        return _librelane_mode(args)
    args = _parse_args(argv)
    try:
        manifest = build_wrapper(
            args.output,
            args.manifest,
            top_pins=args.top_pins,
            right_pins=args.right_pins,
        )
    except (FileNotFoundError, ImportError, RuntimeError, ValueError) as exc:
        print(f"integration failed: {exc}", file=sys.stderr)
        return 1
    print(f"Wrote wrapper GDS: {manifest['gds_path']}")
    print(f"Wrote manifest:    {manifest['manifest_path']}")
    print("Imported modules:  " + ", ".join(module["name"] for module in manifest["modules"]))
    print("Boundary pins:     5 top + 11 right")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
