# FULL AUTOMATE and the multi-agent review model — canonical definition

Single source of truth for `/mbg-full-auto`, the reviewer roles, and the MBG
command namespace. Claude Code, Codex and OpenCode all read generated copies
of this. If they disagree, this file wins — regenerate with
`python3 scripts/sync_agent_tools.py`.

Read `.ai/knowledge/DESIGN_FLOW.md` first: FULL AUTOMATE *drives* that
two-loop flow, it does not replace it.

## The MBG command namespace

**Every user-facing MBG slash command begins with `/mbg-`.** No exceptions,
identical on all three platforms.

| Command | Purpose |
| --- | --- |
| `/mbg-full-auto` | **canonical** — one design request to sign-off or a truthful failure report |
| `/mbg-partial-automate` | the same flow, confirming each stage with the user |
| `/mbg-review` | Devil + Angel review of the current design state |
| `/mbg-signoff` | run the tapeout-ready gate |
| `/mbg-report` | generate the design report for a completed run |
| `/mbg-status` | stage, iteration and convergence state of a run |
| `/mbg-check` | environment preflight |
| `/mbg-install`, `/mbg-setup-env` | setup |
| `/mbg-new-skill`, `/mbg-new-command` | authoring |
| `/mbg-review-ai-experiment`, `/mbg-review-extension` | audits |

Never expose these generic names for MBG functionality: not `/full-auto`, not
`/full-design`, not `/design`, not `/review`, not `/signoff`, not `/report`,
not `/status`, not `/pex`. A shell CLI may use `mbg full-auto ...`; that is
separate from the slash-command standard.

## Roles

```
                    Orchestrator
                         │
                    Designer Agent
                         │
              ┌──────────┴──────────┐
        Devil Reviewer        Angel Reviewer
        (falsify it)          (best way forward)
              └──────────┬──────────┘
                    Synthesizer
                         │
        ACCEPT · REVISE · RETRY · ROLLBACK · ESCALATE · BLOCK
```

| Role | Responsibility | May edit the design? |
| --- | --- | --- |
| **Designer** | proposes and modifies the design | **yes** |
| **Devil** | adversarial: risks, gaps, unsafe passes, missing evidence | no |
| **Angel** | constructive: the cheapest change most likely to work | no |
| **Synthesizer** | weighs both against measured evidence, decides | no |
| **Orchestrator** | sequences stages, enforces bounds, packages results | no |

Critics return **structured findings and recommendations**, never edits. That
is what lets the framework record who proposed what, whether it was tried,
and whether it helped.

The two reviewers are independent and see the same evidence; neither
summarises the other.

## Precedence — this is the important part

1. A reviewer that failed to run ⇒ `ESCALATE`. Silence is not approval.
2. A hard gate (DRC / LVS / PEX extraction) failing outranks everything.
3. An unresolved `CRITICAL` finding blocks acceptance.
4. Objective specification evidence outranks reviewer sentiment.
5. Only then do the reviewers' verdicts matter.

**Reviewers can block. They cannot approve past a failed gate.** Two
optimistic critics never turn an LVS mismatch into a sign-off.

Severity: `INFO` `LOW` `MEDIUM` `HIGH` `CRITICAL`.

## Review gates

Reviews run at logical stages, not after every subprocess:

`SPECIFICATION` · `INITIAL_CIRCUIT` · `PRE_SIMULATION` · `PRE_OPTIMIZATION` ·
`LAYOUT_GENERATION` · `DRC` · `LVS` · `PEX_EXTRACTION` · `PEX_SIMULATION` ·
`POST_LAYOUT_OPTIMIZATION` · `FINAL_SIGNOFF`

Stage-aware behaviour — a generic prompt is not enough:

| Stage | Devil checks | Angel recommends |
| --- | --- | --- |
| Specification | contradictory or infeasible targets, missing load/corner assumptions | clarifications, safe defaults, alternative topology |
| Pre-layout sim | measurement validity, thin margins, missing operating point | sizing, bias, compensation |
| Layout | matching, symmetry, critical routes, parasitic-prone nodes, wells | common-centroid, shorter routes, higher metal, shielding |
| PEX | degradation, hotspots, unexpected poles, RC loading, coupling | the change with the highest expected recovery |
| Sign-off | unsafe pass conditions, unmeasured claims | residual risk worth accepting |

## What `/mbg-full-auto` does

```
/mbg-full-auto "<design request>"
   -> parse + normalise the specification          (+ review)
   -> LOOP A: pre-layout simulate / evaluate / tune (+ review)
   -> layout -> DRC -> LVS -> PEX extraction        (+ review)
   -> LOOP B: PEX simulate / evaluate / tune        (+ review)
   -> final sign-off gate                           (+ review)
   -> tapeout package + design report, or non-convergence report
```

