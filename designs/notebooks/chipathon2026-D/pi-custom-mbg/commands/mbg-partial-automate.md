# /mbg-partial-automate — Semi-Automatic Analog IC Design Flow

**Mode**: Step-by-step with user confirmation at each stage.

## Workflow

### Step 1: Input — User Defines Design
Ask the user:
- What circuit to design?
- Target specifications?
- Any preferences for topology or sizing?

### Step 2: Research — AI Proposes, User Reviews
- AI researches topology and sizing
- Present findings to user
- **User reviews and gives feedback** before proceeding

### Step 3: Spec-to-Netlist — AI Generates, User Edits
- AI generates SPICE netlist
- Present netlist to user
- **User can edit or request changes**

### Step 4: Pre-Simulation — AI Runs, User Reviews
- AI runs `ngspice` simulation
- Present waveform/results to user
- **User confirms specs are met** or requests sizing changes

### Step 5: Layout — AI Generates, User Directs
- AI generates placement + power + routing
- Present SVG/PNG preview to user
- **User reviews layout and gives placement/routing guidance**

### Step 6: DRC/LVS — AI Checks, User Reviews Errors
- AI runs DRC and LVS
- Present results to user
- **User decides how to fix violations**

### Step 7: PEX — AI Extracts, User Compares
- AI runs parasitic extraction and post-layout simulation
- Present pre-sim vs post-sim comparison
- **User confirms results or requests finetuning**

### Step 8: Tapeout — Final User Approval
- AI prepares final GDS and documentation
- **User gives final approval** before tapeout

## Safety
- Never claim DRC/LVS/PEX success without evidence
- Each step requires explicit user confirmation
- No automatic git operations
