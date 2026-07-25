---
name: custom-ic-research
description: >
  Deep research for custom analog IC design. Researches circuit topologies, device
  sizing, design trade-offs, and foundry PDK characteristics. Integrates with
  mbg-full-automate and mbg-cowork-design to provide evidence-based design
  decisions. Use when you need to research the best topology, sizing, or approach
  for a given set of IC design specifications.
metadata:
  version: "1.0.0"
  integrates_with:
    - mbg-full-automate
    - mbg-cowork-design
    - custom-ic-spec-to-netlist
---

# Custom IC: Deep Research for Analog Design

## Overview

Research is a critical first step in any IC design project. Before committing to a topology or device sizing, it's essential to understand what has been done before, what trade-offs exist, and what the PDK supports.

This skill provides **structured research** on four key IC design questions:

| Research Type | When to Use | Output |
|--------------|-------------|--------|
| **Topology Research** | Choosing circuit architecture | Comparison table of topologies with pros/cons |
| **Sizing Research** | Determining W/L for given specs | Recommended device sizes with rationale |
| **Trade-off Analysis** | Power vs Area vs Speed | Pareto-front analysis |
| **PDK Research** | Understanding technology limits | Key PDK parameters (Vth, Cox, etc.) |

## Integration with MBG Flow

```
User Specs ──► custom-ic-research ──► Design Plan ──► mbg-full-automate / mbg-cowork-design
                      │                        │
                      ▼                        ▼
              Literature + PDK           Approved by User
              Data + Trade-offs
```

## Research Methodology (Adapted from Deep Research)

### Phase 1: Scoping

Define the research question precisely:

```
Research Question: "What is the optimal OTA topology for <specs>?"
Constraints: <supply, power, area, technology>
Success Criteria: <gain, BW, PM targets>
```

### Phase 2: Literature Search

Search for published work on similar designs:

```
Search queries:
- "OTA design <technology> low power <gain>"
- "Single-stage vs two-stage OTA comparison <process>"
- "<topology> design methodology analog"
```

### Phase 3: PDK Parameter Extraction

Research key PDK parameters from the foundry documentation:

```bash
# From PDK model files
grep "VTO\|KP\|THICK\|COX" $PDKPATH/libs.tech/ngspice/sm141064.ngspice | head -20
```

### Phase 4: Synthesis & Recommendation

Synthesize findings into a structured recommendation:

```python
recommendation = {
    "topology": "Folded-cascode OTA",
    "rationale": [
        "Higher gain than single-stage (60dB vs 40dB)",
        "Better PSRR than telescopic",
        "Wider output swing than telescopic"
    ],
    "estimated_sizing": {
        "M1/M2": "W=10u L=1u",
        "M3/M4": "W=20u L=1u",
        "M5": "W=15u L=1u"
    },
    "risks": [
        "Higher power than single-stage",
        "More complex compensation"
    ]
}
```

## Research Agents

When invoked, this skill deploys multiple research perspectives:

### 1. Circuit Designer Agent
- Researches circuit topologies from textbooks and papers
- Analyzes trade-offs between architectures
- Estimates first-pass device sizing

### 2. PDK Expert Agent
- Extracts key parameters from PDK model files
- Identifies process limitations (min W/L, available devices)
- Checks design rule constraints

### 3. Verification Agent
- Researches testbench design
- Identifies potential simulation pitfalls
- Suggests corner case analysis

## Quick Start

```python
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "core"))

# Research a design topology
specs = {
    "circuit": "OTA",
    "gain_db": 60,
    "gbw_mhz": 5,
    "power_uw": 500,
    "supply_v": 1.8,
    "load_pf": 5,
    "technology": "GF180MCU"
}

# The AI agent will research and return a structured recommendation
# (This is an AI-driven process — see SKILL.md for full methodology)
```

## Research Templates

### Topology Comparison Template

| Topology | Gain | BW | Power | Swing | Area | Complexity |
|----------|------|----|-------|-------|------|------------|
| Single-stage OTA | 40dB | High | Low | Medium | Small | Low |
| Two-stage Miller | 80dB | Medium | Medium | High | Medium | Medium |
| Folded-cascode | 70dB | High | Medium | High | Medium | Medium |
| Telescopic | 70dB | High | Low | Low | Small | Low |
| Current-mirror OTA | 60dB | Medium | Low | Medium | Medium | Low |

### Sizing Estimation Template

```python
def estimate_sizing(gm, id, vov, technology="gf180mcu"):
    """Estimate W/L from gm/ID methodology."""
    # gm = 2*ID/Vov (strong inversion)
    # W/L = gm^2 / (2 * KP * ID)
    KP_N = 200e-6  # for GF180MCU NMOS (typical)
    KP_P = 100e-6  # for GF180MCU PMOS (typical)
    # ... calculation
    return {"W": w, "L": l}
```

## Files

- `scripts/research_topology.py` — Topology research helper
- `scripts/extract_pdk_params.py` — PDK parameter extraction
- `scripts/estimate_sizing.py` — First-pass sizing estimation