Specification provenance is tracked as `given` / `inferred` / `defaulted` /
`missing`. **A performance target that was not asked for is never invented** —
it is reported missing. A request with no target at all is a
`CONFIGURATION_FAILURE`, not a guess.

## Convergence strategy — search, don't guess

`/mbg-full-auto` does not stop because one or two edits failed. Do not stop
early: continue through the configured search budget until a legitimate
termination condition is reached.

**What went wrong before.** The optimizer took one fixed step per iteration
with a two-iteration budget. On the regression inverter it went
63.1 -> 89.1 MHz against a 100 MHz target and reported NOT_CONVERGED. A
measured sweep afterwards found the passing design one step further on
(125.9 MHz at width scale 0.80). The direction was right; the step policy and
the budget were wrong.

**Branch-and-compare.** Each iteration proposes several *distinct* candidates
from the same baseline, measures each independently, promotes the winner and
archives the rest:

```
best design
  +-- candidate A   measured
  +-- candidate B   measured   <- promoted
  +-- candidate C   measured
```

Because each candidate is built and simulated on its own, an improvement is
attributable to exactly one change. Applying three edits at once and crediting
all three — which the previous ledger did — is not evidence.

**Strategies, in escalation order.** `sensitivity` sizes the next step from a
measured d(metric)/d(knob); `line_search` continues a direction that already
worked, and brackets it so the search can overshoot and come back;
`heuristic` supplies the first move; a wide bracket fires only when nothing
local remains.

**Never extrapolate.** The same sweep shows shrinking further raises
bandwidth to 224 MHz but drops gain to 26.2 dB, breaking the *gain*
constraint, and that the space is non-monotonic. A step is chosen by
measurement, never by assuming the trend continues.

**Memory.** A move that fails twice without ever helping is withheld. Measured
sensitivities are retained and used to size later steps.

**Rollback.** If an iteration scores worse than the incumbent, the next one
resumes from the best design, not from the regression. Harmful edits do not
accumulate.

**Multi-objective.** The score is total normalised violation across *all*
required specs, so trading one violation for another scores worse, not
better. Margin breaks ties, because a design that scrapes past its target has
less left for PVT.

**Effort levels.** `FullAutoConfig.for_effort("normal" | "high" |
"exhaustive")` buys iterations and candidates per iteration. Default is
`normal` (12 pre / 12 PEX / 3 candidates), which prioritises convergence over
wall-clock.

**Escalation before giving up.** Local tuning, then wider brackets, then
`NOT_CONVERGED` — and the report must say which hypotheses were tested, which
parameter regions were sampled, and where the limit appeared.

## Bounds

`max_pre_iterations`, `max_pex_iterations`, `patience`, review timeouts and
retry counts. The run always terminates.

Final statuses: `SUCCESS` `NOT_CONVERGED` `BLOCKED` `TOOL_FAILURE`
`CONFIGURATION_FAILURE` `VERIFICATION_FAILURE` `SPEC_INFEASIBLE`.

Reviewer statuses: `OK` `REVIEWER_FAILURE` `REVIEW_INCOMPLETE`. A missing
mandatory review blocks tapeout-ready status.

## Tapeout-ready gate

`SUCCESS` requires every configured condition to be `PASS`:

```
pre-layout specs        PEX specs           DRC clean
LVS match               PEX extraction      final GDS
final PEX netlist       no CRITICAL findings
reviews complete        design report
PVT corners             (only if configured)
Monte Carlo / mismatch  (only if configured)
```

A condition that was not evaluated is reported **`NOT RUN`** and fails the
gate. It is never counted as passed. If corner or Monte-Carlo analysis did
not run, no claim is made about it.

## Outputs

```
outputs/<design>/
    history.json               per-iteration flow record
    review_history.json        decisions, findings, recommendation trace
    full_auto_result.json      machine-readable result
    final_design_report.md     design report, or non-convergence report
    final/                     GDS, PEX netlist, DRC/LVS reports, history
```

The recommendation trace records, per recommendation:
`PROPOSED → APPLIED → IMPROVED | NEUTRAL | DEGRADED`, with the measured score
before and after. Advice that never helps is withheld after two attempts.

## Honesty

FULL AUTOMATE means **autonomous execution of the supported design,
verification and optimization loop**. It does not mean guaranteed analog
design success. Outcomes are `TAPEOUT_READY` *or* a diagnosed failure state.
Never claim otherwise.

An agent must never:

- declare success after pre-layout simulation only;
- declare success after DRC/LVS only;
- declare success because PEX **extraction** completed;
- treat a tool crash as a specification failure;
- present a reviewer's sentence as a verification result;
- invent a specification the user did not give;
- report `NOT RUN` conditions as passed.
