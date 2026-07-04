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

## 🚀 Project Overview

We are developing a framework to automate the design of Analog IC blocks using **gLayout**, **gdsfactory**, and open-weight models from **HuggingFace**. 

Our framework successfully integrates **AI Agentic Models** acting as autonomous Analog Design Engineers. By employing an advanced **SPICE-in-the-loop Finetuning** mechanism, the LLM receives direct feedback (e.g., Delay, VOH/VOL, Input Offset, and PVT Corners) from the simulator to iteratively refine the circuit's netlist and topology until it achieves 100% functionality. Once verified, our custom engine automatically translates the netlist into a fully routed GDS layout.

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
