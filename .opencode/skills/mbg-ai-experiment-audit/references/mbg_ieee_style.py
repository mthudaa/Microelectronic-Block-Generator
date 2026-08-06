"""IEEE-compliant Matplotlib styling for Microelectronic Block Generator plots.

@Owner: Moh. Jabir Mubarok (AI/LLM Integration & Software Architect)
@Standard: IEEE_REPORT_STYLE.md (same directory)

Applies the geometry, typography, line-style, and export rules defined by the
project IEEE presentation standard. Presentation only -- this module does not
run, interpret, or modify any simulation.

Usage
-----
    from mbg_ieee_style import use_ieee_style, new_figure, save_figure

    use_ieee_style()
    fig, ax = new_figure(columns=1)
    ax.semilogx(freq, gain_db, **trace(0), label="Pre-layout")
    ax.semilogx(freq, gain_db_post, **trace(1), label="Post-layout")
    ax.set_xlabel("Frequency (Hz)")
    ax.set_ylabel("Gain (dB)")
    ax.legend()
    save_figure(fig, "ota_5t", "ac", "pre")
"""

from __future__ import annotations

import os
import warnings

import matplotlib
import matplotlib.pyplot as plt
from matplotlib import font_manager

__all__ = [
    "COLUMN_WIDTH_IN",
    "PAGE_WIDTH_IN",
    "MAX_FIGURE_HEIGHT_IN",
    "OKABE_ITO",
    "use_ieee_style",
    "new_figure",
    "trace",
    "annotate_measurement",
    "save_figure",
    "figure_filename",
]

# -- Section 3.1: geometry ------------------------------------------------

COLUMN_WIDTH_IN = 3.5      # IEEE single column, 88.9 mm
PAGE_WIDTH_IN = 7.16       # IEEE double column, 181.6 mm
DEFAULT_ASPECT = 0.68      # height / width, keeps a 3.5 x 2.38 in single column
MAX_FIGURE_HEIGHT_IN = 8.8  # usable text height of an IEEE two-column page

# -- Section 3.6: colorblind-safe palette (Okabe-Ito) ---------------------

OKABE_ITO = [
    "#000000",  # black
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#009E73",  # bluish green
    "#CC79A7",  # reddish purple
    "#E69F00",  # orange
    "#56B4E9",  # sky blue
]

_LINE_STYLES = [
    "-",                    # solid
    (0, (4, 1.5)),          # dashed
    (0, (4, 1.5, 1, 1.5)),  # dash-dot
    (0, (1, 1.5)),          # dotted
    (0, (7, 2)),            # long dash
    (0, (4, 1.5, 1, 1.5, 1, 1.5)),
    (0, (2, 1)),
]

_MARKERS = ["", "o", "s", "^", "D", "v", "P"]

# -- Section 3.3: typography ----------------------------------------------

_SERIF_PREFERENCE = [
    "Times New Roman",
    "Nimbus Roman",
    "Liberation Serif",
    "FreeSerif",
    "DejaVu Serif",
]


def _available_serif() -> list[str]:
    """Return the preferred serif families that actually exist on this host.

    Times New Roman is the IEEE preference but is frequently absent inside
    containers. Nimbus Roman and Liberation Serif are metric-compatible
    substitutes; DejaVu Serif is the guaranteed Matplotlib fallback.
    """
    installed = {f.name for f in font_manager.fontManager.ttflist}
    found = [name for name in _SERIF_PREFERENCE if name in installed]

    if not found:
        warnings.warn(
            "No preferred serif font found; falling back to the Matplotlib "
            "default. Figures will render but will not match the IEEE "
            "typographic specification.",
            RuntimeWarning,
            stacklevel=2,
        )
        return list(_SERIF_PREFERENCE)

    if found[0] not in ("Times New Roman", "Nimbus Roman", "Liberation Serif"):
        warnings.warn(
            f"Using '{found[0]}' instead of a Times-metric serif. Acceptable "
            "for review drafts; install Liberation Serif or Nimbus Roman "
            "before producing a submission figure.",
            RuntimeWarning,
            stacklevel=2,
        )

    return found + list(_SERIF_PREFERENCE)


