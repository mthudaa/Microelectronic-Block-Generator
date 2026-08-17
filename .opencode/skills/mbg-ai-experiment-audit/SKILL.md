---
name: mbg-ai-experiment-audit
description: Audit an MBG AI-assisted analog-design experiment for reproducibility, prompt independence, bounded LLM refinement, artifact completeness, AI metrics, evidence-based results, and IEEE-compliant presentation of data, figures, and design reports. Use this skill when reviewing experiment.json, generated SPICE, GDS, simulation plots, result tables, a design report delivered to a user or prompter, or DRC/LVS/PEX reports. Do not use it to modify analog-design, simulation, routing, or verification implementations.
license: Apache-2.0
compatibility: opencode
metadata:
  owner: jabir
  project: microelectronic-block-generator
  status: experimental
---

# MBG AI Experiment Audit

## Purpose

Audit an AI-assisted analog-design experiment and determine whether its claims
are supported by reproducible artifacts, verification evidence, and a
presentation that meets the project IEEE standard.

The audit covers:

* Prompt traceability
* Model traceability
* API-call and refinement metrics
* Generated-netlist validation
* Prompt-detail classification
* GDS-generation status
* Simulation and verification evidence
* Numerical reporting completeness
* Figure and table IEEE compliance
* Design-report structure
* Final experiment status
* Reviewer-facing AI metrics

## When to Use

Use this skill when:

* Reviewing an `experiment.json` file.
* Reviewing a prompt-to-GDS experiment.
* Reviewing a design report delivered to a user or prompter.
* Reviewing simulation plots or result tables before publication.
* Preparing AI metrics for a report or presentation.
* Verifying that LLM retries are bounded.
* Checking whether an experiment can be reproduced.
* Checking whether `PASS`, `FAIL`, or `PARTIAL` is supported.
* Reviewing generated SPICE, GDS, DRC, LVS, PEX, or simulation artifacts.
* Comparing minimal, constrained, and detailed prompts.

## When Not to Use

Do not use this skill to:

* Select final transistor models or device sizes.
* Correct analog circuit topology.
* Modify placement, routing, or power implementation.
* Correct simulation algorithms.
* Modify DRC, LVS, or PEX implementation.
* Decide whether a measured value meets an analog design target.
* Decide final tapeout scope.

Record these findings as dependencies for their respective owners. This skill
audits how results are recorded and presented, not whether the circuit is
good.

## Ownership

Primary owner:

```text
Moh. Jabir Mubarok
AI/LLM Integration & Software Architect
```

Dependencies:

* Analog design and simulation results: Huda.
* Physical verification and automation: Ahmad.
* Final tapeout scope and team milestones: Team lead.

## Required Inputs

At least one of the following must be supplied:

* Path to `experiment.json`.
* Path to an experiment output directory.
* Generated SPICE netlist.
* Original prompt.
* Generated GDS.
* Simulation report or plot.
* Design report delivered to the user or prompter.
* DRC report.
* LVS report.
* PEX output.
* Post-layout simulation report.

Preferred experiment structure:

```text
outputs/<experiment-id>/
├── experiment.json
├── prompt.txt
├── generated_netlist.spice
├── circuit_graph.svg
├── generated_layout.gds
├── report/
│   ├── design_report.md
│   └── figures/
│       ├── <cell>_ac_pre.pdf
│       ├── <cell>_ac_pre.png
│       └── ...
├── pre_simulation/
├── drc/
├── lvs/
├── pex/
└── post_simulation/
```

## Presentation Standard

Figures, tables, numerical claims, and design reports are audited against:

```text
.opencode/skills/mbg-ai-experiment-audit/references/IEEE_REPORT_STYLE.md
```

That document is normative. This skill does not restate its rules; it applies
them. When a presentation finding is reported, cite the section number from
the standard so the author can locate the rule.

The reference implementation that satisfies the typographic and geometric
rules automatically is:

```text
.opencode/skills/mbg-ai-experiment-audit/references/mbg_ieee_style.py
```

An experiment whose figures were produced without that helper is not
automatically non-compliant, but each figure must then be checked against
section 3 of the standard individually.

## Preconditions

Before auditing:

1. Confirm that all supplied paths are repository-relative.
2. Reject parent-directory traversal.
3. Do not read `.env`.
4. Do not expose API credentials.
5. Do not modify experiment artifacts.
6. Confirm that the project PDK is identified.
7. Confirm that the experiment has a unique identifier.

## Required Experiment Metadata

An experiment record should include:

