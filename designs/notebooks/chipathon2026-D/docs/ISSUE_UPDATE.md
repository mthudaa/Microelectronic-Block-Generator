# Analog Chip Design Generator based on AI/LLM Agentic Models
### *From IDEA to SPICE, from SPICE to GDS in an instant.*

---

## 📋 Team Information

* **Track:** D
* **Team Name:** D8 Microelectronic Block Generator
* **Leader:** M. Taufiqul Huda

### Team Members

| Name | GitHub | Affiliation | Role |
| :--- | :--- | :--- | :--- |
| **M. Taufiqul Huda** | [@mthudaa](https://github.com/mthudaa) | NTUST | Master Student, ECE |
| **Ahmad Jabar Ilmi** | [@ilmiahmad](https://github.com/ilmiahmad) | LG Indonesia | Hardware Engineer |
| **Jabir Mubarok** | [@jabirmbrok](https://github.com/jabirmbrok) | NTUST | PhD Student, CS |

---
## Moh. Jabir Mubarok — AI/LLM Integration & Software Architect

### AI/LLM Reviewer Items

- [ ] **PDK consistency:** Standardize the AI pipeline and documentation on GF180MCU using the `gf180mcuD` identifier. Remove unsupported references to other PDKs.
- [ ] **Complete AI-assisted flow:** Document one reproducible flow from prompt → generated netlist → validation → simulation → GDS → DRC/LVS → PEX → post-layout comparison.
- [ ] **Graphical netlist representation:** Produce and save a readable circuit-connectivity graph for the LLM-generated netlist.
- [ ] **AI metrics:** Report valid-netlist rate, first-pass success, refinement iterations, API calls, runtime, GDS-generation rate, DRC-clean rate, LVS-match rate, and end-to-end success rate.
- [ ] **Prompt independence:** Compare minimal, constraint-based, and detailed prompts instead of evaluating only a prompt that already specifies the full topology.
- [ ] **Evidence-based claims:** Remove unsupported absolute-success claims. Use `PASS`, `FAIL`, `PARTIAL`, `NOT RUN`, or `NOT AVAILABLE`.
- [ ] **OpenCode documentation:** Provide templates and authoring guidance for skills, tools, commands, and project-level agent instructions.

### Dependencies

- Simulation results and waveform generation: Huda.
- Final transistor/model selection: Huda.
- DRC, LVS, PEX, and verification scripts: Ahmad.
- Final tapeout scope and project milestones: Team lead.

Jabir integrates, records, visualizes, and documents outputs from these modules but does not modify their implementation as part of this documentation task.

### Acceptance Criteria

- [ ] README consistently uses `GF180MCU` and `gf180mcuD`.
- [ ] The real notebook path is documented as `llm_to_gds.ipynb`.
- [ ] API-key setup does not expose secrets.
- [ ] Prompt, model, generated netlist, API calls, iterations, and output artifacts are traceable.
- [ ] Minimal and detailed prompts are compared.
- [ ] AI metrics are generated from structured experiment records.
- [ ] No unsupported absolute success claim remains.
- [ ] OpenCode skill, tool, and command templates are documented.
- [ ] No personal filesystem path is committed.


## 🚀 Project Overview

We are developing a framework to automate the design of Analog IC blocks using **gLayout**, **gdsfactory**, and open-weight models from **HuggingFace**. 

Our framework integrates **AI agentic models** into an assisted analog-design workflow. A bounded **SPICE-in-the-loop refinement** process can provide simulation feedback, including delay, VOH/VOL, input offset, and PVT-corner results, to improve generated netlists. Each stage must be evaluated using recorded evidence and reported as `PASS`, `PARTIAL`, `FAIL`, `NOT RUN`, or `NOT AVAILABLE`. After validation, the custom engine translates the accepted netlist into a routed GDS layout.

---

## 📈 Latest Updates & Tapeout Plan

We have successfully expanded our framework beyond our initial Proof-of-Concept (OTA) and have achieved the following milestones:
* **Autonomous Optimization:** Our LLM agent has successfully generated and autonomously tuned a **StrongARM Latch Comparator** that achieves `<10mV` input offset across all PVT corners.
* **Layout-Aware PEX Feedback:** The agent receives exact post-layout $\Delta$ metrics (from Magic PEX) to close the gap between schematic simulation and actual silicon performance.
* **Multi-Model Tapeout Strategy:** For the final tapeout, we plan to implement a comprehensive side-by-side benchmark on the same die. We will multiplex several instances of the same analog blocks:
  1. A baseline design crafted manually (Without AI).
  2. AI-generated designs from various state-of-the-art models (**DeepSeek, Gemma4, Qwen, Nemotron**).

This empirical silicon validation will serve as a groundbreaking benchmark for AI-driven analog layouts.

---

## 🔗 Project Links

* **Repository:** [mthudaa/Microelectronic-Block-Generator](https://github.com/mthudaa/Microelectronic-Block-Generator)
* **Latest Proposal:** [Link to Document](https://docs.google.com/presentation/d/1RD4kdihEX_O-pv52pQHfofJ6L5FtYVQT/edit?usp=sharing)
* **Demo Video:** [Link to Video](https://drive.google.com/file/d/13hEcmMVf-bekuyur6hDBJmNSmHXqoydd/view?usp=sharing)
* **Schematic Review Presentation:** [Link to Document](https://docs.google.com/presentation/d/1mi2Mj95aQM9AowrDk6M0F4ldJfMq8vN7pfCQlcB8WS4/edit?usp=sharing)
* **Schematic Review Video:** [Link to Video](https://drive.google.com/file/d/1EUOmRXneFbURQ1H17LzCyvCLNF5sOewz/view?usp=sharing)