def use_ieee_style(base_font_pt: float = 8.0) -> None:
    """Apply the project IEEE rcParams globally.

    Args:
        base_font_pt: Axis-label size at final print size. Section 3.3 sets
            8 pt. Values below 6 pt are rejected because no text in an IEEE
            figure may fall below 6 pt at final size.

    Raises:
        ValueError: If base_font_pt would put tick labels below 6 pt.
    """
    if base_font_pt < 7.0:
        raise ValueError(
            f"base_font_pt={base_font_pt} would place tick labels below the "
            "6 pt IEEE minimum. Use 7.0 or larger, 8.0 recommended."
        )

    serif = _available_serif()

    plt.rcParams.update({
        # Typography -- section 3.3
        "font.family": "serif",
        "font.serif": serif,
        "font.size": base_font_pt,
        "axes.labelsize": base_font_pt,
        "axes.titlesize": base_font_pt,
        "xtick.labelsize": base_font_pt - 1,
        "ytick.labelsize": base_font_pt - 1,
        "legend.fontsize": base_font_pt - 1,
        "figure.titlesize": base_font_pt,
        "mathtext.fontset": "stix",       # serif math, not sans default
        "mathtext.default": "regular",

        # Axes -- section 3.4
        "axes.linewidth": 0.7,
        "axes.grid": True,
        "axes.axisbelow": True,
        "axes.prop_cycle": matplotlib.cycler(color=OKABE_ITO),
        "grid.linewidth": 0.35,
        "grid.alpha": 0.4,
        "grid.linestyle": "-",
        "grid.color": "#B0B0B0",

        # Ticks inward on all four spines
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "xtick.major.width": 0.7,
        "ytick.major.width": 0.7,
        "xtick.minor.width": 0.5,
        "ytick.minor.width": 0.5,
        "xtick.major.size": 3.0,
        "ytick.major.size": 3.0,
        "xtick.minor.size": 1.5,
        "ytick.minor.size": 1.5,
        "xtick.minor.visible": True,
        "ytick.minor.visible": True,

        # Data -- section 3.6
        "lines.linewidth": 1.1,
        "lines.markersize": 3.0,
        "lines.markeredgewidth": 0.7,

        # Legend -- section 3.7
        "legend.frameon": True,
        "legend.framealpha": 1.0,
        "legend.edgecolor": "black",
        "legend.fancybox": False,
        "legend.borderpad": 0.35,
        "legend.labelspacing": 0.3,
        "legend.handlelength": 2.2,

        # Export -- section 3.2
        "figure.dpi": 150,
        "savefig.dpi": 600,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.02,
        "savefig.transparent": False,
        "pdf.fonttype": 42,   # embed TrueType so text stays selectable
        "ps.fonttype": 42,
        "svg.fonttype": "none",
    })

    # Section 3.5: a figure carries no internal title.
    plt.rcParams["axes.titlepad"] = 3.0


def new_figure(columns: int = 1, aspect: float = DEFAULT_ASPECT,
               nrows: int = 1, ncols: int = 1, **kwargs):
    """Create a figure sized to an IEEE column width.

    Args:
        columns: 1 for single-column (3.5 in), 2 for double-column (7.16 in).
        aspect: Height divided by width. Section 3.1 keeps this near 0.68.
        nrows: Subplot rows.
        ncols: Subplot columns.
        **kwargs: Passed through to plt.subplots.

    Returns:
        (figure, axes) exactly as plt.subplots returns.

    Raises:
        ValueError: If columns is not 1 or 2.
    """
    if columns == 1:
        width = COLUMN_WIDTH_IN
    elif columns == 2:
        width = PAGE_WIDTH_IN
    else:
        raise ValueError(
            f"columns={columns} is not an IEEE column width. Use 1 (3.5 in) "
            "or 2 (7.16 in)."
        )

    height = width * aspect
    if nrows > 1:
        height = width * aspect * (0.62 * nrows + 0.38)

    # An IEEE two-column page leaves roughly 9.2 in of text height. A figure
    # taller than that cannot be placed without splitting it.
    if height > MAX_FIGURE_HEIGHT_IN:
        warnings.warn(
            f"Figure height {height:.2f} in exceeds the {MAX_FIGURE_HEIGHT_IN} "
            "in page limit and has been clamped. Consider fewer subplot rows "
            "or a smaller aspect.",
            RuntimeWarning,
            stacklevel=2,
        )
        height = MAX_FIGURE_HEIGHT_IN

    fig, axes = plt.subplots(
        nrows, ncols, figsize=(width, height), constrained_layout=True,
        **kwargs
    )
    return fig, axes


