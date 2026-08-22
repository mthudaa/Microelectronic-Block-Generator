"""Loader for the regression netlists in ``tests/netlists``.

The netlists used to live in a dict inside ``test_all_designs.py``, and the
one that mattered most — the 12-MOS clocked comparator that first exposed
MBG's complexity boundary — lived only inside a notebook cell, where it could
not be run by any test and was lost the moment someone edited the notebook.
They are files now so every test, script and notebook reads the same bytes.

Each file keeps the convention the inline designs used: the model library is
the literal placeholder ``{PDK_LIB}``, resolved against the live ``$PDKPATH``
at load time, so no personal path is ever committed.

    from fixtures import load, load_all, names
    netlist = load("cmp_2stage_clk")
"""

import os
from typing import Dict, List

NETLIST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "netlists")


def pdk_lib() -> str:
    """Path to the ngspice model library of the active PDK."""
    pdkpath = os.environ.get("PDKPATH") or os.path.join(
        os.environ.get("PDK_ROOT", os.path.expanduser("~/.volare")),
        os.environ.get("PDK", "gf180mcuD"))
    return os.path.join(pdkpath, "libs.tech", "ngspice", "sm141064.ngspice")


def names() -> List[str]:
    """Every available netlist name, sorted."""
    return sorted(f[:-6] for f in os.listdir(NETLIST_DIR) if f.endswith(".spice"))


def path(name: str) -> str:
    p = os.path.join(NETLIST_DIR, f"{name}.spice")
    if not os.path.isfile(p):
        raise FileNotFoundError(
            f"no regression netlist named {name!r} in {NETLIST_DIR} "
            f"(have: {', '.join(names())})")
    return p


def load(name: str) -> str:
    """The netlist text with ``{PDK_LIB}`` resolved."""
    with open(path(name)) as fh:
        return fh.read().replace("{PDK_LIB}", pdk_lib())


def load_all() -> Dict[str, str]:
    return {n: load(n) for n in names()}