```json
{
  "experiment_id": "comparator-minimal-001",
  "model": "model-identifier",
  "pdk": "gf180mcuD",
  "prompt_level": "minimal",
  "api_calls": 1,
  "refinement_iterations": 0,
  "max_refinement_iterations": 2,
  "netlist_valid": true,
  "pre_simulation_status": "PASS",
  "gds_generated": true,
  "drc_status": "PASS",
  "lvs_status": "PASS",
  "pex_status": "NOT RUN",
  "post_simulation_status": "NOT RUN",
  "llm_runtime_seconds": 18.4,
  "total_runtime_seconds": 94.2,
  "report_path": "report/design_report.md",
  "figures": [
    {
      "path": "report/figures/comparator_core_tran_pre.pdf",
      "analysis": "tran",
      "stage": "pre",
      "supports": ["propagation_delay_ns"]
    }
  ],
  "final_status": "PARTIAL"
}
```

The `figures` array binds each figure to the numeric claims it supports. A
numeric claim in the report with no figure or table backing it is a blocking
finding.

## Prompt Detail Classification

Classify the prompt as one of:

### Minimal

Contains only high-level circuit objective, PDK, supply, and output format.

### Constraint-Based

Adds required behavior, ports, performance constraints, or topology-independent
design constraints.

### Detailed

Includes substantial topology, exact model names, connectivity, transistor
sizes, or a reference implementation.

The audit must state that a detailed prompt demonstrates constrained
generation, while a minimal prompt provides stronger evidence of independent
LLM design contribution.

## Status Values

Use only:

* `PASS`
* `FAIL`
* `PARTIAL`
* `NOT RUN`
* `NOT AVAILABLE`

Do not accept:

* `100% functional`
* `fully successful`
* `completely autonomous`
* Other unsupported absolute-success claims

## Status Rules

### PASS

Use only when every required stage:

* Was run.
* Produced its required artifact.
* Satisfied its acceptance criterion.
* Has supporting evidence.

### PARTIAL

Use when some required stages passed, but one or more stages:

* Were not run.
* Are unavailable.
* Failed.
* Lack evidence.

### FAIL

Use when a required stage failed and prevents acceptance of the experiment.

### NOT RUN

Use when a stage was intentionally not executed.

### NOT AVAILABLE

Use when the required data or implementation is unavailable.

Presentation findings never raise a stage status. A figure that violates the
IEEE standard does not turn a verified `PASS` into a `FAIL`. It is reported
separately under presentation compliance, because a correct result that is
badly presented is still a correct result — but it is not yet publishable.

## Workflow

### 1. Identify Experiment

Record:

* Experiment ID
* Model identifier
* PDK
* Prompt level
* Circuit or subcircuit name
* Experiment directory

### 2. Validate Prompt Traceability

Confirm that:

* The original prompt is preserved.
* Prompt-detail level is recorded.
* The prompt does not contain an API key.
* The prompt does not use an unapproved PDK.
* The prompt does not silently include a complete reference answer unless the
  experiment is explicitly classified as detailed.
* Every specification the prompter asked for appears in the report's
  specification table, including specifications that were not met.

The last item matters most. A report that silently drops a requested
specification misrepresents the experiment even when every reported number is
accurate.

### 3. Validate LLM Metadata

Confirm that:

* Model identifier is recorded.
* API-call count is recorded.
* Refinement-iteration count is recorded.
* Maximum refinement iterations is defined.
* Actual refinements do not exceed the maximum.
* LLM runtime is recorded when available.
* Token usage is recorded when available.

### 4. Validate Generated Netlist

Confirm that:

* A generated SPICE artifact exists.
* A valid `.subckt` is present.
* Subcircuit ports are identifiable.
* At least one supported device is present.
* Device models match the approved GF180MCU allowlist.
* No personal filesystem path is embedded.
* No API key or credential is embedded.
* Parser-validation status is recorded.

### 5. Validate Graphical Representation

Confirm that:

* A circuit graph or schematic representation exists.
* Device names are visible.
* Device types are visible.
* Supply and ground nets are visible.
* Input and output ports are identifiable.
* The graph belongs to the same experiment ID.

A connectivity graph is acceptable as supporting evidence, but it does not
replace analog schematic review.

### 6. Validate Simulation Evidence

For pre-layout and post-layout simulation, confirm:

* Status is recorded.
* Report path exists when status is `PASS` or `FAIL`.
* Required waveform or metric evidence exists.
* Numerical claims are sourced from one experiment record.
* Delay, offset, VOH, VOL, and PVT values do not conflict across artifacts.

Do not determine whether the simulator implementation is correct. Record
implementation concerns as dependencies for the simulation owner.

### 7. Validate Numerical Reporting

For every numeric claim in the report, confirm against section 2 of the
presentation standard:

* An SI unit is present and correctly formatted.
* The measurement condition is stated — supply, temperature, load, corner.
* A repository-relative source artifact path is given.
* Significant figures are consistent within a column and not padded beyond
  what the source artifact provides.
