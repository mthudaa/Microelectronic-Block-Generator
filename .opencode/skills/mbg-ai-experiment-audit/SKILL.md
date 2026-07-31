---

name: mbg-ai-experiment-audit
description: Audit an MBG AI-assisted analog-design experiment for reproducibility, prompt independence, bounded LLM refinement, artifact completeness, AI metrics, and evidence-based results. Use this skill when reviewing experiment.json, generated SPICE, GDS, simulation outputs, or DRC/LVS/PEX reports. Do not use it to modify analog-design, simulation, routing, or verification implementations.
license: Apache-2.0
compatibility: opencode

owner: jabir
project: microelectronic-block-generator
status: experimental
--------------------

# MBG AI Experiment Audit

## Purpose

Audit an AI-assisted analog-design experiment and determine whether its claims
are supported by reproducible artifacts and verification evidence.

The audit covers:

* Prompt traceability
* Model traceability
* API-call and refinement metrics
* Generated-netlist validation
* Prompt-detail classification
* GDS-generation status
* Simulation and verification evidence
* Final experiment status
* Reviewer-facing AI metrics

## When to Use

Use this skill when:

* Reviewing an `experiment.json` file.
* Reviewing a prompt-to-GDS experiment.
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
* Decide final tapeout scope.

Record these findings as dependencies for their respective owners.

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
* Simulation report.
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
├── pre_simulation/
├── drc/
├── lvs/
├── pex/
└── post_simulation/
```

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
  "final_status": "PARTIAL"
}
```

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

## Audit Workflow

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

### 7. Validate GDS Evidence

Confirm that:

* GDS-generation status is recorded.
* Generated GDS path exists when `gds_generated` is true.
* Top-cell name is identifiable.
* GDS-validation result is recorded.
* The GDS belongs to the same experiment ID and generated netlist.

### 8. Validate Physical Verification

For DRC, LVS, and PEX:

* Confirm stage status.
* Confirm report or artifact path.
* Confirm evidence exists for `PASS` or `FAIL`.
* Do not infer success from a missing report.
* Do not modify verification implementation.

### 9. Validate Final Status

Check whether `final_status` agrees with all stage statuses.

Examples:

* Post-layout simulation `NOT RUN` means the full end-to-end flow cannot be
  reported as `PASS`.
* LVS `FAIL` means overall status cannot be `PASS`.
* DRC report missing means DRC cannot be reported as `PASS`.
* PEX `NOT RUN` may result in `PARTIAL` when PEX is required.

### 10. Produce Audit Report

Report errors before warnings.

Each finding must include:

* Severity
* Field or artifact
* Current value
* Expected rule
* Required correction
* Responsible owner

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

Do not calculate a rate with an unclear denominator.

Report both numerator and denominator:

```text
DRC-clean rate: 7/10 = 70%
```

## Safety Rules

* Never read `.env`.
* Never display API keys.
* Never include credentials in an audit report.
* Never modify experiment artifacts during an audit.
* Never stage, commit, or push automatically.
* Never use personal absolute filesystem paths.
* Never claim verification success without evidence.
* Never convert `NOT RUN` into `PASS`.
* Never hide missing or conflicting results.
* Never modify another team member's implementation.

## Output Contract

Use:

```text
Experiment:
Model:
PDK:
Prompt level:
Audit status:

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

## Test Cases

### Success Case

Input:

* Valid repository-relative experiment path.
* Complete metadata.
* Bounded refinement.
* Saved prompt and netlist.
* Evidence-backed DRC and LVS results.
* Final status consistent with stage results.

Expected:

```text
Audit status: PASS
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

## ⚠️ PDK Body Constraint

**MOSFET body: pfet_03v3→VDD ONLY, nfet_03v3→VSS ONLY.** When auditing
generated SPICE netlists, verify that all body terminals connect exclusively
to the appropriate supply rail.
