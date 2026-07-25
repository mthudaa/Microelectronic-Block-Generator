import numpy as np
if not hasattr(np, 'float_'):
    np.float_ = np.float64

from core.utils import clean_param, display_gds, display_component, GDS_PATH, SVG_PATH
from core.routing import (
    MemoryMap, set_pdk, get_pdk,
    draw_trace, place_via, find_clear_midpoint,
    decompose_mst, route_I, route_L, route_Z, route_U,
    manual_route,
    auto_router, H_LAYERS, L_M3, L_M4, L_M5, MIN_SPACING,
    get_net_distance, get_net_constraint,
)
from core.placement import (
    placement, manual_placement, petakan_koneksi_net,
    _get_all_ports, _get_first_port, buat_daftar_koneksi,
)
from glayout import nmos, pmos, resistor, mimcap, mimcap_array, multiplier, tapring, via_stack
from core.power import add_power_strips, add_double_guardring, manual_power
from core.pipeline import spice_to_gds, llm_to_gds, generate_netlist_from_prompt
from core.checks import run_drc, run_lvs, run_pex, check_tools, validate_gds, extract_layout_netlist, fix_port_order
from core.simulation import run_spice, raw_to_csv, parse_dat, pdk_path
from core.spice_parser import parse_netlist_with_pdk
from core.pdk_devices import DEVICES, SPICE_MODELS, lookup, print_catalog