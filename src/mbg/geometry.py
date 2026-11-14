"""Pure rectilinear geometry helpers."""
from typing import List, Tuple

def rect_decompose(points: List[Tuple[float, float]]) -> List[Tuple[float, float, float, float]]:
    """Split a rectilinear polygon into rectangles (xmin, ymin, xmax, ymax).

    Horizontal slab decomposition: between consecutive distinct vertex y's,
    the polygon's cross-section is a set of x-intervals (even-odd rule over
    the vertical edges); vertically adjacent slabs with the same interval are
    merged. Exact for rectilinear input, including rings (holes are
    represented in a single boundary with a cut, as GDS stores them).
    """
    pts = [(round(x, 4), round(y, 4)) for x, y in points]
    n = len(pts)
    vedges = []
    for i in range(n):
        (x1, y1), (x2, y2) = pts[i], pts[(i + 1) % n]
        if x1 == x2 and y1 != y2:
            vedges.append((x1, min(y1, y2), max(y1, y2)))
    ys = sorted({y for _, y in pts})
    out: List[Tuple[float, float, float, float]] = []
    open_: Dict[Tuple[float, float], float] = {}
    for y0, y1 in zip(ys, ys[1:]):
        ym = (y0 + y1) / 2.0
        xs = sorted(x for x, lo, hi in vedges if lo < ym < hi)
        intervals = set()
        for k in range(0, len(xs) - 1, 2):
            if xs[k + 1] > xs[k]:
                intervals.add((xs[k], xs[k + 1]))
        for iv in list(open_):
            if iv not in intervals:
                out.append((iv[0], open_.pop(iv), iv[1], y0))
        for iv in intervals:
            open_.setdefault(iv, y0)
    for iv, ystart in open_.items():
        out.append((iv[0], ystart, iv[1], ys[-1]))
    return out
