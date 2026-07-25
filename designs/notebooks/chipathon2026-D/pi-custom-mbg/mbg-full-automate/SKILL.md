---
name: mbg-full-automate
description: >
  Fully automated custom analog IC design. AI interviews the user about specifications,
  does deep research on the design requirements, proposes a plan, gets user confirmation,
  then fully automates: netlist generation → pre-simulation → layout → DRC → LVS → PEX →
  post-simulation comparison. AI asks for final confirmation before delivering the GDS.
  Use /mbg-full-automate when you want the AI to handle everything from spec to tapeout.
---

# MBG Full Automate — End-to-End Custom IC Design

## Overview

This skill fully automates the custom analog IC design flow from specification to verified GDSII. The AI agent acts as a lead designer: it researches, proposes, builds, verifies, and delivers.

## Flow

```
/user: "Design an OTA for me"
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 1: Discovery & Research                    │
│  AI asks user about:                             │
│  • Circuit type (OTA, comparator, inverter, etc) │
│  • Specifications (gain, BW, power, supply, etc) │
│  • Technology (GF180MCU default)                 │
│  • Area / power / speed priorities               │
│  AI does deep research on similar designs        │
│  AI presents analysis + proposed plan            │
│  User provides feedback → AI re-researches       │
│  User approves plan → proceed                    │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 2: Pre-Layout Simulation                   │
│  AI generates SPICE netlist                      │
│  AI builds testbench                             │
│  AI runs ngspice simulation                      │
│  AI extracts metrics                             │
│  AI compares against specs                       │
│  If FAIL → AI iterates (sizing, topology)        │
│  If PASS → proceed                               │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 3: Layout Generation                       │
│  AI runs spice_to_gds()                          │
│  (or manual placement/power/routing for control) │
│  AI writes GDS + SVG                             │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 4: Physical Verification                    │
│  AI runs DRC → clean? → fix → re-run             │
│  AI runs LVS → match? → fix → re-run             │
│  AI runs PEX → extract parasitics                │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 5: Post-Layout Simulation                   │
│  AI runs post-layout sim with PEX netlist        │
│  AI compares pre vs post metrics                 │
│  AI reports degradation                          │
│  If degradation > 20% → AI flags and suggests    │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 6: Delivery                                │
│  AI presents final results to user               │
│  AI asks: "Approve this design?"                 │
│  User approves → AI packages tapeout             │
│  User requests debug → AI runs fix-flow          │
└─────────────────────────────────────────────────┘
```

## ⚠️ CRITICAL: No Hallucination

**Never fabricate data.** All claims must come from actual tool execution:

- ❌ "Gain = 45.2 dB" without running ngspice → ❌ FORBIDDEN
- ❌ "DRC: CLEAN" without running `run_drc()` → ❌ FORBIDDEN  
- ❌ "LVS: MATCHED" without running `run_lvs()` → ❌ FORBIDDEN
- ❌ Citing a paper you haven't read → ❌ FORBIDDEN

✅ Only report: raw tool output, verified file paths, real PDK parameters.

Before any claim, ask: *"Did I actually run the tool for this?"*

## Research-Enhanced Discovery

Before proposing a design, the AI **must** perform deep research:

### Research Steps (Phase 0)

1. **Search for similar designs** — Find published OTAs/comparators/amplifiers with comparable specs
2. **Extract PDK parameters** — Run `scripts/extract_pdk_params.py` to get Vth, KP, Cox
3. **Compare topologies** — Use the topology comparison table to pick the best fit
4. **Estimate first-pass sizing** — Use gm/ID or square-law for initial W/L
5. **Present evidence** — Show research findings alongside the proposal

### Research Prompts for the AI

```
Search: "Low-power OTA design GF180MCU 3.3V 500uW"
Search: "Single-stage vs two-stage OTA comparison 180nm"
Search: "OTA design methodology gain 60dB GBW 5MHz"
```

### Phase 1: Discovery

```
AI: I'll design a custom analog IC for you. Let me ask a few questions:

1. What type of circuit do you need?
   (e.g., OTA, comparator, inverter, LDO, buffer, custom)

2. What are your target specifications?
   - Supply voltage (default: 1.8V)
   - DC gain (for amplifiers)
   - Gain-bandwidth / speed
   - Power budget
   - Output swing
   - Load capacitance
   - Phase margin

3. Any area constraints? (compact? large but高性能?)

4. Technology preference? (GF180MCU, Sky130, or other)

Let me research similar designs and come back with a proposal.
```

After user responds, AI does deep research via web search on similar circuit topologies and specifications, then presents:

```
AI: Based on your requirements and my research, here's my proposal:

📋 DESIGN PLAN
  Circuit: 5-transistor OTA
  Technology: GF180MCU (180nm)
  Supply: 1.8V
  Topology: Single-stage differential OTA
  Target specs:
    • DC Gain: > 60dB
    • GBW: > 5MHz
    • Power: < 0.5mW
    • Load: 5pF

  Device sizes (first-pass estimate):
    M1/M2 (diff pair): W=10u, L=1u
    M3/M4 (load): W=20u, L=1u
    M5 (tail): W=15u, L=1u

  Estimated area: ~50×80µm

Does this look good? Any changes you'd like?
```

### Phase 2-5: Automation

AI runs the flow automatically using the core library. At each stage, AI reports progress:

```
✅ Pre-sim PASSED: Gain=65dB GBW=5.2MHz Power=0.45mW
✅ DRC: CLEAN (0 violations)
✅ LVS: MATCHED (Circuits match uniquely)
⚠️ Post-sim: Gain=62dB (5% degradation — acceptable)
```