def trace(index: int, marker: bool = False) -> dict:
    """Return grayscale-safe style kwargs for trace number `index`.

    Section 3.6 forbids distinguishing traces by color alone, so each index
    maps to a distinct dash pattern as well as a distinct color.

    Args:
        index: Zero-based trace index. Wraps around after seven traces.
        marker: Attach the index's marker. Use for sparse or measured data;
            leave off for dense sweeps where markers would merge.

    Returns:
        Keyword arguments for a Matplotlib plot call.
    """
    i = index % len(_LINE_STYLES)
    style = {
        "color": OKABE_ITO[i],
        "linestyle": _LINE_STYLES[i],
        "linewidth": 1.1,
    }
    if marker and _MARKERS[i]:
        style.update({
            "marker": _MARKERS[i],
            "markersize": 3.0,
            "markevery": 0.15,
            "markerfacecolor": "white",
            "markeredgewidth": 0.7,
        })
    return style


def annotate_measurement(ax, x, y, text, dx=12, dy=10):
    """Mark and label a measured point on a figure.

    Section 3.8 requires that any numeric claim supported by a figure has the
    measured point visible and annotated with its value and unit.

    Args:
        ax: Target axes.
        x: Data-coordinate x of the measured point.
        y: Data-coordinate y of the measured point.
        text: Annotation carrying value and unit, e.g. "GBW = 12.41 MHz".
        dx: Horizontal label offset in points.
        dy: Vertical label offset in points.
    """
    ax.plot([x], [y], marker="o", markersize=3.5, color="black",
            markerfacecolor="none", markeredgewidth=0.9, zorder=5,
            linestyle="none")
    ax.annotate(
        text, xy=(x, y), xytext=(dx, dy), textcoords="offset points",
        fontsize=plt.rcParams["legend.fontsize"],
        arrowprops={"arrowstyle": "-", "linewidth": 0.6, "color": "black"},
        bbox={"boxstyle": "square,pad=0.25", "facecolor": "white",
              "edgecolor": "black", "linewidth": 0.5},
        zorder=6,
    )


def figure_filename(cell: str, analysis: str, stage: str | None = None) -> str:
    """Build a section 5 compliant figure stem.

    Args:
        cell: Subcircuit name, e.g. "ota_5t".
        analysis: One of ac, dc, tran, temp, noise, mc, pvt, compare.
        stage: "pre", "post", or None when the figure spans both stages.

    Returns:
        Filename stem without an extension.

    Raises:
        ValueError: If analysis or stage is outside the allowed vocabulary.
    """
    allowed_analysis = {"ac", "dc", "tran", "temp", "noise", "mc", "pvt",
                        "compare"}
    allowed_stage = {"pre", "post", None}

    if analysis not in allowed_analysis:
        raise ValueError(
            f"analysis='{analysis}' is not allowed. Use one of "
            f"{sorted(allowed_analysis)}."
        )
    if stage not in allowed_stage:
        raise ValueError(
            f"stage='{stage}' is not allowed. Use 'pre', 'post', or None."
        )

    stem = f"{cell}_{analysis}"
    if stage:
        stem = f"{stem}_{stage}"
    return stem


def save_figure(fig, cell: str, analysis: str, stage: str | None = None,
                outdir: str = ".", close: bool = True) -> dict:
    """Export a figure in every format section 3.2 requires.

    Emits PDF and SVG as the report deliverables plus a 600 dpi PNG for
    Markdown preview.

    Args:
        fig: Figure to export.
        cell: Subcircuit name.
        analysis: Analysis type.
        stage: "pre", "post", or None.
        outdir: Destination directory. Created if absent.
        close: Close the figure after writing. Keep True in batch runs.

    Returns:
        dict mapping extension to the written path.
    """
    stem = figure_filename(cell, analysis, stage)
    os.makedirs(outdir, exist_ok=True)

    written = {}
    for ext in ("pdf", "svg", "png"):
        path = os.path.join(outdir, f"{stem}.{ext}")
        fig.savefig(path, format=ext)
        written[ext] = path

    if close:
        plt.close(fig)

    return written
