---
description: Review an MBG AI experiment for reproducibility, bounded refinement, artifact completeness, metrics, and evidence-backed status.
agent: plan
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/workflows/mbg-review-ai-experiment.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

Review the following MBG AI experiment record:

```text
$1
```

## Required Workflow

1. Load the `mbg-ai-experiment-audit` skill.
2. Require exactly one repository-relative path to an `experiment.json`
   file.
3. Confirm that the supplied path:
   - Is not empty.
   - Is not absolute.
   - Does not contain `../` or parent-directory traversal.
   - Remains inside the current Git worktree.
   - Is not `.env`, a credential file, or a private-key file.
4. Read and validate the experiment record directly against the rules in
   `mbg-ai-experiment-audit` (required fields, status values, refinement
   bounds).
5. Report errors before warnings.
6. Do not modify the experiment record or any generated artifact.
7. Do not stage, commit, or push any file.
8. Do not claim DRC, LVS, PEX, simulation, or end-to-end success without
   evidence.
9. Stop after any blocking path, JSON, schema, or security error.

## Audit Requirements

Review the experiment for: experiment ID, model identifier, PDK
consistency, prompt-detail classification, API-call count,
refinement-iteration count, maximum refinement limit, LLM runtime, total
runtime, netlist-validation status, GDS-generation status, pre-layout
simulation status, DRC status, LVS status, PEX status, post-layout
simulation status, final-status consistency, prompt artifact, generated
netlist, circuit graph, GDS artifact, simulation and verification reports,
credential leakage, and personal absolute filesystem paths.

## PDK Body Constraint

**MOSFET body: `pfet_03v3` -> VDD ONLY, `nfet_03v3` -> VSS ONLY.** When
reviewing generated SPICE, verify all body terminals are connected to the
correct supply rail.

## Prompt Classification

Use only: `minimal`, `constraint-based`, `detailed`.

A detailed prompt may demonstrate constrained generation, but it must not
be presented as strong evidence of independent LLM circuit design unless
the experiment methodology explicitly supports that claim.

## Status Rules

Use only: `PASS`, `FAIL`, `PARTIAL`, `NOT RUN`, `NOT AVAILABLE`.

- A missing report cannot support `PASS`.
- A failed required stage prevents an overall `PASS`.
- A `NOT RUN` required stage prevents a full end-to-end `PASS`.
- `netlist_valid: false` prevents an overall `PASS`.
- `gds_generated: false` prevents an overall physical-flow `PASS`.
- Refinement iterations must not exceed the configured maximum.
- Unsupported absolute-success language must be reported.

## Ownership Rules

Assign findings according to project ownership:

- AI metadata, prompt traceability, AI metrics, and experiment schema:
  `Jabir`.
- Analog design, device selection, sizing, and simulation interpretation:
  `Huda`.
- DRC, LVS, PEX, and verification automation: `Ahmad`.
- Tapeout scope, milestone, or cross-team acceptance: `Team`.

Do not modify implementation owned by another team member.

## Output Format

```text
Experiment:
Experiment path:
Model:
PDK:
Prompt level:
Audit status:

Blocking errors:
1. ...

Warnings:
1. ...

Artifact completeness:
- Prompt:
- Generated netlist:
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
- Maximum refinement iterations:
- LLM runtime:
- Total runtime:

Stage results:
- Netlist validation:
- Pre-layout simulation:
- GDS generation:
- DRC:
- LVS:
- PEX:
- Post-layout simulation:
- Final status:

Security findings:
- Credential material:
- Personal paths:
- Unsafe artifact paths:

Ownership:
- Jabir:
- Huda:
- Ahmad:
- Team:

Required corrections:
1. ...

Recommended next action:
...
```

## Failure Handling

If no path is supplied:

```text
Missing required argument.

Usage:
/mbg-review-ai-experiment path/to/experiment.json
```

If the supplied file is not named `experiment.json`, stop and report:

```text
The supplied path must point to an experiment.json file.
```

If JSON parsing fails:

- Report the parsing error.
- Do not infer missing metadata.
- Do not continue to aggregate metrics.
- Mark the audit itself as `FAIL`.

If credential material is found:

- Do not repeat the credential value.
- Report only the field or file containing it.
- Recommend removing and rotating the exposed credential.

## Example

```text
/mbg-review-ai-experiment outputs/comparator-minimal-001/experiment.json
```
