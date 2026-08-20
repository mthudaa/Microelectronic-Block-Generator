"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Centralised PDK design-rule abstraction.

Wraps a glayout ``MappedPDK`` so that placement, routing and verification
never hardcode GDS layer numbers, metal widths, spacings, via sizes or
enclosures.  Every value returned here comes from the PDK itself
(``get_glayer`` / ``get_grule`` / ``grid_size``); nothing is invented.

This module deliberately *wraps* rather than *duplicates* the PDK: if
glayout already knows a rule we ask it, and we only supply a documented
fallback when the PDK genuinely has no rule for the query.
"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

# Routing metal stack, bottom → top.  Names are glayout glayer names; the
# concrete GDS layers are resolved from the PDK at runtime.
DEFAULT_METALS = ["met1", "met2", "met3", "met4", "met5"]

# Via glayer between consecutive metals (index i connects METALS[i] → METALS[i+1]).
DEFAULT_VIAS = ["via1", "via2", "via3", "via4"]

# Preferred routing direction per metal.  Analog convention used by this
# project: odd metals horizontal, even metals vertical.  Overridable.
DEFAULT_DIRECTIONS = {
    "met1": "H", "met2": "V", "met3": "H", "met4": "V", "met5": "H",
}


@dataclass
class LayerInfo:
    """Everything the router needs to know about one routing metal."""
    name: str
    gds_layer: int
    gds_datatype: int
    min_width: float
    min_spacing: float
    direction: str          # "H" | "V"
    index: int              # position in the metal stack, 0 = met1

    @property
    def layer_tuple(self) -> Tuple[int, int]:
        return (self.gds_layer, self.gds_datatype)


@dataclass
class ViaInfo:
    """Everything the router needs to know about one via cut layer."""
    name: str
    lower: str
    upper: str
    cut_width: float
    cut_spacing: float
    enclosure_lower: float
    enclosure_upper: float

    def min_pad(self) -> float:
        """Smallest legal metal pad width around this via (both directions)."""
        return self.cut_width + 2.0 * max(self.enclosure_lower, self.enclosure_upper)


