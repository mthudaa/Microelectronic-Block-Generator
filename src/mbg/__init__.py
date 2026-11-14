"""MBG public basic/intermediate analog-layout tools."""
from importlib import import_module
from mbg import config as config
from mbg.config import ToolError, ensure_pdk_env, pdk_config, repo_root, describe_environment
ensure_pdk_env()
__version__ = "0.3.0"
_LAZY = {'spice_to_gds_with_checks': 'pipeline', 'spice_to_gds_with_checks_ctx': 'pipeline', 'spice_to_gds_ctx': 'pipeline', 'Spec': 'specs', 'SpecResult': 'specs', 'SpecReport': 'specs', 'evaluate_specs': 'specs', 'format_spec_table': 'specs', 'parse_netlist_with_pdk': 'spice_parser', 'build_design_context': 'spice_parser', 'DesignContext': 'design_context', 'Device': 'design_context', 'Net': 'design_context', 'MatchingGroup': 'design_context', 'SymmetryConstraint': 'design_context', 'Placement': 'design_context', 'PinAccessPoint': 'design_context', 'Zone': 'design_context', 'Obstacle': 'design_context', 'Segment': 'design_context', 'Via': 'design_context', 'RoutePlan': 'design_context', 'RoutedNet': 'design_context', 'RoutingFailure': 'design_context', 'PlacementFeedback': 'design_context', 'DRCViolation': 'design_context', 'LVSViolation': 'design_context', 'BoundingBox': 'design_context', 'CongestionMap': 'design_context', 'PDKRules': 'pdk_rules', 'get_rules': 'pdk_rules', 'DEVICES': 'pdk_devices', 'SPICE_MODELS': 'pdk_devices', 'lookup': 'pdk_devices', 'print_catalog': 'pdk_devices', 'PlacementConfig': 'placement_engine', 'place': 'placement_engine', 'place_with_routability': 'placement_engine', 'build_device': 'placement_engine', 'GridRouter': 'router', 'RouterConfig': 'router', 'OccupancyDB': 'router', 'realize': 'router', 'add_power_strips': 'power', 'add_double_guardring': 'power', 'manual_power': 'power', 'run_drc': 'checks', 'run_lvs': 'checks', 'run_pex': 'checks', 'check_tools': 'checks', 'validate_gds': 'checks', 'extract_layout_netlist': 'checks', 'fix_port_order': 'checks', 'run_spice': 'simulation', 'raw_to_csv': 'simulation', 'parse_dat': 'simulation', 'pdk_path': 'simulation', 'Testbench': 'analysis', 'SimResult': 'analysis', 'fft': 'analysis', 'write_all': 'outputs', 'classify_ports': 'outputs', 'OutputSet': 'outputs', 'PortSpec': 'outputs', 'clean_param': 'utils', 'display_gds': 'utils', 'display_component': 'utils', 'GDS_PATH': 'utils', 'SVG_PATH': 'utils'}

def __getattr__(name):
    if name in _LAZY:
        value = getattr(import_module('mbg.' + _LAZY[name]), name)
        globals()[name] = value
        return value
    raise AttributeError(name)

def __dir__():
    return sorted(set(globals()) | set(_LAZY))

__all__ = list(_LAZY) + ['__version__']