* The value matches the source artifact. Recompute the deviation column and
  confirm the arithmetic.
* Pre-layout and post-layout values are labelled as such and never mixed in
  one column.

Recomputing the deviation column is not optional. A stated deviation that does
not follow from the stated pre and post values is a blocking finding regardless
of which of the three numbers is wrong.

### 8. Validate Figures and Tables

For every figure, confirm against section 3 of the presentation standard:

* Both axes carry a quantity name and a unit in parentheses.
* No internal title is present.
* A caption exists below the figure, states the operating condition, and cites
  the source artifact.
* Multi-trace figures distinguish traces by dash pattern, not color alone.
* Every trace is labelled with physical meaning.
* A vector format exists alongside the PNG preview.
* The figure width matches a single- or double-column width.
* No text falls below 6 pt at final size.
* Measured points supporting a numeric claim are marked and annotated.
* The filename encodes cell, analysis, and stage.
* No personal absolute path appears in a caption or embedded in the figure.

For every table, confirm against section 4:

* Roman-numeral numbering with the caption above the table.
* Units in the column header, not repeated in cells.
* Numeric columns right-aligned.
* Empty cells marked with an em dash rather than left blank.

### 9. Validate Report Structure

Confirm against section 1 of the presentation standard:

* Section order matches the required order.
* The abstract states topology, PDK, headline results with units, and
  verification status.
* Every figure and table is referenced in the body text before it appears.
* The discussion states what was not run.
* The conclusion introduces no data absent from the results section.
* References use IEEE numeric style and cite the PDK, layout framework,
  simulator, and LLM model identifier.

A report that omits the model identifier from its references is not
reproducible and must be reported as a blocking finding.

### 10. Validate GDS Evidence

Confirm that:

* GDS-generation status is recorded.
* Generated GDS path exists when `gds_generated` is true.
* Top-cell name is identifiable.
* GDS-validation result is recorded.
* The GDS belongs to the same experiment ID and generated netlist.

### 11. Validate Physical Verification

For DRC, LVS, and PEX:

* Confirm stage status.
* Confirm report or artifact path.
* Confirm evidence exists for `PASS` or `FAIL`.
* Confirm the report's stated status matches the raw report text. Read the
  final result line of the verification report rather than trusting a summary
  field.
* Do not infer success from a missing report.
* Do not modify verification implementation.

The second item catches the most damaging class of error in this project: a
summary field that says the stage passed while the underlying report says it
did not. When they disagree, the raw report wins and the disagreement is a
blocking finding.

### 12. Validate Final Status

Check whether `final_status` agrees with all stage statuses.

Examples:

* Post-layout simulation `NOT RUN` means the full end-to-end flow cannot be
  reported as `PASS`.
* LVS `FAIL` means overall status cannot be `PASS`.
* DRC report missing means DRC cannot be reported as `PASS`.
* PEX `NOT RUN` may result in `PARTIAL` when PEX is required.

### 13. Produce Audit Report

Report errors before warnings, and evidence findings before presentation
findings.

Each finding must include:

* Severity
* Field or artifact
* Current value
* Expected rule, with the standard's section number for presentation findings
* Required correction
* Responsible owner

## Presentation Severity

Apply the severity table in section 7 of the presentation standard. In
summary:

| Severity | Examples |
| :--- | :--- |
| Blocking error | Missing unit, missing source path, unlabeled axis, figure contradicting the record, unlabeled trace, personal absolute path, unsupported success claim |
| Warning | Font between 6 pt and 8 pt, raster-only export, non-standard width, color-only trace distinction, missing measured-point annotation, caption without operating condition, inconsistent significant figures |
| Advisory | Heavy grid, legend placement, appendix ordering |

Presentation findings are reported in their own block and never silently
merged with verification findings.

## AI Metrics

When multiple experiment records are supplied, calculate:

* Total prompts
* Total API calls
* First-pass valid-netlist rate
* Final valid-netlist rate
* Average refinement iterations
* Layout-generation rate
* DRC-clean rate
* LVS-match rate
* End-to-end success rate
* Average LLM runtime
* Average total runtime
* Token usage when available
* Estimated API cost when available
* IEEE-compliant-report rate

Do not calculate a rate with an unclear denominator.

Report both numerator and denominator:

```text
DRC-clean rate: 7/10 = 70%
```

When presenting aggregate metrics as a figure or table, that figure or table is
itself subject to the presentation standard.

## Safety Rules

* Never read `.env`.
* Never display API keys.
* Never include credentials in an audit report.
* Never modify experiment artifacts during an audit.
* Never modify or regenerate a figure during an audit. Report the finding and
  leave correction to the artifact owner.
