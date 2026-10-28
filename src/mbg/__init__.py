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
    mbg.simulation     ngspice transport (run a deck, get files back)
    mbg.analysis       op / dc / ac / tran / Monte Carlo / FFT
    mbg.outputs        LEF / Liberty / Verilog views for integration
    mbg.llm            natural language -> SPICE
    mbg.specs          target specs, evaluation, degradation analysis
    mbg.flow           the two-loop design flow (pre-layout + PEX-aware)
    mbg.flow_runtime   real ngspice/Magic/netgen hooks for that flow
    mbg.pipeline       the flows that tie the above together

`mbg.placement` and `mbg.routing` are the superseded first-generation
implementations. They are kept working for backward compatibility; new work
should use `mbg.placement_engine` and `mbg.router`.
"""

# ── environment first, imports second ─────────────────────────────────
# gLayout reads PDK_ROOT at *import* time and calls Path() on it, so importing
# anything from this package with the variable unset used to fail as
#     TypeError: expected str, bytes or os.PathLike object, not NoneType
# raised inside glayout/pdk/sky130_mapped.py — a traceback that names neither
# the PDK nor the missing variable. Populating the environment here, before
# any stage module (and so gLayout) is loaded, is what keeps that from happening.
from mbg import config as config           # noqa: E402  (must precede glayout)
from mbg.config import (                   # noqa: E402
    ToolError, ensure_pdk_env, pdk_config, repo_root,
    resolve_magic, resolve_netgen, resolve_klayout, describe_environment,
)

ensure_pdk_env()

import numpy as _np                        # noqa: E402

if not hasattr(_np, "float_"):          # gdsfactory 7 expects the numpy 1 alias
    _np.float_ = _np.float64

# ── lazy public API ───────────────────────────────────────────────────
# Every name below used to be imported eagerly, which made `import mbg` pull
# in gLayout + gdsfactory even for callers that only wanted `Spec`, the PDK
# profiles or the agent CLI. They now load on first attribute access
# (PEP 562), so `from mbg import Spec` works without the layout stack and
# `from mbg import spice_to_gds_with_checks` behaves exactly as before.
_LAZY = {
    # mbg.pipeline
    "spice_to_gds_with_checks": "pipeline",
    "spice_to_gds_with_checks_ctx": "pipeline",
    "spice_to_gds_with_checks_legacy": "pipeline",
    "spice_to_gds": "pipeline",
    "spice_to_gds_ctx": "pipeline",
    # mbg.llm
    "llm_to_gds": "llm",
    "generate_netlist_from_prompt": "llm",
    # mbg.specs
    "Spec": "specs",
    "SpecResult": "specs",
    "SpecReport": "specs",
    "Degradation": "specs",
    "evaluate_specs": "specs",
    "compare_degradation": "specs",
    "format_spec_table": "specs",
    # mbg.flow
    "DesignFlow": "flow",
    "DesignPoint": "flow",
    "FlowConfig": "flow",
    "FlowHooks": "flow",
    "FlowResult": "flow",
    "LayoutResult": "flow",
    "IterationRecord": "flow",
    "Stage": "flow",
    "Outcome": "flow",
    "Failure": "flow",
    "run_flow": "flow",
    # mbg.flow_runtime
    "make_hooks": "flow_runtime",
    "measure_ac_metrics": "flow_runtime",
    "scale_device_widths": "flow_runtime",
    "default_tune_pre": "flow_runtime",
    "default_tune_post": "flow_runtime",
    # mbg.spice_parser
    "parse_netlist_with_pdk": "spice_parser",
    "build_design_context": "spice_parser",
    # mbg.design_context
    "DesignContext": "design_context",
    "Device": "design_context",
    "Net": "design_context",
    "MatchingGroup": "design_context",
    "SymmetryConstraint": "design_context",
    "Placement": "design_context",
    "PinAccessPoint": "design_context",
    "Zone": "design_context",
    "Obstacle": "design_context",
    "Segment": "design_context",
    "Via": "design_context",
    "RoutePlan": "design_context",
    "RoutedNet": "design_context",
    "RoutingFailure": "design_context",
    "PlacementFeedback": "design_context",
    "DRCViolation": "design_context",
    "LVSViolation": "design_context",
    "BoundingBox": "design_context",
    "CongestionMap": "design_context",
    # mbg.pdk_rules
    "PDKRules": "pdk_rules",
    "get_rules": "pdk_rules",
    # mbg.pdk_devices
    "DEVICES": "pdk_devices",
    "SPICE_MODELS": "pdk_devices",
    "lookup": "pdk_devices",
    "print_catalog": "pdk_devices",
    # mbg.placement_engine
    "PlacementConfig": "placement_engine",
    "place": "placement_engine",
    "place_with_routability": "placement_engine",
    "build_device": "placement_engine",
    # mbg.router
    "GridRouter": "router",
    "RouterConfig": "router",
    "OccupancyDB": "router",
    "realize": "router",
    # mbg.power
    "add_power_strips": "power",
    "add_double_guardring": "power",
    "manual_power": "power",
    # mbg.checks
    "run_drc": "checks",
    "run_lvs": "checks",
    "run_pex": "checks",
    "check_tools": "checks",
    "validate_gds": "checks",
    "extract_layout_netlist": "checks",
    "fix_port_order": "checks",
    # mbg.simulation
    "run_spice": "simulation",
    "raw_to_csv": "simulation",
    "parse_dat": "simulation",
    "pdk_path": "simulation",
    # mbg.analysis
    "Testbench": "analysis",
    "SimResult": "analysis",
    "MonteCarloResult": "analysis",
    "fft": "analysis",
    # mbg.outputs
    "write_all": "outputs",
    "classify_ports": "outputs",
    "OutputSet": "outputs",
    "PortSpec": "outputs",
    # mbg.utils
    "clean_param": "utils",
    "display_gds": "utils",
    "display_component": "utils",
    "GDS_PATH": "utils",
    "SVG_PATH": "utils",
    # mbg.placement
    "placement": "placement",
    "manual_placement": "placement",
    # mbg.routing
    "auto_router": "routing",
    "manual_route": "routing",
    "set_pdk": "routing",
    "get_pdk": "routing",
}


def __getattr__(name):
    mod = _LAZY.get(name)
    if mod is not None:
        import importlib
        value = getattr(importlib.import_module(f"mbg.{mod}"), name)
        globals()[name] = value
        return value
    if not name.startswith("__"):
        import importlib
        try:
            module = importlib.import_module(f"mbg.{name}")
        except ModuleNotFoundError as exc:
            if exc.name != f"mbg.{name}":
                raise
        else:
            return module
    raise AttributeError(f"module 'mbg' has no attribute {name!r}")


def __dir__():
    return sorted(set(globals()) | set(_LAZY))


__version__ = "0.2.0"

__all__ = [
    # design flow (two loops: pre-layout, then PEX-aware)
    "Spec", "SpecResult", "SpecReport", "Degradation",
    "evaluate_specs", "compare_degradation", "format_spec_table",
    "DesignFlow", "DesignPoint", "FlowConfig", "FlowHooks", "FlowResult",
    "LayoutResult", "IterationRecord", "Stage", "Outcome", "Failure",
    "run_flow", "make_hooks", "measure_ac_metrics", "scale_device_widths",
    "default_tune_pre", "default_tune_post",

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
    "Testbench", "SimResult", "MonteCarloResult", "fft",
    "write_all", "classify_ports", "OutputSet", "PortSpec",
    # helpers
    "clean_param", "display_gds", "display_component", "GDS_PATH", "SVG_PATH",
    # superseded
    "placement", "manual_placement", "auto_router", "manual_route",
    "set_pdk", "get_pdk",
    "__version__",
]
