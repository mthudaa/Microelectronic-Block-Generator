# MBG Design Flow Reference

## Complete Analog IC Design Flow

```
Phase 0: Specification ──► Phase 1: Pre-Layout Sim ──► Phase 2: Layout ──► Phase 3: Verification ──► Phase 4: Post-Sim ──► Phase 5: Tapeout
```

### Phase 0: Specification & Architecture

1. Define circuit specs (gain, BW, power, swing, etc.)
2. Select topology
3. First-pass device sizing
4. Generate SPICE netlist (manually or via LLM)

### Phase 1: Pre-Layout Simulation

1. Create testbench (DC/AC/Transient)
2. Run ngspice
3. Extract metrics
4. Compare against specs
5. Iterate if needed

### Phase 2: Layout Design

1. Parse SPICE → device list
2. Generate devices via gLayout
3. Place PMOS top, NMOS bottom (ALIGN-inspired)
4. Add power strips (VDD/VSS on M5)
5. Auto-route signals (PathFinder NCR)
6. Add pin labels (Magic-readable)
7. Write GDSII + SVG

### Phase 3: Physical Verification

1. DRC (Magic or KLayout)
2. LVS (Magic extract + netgen)
3. PEX (Magic parasitic extraction)

### Phase 4: Post-Layout Simulation

1. Create post-layout testbench with PEX netlist
2. Run ngspice
3. Compare pre vs post metrics
4. Accept if degradation ≤ 20%

### Phase 5: SPICE-in-the-Loop

1. If specs not met: generate LLM feedback
2. LLM revises netlist
3. Repeat from Phase 1

### Phase 6: Tapeout

1. Final DRC/LVS/PEX
2. Package GDS + netlist + reports
3. Generate summary
