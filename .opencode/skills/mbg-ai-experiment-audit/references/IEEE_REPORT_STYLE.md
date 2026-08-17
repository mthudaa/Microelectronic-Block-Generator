# MBG IEEE Presentation Standard

Normative reference for every figure, table, and design report produced by the
Microelectronic Block Generator project.

| Field | Value |
| :--- | :--- |
| Owner | Moh. Jabir Mubarok — AI/LLM Integration & Software Architect |
| Applies to | Design reports, experiment reports, simulation plots, result tables |
| Basis | IEEE Author Center graphics guidance and IEEE conference template conventions |
| Status | Project standard — deviations must be recorded as findings |

This document defines **presentation only**. It does not define analog design
targets, simulation methodology, or verification acceptance criteria. Those
remain owned by Huda and Ahmad.

---

## 1. Report Structure

A design report delivered to a user or prompter must use this section order.
Do not add, remove, or reorder top-level sections.

```text
I.    Abstract
II.   Introduction
III.  Design Specification
IV.   Methodology
V.    Results
VI.   Discussion
VII.  Conclusion
      References
      Appendix (optional)
```

### Section content

| Section | Required content |
| :--- | :--- |
| Abstract | 150–250 words. Topology, PDK, headline measured results with units, verification status. No citations, no figure references. |
| Introduction | Problem statement, target application, and what the AI agent was asked to produce. |
| Design Specification | Two tables: requested specification (from the prompt) and the resulting device table. |
| Methodology | Prompt level, model identifier, refinement bound, tool chain and versions, testbench and stimulus conditions. |
| Results | Measured values against targets, pre- versus post-layout comparison, verification outcomes. Every claim carries a figure or table reference. |
| Discussion | Deviations, root causes, and limitations. State what was not run. |
| Conclusion | What was demonstrated and what remains open. No new data. |
| References | IEEE numeric style. |

### Section numbering

Use uppercase Roman numerals for top-level sections and uppercase letters for
subsections:

```text
IV. METHODOLOGY
  A. Prompt Construction
  B. Simulation Setup
```

`References` and `Appendix` are unnumbered.

---

## 2. Numerical Reporting

Every numeric claim in a report must satisfy all of the following.

1. Carry an SI unit, written in parentheses in table headers and axis labels.
2. State the measurement condition — supply, temperature, load, corner.
3. Cite the source artifact by repository-relative path.
4. Be traceable to exactly one experiment record.
5. Use consistent significant figures within a column.

### Units and symbols

| Rule | Correct | Incorrect |
| :--- | :--- | :--- |
| Space before unit | `1.2272 V` | `1.2272V` |
| Micro sign | `376 µW` | `376 uW` |
| Degree Celsius | `27 °C` | `27C`, `27℃` |
| Ohm | `12.4 kΩ` | `12.4 kohm` |
| Decibel, unitless ratio | `41.3 dB` | `41.3 db` |
| Parts per million | `60 ppm/°C` | `60ppm/C` |
| Percent | `0.65 %` | `.65%` |
| Range | `−40 °C to 125 °C` | `-40~125C` |

Use the Unicode minus sign `−` (U+2212) for negative quantities in tables and
figures. Use `×` (U+00D7) for dimensions, not the letter `x`.

### Significant figures

| Quantity class | Significant figures |
| :--- | :--- |
| Voltage, current, power | 4 |
| Gain in dB, phase margin | 3 |
| Temperature coefficient | 2 |
| Percentage deviation | 2 decimal places |
| Area, dimensions | Integer µm, integer µm² |

Do not report more precision than the simulator step size supports. If the
source artifact provides fewer digits, report fewer digits — never pad.

### Required results table shape

Every performance claim must appear in a table with this column set:

```text
| Parameter | Unit | Target | Pre-Layout | Post-Layout | Deviation | Condition | Source |
```

`Source` is a repository-relative artifact path. A row without a `Source` value
is a blocking finding.

---

## 3. Figure Requirements

### 3.1 Geometry