class PDKRules:
    """Design-rule facade over a glayout MappedPDK.

    All queries are cached, because ``get_grule`` is a pydantic-validated
    call and the router asks for the same rules thousands of times.
    """

    def __init__(self, pdk, metals: Optional[List[str]] = None,
                 vias: Optional[List[str]] = None,
                 directions: Optional[Dict[str, str]] = None):
        self.pdk = pdk
        self.metals = list(metals or DEFAULT_METALS)
        self.vias = list(vias or DEFAULT_VIAS)
        self._directions = dict(directions or DEFAULT_DIRECTIONS)
        self._layer_cache: Dict[str, LayerInfo] = {}
        self._via_cache: Dict[str, ViaInfo] = {}
        self._build()

    # ── construction ────────────────────────────────────────────────
    def _grule(self, a, b=None) -> dict:
        try:
            return self.pdk.get_grule(a, b) if b else self.pdk.get_grule(a)
        except Exception:
            return {}

    def _build(self):
        for i, m in enumerate(self.metals):
            try:
                gds = self.pdk.get_glayer(m)
            except Exception:
                continue
            r = self._grule(m)
            self._layer_cache[m] = LayerInfo(
                name=m,
                gds_layer=int(gds[0]),
                gds_datatype=int(gds[1]) if len(gds) > 1 else 0,
                min_width=float(r.get("min_width", 0.28)),
                min_spacing=float(r.get("min_separation", 0.3)),
                direction=self._directions.get(m, "H" if i % 2 == 0 else "V"),
                index=i,
            )
        for i, v in enumerate(self.vias):
            if i + 1 >= len(self.metals):
                break
            lower, upper = self.metals[i], self.metals[i + 1]
            r = self._grule(v)
            if not r:
                continue
            self._via_cache[v] = ViaInfo(
                name=v, lower=lower, upper=upper,
                cut_width=float(r.get("width", 0.26)),
                cut_spacing=float(r.get("min_separation", 0.36)),
                enclosure_lower=float(self._grule(v, lower).get("min_enclosure", 0.12)),
                enclosure_upper=float(self._grule(v, upper).get("min_enclosure", 0.12)),
            )

    # ── layer queries ───────────────────────────────────────────────
    def layer(self, name: str) -> LayerInfo:
        if name not in self._layer_cache:
            raise KeyError(f"{name!r} is not a routing metal in this PDK "
                           f"(known: {list(self._layer_cache)})")
        return self._layer_cache[name]

    def has_layer(self, name: str) -> bool:
        return name in self._layer_cache

    def layer_tuple(self, name: str) -> Tuple[int, int]:
        return self.layer(name).layer_tuple

    def gds_layer(self, name: str) -> int:
        return self.layer(name).gds_layer

    def name_of_gds(self, gds_layer: int) -> Optional[str]:
        for n, li in self._layer_cache.items():
            if li.gds_layer == gds_layer:
                return n
        return None

    def min_width(self, layer: str) -> float:
        return self.layer(layer).min_width

    def min_spacing(self, layer: str, other_layer: Optional[str] = None) -> float:
        """Same-layer spacing.  Different metals never interact laterally,
        so a cross-layer query returns 0."""
        if other_layer is not None and other_layer != layer:
            return 0.0
        return self.layer(layer).min_spacing

    def preferred_direction(self, layer: str) -> str:
        return self.layer(layer).direction

    def routing_width(self, layer: str, multiplier: float = 1.0) -> float:
        """Default conductor width for a layer: min_width, optionally widened."""
        return self.snap(self.layer(layer).min_width * multiplier)

    # ── via queries ─────────────────────────────────────────────────
    def via_between(self, lower: str, upper: str) -> Optional[ViaInfo]:
        """The single via cut directly connecting two adjacent metals."""
        for v in self._via_cache.values():
            if (v.lower, v.upper) == (lower, upper) or (v.lower, v.upper) == (upper, lower):
                return v
        return None

    def via_stack_between(self, lower: str, upper: str) -> List[ViaInfo]:
        """All via cuts traversed when stacking from ``lower`` to ``upper``."""
        if lower == upper:
            return []
        li, ui = self.layer(lower).index, self.layer(upper).index
        lo, hi = min(li, ui), max(li, ui)
        out = []
        for i in range(lo, hi):
            v = self.via_between(self.metals[i], self.metals[i + 1])
            if v:
                out.append(v)
        return out

    def via_spacing(self, via: ViaInfo) -> float:
        return via.cut_spacing

    def via_enclosure(self, via: ViaInfo, layer: str) -> float:
        if layer == via.lower:
            return via.enclosure_lower
        if layer == via.upper:
            return via.enclosure_upper
        return max(via.enclosure_lower, via.enclosure_upper)

    def via_footprint(self, lower: str, upper: str) -> float:
        """Worst-case metal pad size needed for a stack from lower→upper.

        Used by the router to reserve occupancy on *every* metal the stack
        passes through, which is what prevents two different nets dropping
        overlapping via stacks onto the same spot.
        """
        stack = self.via_stack_between(lower, upper)
        if not stack:
            return self.min_width(lower)
        return max(v.min_pad() for v in stack)

    def layers_traversed(self, lower: str, upper: str) -> List[str]:
        """Every metal a via stack from lower→upper occupies, inclusive."""
        li, ui = self.layer(lower).index, self.layer(upper).index
        lo, hi = min(li, ui), max(li, ui)
        return self.metals[lo:hi + 1]

    # ── grid ────────────────────────────────────────────────────────
    def manufacturing_grid(self) -> float:
        return float(getattr(self.pdk, "grid_size", 0.005) or 0.005)

    def snap_grid(self) -> float:
        """The grid every emitted coordinate is placed on (§54).

        Deliberately 2x the manufacturing grid, because the output stage runs
        gLayout's ``component_snap_to_grid`` which snaps to 2x.  Emitting
        coordinates on the 1x grid means that final snap can move the two
        edges of a wire in opposite directions and turn a legal 0.28um
        conductor into an illegal 0.27um one — Magic reported exactly that as
        "Metal3 width < 0.28um".  Placing geometry on the coarser grid to
        begin with makes the final snap a no-op.
        """
        return 2.0 * self.manufacturing_grid()

    def snap(self, value: float) -> float:
        """Snap one coordinate to the output grid (§54)."""
        g = self.snap_grid()
        return round(round(value / g) * g, 6)

    def snap_xy(self, x: float, y: float) -> Tuple[float, float]:
        return self.snap(x), self.snap(y)

    # ── misc ────────────────────────────────────────────────────────
    def max_metal_separation(self) -> float:
        try:
            return float(self.pdk.util_max_metal_seperation())
        except Exception:
            return max(li.min_spacing for li in self._layer_cache.values())

    def summary(self) -> str:
        lines = [f"PDKRules({getattr(self.pdk, 'name', '?')}) grid={self.manufacturing_grid()}"]
        for m in self.metals:
            if m in self._layer_cache:
                li = self._layer_cache[m]
                lines.append(f"  {li.name:5s} gds={li.gds_layer:3d} w>={li.min_width:.3f} "
                             f"s>={li.min_spacing:.3f} dir={li.direction}")
        for v in self._via_cache.values():
            lines.append(f"  {v.name:5s} {v.lower}->{v.upper} cut={v.cut_width:.3f} "
                         f"sep={v.cut_spacing:.3f} enc={v.enclosure_lower:.3f}/{v.enclosure_upper:.3f}")
        return "\n".join(lines)


_RULES_CACHE: Dict[int, PDKRules] = {}


def get_rules(pdk) -> PDKRules:
    """Cached PDKRules for a given MappedPDK instance."""
    key = id(pdk)
    if key not in _RULES_CACHE:
        _RULES_CACHE[key] = PDKRules(pdk)
    return _RULES_CACHE[key]
