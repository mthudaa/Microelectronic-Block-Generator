"""
GF180MCU Device Catalog — devices supported by gLayout for layout generation.
AI agents use this to discover available devices and their parameters.
"""
import os

# ═══════════════════════════════════════════════════════════════
# Devices with gLayout layout support
# ═══════════════════════════════════════════════════════════════

DEVICES = {
    "nmos": {
        "description": "NMOS transistor (any PDK model: nfet_03v3, nfet_06v0, etc.)",
        "generator": "glayout.nmos(pdk, width, length, fingers, multipliers, ...)",
        "params": {
            "width": "Width in µm (default: 3)",
            "length": "Gate length in µm (default: PDK minimum)",
            "fingers": "Number of gate fingers (default: 1)",
            "multipliers": "Number of identical copies (default: 1)",
            "with_tie": "Add body tie (default: True)",
            "with_dnwell": "Add deep N-well (NMOS only, default: False)",
            "with_substrate_tap": "Add substrate tap (default: True)",
            "with_dummy": "Add dummy gates (default: True)",
        },
        "pins": ["drain (N/E/S/W)", "gate (N/E/S/W)", "source (N/E/S/W)", "body (tie_W)"],
        "note": "Most commonly used with nfet_03v3 (3.3V) model in SPICE",
    },
    "pmos": {
        "description": "PMOS transistor (any PDK model: pfet_03v3, pfet_06v0, etc.)",
        "generator": "glayout.pmos(pdk, width, length, fingers, multipliers, ...)",
        "params": {
            "width": "Width in µm (default: 3)",
            "length": "Gate length in µm (default: PDK minimum)",
            "fingers": "Number of gate fingers (default: 1)",
            "multipliers": "Number of identical copies (default: 1)",
            "with_tie": "Add body tie (default: True)",
            "dnwell": "Deep N-well (PMOS only, default: False)",
            "with_substrate_tap": "Add substrate tap (default: True)",
            "with_dummy": "Add dummy gates (default: True)",
        },
        "pins": ["drain (N/E/S/W)", "gate (N/E/S/W)", "source (N/E/S/W)", "body (tie_W)"],
    },
    "resistor": {
        "description": "Resistor (PDK-parameterized, uses PPOLY/DIFF/etc.)",
        "generator": "glayout.resistor(pdk, width, length, num_series, ...)",
        "params": {
            "width": "Width in µm (default: 5)",
            "length": "Length in µm (default: 1)",
            "num_series": "Number of series segments (default: 1)",
            "multipliers": "Number of copies (default: 1)",
        },
        "pins": ["1", "2"],
    },
    "mimcap": {
        "description": "MIM (Metal-Insulator-Metal) capacitor",
        "generator": "glayout.mimcap(pdk, size=(width, height))",
        "params": {
            "size": "Tuple of (width, height) in µm (default: (5.0, 5.0))",
        },
        "pins": ["1", "2"],
    },
    "mimcap_array": {
        "description": "MIM capacitor array (unit cells)",
        "generator": "glayout.mimcap_array(pdk, rows, columns, size, rmult)",
        "params": {
            "rows": "Number of rows",
            "columns": "Number of columns",
            "size": "Unit cell size (width, height) in µm",
        },
        "pins": ["1", "2"],
    },
    "multiplier": {
        "description": "Multi-finger/multi-device array wrapper",
        "generator": "glayout.multiplier(pdk, sub_component, rows, columns, ...)",
        "params": {
            "component": "Sub-component to array",
            "rows": "Number of rows",
            "columns": "Number of columns",
        },
    },
    "tapring": {
        "description": "Guard ring (substrate/well contact ring)",
        "generator": "glayout.tapring(pdk, enclosed_rectangle, sdlayer, ...)",
        "params": {
            "enclosed_rectangle": "(width, height) of area to enclose",
            "sdlayer": "Diffusion layer: 'p+s/d' (P+) or 'n+s/d' (N+)",
        },
    },
    "via_stack": {
        "description": "Via stack between metal layers",
        "generator": "glayout.via_stack(pdk, glayer1, glayer2, centered=True)",
        "params": {
            "glayer1": "Bottom layer name (e.g. 'met2', 'met3', 'met4')",
            "glayer2": "Top layer name (e.g. 'met4', 'met5')",
        },
    },
    "two_transistor_interdigitized": {
        "description": "Two transistors interdigitated (matched pair)",
        "generator": "glayout.two_transistor_interdigitized(pdk, ...)",
        "note": "Use for differential pair matching",
    },
}

# ═══════════════════════════════════════════════════════════════
# PDK SPICE model names (for simulation netlists)
# ═══════════════════════════════════════════════════════════════

SPICE_MODELS = {
    # MOSFETs
    "nfet_03v3": "3.3V NMOS (standard, most common)",
    "pfet_03v3": "3.3V PMOS (standard, most common)",
    "nfet_06v0": "6.0V NMOS (high voltage)",
    "pfet_06v0": "6.0V PMOS (high voltage)",
    "nfet_03v3_dss": "3.3V NMOS drain-side salicide block",
    "pfet_03v3_dss": "3.3V PMOS drain-side salicide block",
    "nfet_06v0_nvt": "6.0V native NMOS (low Vth)",
    # Capacitors
    "cap_mim_2f0fF": "MIM capacitor 2.0fF/µm² (recommended)",
    "cap_mim_1f5fF": "MIM capacitor 1.5fF/µm²",
    "cap_mim_1f0fF": "MIM capacitor 1.0fF/µm²",
    "cap_nmos_03v3": "3.3V NMOS capacitor",
    "cap_pmos_03v3": "3.3V PMOS capacitor",
    # Resistors
    "ppolyf_u": "Unsilicided P+ poly resistor",
    "npolyf_u": "Unsilicided N+ poly resistor",
    "nwell": "N-well resistor",
    "rm1": "Metal 1 resistor",
    "rm2": "Metal 2 resistor",
    "rm3": "Metal 3 resistor",
    # Diodes
    "diode_nd2ps_03v3": "3.3V N+/Psub diode",
    "diode_pd2nw_03v3": "3.3V P+/Nwell diode",
    # BJTs
    "pnp_10p00x10p00": "VPNP 10×10µm",
    "npn_10p00x10p00": "VNPN 10×10µm",
}


def lookup(name):
    """Look up a device or SPICE model by name."""
    name = name.lower()
    for dev_name, info in DEVICES.items():
        if name in dev_name:
            return ("layout", dev_name, info)
    for model_name, desc in SPICE_MODELS.items():
        if name in model_name.lower():
            return ("spice", model_name, desc)
    return None, None, None


def print_catalog():
    """Print the full device catalog."""
    print("=" * 65)
    print("  gLayout Device Catalog — Layout Generation")
    print("=" * 65)
    for name, info in sorted(DEVICES.items()):
        print(f"\n  {name}")
        print(f"    {info['description']}")
        print(f"    Generator: {info.get('generator', 'N/A')}")
        if "params" in info:
            for p, d in info["params"].items():
                print(f"    • {p}: {d}")

    print(f"\n{'='*65}")
    print("  PDK SPICE Models — for simulation netlists")
    print("=" * 65)
    for name, desc in sorted(SPICE_MODELS.items()):
        print(f"  {name:30s} {desc}")