| Property | Single column | Double column |
| :--- | :--- | :--- |
| Width | 3.5 in (88.9 mm) | 7.16 in (181.6 mm) |
| Typical height | 2.2–2.6 in | 2.6–3.2 in |

Figures are produced at final print size. Never generate at an arbitrary size
and rely on the document to scale — scaling changes the effective font size and
breaks legibility compliance.

### 3.2 Resolution and format

| Content type | Minimum |
| :--- | :--- |
| Vector line art | PDF or SVG — preferred for all simulation plots |
| Raster line art or combination art | 600 dpi |
| Photographs, grayscale halftones, layout screenshots | 300 dpi |

Every plot must be emitted in **both** a vector format for the report and PNG
at 600 dpi for Markdown previews. The PNG is a convenience artifact; the vector
file is the deliverable.

### 3.3 Typography

| Element | Specification |
| :--- | :--- |
| Family | Times New Roman, or a metric-compatible serif fallback |
| Axis label size | 8 pt at final size |
| Tick label size | 7 pt at final size |
| Legend size | 7 pt at final size |
| Minimum any text | 6 pt at final size |
| Math | Serif math rendering, not sans-serif default |

No text in a figure may fall below 6 pt after the figure is placed at its final
width. This is the single most common rejection cause.

### 3.4 Axes

1. Label both axes with the **quantity name and unit**, unit in parentheses.
   Write `Frequency (Hz)`, not `f` or `Freq [Hz]`.
2. Use square brackets for nothing. IEEE uses parentheses for units.
3. Use a logarithmic frequency axis for AC magnitude and phase sweeps, with
   decade major ticks.
4. Tick marks point inward on all four spines.
5. Include a light grid only when it aids reading a value. Grid line width must
   be below the data line width.
6. Do not truncate an axis in a way that exaggerates a difference. If a
   truncated axis is necessary, state the range explicitly in the caption.

### 3.5 Titles

**A figure carries no internal title.** The description lives in the caption
below the figure. An embedded title duplicates the caption and wastes plot
area.

### 3.6 Line styles and color

Figures must remain readable when printed in grayscale.

| Trace index | Style | Marker | Color |
| :--- | :--- | :--- | :--- |
| 1 | solid | none | `#000000` |
| 2 | dashed | circle | `#0072B2` |
| 3 | dash-dot | square | `#D55E00` |
| 4 | dotted | triangle | `#009E73` |
| 5 | long dash | diamond | `#CC79A7` |

Rules:

* Never distinguish traces by color alone.
* Data line width 1.0–1.2 pt. Axis and spine width 0.6–0.8 pt.
* Marker size 3 pt, and marker frequency thinned so markers do not merge.
* The palette above is colorblind-safe (Okabe–Ito). Do not substitute a
  default library colormap.

### 3.7 Legend

* Place inside the axes when white space allows, otherwise directly above the
  axes.
* Frame with a thin border, no shadow, no rounded corners, no transparency
  effects.
* Label with physical meaning: `Pre-layout`, `Post-layout`, `TT 27 °C`, not
  `v(out)` or `series 1`.
* Omit the legend entirely when there is a single trace.

### 3.8 Annotation of measured values

When a figure supports a numeric claim, the measured point must be marked on
the figure — a marker plus a short annotation carrying the value and unit. A
claim of `GBW = 12.4 MHz` requires the unity-gain crossing to be visible and
annotated.

### 3.9 Captions

Captions sit **below** the figure and use the abbreviation `Fig.`:

```text
Fig. 1. Pre- and post-layout AC response of the 5T OTA. VDD = 3.3 V,
CL = 1 pF, TT corner, 27 °C. Source: outputs/ota-5t-001/pre_simulation/ac.raw.
```

Caption rules:

* Sentence case, ending with a period.
* State the operating condition.
* State the source artifact for reproducibility.
* Reference every figure in the body text before it appears.
* Write `Fig. 1` mid-sentence and `Figure 1` only when starting a sentence.

---

## 4. Table Requirements