* Never stage, commit, or push automatically.
* Never use personal absolute filesystem paths.
* Never claim verification success without evidence.
* Never convert `NOT RUN` into `PASS`.
* Never hide missing or conflicting results.
* Never modify another team member's implementation.
* Never let a presentation finding upgrade or downgrade a verification status.

## Output Contract

Use:

```text
Experiment:
Model:
PDK:
Prompt level:
Audit status:
Presentation status:

Errors:
1. ...

Warnings:
1. ...

Artifact completeness:
- Prompt:
- Netlist:
- Circuit graph:
- Pre-layout simulation:
- GDS:
- DRC:
- LVS:
- PEX:
- Post-layout simulation:
- Design report:
- Figures:

LLM metrics:
- API calls:
- Refinement iterations:
- Maximum refinements:
- LLM runtime:
- Token usage:

Stage results:
- Netlist validation:
- Pre-layout simulation:
- GDS generation:
- DRC:
- LVS:
- PEX:
- Post-layout simulation:
- Final status:

Numerical reporting:
- Claims checked:
- Claims with unit:
- Claims with condition:
- Claims with source path:
- Arithmetic mismatches:

Figure compliance:
- Figures checked:
- Axis labels and units:
- Captions with condition and source:
- Vector format present:
- Column width conformance:
- Grayscale safety:
- Measured-point annotation:
- Filename convention:

Table compliance:
- Tables checked:
- Numbering and caption position:
- Units in header:
- Empty-cell handling:

Report structure:
- Section order:
- Abstract completeness:
- Figure and table cross-references:
- References and model citation:

Dependencies:
- ...

Required corrections:
1. ...

Recommended next action:
...
```

## Failure Handling

If the experiment record is invalid:

1. Stop before calculating aggregate metrics.
2. Report every missing required field.
3. Do not infer missing values.
4. Do not rewrite the experiment record.
5. Return `FAIL` for the audit itself.
6. Identify which owner must resolve each issue.

If the experiment record is valid but the report or figures are absent:

1. Continue the evidence audit to completion.
2. Set `Presentation status` to `NOT AVAILABLE`.
3. Do not report the experiment as publishable.
4. Do not treat missing figures as a verification failure.

If a figure and the experiment record disagree on a numeric value:

1. Report a blocking finding naming both values and both artifact paths.
2. Do not choose which value is correct.
3. Assign the finding to the artifact owner.
4. Stop before aggregating that metric across experiments.

## Test Cases

### Success Case

Input:

* Valid repository-relative experiment path.
* Complete metadata.
* Bounded refinement.
* Saved prompt and netlist.
* Evidence-backed DRC and LVS results.
* Final status consistent with stage results.
* Report with IEEE section order, units on every claim, and vector figures.

Expected:

```text
Audit status: PASS
Presentation status: PASS
```

### Failure Case — Path Traversal

Input:

```text
../experiment.json
```

Expected:

* Reject the path.
* Do not inspect files outside the worktree.

### Failure Case — Unbounded Refinement

Input:

```json
{
  "refinement_iterations": 5,
  "max_refinement_iterations": null
}
```

Expected:

* Report a blocking error.
* Do not report the experiment as reproducible.

### Failure Case — Unsupported Final Status

Input:

```json
{
  "drc_status": "PASS",
  "lvs_status": "FAIL",
  "final_status": "PASS"
}
```

Expected:

* Report a status-consistency error.
* Require the final status to be changed to `FAIL` or `PARTIAL` according to
  project acceptance rules.

### Failure Case — Summary Contradicts Raw Report

Input:

```json
{ "lvs_status": "PASS" }
```

with an LVS report whose final line reads:

```text
Final result: Top level cell failed pin matching.
```

Expected:

* Report a blocking evidence conflict naming both sources.
* Treat the raw report as authoritative.
* Do not aggregate the LVS-match rate until resolved.

### Failure Case — Unitless Claim

Input:

```text
Measured DC gain: 31.42
```

Expected:

* Report a blocking presentation error citing standard section 2.
* Require the unit, the operating condition, and the source artifact path.

### Failure Case — Non-Compliant Figure

Input:

* A PNG-only plot titled `AC Response`.
* Axes labelled `f` and `dB`.
* Two traces distinguished only by red and blue.

Expected:

* Blocking error: axis labels lack quantity names and units, section 3.4.
* Warning: internal title present, section 3.5.
* Warning: traces distinguished by color alone, section 3.6.
* Warning: no vector export, section 3.2.
* Assign to the figure's owner. Do not regenerate the figure.

## ⚠️ PDK Body Constraint

**MOSFET body: pfet_03v3→VDD ONLY, nfet_03v3→VSS ONLY.** When auditing
generated SPICE netlists, verify that all body terminals connect exclusively
to the appropriate supply rail.
