<div align="center">

# ⚡ MICROELECTRONIC BLOCK GENERATOR

### *From IDEA to SPICE, from SPICE to GDS — in an instant.*

**An autonomous analog layout engine.**
Describe a circuit in plain language; get back a routed, DRC-clean,
LVS-matched GDSII you can tape out.

<br/>

[![License](https://img.shields.io/badge/License-Apache_2.0-0b7285?style=for-the-badge&logo=apache&logoColor=white)](LICENSE)
[![PDK](https://img.shields.io/badge/PDK-GF180MCU_·_180nm-6741d9?style=for-the-badge)](https://github.com/google/gf180mcu-pdk)
[![Python](https://img.shields.io/badge/Python-3.10+-2b8a3e?style=for-the-badge&logo=python&logoColor=white)](pyproject.toml)
[![Chipathon](https://img.shields.io/badge/SSCS_Chipathon-2026_·_Track_D-c2255c?style=for-the-badge)](https://github.com/sscs-ose/sscs-chipathon-2026)

![DRC](https://img.shields.io/badge/DRC-clean_6%2F6-2b8a3e?style=flat-square)
![LVS](https://img.shields.io/badge/LVS-match_6%2F6-2b8a3e?style=flat-square)
![Connectivity](https://img.shields.io/badge/connectivity-0_opens_·_0_shorts-2b8a3e?style=flat-square)
![Agents](https://img.shields.io/badge/agents-OpenCode_·_Claude_·_Codex-1971c2?style=flat-square)

</div>

---

> **SSCS Chipathon 2026 — gLayout Track (D): AI/LLM for Analog Circuits**

An AI-assisted analog-layout framework that converts SPICE subcircuit netlists
into DRC-clean GDSII using [gLayout](https://github.com/ReaLLMASIC/gLayout),
[gdsfactory](https://github.com/gdsfactory/gdsfactory) and the **DeepSeek API**.
It closes the loop: ngspice drives the netlist, the layout engine realises it,
and Magic/netgen verify it — with every stage reporting honestly, so a failed
route is reported as a failure rather than quietly emitted as geometry.

| | |
| :--- | :--- |
| 🧠 **Agentic** | An LLM writes and tunes the netlist against real ngspice measurements |
| 📐 **Analog-aware** | Matching groups, symmetry constraints, per-device deep n-well isolation |
| 🧭 **DRC-aware routing** | A\* grid maze router with negotiated rip-up and via legality checks |
| 🔍 **Self-verifying** | Union-find connectivity check catches opens/shorts *before* signoff |
| 🧱 **Native passives** | Real `ppolyf_u` resistors and metal4/metal5 MIM caps, built from PDK layers |
| 📦 **Tapeout-ready** | Emits GDS · LEF · LIB · Verilog · SPICE · PEX · SVG for LibreLane |

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
| **Install** | local scripts (`setup_env.sh`) — Docker optional |
| **Languages** | Python 3, SPICE, Tcl, Bash |

---

## ⚡ Design Flow

```mermaid
flowchart LR
    A["💬 Prompt"] --> B["🤖 LLM<br/>netlist"]
    B --> C["📄 SPICE"]
    C --> D["🔬 ngspice<br/>measure"]
    D -->|specs not met| B
    D -->|specs met| E["🧩 Parse<br/>devices + constraints"]
    E --> F["📐 Analog-aware<br/>placement"]
    F --> G["🧭 DRC-aware<br/>grid routing"]
    G --> H["🔍 Connectivity<br/>opens / shorts"]
    H -->|fail| F
    H -->|clean| I["📦 GDSII<br/>+ LEF/LIB/Verilog/SVG"]
    I --> J["✅ DRC"] --> K["✅ LVS"] --> L["⚡ PEX"]
    L --> M["🚀 Tapeout"]

    style A fill:#6741d9,stroke:#4c2fb8,color:#fff
    style B fill:#6741d9,stroke:#4c2fb8,color:#fff
    style M fill:#2b8a3e,stroke:#1d6329,color:#fff
    style H fill:#c2255c,stroke:#9c1a48,color:#fff
```

The loop that matters is `D → B`: the agent keeps rewriting the netlist until
ngspice says the specifications are met. The second loop, `H → F`, is the one
most flows omit — if the router can't complete a net, placement is retried
rather than shipping a layout with a hidden open.

### Primary Pipeline API

```python
from mbg.pipeline import spice_to_gds_with_checks

r = spice_to_gds_with_checks(netlist)
r["all_pass"]     # True only if DRC, LVS *and* internal connectivity all pass
r["drc"], r["lvs"], r["pex"]
r["gds_path"], r["outdir"]
r["views"]        # GDS · LEF · LIB · Verilog · SCH SPICE · PEX SPICE · SVG
```

Every run emits a full set of downstream views, so a block drops straight into
a LibreLane macro flow:

```python
from mbg.analysis import Testbench          # op / dc / ac / tran / monte_carlo
from mbg.integrate import integrate         # multi-macro chip assembly
```

`spice_to_gds_with_checks` runs the **DesignContext** engine (analog-aware
placement, DRC-aware grid router, union-find connectivity verification). Pass
`legacy=True` to reproduce the original shape-router behaviour.

### Chip integration

```bash
python scripts/integrate_modules.py --librelane \
       --top mbg_top --search outputs/regression --outdir integration/
```

Discovers every block that published a `*.views.json`, assembles them into one
top cell and signs it off — emitting the integration **GDS · LEF · LIB · SCH
SPICE · PEX SPICE · Verilog · DRC · LVS**, plus `info.yaml` and one
`lvs_config_<cell>.json` per block in the [SSCS Chipathon
2026](https://github.com/sscs-ose/sscs-chipathon-2026/tree/main/resources)
submission format. Add `--run` to hand the generated config to LibreLane.

Two things it will tell you rather than hide:

- **Ground is global.** The macros share a p-substrate, so substrate-tied
  grounds really are one net and the top netlist says so. A pin declared as
  ground that *isn't* tied gets named in a warning — Magic splits it off as
  `vss_uq2`, which means that block's ground is floating.
- **Top-level LVS of disconnected macros is inconclusive**, and is reported as
  such rather than as a pass. With no PDN and no inter-block nets the blocks
  are symmetric islands and netgen cannot assign net classes uniquely. Each
  macro's own LVS is authoritative; run LibreLane for a chip-level verdict.

See [`tests/notebooks/`](tests/notebooks/) for the end-to-end notebooks
(`spice_to_gds.ipynb`, `llm_to_gds.ipynb`) and [`tests/`](tests/) for the
regression suites that exercise the full design flow.

---

## 🛠️ Getting Started

**Local install, no Docker.** Everything lands in two places you control:
`.venv/` inside the clone, and `$MBG_TOOLS_ROOT` (default `~/.local/mbg-tools`)
for EDA builds. Nothing is written to `/usr`, `/usr/local`, or the system
package database unless you explicitly ask for OS build dependencies.

### Prerequisites

| | |
| :--- | :--- |
| **OS** | Linux — Debian/Ubuntu, Fedora/RHEL-like, Arch-like, openSUSE are detected |
| **Python** | 3.10 – 3.12 (`MBG_PYTHON=/path/to/python3.11` to pin one) |
| **Git** | any recent version |
| **Disk** | ~2 GB (the GF180 PDK is most of it) |

Building Magic or netgen needs a C toolchain, Tcl/Tk, Cairo and X11 headers.
You only need these if you don't already have compatible tools:

```bash
./scripts/setup_env.sh --deps        # prints the exact packages for your distro
./scripts/setup_env.sh --deps --yes  # installs them (prompts for sudo)
```

Installing OS packages is the one step that needs root, so it is never done
silently.

### Quick Start

```bash
git clone https://github.com/mthudaa/Microelectronic-Block-Generator.git
cd Microelectronic-Block-Generator

./scripts/setup_env.sh          # venv + dependencies + GF180 PDK + EDA tools
source scripts/activate_mbg.sh  # venv + PDK vars + tool PATH, in one step

./scripts/setup_env.sh --check  # preflight; non-zero if anything required fails
python tests/test_all_designs.py
```

`setup_env.sh` reuses whatever already works. If you have a compatible Magic,
netgen and PDK, it detects them and builds nothing.

<details>
<summary><b>Step by step, on a blank machine</b></summary>

If nothing is installed yet, run the stages individually so a failure tells
you exactly which one it was:

```bash
# 0. OS build packages — the only step that needs root.
#    Skip it if you already have working Magic and netgen.
./scripts/setup_env.sh --deps          # review the list first
./scripts/setup_env.sh --deps --yes    # then install

# 1. Python: .venv, pinned dependencies, `pip install -e .`
./scripts/setup_env.sh --python-only

# 2. GF180MCU PDK via volare (~1.5 GB download)
./scripts/setup_env.sh --pdk

# 3. Magic and netgen — builds only what is missing or incompatible
./scripts/setup_env.sh --eda

# 4. Activate, then confirm
source scripts/activate_mbg.sh
./scripts/setup_env.sh --check
```

Each stage is idempotent: re-running one that already succeeded does nothing.

</details>

### Installation modes

| Command | What it does |
| :--- | :--- |
| `./scripts/setup_env.sh` | everything below, in order |
| `./scripts/setup_env.sh --python-only` | `.venv`, pinned dependencies, `pip install -e .` |
| `./scripts/setup_env.sh --pdk` | GF180MCU via volare into `$PDK_ROOT` |
| `./scripts/setup_env.sh --eda` | build Magic / netgen into `$MBG_TOOLS_ROOT` — only what's missing |
| `./scripts/setup_env.sh --deps` | print (or `--yes`, install) OS build packages |
| `./scripts/setup_env.sh --check` | full preflight, installs nothing |

### Tool versions

| Tool | Requirement | Tested |
| :--- | :--- | :--- |
| Python | 3.10 – 3.12 | 3.10.20, 3.11 |
| Magic | **≥ the version the techfile names** (`requires magic-8.3.411`) | 8.3.669, 8.3.681 |
| netgen | ≥ 1.5.200, must terminate in `-batch` | 1.5.322, 1.5.323 |
| PDK | `gf180mcuD` via volare | — |
| KLayout | **optional** — not used by the default flow | — |
| ngspice | **optional** — simulation only | 45 |

The Magic floor is read from *your* installed techfile rather than hard-coded,
so the check tracks the PDK you actually have. An exact-version pin would
reject working installations for no reason.

### Environment variables

`source scripts/activate_mbg.sh` sets all of these; you shouldn't need to
export them by hand. Any value you set first is respected.

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `PDK_ROOT` | `$HOME/.volare` | where PDKs live |
| `PDK` | `gf180mcuD` | active PDK |
| `PDKPATH` | `$PDK_ROOT/$PDK` | active PDK root |
| `STD_CELL_LIBRARY` | `gf180mcu_fd_sc_mcu7t5v0` | standard cells |
| `MBG_TOOLS_ROOT` | `$HOME/.local/mbg-tools` | where MBG builds EDA tools |
| `MBG_MAGIC` / `MBG_NETGEN` | — | pin an exact executable |
| `MBG_MAGIC_ROOT` / `MBG_NETGEN_ROOT` | — | pin a prefix (`<prefix>/bin/<tool>`) |
| `MBG_TOOL_TIMEOUT` | per tool | seconds before an EDA call is killed |
| `MBG_MAGIC_TIMEOUT` / `MBG_NETGEN_TIMEOUT` | 900 | per-tool override |

`PDK_ROOT` has to exist **before** anything imports gLayout, which reads it at
import time. `import mbg` sets it for you, so this is handled even if you
forget — but a wrong value is still your value.

### Which binaries am I actually running?

Every run prints what it resolved, because "there is a `magic` on PATH" and
"Magic can drive this PDK" are different claims:

```text
[TOOLS] magic: /home/user/.local/mbg-tools/magic-8.3.681/bin/magic (8.3.681, via MBG_TOOLS_ROOT)
[TOOLS] netgen: /home/user/.local/mbg-tools/netgen-1.5.323/bin/netgen (1.5.323, via MBG_TOOLS_ROOT)
```

Resolution order: `MBG_MAGIC` → `MBG_MAGIC_ROOT` → `$MBG_TOOLS_ROOT` → `PATH`.
A tool is accepted only after a version check *and* a functional probe. If you
name one explicitly and it doesn't work, that's an error — MBG will not
quietly run a different one instead.

### Verify the install

`--check` is the single source of truth — it asks the same resolver the
pipeline uses, so it cannot pass while a real run picks a different binary.

```bash
./scripts/setup_env.sh --check
```

```text
MBG Local Environment Check
==================================================

Operating System
  distro                 PASS  Fedora Linux 43 (Workstation Edition)

Python
  virtualenv             PASS  /path/to/repo/.venv
  python                 PASS  3.11.15
  mbg                    PASS  0.2.0
  gdsfactory             PASS  7.7.0
  gdstk                  PASS  0.9.62
  glayout                PASS  0.1.2
  numpy                  PASS  1.24.0

PDK
  PDK                   PASS  gf180mcuD
  PDK_ROOT              PASS  /home/user/.volare
  PDKPATH               PASS  /home/user/.volare/gf180mcuD
  standard cells        PASS  gf180mcu_fd_sc_mcu7t5v0
  Magic techfile        PASS  requires magic-8.3.411
  Netgen setup          PASS

EDA
  Magic executable      PASS  /usr/local/bin/magic
  Magic version         PASS  8.3.669
  Netgen executable     PASS  /usr/local/bin/netgen
  Netgen version        PASS  1.5.322
  KLayout executable    OPTIONAL  not installed (not needed for the GF180 flow)
  ngspice               PASS  /usr/local/bin/ngspice

Regression readiness
  GDS generation        READY
  Magic DRC             READY
  Magic extraction      READY
  Netgen LVS            READY

Environment OK — the GF180 regression can run.
```

Exit status is **0** only when every *required* component passes. Optional
components (KLayout, ngspice) are reported but never fail the check.

Then run the real thing:

```bash
python tests/test_all_designs.py     # SPICE -> GDS -> DRC -> extract -> LVS  (~10 min)
python -m pytest tests/ -q           # 73 unit + environment tests           (~2 min)
```

```text
  Inverter: DRC=DRC: CLEAN | LVS=MATCH
  3-stage Ring Oscillator: DRC=DRC: CLEAN | LVS=MATCH
  5T-OTA: DRC=DRC: CLEAN | LVS=MATCH
  StrongArm-Comparator: DRC=DRC: CLEAN | LVS=MATCH
  ...
  7/7 designs pass DRC + LVS
```

### What gets installed, and how to undo it

| Location | Contents | Remove with |
| :--- | :--- | :--- |
| `<repo>/.venv/` | Python environment | `rm -rf .venv` |
| `$PDK_ROOT` (`~/.volare`) | GF180MCU PDK | `rm -rf ~/.volare/gf180mcuD` |
| `$MBG_TOOLS_ROOT` (`~/.local/mbg-tools`) | Magic / netgen builds + sources | `rm -rf ~/.local/mbg-tools` |

Nothing else is touched. `/usr`, `/usr/local` and the system package database
are only ever written to by `--deps --yes`, which asks for sudo explicitly and
installs nothing else.

### Troubleshooting

<details>
<summary><b>PDK_ROOT missing / <code>TypeError: ... not NoneType</code></b></summary>

gLayout calls `Path(os.getenv("PDK_ROOT"))` at import time, so an unset
variable used to surface as a `TypeError` from inside gLayout. `import mbg`
now populates the PDK environment first. If the PDK itself is missing:

```bash
./scripts/setup_env.sh --pdk
```
</details>

<details>
<summary><b>Magic incompatible</b></summary>

```text
Magic version 8.3.411 is required by this techfile, but this version of magic is 0.0.0
Nothing in "cifinput" section of tech file.
```

A Magic that predates the techfile reads no GDS and extracts nothing — and
still exits 0. It is rejected rather than used:

```bash
./scripts/setup_env.sh --eda     # builds a known-good Magic locally
```
</details>

<details>
<summary><b>netgen incompatible or hanging</b></summary>

Some builds sit waiting on stdin under `-batch`; the mesh generator of the
same name isn't the LVS tool at all. Both are caught by the batch probe.

```bash
./scripts/setup_env.sh --eda
```
</details>

<details>
<summary><b>Building Magic/netgen fails on a Tcl 9 system (Fedora 43+)</b></summary>

```text
couldn't load file ".../tclnetgen.so": cannot open shared object file
make[2]: *** No rule to make target '../base/libbase.o', needed by 'tclnetgen.so'
```

Magic and netgen build their Tcl extensions against the system Tcl and
support **8.6**. Distributions that have moved to **Tcl 9** (Fedora 43 and
newer) produce a launcher script with no working library behind it.

`--eda` detects this and **refuses to install the broken build** rather than
leaving you with a tool that exists and never works. Options, in order of
least effort:

1. **Use what you have.** MBG detects and reuses any working Magic/netgen —
   run `./scripts/setup_env.sh --check` first; you may not need to build
   anything.
2. Install Tcl 8.6 development files and rebuild.
3. Use the optional Docker image, which ships working tools.

</details>

<details>
<summary><b>KLayout not found</b></summary>

Optional. The default flow is Magic for DRC and netgen for LVS. The `klayout`
Python module and the `klayout` executable are different things — having the
module does not give you the command. You need the executable only for
`run_drc(engine="klayout")` or `engine="both"`.
</details>

<details>
<summary><b>Extraction failure / LVS skipped</b></summary>

```text
[ERROR][MAGIC_EXTRACTION]
  ...
LVS was SKIPPED because no valid extracted SPICE netlist was generated.
Full log: outputs/regression/inverter/logs/magic_extract.log
```

This is correct behaviour. LVS depends on extraction; with no extracted
netlist there is nothing to compare. Fix the extraction — the log names the
cause. MBG will never substitute the `.gds` for the missing netlist.
</details>

<details>
<summary><b>Tool timeout</b></summary>

```text
netgen exceeded 900s during netgen_lvs and was terminated.
```

The process group is killed and the log kept. Raise the bound if the design
is genuinely that large:

```bash
export MBG_NETGEN_TIMEOUT=1800
```
</details>

<details>
<summary><b>Where are the logs?</b></summary>

Next to each result, never discarded:

```text
outputs/regression/<cell>/logs/
    magic_drc.log
    magic_extract.log
    netgen_lvs.log
```
</details>

### Docker (optional alternative)

Local installation is the supported path. The IIC-OSIC-TOOLS container
remains available if you'd rather not install EDA tools at all:

<details>
<summary>Container instructions</summary>

```bash
./start_chipathon_vnc.sh     # Linux/macOS
.\start_chipathon_vnc.bat    # Windows
```

| Method | Address | Password |
| :--- | :--- | :--- |
| VNC client | `localhost:5901` | `abc123` |
| Browser (noVNC) | `http://localhost` | `abc123` |

Inside the container:

```bash
unset PYTHONPATH PYTHONHOME LD_LIBRARY_PATH
source /headless/conda-env/miniconda3/etc/profile.d/conda.sh
conda activate GLdev
export PDK_ROOT=/foss/pdks PDK=gf180mcuD PDKPATH=/foss/pdks/gf180mcuD
export STD_CELL_LIBRARY=gf180mcu_fd_sc_mcu7t5v0
```

The container ships its own Magic and netgen, so `--eda` is unnecessary there.
</details>

---

## 🤖 AI Coding Agent Integrations

The project ships a **canonical agent layer** under `.ai/` that is the single
source of truth for every domain skill and workflow (SPICE→GDS, DRC/LVS/PEX,
placement/routing debug, design regression, experiment audit, extension
authoring). A sync script regenerates matching, platform-native adapters for
three coding agents — **OpenCode**, **Claude Code**, and **Codex** — so the
same `mbg-` skill behaves the same way no matter which agent you're driving.

All project-specific extensions use the `mbg-` prefix.

### ⚡ Quick install

```bash
git clone <this-repo> && cd Microelectronic-Block-Generator
./scripts/setup_env.sh        # 1. Python env + GF180 PDK + EDA tools
./scripts/install_agents.sh   # 2. OpenCode / Claude Code / Codex integrations
```

That is the whole setup. Both scripts are idempotent, discover the repository
root themselves, and perform no git operations. If you only want the agent
layer and already have a working environment, step 2 alone is enough.

Inside an agent you can run the same thing as a slash command:

```text
/mbg-install      # both steps, then verification
/mbg-setup-env    # Python environment only
```

Codex has no slash commands — ask for the skill by name instead:
*"use the mbg-setup skill to install this repository"*.

**As a Python package**

```bash
pip install -e ".[dev,notebooks]"   # editable, from a clone
pip install -r requirements-lock.txt # exact known-good versions
```

This installs the `mbg` package plus two console commands, `mbg-sync` and
`mbg-validate`.

```python
from mbg import spice_to_gds_with_checks
r = spice_to_gds_with_checks(netlist)
r["gds_path"], r["drc"], r["lvs"], r["pex"], r["all_pass"]
```

**Requirements.** Python 3.10–3.12 — gdsfactory 7 and numpy 1 have no wheels
for 3.13+, and `setup_env.sh` picks a supported interpreter automatically. The
EDA tools (ngspice, Magic, netgen) and the GF180MCU PDK come from the
IIC-OSIC-TOOLS container; the setup script reports whether it can see them but
does not install them.

| | Per-machine step? | What the installer does |
| :--- | :--- | :--- |
| **Python** | yes | creates `.venv`, installs `mbg` editable |
| **OpenCode** | no — reads `.opencode/` from the clone | `npm install` for the custom `.ts` tools |
| **Claude Code** | no — reads `.claude/` from the clone | nothing to register |
| **Codex** | **yes** — no repo-scoped skills exist | registers the local plugin marketplace |

Useful variants:

```bash
./scripts/setup_env.sh --check        # report status, install nothing
./scripts/setup_env.sh --locked       # exact pinned versions
./scripts/setup_env.sh --freeze       # rewrite requirements-lock.txt
./scripts/install_agents.sh --check   # report status, change nothing
./scripts/install_agents.sh --only codex
./scripts/install_agents.sh --uninstall
```

### Canonical architecture: source vs. generated

```text
                         SOURCE OF TRUTH (hand-edited)
        .ai/manifest.json  +  .ai/skills/*/SKILL.md  +  .ai/workflows/*.md
                                        │
                                        │  python3 scripts/sync_agent_tools.py
                                        ▼
        ┌───────────────────────────────────────────────────────────────┐
        │                                                               │
        ▼                              ▼                                ▼
  .opencode/skills/**            .claude/skills/**              plugins/mbg-analog/skills/**
  .opencode/commands/**          .claude/commands/**             plugins/mbg-analog/.codex-plugin/plugin.json
        (OpenCode)               CLAUDE.md (@AGENTS.md import)   .agents/plugins/marketplace.json
                                        (Claude Code)                    (Codex)

                                        +  .ai/project-index.json  (repo map used by all three)

  AGENTS.md — shared rules — is NOT generated. OpenCode and Codex read it
  natively; CLAUDE.md imports it with a single `@AGENTS.md` line so Claude
  Code shares the exact same rules instead of a forked copy.
```

Every generated file opens with an HTML comment banner naming its source and
the regeneration command — if a file doesn't have that banner, it's
hand-maintained and safe to edit directly; if it does, edit the source under
`.ai/` instead and resync.

### Source of truth vs. generated vs. platform-specific

| Layer | Files | Rule |
| :--- | :--- | :--- |
| **Source of truth** (hand-edited) | `.ai/manifest.json`, `.ai/skills/<name>/SKILL.md`, `.ai/workflows/<name>.md`, `.ai/knowledge/PROJECT.md`, `AGENTS.md` | Edit these directly. Everything else flows from them. |
| **Generated** (never hand-edit) | `.opencode/skills/**`, `.opencode/commands/**`, `.claude/skills/**`, `.claude/commands/**`, `CLAUDE.md`, `plugins/mbg-analog/skills/**`, `plugins/mbg-analog/.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `.ai/project-index.json` | Overwritten by `scripts/sync_agent_tools.py`. Hand edits are silently lost on the next sync. |
| **Platform-specific, maintained by hand** | `opencode.jsonc` (OpenCode permissions), `.claude/settings.json` (Claude Code permissions), `.opencode/tools/*.ts` (OpenCode custom code tools — only OpenCode supports repo-scoped code tools) | Not derived from `.ai/`; edit in place for the platform in question. |

> ℹ️ There is exactly **one** copy of the engine: `src/mbg/`. Earlier
> revisions also carried a `.opencode/tools/core/` mirror that silently
> drifted weeks behind; it has been removed, and the OpenCode tools now
> **fail loudly** if `src/mbg/pipeline.py` is missing rather than falling
> back to anything.

### Capability matrix

Sourced directly from `.ai/manifest.json` (15 capabilities as of this writing
— re-run `python3 scripts/sync_agent_tools.py --check` to confirm the count
hasn't moved since). All of them currently
ship to all three platforms as skills — the gaps between platforms show up
one level up, in *workflows* (see next table), not in raw capabilities.

| Capability | OpenCode | Claude Code | Codex | Canonical skill |
| :--- | :---: | :---: | :---: | :--- |
| `inspect_repository` | ✅ | ✅ | ✅ | `mbg-repo-analysis` |
| `analyze_spice` | ✅ | ✅ | ✅ | `mbg-repo-analysis` |
| `spice_to_gds` | ✅ | ✅ | ✅ | `mbg-spice-to-gds` |
| `run_simulation` | ✅ | ✅ | ✅ | `mbg-spice-sim` |
| `debug_placement` | ✅ | ✅ | ✅ | `mbg-placement-debug` |
| `debug_routing` | ✅ | ✅ | ✅ | `mbg-routing-debug` |
| `verify_connectivity` | ✅ | ✅ | ✅ | `mbg-routing-debug` |
| `run_drc` | ✅ | ✅ | ✅ | `mbg-ic-verify` |
| `run_lvs` | ✅ | ✅ | ✅ | `mbg-ic-verify` |
| `run_pex` | ✅ | ✅ | ✅ | `mbg-ic-verify` |
| `inspect_generated_designs` | ✅ | ✅ | ✅ | `mbg-design-regression` |
| `compare_layout_results` | ✅ | ✅ | ✅ | `mbg-design-regression` |
| `audit_ai_experiment` | ✅ | ✅ | ✅ | `mbg-ai-experiment-audit` |
| `author_extension` | ✅ | ✅ | ✅ | `mbg-extension-authoring` |
| `sync_agent_metadata` | ✅ | ✅ | ✅ | `scripts/sync_agent_tools.py` (a command, not a skill) |

Each skill file is at `.ai/skills/<skill-name>/SKILL.md`.

### Workflows (slash commands)

Workflows are where the platforms genuinely diverge — Codex has no
repo-scoped slash-command mechanism at all.

| Workflow | Agent mode | OpenCode | Claude Code | Codex | Canonical source |
| :--- | :--- | :---: | :---: | :---: | :--- |
| `/mbg-full-automate` | `build` | ✅ | ✅ | n/a¹ | `.ai/workflows/mbg-full-automate.md` |
| `/mbg-partial-automate` | `build` | ✅ | ✅ | n/a¹ | `.ai/workflows/mbg-partial-automate.md` |
| `/mbg-review-ai-experiment` | `plan` | ✅ | ✅ | n/a¹ | `.ai/workflows/mbg-review-ai-experiment.md` |
| `/mbg-review-extension` | `plan` | ✅ | ✅ | n/a¹ | `.ai/workflows/mbg-review-extension.md` |
| `/mbg-new-skill` | `build` | ✅ | ✅ | n/a¹ | `.ai/workflows/mbg-new-skill.md` |
| `/mbg-new-command` | `build` | ✅ | ✅ | n/a¹ | `.ai/workflows/mbg-new-command.md` |
| `/mbg-new-tool` | `build` | ✅ | n/a² | n/a¹ | `.ai/workflows/mbg-new-tool.md` |

¹ Codex has no repo-scoped commands or subagents (`.ai/manifest.json` →
`platforms.codex.unsupported`). There is no Codex equivalent of typing
`/mbg-full-automate` — drive the same work by asking Codex directly in
natural language; it still has the skill and reads `AGENTS.md` natively.
² `mbg-new-tool` only targets OpenCode — Claude Code has no repo-scoped
code-tool runtime, so there's nothing for it to generate there.

### OpenCode

**Prerequisites:** OpenCode CLI (tested against `1.18.18`); Node.js on `PATH`
(OpenCode's custom tools in `.opencode/tools/*.ts` run under Node — confirmed
via `.opencode/package.json`'s `@opencode-ai/plugin` dependency); the repo
opened as the OpenCode workspace root so `opencode.jsonc` is picked up.

**Where it lives:** `.opencode/skills/<name>/SKILL.md`,
`.opencode/commands/<name>.md`, `.opencode/tools/*.ts` (hand-maintained,
OpenCode-only), permissions in `opencode.jsonc`.

**Setup:** nothing to install — the generated skills/commands are already
committed. Just open the repo in OpenCode.

**Sync command:**

```bash
python3 scripts/sync_agent_tools.py           # regenerate all adapters
python3 scripts/sync_agent_tools.py --check   # exit 1 if anything is stale
```

**Validation:** run the dedicated validator, which is the authoritative check:

```bash
python3 scripts/validate_agent_integrations.py
```

It runs ten checks (F1-F9): repository-root discovery, canonical frontmatter
parsing, adapter completeness, broken references, sync determinism, capability
parity, documented-command existence, absence of hardcoded home directories,
and a phantom-API check that every `core.*` symbol named in a skill actually
exists in `src/mbg/`. It exits non-zero on any
failure. `python3 scripts/sync_agent_tools.py --check` remains the fast
staleness-only check.

**Quick start:**

```text
/mbg-full-automate
Design a StrongARM latch comparator with <10mV input offset, 1GHz clock,
GF180MCU 3.3V PDK.
```

The agent researches topologies, generates SPICE, simulates, creates layout,
and runs DRC/LVS/PEX automatically. Use `/mbg-partial-automate` instead to
approve each stage yourself.

**Troubleshooting:**

- *A shell command hangs waiting for approval.* `opencode.jsonc` defaults
  `bash: "*"` to `"ask"` and only allow-lists a short list of read-only
  commands (`pwd`, `ls`, `find`, `grep`, `git status|diff|log|branch`,
  `docker ps`). Anything else — including a brand-new script — pauses for
  approval by design; add a narrowly-scoped entry to `opencode.jsonc` rather
  than widening the wildcard.
- *You edited a skill and nothing changed.* Skills under `.opencode/skills/`
  are generated — a hand-edit there is either overwritten on the next
  `sync_agent_tools.py` run, or has no effect at all if another contributor
  syncs first. Edit `.ai/skills/<name>/SKILL.md` and resync.
- *A pipeline tool can't find the engine.* `mbg-spice-to-gds.ts` resolves
  the canonical package at `src/mbg` and throws if `src/mbg/pipeline.py` is
  absent. This is deliberate: the tool used to fall back to a bundled mirror
  and run weeks-old placement/routing code. Run the tool from inside a full
  clone.

### Claude Code

**Prerequisites:** Claude Code CLI (tested against `2.1.235`), launched from
the repo root (the `@AGENTS.md` import in `CLAUDE.md` is a relative path).

**Where it lives:** `.claude/skills/<name>/SKILL.md`,
`.claude/commands/<name>.md`, instructions in `CLAUDE.md` (which imports
`AGENTS.md` — Claude Code does not read `AGENTS.md` natively, hence the
import), permissions in `.claude/settings.json`. This repo defines no
`.claude/agents/` subagents.

**Setup:** nothing to install — `CLAUDE.md`, `.claude/skills/`, and
`.claude/commands/` are already committed and generated. Just open the repo.

**Sync command:** the same sync script regenerates the Claude Code adapter
too — there's no separate Claude-specific generator:

```bash
python3 scripts/sync_agent_tools.py
python3 scripts/sync_agent_tools.py --check
```

**Validation:** same as OpenCode — `python3 scripts/validate_agent_integrations.py`
for the full ten-check run, `python3 scripts/sync_agent_tools.py --check` for a
fast staleness check. `.claude/settings.json` pre-approves both so neither
prompts for permission.

**Quick start:** same invocation shape as OpenCode —

```text
/mbg-full-automate
Design a StrongARM latch comparator with <10mV input offset, 1GHz clock,
GF180MCU 3.3V PDK.
```

**Troubleshooting:**

- *`AGENTS.md` rules don't seem to apply.* The `@AGENTS.md` import in
  `CLAUDE.md` is resolved relative to where Claude Code was launched — start
  the session from the repository root, not a subdirectory.
- *A command you expect to be pre-approved still prompts.* `.claude/settings.json`
  allow-lists exact patterns (`Bash(python3 scripts/sync_agent_tools.py:*)`,
  read-only git/docker inspection, etc.) — a different script or a bare
  `python3` invocation outside that list still asks for approval every time.
- *You expect a generated OpenCode-style code tool and there isn't one.*
  Claude Code has no repo-scoped code-tool runtime (see the workflow table's
  footnote ²) — `.opencode/tools/*.ts` logic has no Claude Code equivalent;
  it has to be re-expressed as skill instructions plus ordinary Bash/Python.

### Codex

**Prerequisites:** Codex CLI (tested against `codex-cli 0.148.0`) with the
`codex plugin` subcommand family available.

**Where it lives:** `AGENTS.md` is read natively at the repo root — no
import shim needed, unlike Claude Code. Repo skills ship as a **local
plugin**: `plugins/mbg-analog/skills/<name>/SKILL.md`, plugin manifest
`plugins/mbg-analog/.codex-plugin/plugin.json`, discovered through a local
marketplace descriptor `.agents/plugins/marketplace.json` (marketplace name
`mbg-local`) that points at `./plugins/mbg-analog`. Codex has **no**
repo-scoped commands, **no** repo-scoped subagents, and **no** repo-scoped
`config.toml` — normal Codex skills otherwise live user-level under
`$CODEX_HOME/skills`, which is exactly why this repo needs its own local
marketplace/plugin instead.

**Setup / install** (syntax verified against `codex plugin marketplace add --help`
and `codex plugin add --help` on `0.148.0`; this is a one-time, per-machine
step, not something `git clone` gives you for free):

```bash
./scripts/install_agents.sh --only codex     # does both steps below for you
```

or manually:

```bash
cd <repo-root>
codex plugin marketplace add .          # the DIRECTORY, not the .json file
codex plugin add mbg-analog@mbg-local
# equivalently: codex plugin add mbg-analog --marketplace mbg-local
```

The marketplace source must be the **directory** that contains
`.agents/plugins/marketplace.json` — pass the repo root (`.`). Pointing at the
JSON file itself fails with *"local marketplace source must be a directory,
not a file"*.

This registers the marketplace and installs the plugin into your user-level
`~/.codex/config.toml` (under `[marketplaces.mbg-local]` and
`[plugins."mbg-analog@mbg-local"]`) — every teammate runs it once, locally.

**Refreshing after a sync:** Codex copies the plugin into
`~/.codex/plugins/cache/` at install time, so regenerating the adapters does
**not** reach Codex on its own. Re-run `./scripts/install_agents.sh --only codex`
— it does a `remove` + `add`, which refreshes the copy without needing a
version bump. OpenCode and Claude Code read the repository directly and need
no refresh step.

**Sync command:** the same script regenerates the Codex adapter (the plugin
skills, `plugin.json`, and `marketplace.json`) from `.ai/`:

```bash
python3 scripts/sync_agent_tools.py
python3 scripts/sync_agent_tools.py --check
```

**Validation:** `python3 scripts/validate_agent_integrations.py` as above, plus,
once the plugin is installed,
`codex plugin list --marketplace mbg-local` (a real, `--help`-confirmed
read-only command) to confirm Codex itself now sees all the `mbg-` skills
(9 as of this writing — count varies as skills are added; re-run
`python3 scripts/sync_agent_tools.py --check` for the current total).

**Quick start:** there is no slash command on Codex — after installing the
plugin, just ask directly:

```text
Using the mbg-spice-to-gds skill, convert this SPICE netlist to a
DRC-clean GDSII layout for the gf180mcuD PDK: <netlist>
```

**Troubleshooting:**

- *`codex plugin marketplace add` fails with "local marketplace source must
  be a directory, not a file".* You passed the manifest path. Pass the
  directory that contains it — the repo root: `codex plugin marketplace add .`
- *Codex still shows old skills after you edited `.ai/`.* The plugin is cached
  at install time. Run `./scripts/install_agents.sh --only codex` to refresh it.
- *You typed `/mbg-full-automate` and nothing happened.* Codex has no
  repo-scoped commands or subagents at all (see the workflow table's
  footnote ¹, and `platforms.codex.unsupported` in `.ai/manifest.json`) —
  there is no slash-command equivalent to fall back to; describe the
  workflow in natural language instead.
- *A teammate says the skills "aren't there" after pulling your change.*
  Marketplace/plugin registration lives in `~/.codex/config.toml`, which is
  per-user and per-machine, not part of the repo — each person who wants the
  `mbg-` skills on Codex has to run both `codex plugin marketplace add` and
  `codex plugin add` themselves.

### Contributor workflow: adding or changing a capability

1. Edit the canonical definition — a new/changed `.ai/skills/<name>/SKILL.md`
   or `.ai/workflows/<name>.md`. Frontmatter is validated by the sync script:
   skills require `name`, `description`, `class`, `owner`, `capabilities`,
   `platforms`; workflows require `name`, `description`, `agent`, `platforms`
   (and workflows may not target `codex` — Codex doesn't support repo-scoped
   commands).
2. Add the implementation, if the capability needs one, under
   `src/mbg/`.
3. Register the capability (and/or workflow) in `.ai/manifest.json`.
4. Regenerate every adapter:
   ```bash
   python3 scripts/sync_agent_tools.py
   ```
5. Confirm nothing drifted:
   ```bash
   python3 scripts/sync_agent_tools.py --check
   ```
6. Commit the canonical `.ai/` change together with every regenerated file
   in the **same** commit — never split a source change from its generated
   output across commits, and never hand-edit a generated file directly.

---

## 📁 Repository Structure

```text
├── src/mbg/                           # THE ENGINE — the only copy, `import mbg`
│   ├── passives.py                    # native ppolyf_u resistor + met4/met5 MIM
│   ├── pipeline.py                    # spice_to_gds_with_checks(), spice_to_gds_ctx()
│   ├── spice_parser.py                # netlist parsing + constraint extraction
│   ├── design_context.py              # DesignContext shared across every stage
│   ├── pdk_rules.py                   # all layer/width/spacing/via rules, from the PDK
│   ├── placement.py placement_engine.py   # legacy rows / analog-aware placement
│   ├── routing.py   router.py             # legacy shapes / DRC-aware grid router
│   ├── connectivity.py                # internal OPEN/SHORT verification
│   ├── checks.py                      # DRC / LVS / PEX automation
│   ├── simulation.py                  # ngspice runner + raw parsing
│   └── power.py utils.py pdk_devices.py experiment_manifest.py
├── pyproject.toml                     # src-layout packaging (`pip install -e .`)
│
├── .ai/                               # canonical agent layer (SOURCE OF TRUTH)
├── .claude/  .opencode/  plugins/  .agents/   # generated per-platform adapters
├── AGENTS.md  CLAUDE.md               # shared agent rules (CLAUDE.md imports AGENTS.md)
├── scripts/                           # sync_agent_tools.py, validate_agent_integrations.py,
│                                      #   install_agents.sh, container launch scripts
│
├── designs/                           # Chipathon design tree (template convention)
│   ├── libs/                          # design & testbench libraries
│   │   ├── core_analog/               # circuit cells (OTA, comparator, ...)
│   │   └── tb_analog/                 # testbench setups
│   └── notebooks/chipathon2026-D/     # the Chipathon project directory
│       ├── scripts/                   # iic-drc.sh, iic-lvs.sh, iic-pex.sh (found
│       │                              #   automatically; override MBG_SCRIPTS_DIR)
│       ├── examples/  docs/  ai_logs/ # runnable examples, reference docs, session logs
│       ├── dataset/                   # finetuning / prompt datasets
│       └── outputs/                   # generated artifacts (gitignored)
│
├── tests/                             # ALL test suites live at the repo root
│   ├── test_all_designs.py            # 6-design DRC + LVS + connectivity regression
│   ├── test_router_synthetic.py       # router unit tests (no PDK required)
│   ├── test_analysis.py               # op/dc/ac/tran/Monte-Carlo
│   ├── test_outputs.py                # GDS/LEF/LIB/Verilog/SPICE/SVG emission
│   ├── test_integration.py            # multi-macro chip integration
│   ├── test_agent_integrations.py     # canonical vs generated agent layer
│   └── notebooks/                     # spice_to_gds.ipynb, llm_to_gds.ipynb
│
├── AI-Generated-Design-Result/        # generated designs + preserved baselines
├── docs/                              # workflow documentation
└── README.md
```

The engine lives at `src/mbg/` and is imported as `mbg` from anywhere in the
repository. There is exactly one copy — earlier revisions carried three, which
silently diverged. Tests sit at the repository root so they run against the
installed package rather than a relative path. The Chipathon design directory
keeps its EDA scripts, examples and outputs so the template layout is preserved.

## 🧪 Test Key Circuits (Tapeout Plan)

| Circuit | Status | Key Metric |
| :--- | :--- | :--- |
| **5T OTA** | ✅ Proven | Gain, GBW, Phase Margin |
| **StrongARM Comparator** | ✅ Autonomous Tuning | `<10mV` Offset (all PVT) |
| **Voltage Reference** | ✅ Layout DRC/LVS clean | Temperature Coefficient *(not yet characterised)* |

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
| Analog Design, Placement, Routing, Power, Simulation | **Huda** | `src/mbg/`: `placement_engine.py`, `router.py`, `connectivity.py`, `power.py`, `simulation.py`, `analysis.py`, `spice_parser.py` |
| DRC, LVS, PEX, Verification, Environment | **Ahmad** | `src/mbg/`: `checks.py`, `pdk_rules.py`, `utils.py` · `scripts/`, `tests/` |
| AI/LLM Integration, Prompts, Pipeline, Docs | **Jabir** | `src/mbg/`: `pipeline.py`, `llm.py`, `outputs.py`, `integrate.py` · `tests/notebooks/llm_to_gds.ipynb`, `.ai/` |

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

## 🙏 Acknowledgments

This project is built on top of two outstanding open-source frameworks:

| Project | Role | Link |
| :--- | :--- | :--- |
| **gLayout** | SPICE-to-GDS layout generation engine — automated device placement, power routing, and PathFinder negotiated-congestion signal routing | [github.com/ReaLLMASIC/gLayout](https://github.com/ReaLLMASIC/gLayout) |
| **gdsfactory** | PDK activation, device library (nmos, pmos, mimcap, via_stack), and GDSII I/O | [github.com/gdsfactory/gdsfactory](https://github.com/gdsfactory/gdsfactory) |

We are grateful to the maintainers and contributors of both projects for
making automated analog layout generation possible.

---

## 📄 License

This project is licensed under the Apache License, Version 2.0. See the [LICENSE](LICENSE) file
for details.