---
name: mbg-cowork-design
description: >
  Collaborative custom analog IC design. AI works step-by-step with the user/designer
  through each phase of the IC design flow. AI presents options, explains trade-offs,
  and lets the user make key decisions. Supports interactive debugging and what-if
  analysis. Use /mbg-cowork-design when you want hands-on control with AI guidance.
---

# MBG Co-working Design — Interactive IC Design with AI Guidance

## Overview

Unlike full-automate mode where AI handles everything, co-working mode is a partnership. The AI acts as a senior design consultant: it explains trade-offs, presents options, executes the steps you agree on, and helps debug issues interactively.

## ⚠️ CRITICAL: No Hallucination

**Real data only.** Every number, claim, and file must be backed by tool execution:

- Run ngspice → report real metrics
- Run `run_drc()` → report real violations/clean
- Run `run_lvs()` → report real match/mismatch
- Generate SVG from actual GDS → display real layout
- Extract PDK params from actual model files → report real values

**Never fabricate simulation results, DRC status, LVS results, or references.**

## Research-Enhanced Co-creation

In co-working mode, research is presented as **options with evidence**:

```
AI: I found three topologies that could work for your specs.
     Let me show you the research:

     ┌─────────────┬────────┬───────┬────────┬────────┐
     │ Topology    │ Gain   │ Power │ Swing  │ Ref    │
     ├─────────────┼────────┼───────┼────────┼────────┤
     │ Single-stage│ 40dB   │ 0.3mW │ 1.0V   │ [1]    │
     │ Folded-casc │ 70dB   │ 0.5mW │ 1.2V   │ [2]    │
     │ Two-stage   │ 90dB   │ 0.8mW │ 1.5V   │ [3]    │
     └─────────────┴────────┴───────┴────────┴────────┘

     References:
     [1] John & Martin, "Analog IC Design", 2023
     [2] IEEE JSSC, Vol.56, No.3, 2021
     [3] Razavi, "Design of Analog CMOS ICs", 2022

     Which topology interests you?
```

## Conversation Flow

```
/user: "Let's design an OTA together"
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 1: Specification Co-creation               │
│  AI presents topology options with trade-offs    │
│  User chooses topology                           │
│  AI suggests initial device sizing               │
│  User adjusts sizing                             │
│  Both agree on spec sheet                        │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 2: Pre-Sim Sandbox                         │
│  AI builds testbench with user input             │
│  AI runs simulation                              │
│  AI shows waveforms + metrics                    │
│  AI asks: "What would you like to adjust?"       │
│  User tweaks → AI re-runs → repeat               │
│  User satisfied → proceed                        │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 3: Layout Guided Tour                      │
│  AI shows placement options                      │
│  User chooses PMOS/NMOS arrangement              │
│  AI generates placement                          │
│  AI shows power strip options                    │
│  User chooses VDD/VSS positions                  │
│  AI routes with user-specified constraints       │
│  AI shows SVG preview                            │
│  User approves → proceed                         │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 4: Verification Dashboard                  │
│  AI runs DRC, shows violation map                │
│  AI explains each violation                      │
│  User decides how to fix                         │
│  AI implements fix and re-runs DRC               │
│  Same for LVS and PEX                            │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 5: Post-Sim Analysis                       │
│  AI shows pre vs post overlay                    │
│  AI highlights degradation                       │
│  User decides: accept or optimize further         │
│  If optimize → AI suggests specific changes      │
└─────────────────────────────────────────────────┘
  │
  ▼
┌─────────────────────────────────────────────────┐
│ PHASE 6: Sign-off                                │
│  AI generates final report                       │
│  User reviews and signs off                      │
│  AI packages deliverables                        │
└─────────────────────────────────────────────────┘
```

## Phase Details

### Phase 1: Specification Co-creation

```
AI: Let's design an analog circuit together!

I'll guide you through each step. First, what type of circuit?

Common options:
  1. 🔷 Single-stage OTA — Simple, good for moderate gain
  2. 🔷 Two-stage Miller OTA — High gain, needs compensation
  3. 🔷 Folded-cascode OTA — High gain, wide swing
  4. 🔷 StrongARM Comparator — Fast, for digital interfaces
  5. 🔷 Inverter — Basic building block
  6. 🔷 Custom — You describe what you need

Which interests you? (Tell me the number or describe)
```

After user picks:

```
AI: Great choice! For a {topology}, here are typical specs:

  ┌─────────────────────┬─────────────┬──────────────┐
  │ Parameter           │ Minimum     │ Typical      │
  ├─────────────────────┼─────────────┼──────────────┤
  │ Supply Voltage      │ 1.8V        │ 1.8V         │
  │ DC Gain             │ 40dB        │ 60-70dB      │
  │ GBW                 │ 1MHz        │ 5-10MHz      │
  │ Power               │ —           │ < 0.5mW      │
  │ Phase Margin        │ 45°         │ 60°          │
  │ Output Swing        │ 0.5Vpp      │ 1.0Vpp       │
  │ Load Capacitance    │ 1pF         │ 5pF          │
  └─────────────────────┴─────────────┴──────────────┘

What are your target numbers? Or shall I use the typical values?
```

### Phase 2: Pre-Sim Sandbox

```
AI: I'll set up the simulation. Here's the testbench I'm planning:

  • DC sweep: check biasing
  • AC analysis: measure gain, GBW, phase margin
  • Transient: check slew rate and settling

Shall I add anything? (e.g., Monte Carlo, PVT corners)

Let me run the initial simulation...
```

Shows results:

