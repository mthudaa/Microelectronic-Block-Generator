# AI / LLM Conversation Logs

This directory is dedicated to storing the chat histories and conversation logs between team members and their respective AI code agents or LLMs (e.g., ChatGPT, Claude, Gemini, DeepSeek, etc.). 

## Why is this necessary?
Since our team members use different LLM providers, maintaining a synchronized record of AI conversations ensures that:
1. **Context is Preserved:** Other team members can understand how a specific piece of code, algorithm, or prompt was engineered.
2. **Reproducibility:** Prompts that yielded good results (especially for SPICE netlist generation) can be reused, studied, or fine-tuned.
3. **Troubleshooting:** If an AI agent introduces a bug or a subtle design flaw, the conversation history can help trace the root cause and the AI's reasoning.

## File Naming Convention
Please save your conversation logs as Markdown (`.md`), text (`.txt`), or JSON files using the following naming convention:
`YYYY-MM-DD_[TeamMember]_[Task-or-Module]_[LLM-Provider].md`

**Examples:**
- `2026-07-11_Jabir_Prompt_Engineering_DeepSeek.md`
- `2026-07-12_Huda_Analog_Placement_Gemini.md`
- `2026-07-13_Ahmad_DRC_Automation_Claude.md`

## What to Include
- The original context, prompt, or instructions given to the LLM.
- The LLM's complete response (code blocks, explanations, configurations).
- Any follow-up corrections, error logs provided to the LLM, or iterative refinements.
