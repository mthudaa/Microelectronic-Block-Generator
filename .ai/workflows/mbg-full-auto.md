---
name: mbg-full-auto
description: Fully automated analog design from one request — specification to tapeout-ready package or a diagnosed non-convergence report, with multi-agent review, branch-and-compare search, and PEX-aware optimization.
agent: build
platforms: [opencode, claude]
---

Run the MBG fully automated design flow for:

```text
$ARGUMENTS
```

If no design request was given, ask for one. Do not invent specifications.

## Load first

The `mbg-full-auto` skill, plus `mbg-reviewers` and `mbg-pex-aware-flow`.
Canonical definitions: `.ai/knowledge/FULL_AUTOMATE.md` and
`.ai/knowledge/DESIGN_FLOW.md`.

## Run it

```python
from mbg import Spec, make_hooks
from mbg.full_auto import run_full_auto, FullAutoConfig

specs = [Spec("gain_db", ">=", 30.0, " dB"), Spec("bw_hz", ">=", 100e6, " Hz")]

hooks = make_hooks(cell=cell, in_node=..., out_node=..., supplies=...,
                   spec_names=[s.name for s in specs], specs=specs,
                   outdir=outdir, verbosity=1)

res = run_full_auto(request, hooks, cell=cell, specs=specs, netlist=netlist,
                    config=FullAutoConfig.for_effort("normal", outdir=outdir))
print(res.summary() if hasattr(res, "summary") else res.status)
```

Pass `specs=` to `make_hooks` — without it branch-and-compare is disabled and
the search degrades to a single edit per iteration.

Effort: `"normal"` (12/12/3) · `"high"` (20/20/4) · `"exhaustive"` (30/30/5),
as pre-iterations / PEX-iterations / candidates per iteration.

## What the flow does

```
specification (+ review)
  -> LOOP A  pre-layout simulate / evaluate / tune      (+ review)
  -> layout -> DRC -> LVS -> PEX extraction             (+ review)
  -> PEX simulation of the extracted netlist            (+ review)
  -> LOOP B  evaluate / branch-and-compare / re-verify  (+ review)
  -> final sign-off gate                                (+ review)
  -> tapeout package + design report,  or  non-convergence report
```

Each PEX iteration proposes several distinct candidates from one baseline,
measures each independently, promotes the winner and archives the rest. A
regression rolls back to the best design rather than compounding.

## Do not stop early

A spec miss starts a search, not a shutdown. Continue through the configured
budget until specs pass, the budget is exhausted, no improvement for
`patience` iterations, every feasible move is exhausted, or a tool fails.

## Report honestly

`res.status` ∈ `SUCCESS | NOT_CONVERGED | BLOCKED | TOOL_FAILURE |
CONFIGURATION_FAILURE | VERIFICATION_FAILURE | SPEC_INFEASIBLE`.

Only `SUCCESS` is tapeout-ready, and only when every gate condition passed.
Never claim an analysis that reported `NOT RUN`. On non-convergence report the
best iteration, which specs remain unmet and by how much, what was tried, what
helped, and what you recommend a human do next.

Outputs land in `<outdir>/`: `history.json`, `review_history.json`,
`full_auto_result.json`, `final_design_report.md`, and `final/` on success.