| Rule | Specification |
| :--- | :--- |
| Numbering | Uppercase Roman numerals — `TABLE I`, `TABLE II` |
| Caption position | Above the table |
| Caption case | Title case for the label line |
| Units | In the column header in parentheses, not repeated per cell |
| Alignment | Numeric columns right-aligned on the decimal point |
| Rules | Horizontal rules only — no vertical rules |
| Empty cells | Use `—` (em dash), never blank or `N/A` without explanation |

Example:

```text
TABLE II
Pre- and Post-Layout Performance of the 5T OTA

| Parameter        | Unit   | Target | Pre    | Post   | Δ (%) |
| :--------------- | :----- | -----: | -----: | -----: | ----: |
| DC gain          | dB     |  ≥ 25  |  31.42 |  30.18 | −3.95 |
| Unity-gain freq. | MHz    |   —    |  12.41 |  11.86 | −4.43 |
```

---

## 5. File Naming

```text
<cell>_<analysis>_<stage>.<ext>
```

| Field | Allowed values |
| :--- | :--- |
| `<cell>` | Subcircuit name, lowercase, underscores |
| `<analysis>` | `ac`, `dc`, `tran`, `temp`, `noise`, `mc`, `pvt`, `compare` |
| `<stage>` | `pre`, `post`, or omitted when the figure spans both |
| `<ext>` | `pdf` and `svg` for the deliverable, `png` for preview |

Examples:

```text
ota_5t_ac_pre.pdf
ota_5t_ac_pre.png
comparator_core_tran_post.pdf
vref_1v2_temp_compare.pdf
```

A figure whose filename does not encode cell, analysis, and stage cannot be
traced back to an experiment record and must be reported as a finding.

---

## 6. References

Use IEEE numeric citation style. Number in order of first appearance, cite
inline in square brackets.

```text
[1] R. J. Baker, CMOS: Circuit Design, Layout, and Simulation, 4th ed.
    Hoboken, NJ, USA: Wiley-IEEE Press, 2019.
[2] GlobalFoundries, "GF180MCU open source PDK," GitHub repository, 2024.
    [Online]. Available: https://github.com/google/gf180mcu-pdk
```

Cite the PDK, the layout framework, the simulator, and the LLM provider. An
LLM-generated design report that does not cite the model identifier and version
is not reproducible.

---

## 7. Compliance Severity

Use these severities when auditing presentation.

### Blocking error

* A numeric claim without a unit.
* A numeric claim without a source artifact path.
* An axis without a quantity label or without a unit.
* A figure whose values contradict the experiment record.
* An unlabeled trace in a multi-trace figure.
* A personal absolute filesystem path in a caption or figure.
* A claim of verification success unsupported by a report artifact.

### Warning

* Font below 8 pt but at or above 6 pt at final size.
* Raster-only output where a vector format is expected.
* Figure width not matching a column width.
* Traces distinguished by color alone.
* Missing annotation on a measured point.
* Caption missing the operating condition.
* Inconsistent significant figures within a column.
* Filename not matching the naming convention.

### Advisory

* Grid heavier than necessary.
* Legend placed outside the axes where inside would fit.
* Non-standard section ordering in an appendix.

---

## 8. Reference Implementation

`mbg_ieee_style.py` in this directory applies every typographic and geometric
rule above to Matplotlib. Import it before creating any figure:

```python
from mbg_ieee_style import use_ieee_style, new_figure, save_figure

use_ieee_style()
fig, ax = new_figure(columns=1)
ax.semilogx(freq, gain_db, label="Pre-layout")
ax.set_xlabel("Frequency (Hz)")
ax.set_ylabel("Gain (dB)")
ax.legend()
save_figure(fig, "ota_5t_ac_pre")
```

`save_figure` emits the PDF, SVG, and 600 dpi PNG required by section 3.2 and
enforces the naming rule in section 5.

The helper reduces effort but does not guarantee compliance. Axis labels,
units, captions, and source paths remain the author's responsibility and are
audited by `mbg-ai-experiment-audit`.
