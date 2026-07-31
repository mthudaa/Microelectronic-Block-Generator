# Microelectronic Block Generator — AI/LLM Agentic Analog Chip Design

### *From IDEA to SPICE, from SPICE to GDS in an instant.*

**SSCS Chipathon 2026 — gLayout Track (D): AI/LLM for Analog Circuits**

An AI-assisted analog-layout framework that converts SPICE subcircuit netlists to
DRC-clean GDSII layout using [gLayout](https://github.com/ReaLLMASIC/gLayout),
[gdsfactory](https://github.com/gdsfactory/gdsfactory), and the **DeepSeek API**.
Supports AC/transient simulation,
DRC/LVS/PEX verification, and pre/post-layout comparison.

---

## 📋 Team Information

| | | |
| :--- | :--- | :--- |
| **Track** | D — gLayout | |
| **Team Name** | D08 Microelectronic Block Generator | |
| **Leader** | M. Taufiqul Huda | [@mthudaa](https://github.com/mthudaa) |

### Team Members

| Name | GitHub | Affiliation | Role |
| :--- | :--- | :--- | :--- |
| **M. Taufiqul Huda** | [@mthudaa](https://github.com/mthudaa) | NTUST | Lead Analog / Mixed-Signal Designer |
| **Ahmad Jabar Ilmi** | [@ilmiahmad](https://github.com/ilmiahmad) | LG Indonesia | Physical Verification & Automation |
| **Moh. Jabir Mubarok** | [@jabirmbrok](https://github.com/jabirmbrok) | NTUST | AI/LLM Integration & Software Architect |

---

## 🚀 Project Overview

We are developing a framework to automate the design of Analog IC blocks using
**gLayout**, **gdsfactory**, and the **DeepSeek API**.

Our framework leverages the **DeepSeek API** as an autonomous Analog Design
Engineer. Using a **SPICE-in-the-loop Finetuning** mechanism, the DeepSeek
model receives direct quantitative feedback from ngspice — including gain,
bandwidth, phase margin, delay, offset voltage, and PVT corner results — and
iteratively refines the SPICE netlist until all specifications are met. Once
verified, our custom engine automatically translates the netlist into a fully
routed, DRC-clean GDS layout.

### Key Milestones

- **Autonomous Optimization:** The DeepSeek agent has successfully generated
  and autonomously tuned a **StrongARM Latch Comparator** achieving `<10mV`
  input offset across all PVT corners.
- **Layout-Aware PEX Feedback:** The agent receives exact post-layout metrics
  from Magic PEX to close the gap between schematic simulation and actual
  silicon performance.
- **Test Key Circuits:** Comparator, OTA, and Voltage Reference.

> 📂 **See detailed AI design results:** [`AI-Generated-Design-Result/`](AI-Generated-Design-Result/README.md)
> — complete SPICE netlists, GDS layouts, DRC/LVS/PEX reports, and simulation
> plots for all three designs.

---

## 🔧 Technology Stack

| Component | Tool / Library |
| :--- | :--- |
| **PDK** | GF180MCU (`gf180mcuD`) — 3.3V, 180nm |
| **Schematic** | Xschem + Ngspice |
| **Layout** | gLayout + gdsfactory |
| **Physical Verification** | Magic (DRC), Netgen (LVS), Magic (PEX) |
| **AI/LLM** | DeepSeek API |
| **Container** | IIC-OSIC-TOOLS Docker |
| **Languages** | Python 3, SPICE, Tcl, Bash |

---

## ⚡ Design Flow

```
SPICE Netlist  →  Parse Devices  →  Multi-Row Placement  →  Power Routing
     ↓                                                    ↓
  Signal Routing  →  GDSII Export  →  DRC  →  LVS  →  PEX  →  Tapeout
```

### Primary Pipeline API

```python
from core.pipeline import spice_to_gds_with_checks
r = spice_to_gds_with_checks(netlist)
# r["outdir"], r["gds_path"], r["drc"], r["lvs"], r["pex"], r["all_pass"]
```

See [`designs/notebooks/chipathon2026-D/`](designs/notebooks/chipathon2026-D/) for
complete notebooks and the full design flow.

---

## 🛠️ Getting Started

### Prerequisites

- **Docker Desktop** ([install guide](https://docs.docker.com/desktop/))
- **GitHub Desktop** ([download](https://desktop.github.com/)) or Git CLI

### 1. Clone the Repository

```bash
git clone https://github.com/mthudaa/Microelectronic-Block-Generator.git
cd Microelectronic-Block-Generator
```

### 2. Launch the Docker Container

**Linux / macOS:**
```bash
./start_chipathon_vnc.sh
```

**Windows:**
```cmd
.\start_chipathon_vnc.bat
```

The script pulls the IIC-OSIC-TOOLS image (first time only) and starts the
container with GF180MCU PDK pre-loaded.

### 3. Access the Design Environment

| Method | Address | Password |
| :--- | :--- | :--- |
| **VNC Client** (recommended) | `localhost:5901` | `abc123` |
| **Web Browser** (noVNC) | `http://localhost` | `abc123` |

### 4. Activate the Python Environment

Inside the container terminal:

```bash
unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH
source /headless/conda-env/miniconda3/etc/profile.d/conda.sh
conda activate GLdev

export PDK_ROOT=/foss/pdks
export PDK=gf180mcuD
export PDKPATH=/foss/pdks/gf180mcuD
export STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0
```

### 5. Run the Design Flow

```bash
cd /foss/designs/notebooks/chipathon2026-D
# Open and run spice_to_gds.ipynb or llm_to_gds.ipynb
```

---

## 🤖 OpenCode Skills & Tools Tutorial

The project ships with a suite of **OpenCode extensions** (`.opencode/`) that
let you run the entire analog design flow — from SPICE netlist to tapeout-ready
GDS — using natural-language commands and AI agents.

All project-specific extensions use the `mbg-` prefix.

### Skills

Skills teach the AI agent how to perform a specific domain task. They are
loaded automatically when the task matches the skill's description.

| Skill | Owner | Purpose |
| :--- | :--- | :--- |
| `mbg-spice-to-gds` | Huda | Convert SPICE netlist → DRC-clean GDSII layout via `spice_to_gds_with_checks()` |
| `mbg-ic-verify` | Ahmad | Run DRC (Magic), LVS (Netgen), and PEX (Magic) on a GDS layout |
| `mbg-ai-experiment-audit` | Jabir | Audit an AI experiment for reproducibility, bounded refinement, and evidence-backed claims |
| `mbg-extension-authoring` | Jabir | Create/review new OpenCode skills, tools, commands, or agents following project standards |

**How to invoke a skill:** Just ask the AI agent naturally — the skill loads
when the request matches its purpose. For example:

> *"Convert this SPICE netlist to GDS and run DRC/LVS/PEX."*
> → loads `mbg-spice-to-gds` + `mbg-ic-verify`

> *"Audit the experiment at outputs/exp-07/experiment.json."*
> → loads `mbg-ai-experiment-audit`

### Slash Commands

Type `/` in the chat to access these workflow commands. Each command runs a
multi-step pipeline with user checkpoints.

| Command | Agent | Description |
| :--- | :--- | :--- |
| `/mbg-full-automate` | `build` | **9-stage fully automatic flow**: spec → SPICE → sim → layout → DRC/LVS/PEX → post-layout → report. No manual steps. |
| `/mbg-partial-automate` | `build` | **8-stage user-guided flow**: same pipeline but the agent pauses at each stage for your review and approval. |
| `/mbg-review-ai-experiment` | `plan` | Validate an `experiment.json` against the project audit standard. Checks prompt traceability, model ID, refinement bounds, and evidence. |
| `/mbg-review-extension` | `plan` | Review an OpenCode extension (skill/tool/command/agent) for naming, safety, ownership, and correctness. |
| `/mbg-new-skill` | `build` | Scaffold a new `mbg-*` skill with proper YAML frontmatter and structure. |
| `/mbg-new-tool` | `build` | Scaffold a new `mbg-*` TypeScript tool with safety guards. |
| `/mbg-new-command` | `build` | Scaffold a new `mbg-*` slash command with required workflow steps. |

**How to use a command:** Type `/mbg-full-automate` in the chat, then describe
your design. The agent guides you through the pipeline:

```
/mbg-full-automate
Design a StrongARM latch comparator with <10mV input offset, 1GHz clock,
GF180MCU 3.3V PDK.
```

### Custom Tools

These are TypeScript tools that agents can call during a workflow. They wrap the
Python core modules with schema validation and safety checks.

| Tool | Purpose |
| :--- | :--- |
| `mbg-spice-to-gds` | Execute `spice_to_gds_with_checks(netlist)` — the primary pipeline tool |
| `mbg-run-verification` | Run DRC, LVS, or PEX on a GDS file (`check_type`: `drc`/`lvs`/`pex`) |
| `mbg-validate-ai-experiment` | Validate `experiment.json` schema, paths, statuses, and metric completeness |
| `mbg-validate-extension` | Validate an OpenCode extension file against project authoring rules |

**How tools are used:** Tools are called automatically by agents when executing
a skill or command. You don't invoke them directly — the agent selects the
right tool for the task.

### Extension Locations

```text
.opencode/
├── skills/
│   ├── mbg-spice-to-gds/SKILL.md
│   ├── mbg-ic-verify/SKILL.md
│   ├── mbg-ai-experiment-audit/SKILL.md
│   └── mbg-extension-authoring/SKILL.md
├── commands/
│   ├── mbg-full-automate.md
│   ├── mbg-partial-automate.md
│   ├── mbg-review-ai-experiment.md
│   ├── mbg-review-extension.md
│   ├── mbg-new-skill.md
│   ├── mbg-new-tool.md
│   └── mbg-new-command.md
├── tools/
│   ├── mbg-spice-to-gds.ts
│   ├── mbg-run-verification.ts
│   ├── mbg-validate-ai-experiment.ts
│   └── mbg-validate-extension.ts
└── tests/
    └── fixtures/
```

### Quick Start: Your First Automated Design

1. Open VS Code in this repository with the OpenCode extension enabled.
2. Type `/mbg-full-automate` in the chat.
3. Describe your circuit requirements (e.g., "5T OTA with 60dB gain, 10MHz GBW").
4. The agent will research topologies, generate SPICE, simulate, create layout,
   and run DRC/LVS/PEX — all automatically.
5. Review the final report and GDS output.

For more control, use `/mbg-partial-automate` to approve each stage before the
agent proceeds.

---

## 📁 Repository Structure

```
├── designs/
│   ├── libs/                          # Design & testbench libraries
│   │   ├── core_analog/               # Core circuit cells (OTA, comparator, etc.)
│   │   └── tb_analog/                 # Testbench setups
│   └── notebooks/chipathon2026-D/     # Main project notebooks & core modules
│       ├── core/                      # Pipeline modules
│       │   ├── pipeline.py            # Main SPICE→GDS pipeline
│       │   ├── placement.py           # Multi-row device placement
│       │   ├── routing.py             # Signal routing
│       │   ├── power.py               # Power grid routing
│       │   ├── simulation.py          # Pre/post-layout simulation
│       │   ├── spice_parser.py        # SPICE netlist parser
│       │   ├── checks.py              # DRC/LVS/PEX automation
│       │   └── utils.py               # Utilities
│       ├── scripts/                   # Verification scripts (DRC, LVS, PEX)
│       ├── spice_to_gds.ipynb         # SPICE → GDS notebook
│       ├── llm_to_gds.ipynb           # LLM → SPICE → GDS notebook
│       └── test_all_designs.py        # Regression test suite
├── scripts/                           # Container launch & tool scripts
├── docs/                              # Workflow documentation
└── README.md
```

---

## 🧪 Test Key Circuits (Tapeout Plan)

| Circuit | Status | Key Metric |
| :--- | :--- | :--- |
| **5T OTA** | ✅ Proven | Gain, GBW, Phase Margin |
| **StrongARM Comparator** | ✅ Autonomous Tuning | `<10mV` Offset (all PVT) |
| **Voltage Reference** | 🔄 In Progress | Temperature Coefficient |

### 📏 Chip Size & Pin List (per judge request — [Issue #20](https://github.com/sscs-ose/sscs-chipathon-2026/issues/20#issuecomment-5138077347))

| Design | Pins | Count | Chip Size (µm) | Area (µm²) |
| :--- | :--- | ---: | :--- | ---: |
| **OTA 5T** | `vdd` `vss` `inp` `inm` `out` `vb` | 6 | 35 × 23 | 805 |
| **Comparator** | `vdd` `vss` `inp` `inm` `vb` `out` | 6 | 35 × 98 | 3,430 |
| **VREF 1.2V** | `vdd` `vss` `vref` | 3 | 46 × 54 | 2,484 |
| **TOTAL** | — | **15** | — | **6,719** |

#### Pin Assignments

> **⚠️ No shared signal I/O pads across designs.** Each pin gets its own
> dedicated `gf180mcu_fd_io__asign` pad. Only VDD and VSS may share pads
> if all blocks operate on the same supply domain.

| Pin | Dir | OTA 5T | Comparator | VREF 1.2V | Dedicated Pad |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `vdd` | PWR | ✅ | ✅ | ✅ | `gf180mcu_fd_io__vdd` ×1 (shared) |
| `vss` | PWR | ✅ | ✅ | ✅ | `gf180mcu_fd_io__vss` ×1 (shared) |
| `ota_inp` | IN | ✅ | — | — | `gf180mcu_fd_io__asign` |
| `ota_inm` | IN | ✅ | — | — | `gf180mcu_fd_io__asign` |
| `ota_out` | OUT | ✅ | — | — | `gf180mcu_fd_io__asign` |
| `ota_vb` | IN | ✅ | — | — | `gf180mcu_fd_io__asign` |
| `cmp_inp` | IN | — | ✅ | — | `gf180mcu_fd_io__asign` |
| `cmp_inm` | IN | — | ✅ | — | `gf180mcu_fd_io__asign` |
| `cmp_out` | OUT | — | ✅ | — | `gf180mcu_fd_io__asign` |
| `cmp_vb` | IN | — | ✅ | — | `gf180mcu_fd_io__asign` |
| `vref_out` | OUT | — | — | ✅ | `gf180mcu_fd_io__asign` |
| **Subtotal** | | **6** | **6** | **3** | **9×asign + 1×vdd + 1×vss** |

#### Total Area Estimation

| Metric | Value |
| :--- | ---: |
| **Core area (3 designs)** | 6,719 µm² (0.0067 mm²) |
| **Pads needed** | 11 pads = 9× `asign` + 1× `vdd` + 1× `vss` |
| **Est. with I/O pads** (~200×200 µm each) | ~0.09 mm² (11 pads) |
| **Est. with I/O pads + seal ring + scribe** | ~0.20 mm² |

Core dimensions are extracted from GDS bounding boxes reported by the pipeline.
I/O pad area is an estimate based on typical GF180MCU I/O cell dimensions
(~200 × 200 µm per pad). Actual tapeout area depends on pad frame arrangement
and seal ring.

---

## 👥 Team Ownership

| Module | Owner | Files |
| :--- | :--- | :--- |
| Analog Design, Placement, Routing, Power, Simulation | **Huda** | `placement.py`, `routing.py`, `power.py`, `simulation.py`, `spice_parser.py` |
| DRC, LVS, PEX, Verification, Environment | **Ahmad** | `checks.py`, `utils.py`, `scripts/` |
| AI/LLM Integration, Prompts, Pipeline, Docs | **Jabir** | `pipeline.py`, `llm_to_gds.ipynb`, `.opencode/` |

---

## 📐 PDK Design Constraints (GF180MCU 3.3V)

| Constraint | Value | Notes |
| :--- | :--- | :--- |
| **Supply** | 3.3V single | Use `nfet_03v3` / `pfet_03v3` only |
| **MOSFET W** | `<10µm` | Per finger width |
| **MOSFET L** | `<10µm` | Per transistor |
| **Device prefix** | `XM1` (not `M1`) | Standard for gf180mcuD |
| **Fingers vs mult** | Prefer `nf=N` over `m=N` | Better matching |
| **MOSFET body** | `pfet_03v3`→VDD ONLY, `nfet_03v3`→VSS ONLY | No other connections allowed |

---

## 📊 Simulation Outputs

> **⚠️ REMEMBER:** Always save simulation plots as `.png` files in the working
> directory. Organize by analysis type:

| Analysis | Plot Content | Suggested Filename |
| :--- | :--- | :--- |
| **AC** | Gain (dB) & Phase (°) vs Frequency | `<cell>_ac_{pre,post}.png` |
| **DC** | IV curves, operating point sweep | `<cell>_dc.png` |
| **TRAN** | Transient waveforms (V/t, I/t) | `<cell>_tran_{pre,post}.png` |

```python
# Example: save plot from simulation
import matplotlib.pyplot as plt
# ... run simulation, collect data ...
plt.savefig(os.path.join(workdir, "ota_5t_ac_pre.png"), dpi=150)
```

These plots are required artifacts for experiment reports and tapeout reviews.

---

## ✅ Tapeout Gate

| Gate | Requirement |
| :--- | :--- |
| **DRC** | Magic DRC zero violations |
| **LVS** | Netgen LVS: netlist matches layout |
| **PEX** | Parasitic extraction complete |
| **Post-layout** | Matches pre-layout within 10% tolerance |

---

## � Acknowledgments

This project is built on top of two outstanding open-source frameworks:

| Project | Role | Link |
| :--- | :--- | :--- |
| **gLayout** | SPICE-to-GDS layout generation engine — automated device placement, power routing, and PathFinder negotiated-congestion signal routing | [github.com/ReaLLMASIC/gLayout](https://github.com/ReaLLMASIC/gLayout) |
| **gdsfactory** | PDK activation, device library (nmos, pmos, mimcap, via_stack), and GDSII I/O | [github.com/gdsfactory/gdsfactory](https://github.com/gdsfactory/gdsfactory) |

We are grateful to the maintainers and contributors of both projects for
making automated analog layout generation possible.

---

## �📄 License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file
for details.