import { tool } from "@opencode-ai/plugin"
import path from "node:path"

type ExtensionKind = "skill" | "tool" | "command" | "agent"

type ValidationResult = {
  valid: boolean
  kind: ExtensionKind
  path: string
  errors: string[]
  warnings: string[]
}

function parseFrontmatter(content: string): Record<string, string> {
  if (!content.startsWith("---\n")) {
    return {}
  }

  const endIndex = content.indexOf("\n---", 4)

  if (endIndex === -1) {
    return {}
  }

  const block = content.slice(4, endIndex)
  const values: Record<string, string> = {}

  for (const line of block.split("\n")) {
    const match = line.match(/^([A-Za-z0-9_-]+):\s*(.+?)\s*$/)

    if (!match) {
      continue
    }

    values[match[1]] = match[2].replace(/^["']|["']$/g, "")
  }

  return values
}

function resolveInsideWorktree(
  worktree: string,
  inputPath: string,
): {
  absolutePath: string
  relativePath: string
} {
  const trimmed = inputPath.trim()

  if (!trimmed) {
    throw new Error("Path cannot be empty")
  }

  if (path.isAbsolute(trimmed)) {
    throw new Error(
      "Use a repository-relative path, not an absolute path",
    )
  }

  const absolutePath = path.resolve(worktree, trimmed)
  const relativePath = path
    .relative(worktree, absolutePath)
    .replaceAll("\\", "/")

  if (
    relativePath === "" ||
    relativePath === ".." ||
    relativePath.startsWith("../") ||
    path.isAbsolute(relativePath)
  ) {
    throw new Error(
      "Path must resolve to a file inside the Git worktree",
    )
  }

  return {
    absolutePath,
    relativePath,
  }
}

function detectKind(relativePath: string): ExtensionKind {
  if (
    /^\.opencode\/skills\/[^/]+\/SKILL\.md$/.test(relativePath)
  ) {
    return "skill"
  }

  if (/^\.opencode\/tools\/.+\.(ts|js)$/.test(relativePath)) {
    return "tool"
  }

  if (/^\.opencode\/commands\/.+\.md$/.test(relativePath)) {
    return "command"
  }

  if (/^\.opencode\/agents\/.+\.md$/.test(relativePath)) {
    return "agent"
  }

  throw new Error(
    [
      "Unsupported extension path.",
      "Expected one of:",
      ".opencode/skills/<name>/SKILL.md",
      ".opencode/tools/<name>.ts",
      ".opencode/commands/<name>.md",
      ".opencode/agents/<name>.md",
    ].join("\n"),
  )
}

function hasSection(content: string, section: string): boolean {
  const escaped = section.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  const pattern = new RegExp(`^##\\s+${escaped}\\s*$`, "mi")

  return pattern.test(content)
}

function validateSkill(
  relativePath: string,
  content: string,
  result: ValidationResult,
): void {
  const folderName = path.basename(path.dirname(relativePath))
  const frontmatter = parseFrontmatter(content)

  const skillName = frontmatter.name ?? ""
  const description = frontmatter.description ?? ""
  const validNamePattern = /^[a-z0-9]+(?:-[a-z0-9]+)*$/

  if (!skillName) {
    result.errors.push("Skill frontmatter requires `name`")
  } else {
    if (!validNamePattern.test(skillName)) {
      result.errors.push(
        "Skill name must use lowercase alphanumeric kebab-case",
      )
    }

    if (skillName !== folderName) {
      result.errors.push(
        `Skill name '${skillName}' does not match folder '${folderName}'`,
      )
    }

    if (!skillName.startsWith("mbg-")) {
      result.errors.push(
        "Project-specific skill names must start with `mbg-`",
      )
    }
  }

  if (!description) {
    result.errors.push("Skill frontmatter requires `description`")
  } else if (description.length > 1024) {
    result.errors.push(
      "Skill description must not exceed 1024 characters",
    )
  }

  const recommendedSections = [
    "Purpose",
    "When to Use",
    "When Not to Use",
    "Required Inputs",
    "Workflow",
    "Safety Rules",
    "Output Contract",
    "Failure Handling",
    "Test Cases",
  ]

  for (const section of recommendedSections) {
    if (!hasSection(content, section)) {
      result.warnings.push(
        `Recommended skill section is missing: ${section}`,
      )
    }
  }
}

function validateTool(
  relativePath: string,
  content: string,
  result: ValidationResult,
): void {
  const filename = path.basename(relativePath)
  const toolName = filename.replace(/\.(ts|js)$/, "")

  if (!toolName.startsWith("mbg-")) {
    result.errors.push(
      "Project-specific tool names must start with `mbg-`",
    )
  }

  const reservedNames = new Set([
    "bash",
    "read",
    "write",
    "edit",
    "grep",
    "glob",
  ])

  if (reservedNames.has(toolName)) {
    result.errors.push(
      `Tool name '${toolName}' conflicts with a built-in tool`,
    )
  }

  if (!content.includes("@opencode-ai/plugin")) {
    result.errors.push(
      "Tool must import `tool` from `@opencode-ai/plugin`",
    )
  }

  if (!content.includes("export default tool(")) {
    result.errors.push(
      "Tool must use `export default tool(...)`",
    )
  }

  if (!content.includes("description:")) {
    result.errors.push("Tool requires a description")
  }

  if (!content.includes("args:")) {
    result.errors.push("Tool requires an argument schema")
  }

  if (!content.includes("execute(")) {
    result.errors.push("Tool requires an execute function")
  }

  if (!content.includes("context.worktree")) {
    result.warnings.push(
      "Tool does not reference `context.worktree` for path safety",
    )
  }
}

function validateCommand(
  relativePath: string,
  content: string,
  result: ValidationResult,
): void {
  const filename = path.basename(relativePath)
  const commandName = filename.replace(/\.md$/, "")
  const frontmatter = parseFrontmatter(content)

  if (!commandName.startsWith("mbg-")) {
    result.errors.push(
      "Project-specific command names must start with `mbg-`",
    )
  }

  if (!frontmatter.description) {
    result.errors.push(
      "Command frontmatter requires `description`",
    )
  }

  if (!frontmatter.agent) {
    result.warnings.push(
      "Command should specify an `agent` in frontmatter",
    )
  }

  if (
    !content.includes("$ARGUMENTS") &&
    !/\$[1-9]/.test(content)
  ) {
    result.warnings.push(
      "Command does not accept `$ARGUMENTS` or positional arguments",
    )
  }

  const frontmatterEnd = content.indexOf("\n---", 4)
  const body =
    frontmatterEnd >= 0
      ? content.slice(frontmatterEnd + 4).trim()
      : ""

  if (!body) {
    result.errors.push("Command body cannot be empty")
  }
}

function validateAgent(
  relativePath: string,
  content: string,
  result: ValidationResult,
): void {
  const filename = path.basename(relativePath)
  const agentName = filename.replace(/\.md$/, "")
  const frontmatter = parseFrontmatter(content)

  if (!agentName.startsWith("mbg-")) {
    result.errors.push(
      "Project-specific agent names must start with `mbg-`",
    )
  }

  if (!frontmatter.description) {
    result.errors.push(
      "Agent frontmatter requires `description`",
    )
  }

  if (!frontmatter.mode) {
    result.warnings.push(
      "Agent should declare its `mode` in frontmatter",
    )
  }

  if (!content.includes("permission:")) {
    result.warnings.push(
      "Agent does not define focused permissions",
    )
  }
}

function validateSecurity(
  content: string,
  result: ValidationResult,
): void {
  if (/DEEPSEEK_API_KEY\s*=\s*\S+/i.test(content)) {
    result.errors.push(
      "Possible DeepSeek credential assignment detected",
    )
  }

  if (/sk-[A-Za-z0-9_-]{20,}/.test(content)) {
    result.errors.push(
      "Possible API token detected",
    )
  }

  const personalPathPatterns = [
    /\/home\/jabir(?:mubarok)?\//i,
    /\/home\/huda\//i,
    /\/Users\/[^/]+\//,
    /C:\\Users\\[^\\]+\\/i,
  ]

  if (personalPathPatterns.some((pattern) => pattern.test(content))) {
    result.errors.push(
      "Personal absolute filesystem path detected",
    )
  }
}

export default tool({
  description:
    "Validate an MBG OpenCode skill, tool, command, or agent file for its location, naming, metadata, structure, and basic security conventions.",

  args: {
    path: tool.schema
      .string()
      .describe(
        "Repository-relative path to an extension under `.opencode/`",
      ),
  },

  async execute(args, context) {
    const { absolutePath, relativePath } = resolveInsideWorktree(
      context.worktree,
      args.path,
    )

    const kind = detectKind(relativePath)
    const file = Bun.file(absolutePath)

    if (!(await file.exists())) {
      throw new Error(`File not found: ${relativePath}`)
    }

    const content = await file.text()

    const result: ValidationResult = {
      valid: false,
      kind,
      path: relativePath,
      errors: [],
      warnings: [],
    }

    switch (kind) {
      case "skill":
        validateSkill(relativePath, content, result)
        break

      case "tool":
        validateTool(relativePath, content, result)
        break

      case "command":
        validateCommand(relativePath, content, result)
        break

      case "agent":
        validateAgent(relativePath, content, result)
        break
    }

    validateSecurity(content, result)

    result.valid = result.errors.length === 0

    return JSON.stringify(result, null, 2)
  },
})