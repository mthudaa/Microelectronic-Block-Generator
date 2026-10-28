import { tool } from "@opencode-ai/plugin"
import path from "node:path"
import { existsSync } from "node:fs"
import { execFileSync } from "node:child_process"

// Thin wrapper over `scripts/mbg verify drc|lvs|pex`. The CLI prints exactly
// one JSON envelope (mbg.result/1) on stdout; it is returned unchanged.
//
// Owner: jabir. Runs Ahmad's verification scripts (Magic, netgen, KLayout)
// through the CLI only.

function resolveInsideWorktree(worktree: string, input: string): string {
  const trimmed = input.trim()
  if (!trimmed) throw new Error("Path cannot be empty")
  if (path.isAbsolute(trimmed)) {
    throw new Error("Use a repository-relative path, not an absolute path")
  }
  if (trimmed.split(/[\\/]/).includes("..")) {
    throw new Error("Parent-directory traversal is not allowed")
  }
  if (/(^|\/)\.env(\.|$)/.test(trimmed)) {
    throw new Error("Secret files cannot be used")
  }
  const rel = path.relative(worktree, path.resolve(worktree, trimmed))
  if (!rel || rel.startsWith("..") || path.isAbsolute(rel)) {
    throw new Error("Path must resolve inside the Git worktree")
  }
  if (!existsSync(path.join(worktree, rel))) {
    throw new Error(`File not found: ${rel}`)
  }
  return rel.replaceAll("\\", "/")
}

export default tool({
  description:
    "Physical verification of an existing GDS with the MBG tools: `drc` (Magic + the PDK's " +
    "KLayout deck), `lvs` (netgen, needs the schematic netlist) or `pex` (Magic extraction to " +
    "a SPICE netlist). Returns the mbg.result/1 JSON envelope.",

  args: {
    check: tool.schema.enum(["drc", "lvs", "pex"]).describe("Which verification to run"),
    gds: tool.schema.string().describe("Repository-relative path to the .gds file"),
    netlist: tool.schema
      .string()
      .describe("Repository-relative schematic netlist (required for lvs)")
      .optional(),
    cell: tool.schema.string().describe("Top cell name (default: from the GDS)").optional(),
    pdk: tool.schema.string().describe("gf180mcuD (default) or sky130A").optional(),
  },

  async execute(args, context) {
    const worktree = context.worktree
    const mbg = path.join(worktree, "scripts", "mbg")
    if (!existsSync(mbg)) {
      throw new Error("scripts/mbg not found — run this tool inside a clone of the repository")
    }
    if (args.check === "lvs" && !args.netlist) {
      throw new Error("lvs needs `netlist`, the schematic SPICE file")
    }
    const argv = ["verify", args.check, resolveInsideWorktree(worktree, args.gds)]
    if (args.netlist) argv.push("--netlist", resolveInsideWorktree(worktree, args.netlist))
    if (args.cell) argv.push("--cell", args.cell)
    if (args.pdk) argv.push("--pdk", args.pdk)
    argv.push("--wait-s", "540")
    try {
      return execFileSync(mbg, argv, {
        cwd: worktree, encoding: "utf-8", timeout: 600_000,
        maxBuffer: 16 * 1024 * 1024, stdio: ["ignore", "pipe", "pipe"],
      }).trim()
    } catch (err: any) {
      const out = (err.stdout || "").toString().trim()
      if (out.startsWith("{")) return out
      return JSON.stringify({
        schema: "mbg.result/1", ok: false, status: "NOT RUN",
        summary: "mbg did not return a result",
        error: { code: "launcher", message: (err.stderr || err.message || "").toString().slice(-2000) },
      })
    }
  },
})