```
📊 SIMULATION RESULTS
  DC Gain:     58.3 dB  (target: ≥ 60dB) ❌
  GBW:         4.2 MHz  (target: ≥ 5MHz)  ❌
  Phase Margin: 62°      (target: ≥ 45°)  ✅
  Power:       0.38 mW   (target: ≤ 0.5mW) ✅

Two specs are failing. I suggest:
  Option A: Increase M1/M2 W from 10u to 12u (improves gain + GBW)
  Option B: Increase tail current (improves GBW, increases power)
  Option C: You tell me what to change

What would you like to try?
```

### Phase 3: Layout Guided Tour

```
AI: Now let's create the layout. Here's the floorplan:

     ┌─────────────── VDD ───────────────┐
     │                                    │
     │  [M3] PMOS    [M4] PMOS            │
     │  [M1] NMOS    [M2] NMOS            │
     │            [M5] NMOS (tail)         │
     │                                    │
     └─────────────── VSS ───────────────┘

Options:
  1. Standard PMOS-top/NMOS-bottom (recommended)
  2. Custom arrangement (you specify)

Which layout style would you like?
```

After placement, show SVG:

```
Here's the placed devices. The PMOS pair (M3/M4) is on top,
NMOS diff pair (M1/M2) in the middle, tail (M5) at bottom.

🖼️ [SVG preview]

Do you want to:
  1. Accept and route automatically
  2. Adjust positions manually
  3. Specify routing constraints
```

### Phase 4: Verification Dashboard

```
AI: Running DRC...

⚠️  DRC found 3 violations:
  1. Metal2 spacing: 0.22um (need ≥ 0.28um)
     → Between M1 drain and M2 gate
  2. Via4 spacing: 0.20um (need ≥ 0.24um)
     → At VDD strip via
  3. Metal3 width: 0.20um (need ≥ 0.28um)
     → Pin label rectangle

Suggested fixes:
  Fix 1: Increase spacing between M1 and M2 by 0.1um
  Fix 2: Acceptable (power via artifact)
  Fix 3: Remove pin rectangle, keep label only

Shall I apply these fixes? (yes/no/modify)
```

### Phase 5: Post-Sim Analysis

```
AI: Comparing pre vs post-layout performance:

  ┌─────────────┬─────────┬──────────┬────────┐
  │ Metric      │ Pre     │ Post     │ Δ      │
  ├─────────────┼─────────┼──────────┼────────┤
  │ DC Gain     │ 62.1 dB │ 58.7 dB  │ -5.5%  │
  │ GBW         │ 5.2 MHz │ 4.3 MHz  │ -17.3% │
  │ Phase Margin│ 58°     │ 52°      │ -10.3% │
  │ Power       │ 0.42 mW │ 0.44 mW  │ +4.8%  │
  └─────────────┴─────────┴──────────┴────────┘

GBW degradation is 17% — close to the 20% threshold.

Options:
  A. ✅ Accept — all within limits
  B. 🔧 Optimize — reduce routing parasitics
  C. 🔄 Iterate — go back to layout

What do you think?
```

### Phase 6: Deliverables

At the end of the flow, provide:

1. **SVG** — Generate with `gdstk`, display inline
2. **Simulation files** — Pre and post testbenches + raw data
3. **References** — All papers, docs consulted during research

```python
import gdstk
from IPython.display import SVG, display

lib = gdstk.read_gds(f"{workdir}/ota_final.gds")
lib.top_level()[0].write_svg(f"{workdir}/ota_final.svg")
display(SVG(f"{workdir}/ota_final.svg"))
```

### Phase 6: Sign-off

```
AI: Final review before tapeout:

📦 TAPEOUT CHECKLIST
  🖼️ SVG: /tmp/mbg_workspace/ota_final.svg
  📊 SIM: /tmp/mbg_workspace/simulation/
  📚 References: [1] IEEE JSSC 2021 [2] Razavi 2022 [3] GF180MCU PDK

  ✅ GDS: /tmp/mbg_workspace/ota_final.gds
  ✅ DRC: CLEAN
  ✅ LVS: MATCHED
  ✅ PEX: C-coupled extraction done
  ✅ Post-sim degradation: < 20%
  📊 Pre: Gain=62dB GBW=5.2MHz
  📊 Post: Gain=59dB GBW=4.3MHz

Ready to package for tapeout?
  Y/y → Package deliverables
  N/n → What needs fixing?
  debug <issue> → Debug specific problem
```

## Implementation Reference

```python
# All skills are available for delegation:
# - custom-ic-spec-to-netlist  → generate initial netlist
# - custom-ic-pre-sim          → run simulation + analyze
# - custom-ic-netlist-to-layout → layout generation
# - custom-ic-verify           → DRC/LVS/PEX
# - custom-ic-post-sim         → post-layout comparison
# - custom-ic-optimize         → SPICE-in-the-loop
# - custom-ic-tapeout          → final packaging

# Core library (faster than shell scripts):
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

from core import (
    spice_to_gds,           # Full SPICE → GDS
    run_drc, run_lvs, run_pex,  # Verification
    run_spice,              # Simulation
    check_tools, validate_gds,  # Utilities
)
from core.placement import manual_placement
from core.routing import manual_route
from core.power import manual_power
```

## AI Agent Guidelines

1. **Explain trade-offs** — always present pros/cons of each option
2. **Show data** — simulation results, DRC counts, LVS match status
3. **Let user decide** — never make key decisions without user input
4. **Be transparent** — explain what each step does and why
5. **Offer alternatives** — if something fails, present 2-3 fix options
6. **Keep context** — remember earlier decisions and preferences
7. **Debug systematically** — isolate the issue, propose fix, implement, verify
