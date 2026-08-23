# Run Notes — ox_alpha_strongarm_comparator

Model: **ox-alpha** · Date: 2026-08-23 · PDK: gf180mcuD · Flow: `/mbg-full-auto`

## Final result

`SUCCESS` — `TAPEOUT_READY`. All 13 sign-off gate conditions PASS
(see `final_design_report.md`). Characterization addendum: 45/45 PVT
conditions pass; mismatch MC offset sigma = 1.65 mV (target <= 10 mV).

Final sizing (all `nfet_03v3`/`pfet_03v3`, nf=1, W < 10 um):

| device | role | W | L |
|---|---|---|---|
| XMTAIL | clocked tail | 9.1u | 0.5u |
| XMINN/XMINP | input pair | 3u | **0.7u** |
| XMLATN/XMLATP | NMOS regen latch | 2.3u | 0.5u |
| XMPLTN/XMLPLTP | PMOS regen latch | 3u | 0.5u |
| XMPRSN/XMPRSP | precharge SN_N/SN_P | 0.8u | 0.5u |
| XMPRON/XMPROP | precharge OUTN/OUTP | 1.6u | 0.5u |

Output polarity is non-inverting by construction (pair drains crossed to the
opposite latch half): OUTP > OUTN when INP > INN.

## How the search actually went (honest trail)

1. v1 design (uniform-ish sizing) had a topology bug I introduced and fixed:
   both pair drains shared one node; split into SN_N/SN_P.
2. v2 (nf=2 pair): layout legs all passed, but Magic extraction split the
   multi-finger pair devices into cross-connected series pairs with oversized
   junction caps -> PEX delay +47% and one wrong decision. Redesigned with
   nf=1 everywhere (matches the tested complexity envelope).
3. Measurement-definition fixes, each verified against raw waveforms:
   - static-current window moved late in the reset phase (the uA-level reading
     right after the falling edge is a relaxation transient with tau ~ 20-30 ns;
     true DC floor ~20 pA by operating point).
   - reltol=1e-2/trtol=2 for the regenerative transient: verified identical
     crossing times (< 0.2 ps delta vs default tolerances), 4x faster.
4. First full flow run (normal effort): NOT_CONVERGED - PEX dt 7.2 ns,
   correct_frac 0.94; built-in branch-and-compare exhausted its global width
   moves instantly ("no candidate moves left").
5. Second run (high effort, comparator-specific candidate vocabulary):
   PEX delay recovered to 4.0-4.4 ns but correct_frac stuck at 0.82-0.94;
   diagnosed the failing corner as +5 mV @ CM 2.3 V (fast but wrong =
   systematic asymmetry > 5 mV equivalent at that bias).
6. v3 seed + checkpointed stepping (`pex_step.py`, one candidate per process,
   state in pex_state.json): baseline 0.2732 -> `pair_L_down` (pair L 1u->0.7u)
   0.0588 -> `combo_tail_nlat` (tail x1.3, NFET latch x1.15) **score 0.0 PASS**.
   Withheld after two failures each: pair_w_up, nlat_up, plat_up.
7. Canonical evidence pass: `run_full_auto` re-run seeded with the winning
   netlist -> pre-layout PASS, single PEX iteration PASS, SUCCESS.

## Environment incidents (disclosed)

- The machine (14 GB RAM, 12 cores) ran several parallel agent sessions
  (other models' comparator benchmarks) at load ~25; my runs were twice
  SIGTERM'd externally and the full-flow process was OOM-killed once
  (systemd unit result `oom-kill`). The search was therefore restructured
  into short checkpointed steps under a systemd --user unit so no kill could
  lose more than one candidate.
- One ngspice invocation was killed by a bash-tool timeout before completing;
  it was re-run and completed normally. No measurement in this report comes
  from an incomplete simulation.

## What was NOT done / limitations

- The sign-off gate lists PVT corners and Monte Carlo as "NOT REQUIRED"
  because the canonical gate does not configure them; they were nevertheless
  executed afterwards as characterization addenda (section 13). The gate rows
  reflect the framework's configuration, not omission of the analyses.
- Offset MC runs on the schematic netlist (standard design-stage practice);
  nominal PEX verification covers parasitics. MC on the extracted netlist was
  not run (60 extracted transients would add hours for little information at
  these margins).
- The intermediate automated stage reviews from the two killed runs were lost
  with their history files; the surviving canonical run contains its complete
  review ledger (Devil 1 HIGH answered in report section 13.4, 1 MEDIUM
  answered by measurement).

## Files

- `final_design_report.md` - canonical report + characterization addendum
- `best/final_sizing.spice` - final schematic netlist (provenance seed)
- `best/strongarm_comparator.gds` - final layout (also in `final/`)
- `best/strongarm_comparator_pex.spice` - final extracted netlist (also `final/`)
- `characterization/` - pvt.json, offset_mc.json, CHARACTERIZATION.md
- `pex_state.json`, `step.log` - checkpointed LOOP B state and log
- `flow_search.log`, `final_run.log`, `char.log` - full run logs
- `strongarm_tb.py` - testbench/measurement module (transient TB, PVT, MC)
- `run_flow.py` / `run_final.py` - flow runners (search / canonical evidence)
