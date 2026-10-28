import { tool } from "@opencode-ai/plugin"
import path from "node:path"
import { existsSync, mkdirSync, writeFileSync } from "node:fs"
import { createHash } from "node:crypto"
import { execFileSync } from "node:child_process"

// Thin wrapper over the `mbg` command line (`scripts/mbg layout generate`).
// The CLI owns the flow — layout, Magic + KLayout DRC, netgen LVS, PEX — and
// prints exactly one JSON envelope (mbg.result/1) on stdout, which is
// returned unchanged. Every other harness reaches the same tool through
// `scripts/mbg` or its MCP server, so all of them see the same behaviour.
//
// Owner: jabir. Depends on Huda's layout pipeline and Ahmad's checks through
// the CLI only.

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
  return rel.replaceAll("\\", "/")
}

function launcher(worktree: string): string {
  const mbg = path.join(worktree, "scripts", "mbg")
  if (!existsSync(mbg)) {
    throw new Error("scripts/mbg not found — run this tool inside a clone of the repository")
  }
  return mbg
}

// Run the CLI without a shell; a non-zero exit (design FAIL, job still
// running) still carries the envelope on stdout.
function runMbg(worktree: string, argv: string[], timeoutMs: number): string {
  try {
    return execFileSync(launcher(worktree), argv, {
      cwd: worktree, encoding: "utf-8", timeout: timeoutMs,
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
}

export default tool({
  description:
    "SPICE subcircuit -> GDS with the MBG analog placer and router, then Magic + KLayout DRC, " +
    "netgen LVS and PEX (`scripts/mbg layout generate`). Returns the mbg.result/1 JSON envelope: " +
    "status PASS only when all four sign-off legs pass. Long runs return a job id; continue " +
    "with `scripts/mbg job wait <id>`.",

  args: {
    netlist: tool.schema
      .string()
      .describe(
        "Repository-relative path to a .spice file with exactly one .subckt, or the netlist " +
        "text itself (saved under outputs/opencode/). Omit when `design` names a workspace.",
      )
      .optional(),
    design: tool.schema
      .string()
      .describe("Design workspace name from `scripts/mbg design init`")
      .optional(),
    pdk: tool.schema
      .string()
      .describe("gf180mcuD (default) or sky130A; inferred from the models when omitted")
      .optional(),
    hints: tool.schema
      .string()
      .describe("Repository-relative path to a placement-hints JSON file")
      .optional(),
  },

  async execute(args, context) {
    const worktree = context.worktree
    const argv = ["layout", "generate"]
    if (args.netlist) {
      if (/\.subckt/i.test(args.netlist)) {
        const digest = createHash("sha256").update(args.netlist).digest("hex").slice(0, 12)
        const dir = path.join(worktree, "outputs", "opencode")
        mkdirSync(dir, { recursive: true })
        writeFileSync(path.join(dir, `${digest}.spice`), args.netlist, "utf-8")
        argv.push(`outputs/opencode/${digest}.spice`)
      } else {
        argv.push(resolveInsideWorktree(worktree, args.netlist))
      }
    }
    if (args.design) argv.push("--design", args.design)
    if (args.pdk) argv.push("--pdk", args.pdk)
    if (args.hints) argv.push("--hints", resolveInsideWorktree(worktree, args.hints))
    argv.push("--wait-s", "540")
    return runMbg(worktree, argv, 600_000)
  },
})
