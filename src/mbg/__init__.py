"""Microelectronic Block Generator — SPICE to DRC-clean GDSII for analog blocks.

Built on gLayout + gdsfactory, targeting the GF180MCU PDK.

Quick start
-----------
    from mbg import spice_to_gds_with_checks
    r = spice_to_gds_with_checks(netlist)
    r["gds_path"], r["drc"], r["lvs"], r["pex"], r["all_pass"]

The package is organised by pipeline stage. Import the stage you need rather
than reaching for internals:

    mbg.spice_parser   SPICE -> logical design + constraints
    mbg.design_context DesignContext, shared by every stage
    mbg.pdk_rules      layer / width / spacing / via rules, read from the PDK
    mbg.placement_engine   analog-aware placement
    mbg.router         DRC-aware grid router
    mbg.connectivity   internal OPEN / SHORT verification
    mbg.checks         Magic DRC, netgen LVS, PEX
    mbg.simulation     ngspice
    mbg.llm            natural language -> SPICE
    mbg.pipeline       the flows that tie the above together

`mbg.placement` and `mbg.routing` are the superseded first-generation
implementations. They are kept working for backward compatibility; new work
should use `mbg.placement_engine` and `mbg.router`.
"""

import numpy as _np

if not hasattr(_np, "float_"):          # gdsfactory 7 expects the numpy 1 alias
    _np.float_ = _np.float64

# ── the flows ─────────────────────────────────────────────────────────
from mbg.pipeline import (
    spice_to_gds_with_checks,       # primary entry point: SPICE -> GDS + DRC/LVS/PEX
    spice_to_gds_with_checks_ctx,   # same, explicit about using the DesignContext flow
    spice_to_gds_with_checks_legacy,
    spice_to_gds,                   # layout only, no signoff
    spice_to_gds_ctx,
)
from mbg.llm import llm_to_gds, generate_netlist_from_prompt

# ── design description ────────────────────────────────────────────────
from mbg.spice_parser import parse_netlist_with_pdk, build_design_context
from mbg.design_context import (
    DesignContext, Device, Net, MatchingGroup, SymmetryConstraint,
    Placement, PinAccessPoint, Zone, Obstacle, Segment, Via, RoutePlan,
    RoutedNet, RoutingFailure, PlacementFeedback, DRCViolation, LVSViolation,
    BoundingBox, CongestionMap,
)

# ── technology ────────────────────────────────────────────────────────
from mbg.pdk_rules import PDKRules, get_rules
from mbg.pdk_devices import DEVICES, SPICE_MODELS, lookup, print_catalog

# ── physical implementation ───────────────────────────────────────────
from mbg.placement_engine import (
    PlacementConfig, place, place_with_routability, build_device,
)
from mbg.router import GridRouter, RouterConfig, OccupancyDB, realize
from mbg.power import add_power_strips, add_double_guardring, manual_power

# ── verification ──────────────────────────────────────────────────────
from mbg import connectivity
from mbg.checks import (
    run_drc, run_lvs, run_pex, check_tools, validate_gds,
    extract_layout_netlist, fix_port_order,
)
from mbg.simulation import run_spice, raw_to_csv, parse_dat, pdk_path

# ── helpers ───────────────────────────────────────────────────────────
from mbg.utils import clean_param, display_gds, display_component, GDS_PATH, SVG_PATH

# ── superseded, kept working ──────────────────────────────────────────
from mbg.placement import placement, manual_placement
from mbg.routing import auto_router, manual_route, set_pdk, get_pdk

__version__ = "0.2.0"

__all__ = [
    # flows
    "spice_to_gds_with_checks", "spice_to_gds_with_checks_ctx",
    "spice_to_gds_with_checks_legacy", "spice_to_gds", "spice_to_gds_ctx",
    "llm_to_gds", "generate_netlist_from_prompt",
    # design description
    "parse_netlist_with_pdk", "build_design_context", "DesignContext",
    "Device", "Net", "MatchingGroup", "SymmetryConstraint", "Placement",
    "PinAccessPoint", "Zone", "Obstacle", "Segment", "Via", "RoutePlan",
    "RoutedNet", "RoutingFailure", "PlacementFeedback", "DRCViolation",
    "LVSViolation", "BoundingBox", "CongestionMap",
    # technology
    "PDKRules", "get_rules", "DEVICES", "SPICE_MODELS", "lookup", "print_catalog",
    # physical
    "PlacementConfig", "place", "place_with_routability", "build_device",
    "GridRouter", "RouterConfig", "OccupancyDB", "realize",
    "add_power_strips", "add_double_guardring", "manual_power",
    # verification
    "connectivity", "run_drc", "run_lvs", "run_pex", "check_tools",
    "validate_gds", "extract_layout_netlist", "fix_port_order",
    "run_spice", "raw_to_csv", "parse_dat", "pdk_path",
    # helpers
    "clean_param", "display_gds", "display_component", "GDS_PATH", "SVG_PATH",
    # superseded
    "placement", "manual_placement", "auto_router", "manual_route",
    "set_pdk", "get_pdk",
    "__version__",
]
