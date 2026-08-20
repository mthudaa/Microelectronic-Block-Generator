"""Native GF180MCU passive devices built directly from PDK layers.

Why this module exists
----------------------
gLayout cannot build either passive that this PDK actually recognises:

* ``glayout.resistor()`` is, in its own docstring, "a diode connected pfet
  which acts as a programmable resistor". Magic extracts it as ``pfet_03v3``,
  so a netlist declaring ``ppolyf_u`` can never LVS-match it.
* ``glayout.mimcap()`` builds the MIM between met2 and met3. gf180mcuD's Magic
  tech defines the device as ``mimcc mimcap metal5`` over metal4, so Magic
  recognises nothing at all and the capacitor silently vanishes from the
  extracted netlist.

Both devices here are drawn from raw PDK layers and verified to extract as the
real primitives (``ppolyf_u`` / ``cap_mim_2f0_m4m5_noshield``) with correct
width and length properties, DRC clean.

Layer numbers come from the ``calma`` statements in
``libs.tech/magic/gf180mcuD.tech``; each is cited at the constant.
"""

from typing import Tuple

import gdsfactory as gf

# ── GDS layers (gf180mcuD.tech `calma` statements) ─────────────────────
POLY = (30, 0)       # layer POLY   calma 30 0
PPLUS = (31, 0)      # layer PPLUS  calma 31 0
CONT = (33, 0)       # layer CONT   calma 33 0
MET1 = (34, 0)       # layer MET1   calma 34 0
SBLK = (49, 0)       # layer SBLK   calma 49 0   (salicide block)
RESDEF = (110, 5)    # layer RESDEF calma 110 5  (RES_MK marker)
VIA3 = (40, 0)       # layer VIA3   calma 40 0
VIA4 = (41, 0)       # layer VIA4   calma 41 0
MET3 = (42, 0)       # layer MET3   calma 42 0
MET4 = (46, 0)       # layer MET4   calma 46 0
CAPM = (75, 0)       # layer CAPM   calma 75 0   (MIM top plate)
CAPDEF = (117, 5)    # layer CAPDEF calma 117 5  (MIM device marker)
MET5 = (81, 0)       # layer MET5   calma 81 0

_DIRS = ("N", "E", "S", "W")


# ── poly resistor ──────────────────────────────────────────────────────

RES_MIN_WIDTH = 0.80     # width rpp 800  (PRES.1)
RES_MIN_SPACE = 0.40     # spacing rpp rpp 400 (PRES.2)

_CONT_SIZE = 0.22        # CO.1
_CONT_GAP = 0.22         # PRES.7 lower bound
_CONT_WINDOW = 0.44      # PRES.7 upper bound (res_no_cont)
_POLY_ENC = 0.07         # CO.3, poly overlap of contact >= 0.065
_M1_ENC = 0.10           # M1.3 minimum metal1 area
_PPLUS_SUR = 0.30        # PPLUS surround of rpp (tech comment, line ~749)
_SAB_OVER = 0.20         # SAB/RES_MK wider than the poly it defines


def poly_resistor(width: float = 1.0, length: float = 4.0) -> gf.Component:
    """An unsalicided P+ poly resistor that extracts as ``ppolyf_u``.

    ``width`` and ``length`` are the resistive segment (what Magic reports as
    ``r_width`` / ``r_length``), not the cell outline.

    The contact placement is the subtle part. gf180 checks it from *both*
    sides: ``res_cont_space_min`` fails if a contact is nearer than 0.22 um to
    the salicide block, and ``res_no_cont`` fails if any part of it is beyond
    0.44 um. Both report as "PRES.7", so moving a too-far contact further away
    looks like it should help and never does. The contact is therefore pinned
    to exactly that window rather than derived from a head length.
    """
    if width < RES_MIN_WIDTH:
        raise ValueError(
            f"poly resistor width {width} um < PRES.1 minimum {RES_MIN_WIDTH} um")
    if length <= 0:
        raise ValueError(f"poly resistor length must be positive, got {length}")

    c = gf.Component()
    half_l = length / 2.0
    cont_lo = half_l + _CONT_GAP
    cont_hi = half_l + _CONT_WINDOW          # == cont_lo + _CONT_SIZE
    head_end = cont_hi + _POLY_ENC

    def _box(layer, hx, ylo, yhi):
        c.add_polygon([(-hx, ylo), (hx, ylo), (hx, yhi), (-hx, yhi)], layer=layer)

    _box(POLY, width / 2.0, -head_end, head_end)
    for lay in (SBLK, RESDEF):
        _box(lay, width / 2.0 + _SAB_OVER, -half_l, half_l)
    _box(PPLUS, width / 2.0 + _PPLUS_SUR, -head_end - _PPLUS_SUR,
         head_end + _PPLUS_SUR)

    cs = _CONT_SIZE
    m1_half = cs / 2.0 + _M1_ENC
    for sgn, term in ((1, "p"), (-1, "n")):
        ylo, yhi = sorted((sgn * cont_lo, sgn * cont_hi))
        c.add_polygon([(-cs / 2, ylo), (cs / 2, ylo),
                       (cs / 2, yhi), (-cs / 2, yhi)], layer=CONT)
        c.add_polygon([(-m1_half, ylo - _M1_ENC), (m1_half, ylo - _M1_ENC),
                       (m1_half, yhi + _M1_ENC), (-m1_half, yhi + _M1_ENC)],
                      layer=MET1)
        _add_ports(c, term, (0.0, (ylo + yhi) / 2.0), 2 * m1_half, MET1)

    c.name = f"mbg_ppolyf_u_w{width:g}_l{length:g}".replace(".", "p")
    return c


# ── MIM capacitor ──────────────────────────────────────────────────────

CAP_MIN_SIZE = 5.00      # width *mimcap 5000 (MIMTM.8a)

