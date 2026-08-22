# The MBG Design Flow — canonical definition

**This is the single source of truth for the design methodology.** The README,
the Claude Code skills, the Codex plugin and the OpenCode skills all describe
this same flow. If they disagree with this file, this file is right and the
others need regenerating (`python3 scripts/sync_agent_tools.py`).

## The one thing to get right

MBG has **two** optimization loops, not one.

```
                ┌───────────────────┐
                │   Specifications  │
                └─────────┬─────────┘
                          ↓
                ┌───────────────────┐
                │  Initial Circuit  │
                └─────────┬─────────┘
                          ↓
              ┌─ Pre-Layout Simulation ─┐          LOOP A
              │           ↓             │      (nominal circuit)
              │      Specs met?         │
              │     ↙          ↘        │
              │   No            Yes     │
              │   ↓              │      │
              │ Fine-tune ───────┘      │
              └─────────┬───────────────┘
                        ↓
                 Generate Layout
                        ↓
                   DRC  →  LVS
                        ↓
                 PEX Extraction
                        ↓
              ┌─ PEX Simulation ────────┐          LOOP B
              │           ↓             │     (layout parasitics)
              │      Specs met?         │
              │     ↙          ↘        │
              │   No            Yes     │
              │   ↓              ↓      │
              │ PEX-Aware      FINAL    │
              │ Fine-Tune               │
              │   ↓                     │
              │ Regenerate Layout       │
              │   ↓                     │
              │ DRC → LVS → PEX ────────┘
              └─────────────────────────┘
```

> Pre-layout optimization finds a nominal circuit solution. PEX-aware
> optimization closes the loop on layout parasitics and produces the final
> sign-off candidate.

**PEX is feedback, not a final verification stamp.** A PEX specification miss
starts an optimization iteration; it does not end the run.

Loop B is **PEX-aware fine-tuning**: post-layout optimization driven by the
measured degradation between the pre-layout and extracted results. It may
change circuit parameters, layout constraints, or both, and every change is
re-verified through DRC → LVS → PEX extraction → PEX simulation before it is
evaluated again.

## DRC is dual-engine

```
              ┌→ Magic DRC   (independent complementary check)
Layout / GDS ─┤
              └→ KLayout DRC (GF180 foundry deck — sign-off authority)
                        │
                  DRC reconciliation
                        │
                  LVS → PEX
```

Both engines examine the **same GDS revision** (verified by hash). They do
not check the same rules — Magic uses its techfile, KLayout runs the deck the
PDK ships at `libs.tech/klayout/tech/drc/gf180mcu.drc` — so counts are never
compared, only statuses, and each engine's rule breakdown is kept separately.

| Situation | Verdict |
| --- | --- |
| both CLEAN | `PASS` |
| KLayout FAIL | `FAIL` |
| Magic FAIL, KLayout CLEAN | `DRC_DISAGREEMENT` — investigate, **not** a pass |
| either ERROR | `ERROR` |
| KLayout or its deck missing | `CONFIGURATION_FAILURE` |
| engines ran on different GDS | `ERROR` |

Two traps this guards against:

- **The GF180 deck always exits 0**, even with violations (its `exit()` is
  commented out for LibreLane). The verdict comes from the `.lyrdb` database,
  never the exit code. A run that produced no database is `ERROR`, never
  "0 violations".
- **Scope.** Die-level density and fill rules (`M1.4`, `PL.8`, `DCF.1b`, ...)
  cannot be met by a leaf cell — they are satisfied by fill during chip
  assembly. Cell-level sign-off runs `decks=all,-density,-dummy`; the
  assembled die runs `decks=all`. That is scope, not relaxation.

Tapeout readiness requires the **reconciled** verdict, not Magic alone.

## Stages

```
SPECIFICATION  PRE_SIMULATION  PRE_EVALUATION  PRE_OPTIMIZATION
LAYOUT_GENERATION  DRC  LVS  PEX_EXTRACTION
PEX_SIMULATION  PEX_EVALUATION  POST_LAYOUT_OPTIMIZATION
FINAL_VERIFICATION  COMPLETE
```

Three separations are load-bearing:

1. **PEX extraction ≠ PEX simulation.** Extraction can succeed while the
   design misses every target. They report separately.
2. **Tool failure ≠ spec failure.** ngspice crashing does not mean the gain is
   too low. Never "tune" in response to a broken tool.
3. **Verification gates extraction.** DRC or LVS failing ⇒ PEX and PEX
   simulation are `SKIP`, never run on a layout known to be wrong.

## Statuses and failure categories

Stage outcome: `PASS` `FAIL` `SKIP` `ERROR` `TIMEOUT` `NOT_CONVERGED`

Failure category: `TOOL_FAILURE` `DESIGN_FAILURE` `SPEC_FAILURE`
`VERIFICATION_FAILURE` `TIMEOUT` `CONFIGURATION_FAILURE`

| Situation | Category |
| --- | --- |
| Magic cannot extract parasitics | `TOOL_FAILURE` |
| LVS mismatch | `VERIFICATION_FAILURE` |
| PEX simulation runs, gain misses target | `SPEC_FAILURE` |
| Iteration limit reached | `DESIGN_FAILURE` (status `NOT_CONVERGED`) |
| No target specs supplied | `CONFIGURATION_FAILURE` |

## Stop conditions

The loop is always bounded. It ends when **any** holds:

- every required specification passes;
- `max_pre_iterations` / `max_pex_iterations` reached;
- no improvement for `patience` iterations;
- an EDA tool or simulation failed (`TOOL_FAILURE`);
- verification failed with no tuner available;
- configuration is invalid.

The best-scoring design is retained even if later iterations are worse:
`FlowResult.best_pex_design` / `best_pex_iteration`.

## The API

```python
from mbg import Spec, DesignPoint, FlowConfig, DesignFlow, make_hooks

specs = [Spec("gain_db", ">=", 30.0, " dB"),
         Spec("bw_hz",   ">=", 100e6, " Hz")]

hooks = make_hooks(cell="inverter", in_node="in", out_node="out",
                   supplies={"vdd": 3.3, "vss": 0.0},
                   spec_names=[s.name for s in specs],
                   bias={"in": "DC 1.42"})

result = DesignFlow(hooks, FlowConfig(specs=specs, outdir="outputs/inv")).run(
    DesignPoint(cell="inverter", netlist=netlist))

result.status              # PASS | FAIL | NOT_CONVERGED | ERROR
result.failure             # SPEC_FAILURE | TOOL_FAILURE | ...
result.degradation         # pre-layout vs PEX, worst first
result.best_pex_iteration
print(result.summary())    # the end-of-run report
```

Iteration history is written to `<outdir>/history.json`.

`tune_pre` and `tune_post` are the extension points. The bundled ones are
documented heuristics (scale widths; widen critical nets); an agent or a
designer supplies better ones.

## Fine-tuning is circuit *and* layout

`DesignPoint` keeps `circuit` and `layout` separate because post-layout tuning
is not only sizing:

| Circuit | Layout |
| --- | --- |
| W, L, multiplicity, finger count, bias current | device spacing and placement, routing width, routing layer, critical-net constraints, matched-routing constraints |

A parasitic problem caused by a long coupled route is not fixable by resizing
a transistor.

## What an agent must never do

- declare success after pre-layout simulation only;
- declare success after DRC/LVS only;
- declare success because PEX **extraction** completed;
- treat a tool crash as a specification failure;
- run PEX simulation on a layout that failed DRC or LVS;
- loop without a bound.
