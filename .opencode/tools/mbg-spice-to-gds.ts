import { tool } from "@opencode-ai/plugin"
import path from "node:path"
import { homedir } from "node:os"
import { execSync } from "node:child_process"
import { writeFile, mkdir } from "node:fs/promises"

const CORE_DIR = path.resolve(import.meta.dirname)

/**
 * Resolve the working directory for pipeline execution.
 *
 * Priority:
 *   1. ``MBG_WORKDIR`` environment variable
 *   2. ``$HOME`` (user home directory)
 *   3. ``context.workdir`` (VS Code workspace root)
 */
function resolveWorkdir(context: { workdir?: string }): string {
  if (process.env.MBG_WORKDIR) {
    return path.resolve(process.env.MBG_WORKDIR)
  }
  return context.workdir || homedir()
}

/**
 * Run the MBG SPICE-to-GDS pipeline with DRC/LVS/PEX checks.
 *
 * Executes `spice_to_gds_with_checks(netlist)` from the core Python pipeline
 * and returns structured results.
 */
const mbgSpiceToGds = tool({
  description:
    "Convert a SPICE subcircuit netlist to GDSII layout and run DRC+LVS+PEX verification. " +
    "This is the PRIMARY pipeline tool — use it instead of manual step-by-step placement/routing. " +
    "Returns outdir, gds_path, svg_path, drc, lvs, pex, and all_pass status.",
  schema: {
    netlist: {
      type: "string",
      description:
        "SPICE subcircuit netlist string with .subckt definition. " +
        "Must include .lib model path. Use XM1 prefix and nf=N for fingers.",
    },
    workdir: {
      type: "string",
      description:
        "Output directory path (repository-relative). Default: cell name under current dir.",
    },
    mode: {
      type: "string",
      enum: ["analog", "digital"],
      description: "Layout mode. Default: analog.",
    },
  },
  execute: async ({ netlist, workdir, mode }, context) => {
    const cwd = resolveWorkdir(context)

    // Build workdir argument for the Python pipeline
    let workdirArg = "None"
    if (workdir) {
      workdirArg = JSON.stringify(path.resolve(cwd, workdir))
    }

    const script = `
import sys, os, json
sys.path.insert(0, ${JSON.stringify(CORE_DIR)})
os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.join(os.environ["PDK_ROOT"], os.environ["PDK"]))

from core.pipeline import spice_to_gds_with_checks

netlist = ${JSON.stringify(netlist)}
wd = ${workdirArg}
r = spice_to_gds_with_checks(netlist, gds_path=wd)
print(json.dumps({
    "outdir": r["outdir"],
    "gds_path": r["gds_path"],
    "svg_path": r.get("svg_path"),
    "cell_name": r["cell_name"],
    "drc_summary": r["drc"].get("summary", "?"),
    "lvs_match": r["lvs"].get("match", False),
    "pex_summary": r["pex"].get("summary", "?"),
    "all_pass": r["all_pass"],
}, indent=2))
`

    const tmpScript = path.join(cwd, "mbg_pipeline_run.py")
    await mkdir(path.dirname(tmpScript), { recursive: true })
    await writeFile(tmpScript, script, "utf-8")

    try {
      const stdout = execSync(
        `python3 ${tmpScript}`,
        {
          cwd,
          timeout: 600_000, // 10 min
          encoding: "utf-8",
          maxBuffer: 10 * 1024 * 1024,
        },
      )
      return JSON.parse(stdout.trim())
    } catch (err: any) {
      return {
        error: true,
        message: err.stderr || err.message || "Pipeline execution failed",
        stdout: err.stdout || "",
      }
    }
  },
})

export default mbgSpiceToGds