_M4_SUR = 0.60           # surround *mimcap m4 600  (MIMTM.3)
_MIM_KEEPOUT = 1.20      # mim_bottom_plate_space: unrelated m4 must clear 1.2
_VIA_SUR = 0.39          # surround mimcc mimcap 390
_VIA_SIZE = 0.28         # width mimcapc/m5 280
_VIA_SPACE = 0.36
_VIA3_SIZE = 0.26        # VIA3 squares-grid 10 260 260
_CAPDEF_G = 0.20         # cifoutput grows CAPDEF 200 beyond the plate
_M5_MIN_W = 0.44         # width *m5 440 (MT.1)
_PAD = 0.60              # landing pad for the via stack down to met3


def mim_cap(size: float = 5.0) -> gf.Component:
    """A metal4/metal5 MIM that extracts as ``cap_mim_2f0_m4m5_noshield``.

    ``size`` is the square top-plate edge in um; the PDK enforces a 5 um
    minimum (MIMTM.8a), which is unusually large and a common surprise.

    Both terminals are brought out on **met3**, and the cell owns every piece
    of met4/met5 geometry near the device. That is deliberate: Magic derives
    the bottom plate as ``bloat-all *mim *m4`` — the whole *connected* metal4
    shape — and then requires any unrelated metal4 to stand 1.2 um clear of
    it. A router that reaches the plates directly on met4/met5 therefore
    trips MIMTM.1/MIMTM.3 no matter how careful it is, so it is given met3
    pads placed outside the keep-out instead.
    """
    if size < CAP_MIN_SIZE:
        raise ValueError(
            f"MIM top plate {size} um < MIMTM.8a minimum {CAP_MIN_SIZE} um")

    c = gf.Component()
    h = size / 2.0
    bot_h = h + _M4_SUR                      # bottom-plate half-extent

    def _rect(layer, x0, y0, x1, y1):
        c.add_polygon([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], layer=layer)

    def _sq(layer, half):
        _rect(layer, -half, -half, half, half)

    _sq(CAPM, h)                    # top plate
    _sq(CAPDEF, h + _CAPDEF_G)      # device marker

    # ── VIA4 array on the top plate, kept _VIA_SUR inside its edge ──
    usable = size - 2 * _VIA_SUR
    pitch = _VIA_SIZE + _VIA_SPACE
    n = max(1, int((usable + _VIA_SPACE) // pitch))
    span = (n - 1) * pitch
    for i in range(n):
        for j in range(n):
            x, y = -span / 2 + i * pitch, -span / 2 + j * pitch
            _rect(VIA4, x - _VIA_SIZE / 2, y - _VIA_SIZE / 2,
                  x + _VIA_SIZE / 2, y + _VIA_SIZE / 2)

    # ── bottom plate ("n"): met4 square + tab to the RIGHT ──
    tab_x1 = bot_h + _MIM_KEEPOUT
    _sq(MET4, bot_h)
    _rect(MET4, bot_h, -_PAD / 2, tab_x1, _PAD / 2)
    n_pad = (tab_x1 - _PAD / 2, 0.0)
    _via_stack(c, n_pad, VIA3, MET4, MET3)

    # ── top plate ("p"): met5 over the plate + strap to the LEFT ──
    # The strap's met4 landing must clear the bottom plate by _MIM_KEEPOUT,
    # because that pad is "unrelated metal4" as far as MIMTM.1 is concerned.
    strap_w = max(_M5_MIN_W, _PAD)
    pad_x1 = -(bot_h + _MIM_KEEPOUT)
    pad_x0 = pad_x1 - _PAD
    _sq(MET5, h)
    _rect(MET5, pad_x0, -strap_w / 2, -h, strap_w / 2)
    p_pad = (pad_x0 + _PAD / 2, 0.0)
    _rect(MET4, p_pad[0] - _PAD / 2, -_PAD / 2, p_pad[0] + _PAD / 2, _PAD / 2)
    _via_stack(c, p_pad, VIA4, MET5, MET4)
    _via_stack(c, p_pad, VIA3, MET4, MET3)

    _add_ports(c, "p", p_pad, _PAD, MET3)
    _add_ports(c, "n", n_pad, _PAD, MET3)

    c.name = f"mbg_cap_mim_{size:g}".replace(".", "p")
    return c


def _via_stack(c, center, via_layer, upper, lower) -> None:
    """One via plus its two landing pads, centred on `center`."""
    x, y = center
    vs = _VIA_SIZE if via_layer == VIA4 else _VIA3_SIZE
    for lay in (upper, lower):
        c.add_polygon([(x - _PAD / 2, y - _PAD / 2), (x + _PAD / 2, y - _PAD / 2),
                       (x + _PAD / 2, y + _PAD / 2), (x - _PAD / 2, y + _PAD / 2)],
                      layer=lay)
    c.add_polygon([(x - vs / 2, y - vs / 2), (x + vs / 2, y - vs / 2),
                   (x + vs / 2, y + vs / 2), (x - vs / 2, y + vs / 2)],
                  layer=via_layer)


# ── shared port helper ─────────────────────────────────────────────────

def _add_ports(c: gf.Component, term: str, center: Tuple[float, float],
               width: float, layer) -> None:
    """Add one port per compass direction for a terminal.

    The router picks whichever side it can reach, exactly as it does for the
    gLayout MOS ports (`multiplier_0_drain_N` and friends), so the naming
    convention has to match: ``<terminal>_<N|E|S|W>``.
    """
    x, y = center
    orient = {"N": 90.0, "E": 0.0, "S": 270.0, "W": 180.0}
    for d in _DIRS:
        c.add_port(name=f"{term}_{d}", center=(x, y), width=width,
                   orientation=orient[d], layer=layer)
