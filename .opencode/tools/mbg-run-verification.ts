import { tool } from "@opencode-ai/plugin"
import path from "node:path"
import { existsSync } from "node:fs"
import { homedir } from "node:os"
import { execSync } from "node:child_process"
import { writeFile, mkdir } from "node:fs/promises"

// Resolve the CANONICAL core package, not the copy that used to sit beside
// this file. `.opencode/tools/core/` is a stale mirror (it lags the maintained
// package by weeks and is missing whole modules), so importing it silently ran
// old placement/routing code. Fall back to the local directory only if the
// canonical path is absent, so a partial checkout still works.
const REPO_ROOT = path.resolve(import.meta.dirname, "..", "..")
const CORE_DIR = path.join(REPO_ROOT, "src")
if (!existsSync(path.join(CORE_DIR, "mbg", "pipeline.py"))) {
  // Fail loudly rather than silently falling back to a stale copy — that is
  // exactly how this tool ended up running weeks-old code before.
  throw new Error(
    `mbg package not found at ${CORE_DIR}/mbg — run this tool from inside a clone of the repository`,
  )
}

/**
 * Resolve the working directory for verification execution.
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
 * Run DRC, LVS, or PEX verification on a GDSII layout.
 *
 * Executes the appropriate Python core.check function and returns
 * structured verification results.
 */
const mbgRunVerification = tool({
  description:
    "Run DRC (Design Rule Check), LVS (Layout vs Schematic), or PEX (Parasitic Extraction) " +
    "on a GDSII layout file. For LVS, provide netlist_content to compare against. " +
    "Netgen permute 1 3 handles MOSFET D/S swapping natively.",
  schema: {
    check_type: {
      type: "string",
      enum: ["drc", "lvs", "pex"],
      description: "Verification type to run.",
    },
    gds_path: {
      type: "string",
      description: "Path to GDSII file (repository-relative).",
    },
    netlist_content: {
      type: "string",
      description:
        "SPICE netlist string for LVS comparison. Required when check_type=lvs.",
    },
    cell_name: {
      type: "string",
      description: "Top cell name. Auto-detected from GDS filename if omitted.",
    },
    workdir: {
      type: "string",
      description: "Working directory for report output.",
    },
  },
  execute: async (
    { check_type, gds_path, netlist_content, cell_name, workdir },
    context,
  ) => {
    const cwd = resolveWorkdir(context)
    const resolvedGds = path.resolve(cwd, gds_path || "")

    let netlistArg = "None"
    if (netlist_content) {
      netlistArg = JSON.stringify(netlist_content)
    }

    let cellArg = "None"
    if (cell_name) {
      cellArg = JSON.stringify(cell_name)
    }

    let workdirArg = "None"
    if (workdir) {
      workdirArg = JSON.stringify(path.resolve(cwd, workdir))
    } else {
      workdirArg = JSON.stringify(path.dirname(resolvedGds))
    }

    const script = `
import sys, os, json
sys.path.insert(0, ${JSON.stringify(CORE_DIR)})
os.environ.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
os.environ.setdefault("PDK", "gf180mcuD")
os.environ.setdefault("PDKPATH", os.path.join(os.environ["PDK_ROOT"], os.environ["PDK"]))

from mbg.checks import run_drc, run_lvs, run_pex

check = ${JSON.stringify(check_type)}
gds = ${JSON.stringify(resolvedGds)}
netlist = ${netlistArg}
cell = ${cellArg}
wd = ${workdirArg}

result = None
if check == "drc":
    result = run_drc(gds, cell_name=cell, workdir=wd)
    out = {"summary": result.get("summary", "?"), "clean": result.get("clean", False)}
elif check == "lvs":
    if netlist is None:
        raise ValueError("netlist_content is required for LVS")
    result = run_lvs(gds, netlist_content=netlist, cell_name=cell, workdir=wd)
    out = {
        "match": result.get("match", False),
        "message": result.get("summary", {}).get("message", "?"),
        "device_mismatch": result.get("summary", {}).get("device_mismatch", "?"),
        "net_mismatch": result.get("summary", {}).get("net_mismatch", "?"),
    }
elif check == "pex":
    result = run_pex(gds, cell_name=cell, workdir=wd, mode=2)
    out = {"summary": result.get("summary", "?"), "pex_path": result.get("pex_path")}
else:
    raise ValueError(f"Unknown check_type: {check}")

print(json.dumps(out, indent=2))
`

    const tmpScript = path.join(cwd, "mbg_verify_run.py")
    await mkdir(path.dirname(tmpScript), { recursive: true })
    await writeFile(tmpScript, script, "utf-8")

    try {
      const stdout = execSync(`python3 ${tmpScript}`, {
        cwd,
        timeout: 600_000,
        encoding: "utf-8",
        maxBuffer: 10 * 1024 * 1024,
      })
      return JSON.parse(stdout.trim())
    } catch (err: any) {
      return {
        error: true,
        check_type,
        message: err.stderr || err.message || "Verification failed",
        stdout: err.stdout || "",
      }
    }
  },
})

export default mbgRunVerification
