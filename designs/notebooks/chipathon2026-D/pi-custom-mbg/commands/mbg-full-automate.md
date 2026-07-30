# /mbg-full-automate — Full Automatic Analog IC Design Flow

**Mode**: AI-driven, minimal user intervention after initial spec.

## Workflow

### Step 1: Gather Requirements
Ask the user:
- What circuit to design? (e.g. "5T-OTA", "bandgap reference", "comparator")
- Target specifications? (gain, bandwidth, power, area)
- PDK constraints? (default: gf180mcuD, 1.8V)

### Step 2: Research & Topology
- Research optimal topology for given specs
- Determine initial device sizing
- Analyze trade-offs (power vs speed, area vs matching)
- Present findings to user for confirmation

### Step 3: Confirmation
- Show proposed topology and sizing
- **User must confirm** before proceeding
- If rejected, return to Step 2 with feedback

### Step 4: Pre-Layout Simulation & Finetuning
- Generate SPICE netlist with initial sizing
- Run `ngspice` simulation
- Compare results against target specs
- **Auto-finetune**: iteratively adjust W/L until specs met
- Report final pre-simulation results

### Step 5: Layout Generation (SPICE → GDS)
- Convert SPICE to GDS using `spice_to_gds_with_checks()`
- Auto-placement, power routing, signal routing (PathFinder NCR)
- Run DRC — auto-fix if errors
- Run LVS:
  - **MATCH** → proceed to Step 6
  - **MISMATCH** → simplify SPICE architecture, retry

### Step 6: PEX & Post-Layout Verification
- Run parasitic extraction (PEX)
- Run post-layout simulation
- Compare pre-sim vs post-sim:
  - **Within spec** → proceed to Step 7
  - **Too far off** → finetune sizing, retry from Step 4

### Step 7: Final Report
- Layout GDS file
- DRC/LVS/PEX status
- Pre-sim vs post-sim comparison
- **Tapeout-ready** design

## Safety
- Never claim DRC/LVS/PEX success without evidence
- Verify ngspice output before claiming results
- No automatic git operations