### Phase 6: Final Deliverables

When the flow completes, the AI **must** provide all of the following to the user:

#### 1. 🖼️ Layout Visualization (SVG)

```python
import gdstk
from IPython.display import SVG, display

lib = gdstk.read_gds(f"{workdir}/ota_final.gds")
lib.top_level()[0].write_svg(f"{workdir}/ota_final.svg")
display(SVG(f"{workdir}/ota_final.svg"))
```

#### 2. 📊 Testbench & Simulation Files

Provide the complete testbench SPICE file used for pre and post-layout simulation:

- `{workdir}/simulation/pre_sim.spice` — Pre-layout testbench
- `{workdir}/simulation/post_sim.spice` — Post-layout testbench (with PEX)
- `{workdir}/simulation/pre_sim.raw` — Pre-layout raw simulation data
- `{workdir}/simulation/post_sim.raw` — Post-layout raw simulation data

#### 3. 📚 Research References

List all sources, papers, and PDK documentation consulted during the research phase:

```markdown
## References Consulted
1. IEEE JSSC, Vol.56, No.3, 2021 — "Low-power OTA design in 180nm"
2. Razavi, "Design of Analog CMOS Integrated Circuits", 2022
3. GF180MCU PDK Documentation — sm141064.ngspice model parameters
4. John & Martin, "Analog Integrated Circuit Design", 2023
5. [gLayout cells] https://github.com/ReaLLMASIC/gLayout/tree/main/src/glayout/cells
```

### Phase 6: Final Confirmation

```
AI: Design complete! Here's the summary:

📦 FINAL DESIGN SUMMARY
  🖼️ SVG: /tmp/mbg_workspace/ota_final.svg (layout visualization)
  📊 SIM: /tmp/mbg_workspace/simulation/ (pre + post testbenches)
  📚 REF: Research references listed below

  • GDS: /tmp/mbg_workspace/ota_final.gds (45kB)
  • DRC: ✅ CLEAN
  • LVS: ✅ MATCHED
  • Pre vs Post:
      Gain: 65dB → 62dB (Δ = -5%)
      GBW:  5.2MHz → 4.8MHz (Δ = -8%)
      Power: 0.45mW → 0.47mW (Δ = +4%)

📚 References:
  [1] IEEE JSSC, Vol.56, No.3, 2021
  [2] Razavi, "Design of Analog CMOS ICs", 2022
  [3] GF180MCU PDK Documentation

  All within acceptable limits. 

  ✅ APPROVE and package for tapeout?
  🔧 DEBUG a specific issue?
```

## Implementation

### Phase 1 helper — spec gathering and research

Use the `custom-ic-spec-to-netlist` skill to generate the initial netlist after the plan is approved.

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from core.pipeline import generate_netlist_from_prompt

# After user approves the plan
netlist = generate_netlist_from_prompt(f"""
Design a {circuit_type} in GF180MCU:
- Supply: {vdd}V
- DC Gain: > {gain}dB
- GBW: > {gbw}MHz
- Power: < {power}mW
- Load: {load}pF
- Topology: {topology}
Use nfet_03v3 and pfet_03v3 models.
""")
```

### Phase 2 helper — pre-simulation check

```python
from core.simulation import run_spice
from custom-ic-pre-sim.scripts.analyze_results import parse_raw, analyze_transient

result = run_spice(netlist_with_tb)
data = parse_raw(result["raw_path"])
metrics = analyze_transient(data)
# Compare against specs
all_pass = all(metrics[k] >= specs[k] for k in specs)
```

### Phase 3-5 helpers

Use the existing skills:
- `custom-ic-netlist-to-layout` for layout generation **(read the verified inverter example for routing rules)**
- `custom-ic-verify` for DRC/LVS/PEX
- `custom-ic-post-sim` for post-layout comparison

**Routing rules (from the verified inverter example):**
1. met3 = horizontal, met4 = vertical, met5 = power strips
2. Each met4 vertical must have a UNIQUE x-track (≥ 2µm apart)
3. Use `via1_layer: "met3"` / `via2_layer: "met3"` for VDD/VSS port vias
4. Add `via_met3_met4` at every met3↔met4 transition
5. **Always route body ties** — PMOS body_W → VDD, NMOS body_W → VSS
6. Start horizontal traces at via-center y (port_y ± 0.25 for orientation 90/270)
7. Never add `via_met4_met5` — the power strip creates its own via

### Debug flow

When user asks to debug:

```
AI: What issue are you seeing?
  1. DRC violations → Run fix_drc() helper
  2. LVS mismatch → Check ports, run fix_lvs()
  3. Simulation fail → Check testbench, run fix_sim()
  4. Performance issue → Run SPICE-in-the-loop optimization
```

```python
from core.checks import run_drc, run_lvs
from core import spice_to_gds

def fix_drc(gds_path):
    drc = run_drc(gds_path)
    if "spacing" in drc["summary"].lower():
        # Increase spacing and regenerate
        pass
    elif "width" in drc["summary"].lower():
        # Fix metal widths
        pass
    return drc["clean"]
```

## Key Rules for the AI Agent

1. **Always research first** — before proposing a design, search for similar circuits, topologies, and typical device sizes
2. **Get explicit approval** — never generate layout without user confirming the plan
3. **Report every phase** — show results and metrics at each stage
4. **Ask before tapeout** — final confirmation before packaging
5. **Handle errors gracefully** — if a step fails, explain the issue and offer solutions
6. **Iterate on feedback** — if user doesn't like the plan, research again with their feedback
