import { tool } from "@opencode-ai/plugin"
import path from "node:path"
import { readFile, stat } from "node:fs/promises"

const VALID_STATUSES = new Set([
  "PASS",
  "FAIL",
  "PARTIAL",
  "NOT RUN",
  "NOT AVAILABLE",
])

const VALID_PROMPT_LEVELS = new Set([
  "minimal",
  "constraint-based",
  "detailed",
])

const REQUIRED_STAGE_FIELDS = [
  "pre_simulation_status",
  "drc_status",
  "lvs_status",
  "pex_status",
  "post_simulation_status",
] as const

type StageField = (typeof REQUIRED_STAGE_FIELDS)[number]

type ArtifactCheck = {
  name: string
  configuredPath: string | null
  resolvedPath: string | null
  required: boolean
  exists: boolean
  validPath: boolean
  message: string
}

type AuditResult = {
  valid: boolean
  audit_status: "PASS" | "FAIL"
  experiment_path: string
  experiment_id: string | null
  model: string | null
  pdk: string | null
  prompt_level: string | null
  final_status: string | null
  errors: string[]
  warnings: string[]
  metrics: {
    api_calls: number | null
    refinement_iterations: number | null
    max_refinement_iterations: number | null
    llm_runtime_seconds: number | null
    total_runtime_seconds: number | null
  }
  stage_results: Record<string, unknown>
  artifact_checks: ArtifactCheck[]
}

type ExperimentRecord = Record<string, unknown>

function isRecord(value: unknown): value is Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    !Array.isArray(value)
  )
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim()
    ? value.trim()
    : null
}

function asBoolean(value: unknown): boolean | null {
  return typeof value === "boolean" ? value : null
}

function asFiniteNumber(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value)
    ? value
    : null
}

function asNonNegativeInteger(value: unknown): number | null {
  if (
    typeof value !== "number" ||
    !Number.isInteger(value) ||
    value < 0
  ) {
    return null
  }

  return value
}

function normalizeStatus(value: unknown): string | null {
  const status = asString(value)

  if (!status) {
    return null
  }

  return status.toUpperCase()
}

function containsParentTraversal(inputPath: string): boolean {
  return inputPath
    .replaceAll("\\", "/")
    .split("/")
    .some((part) => part === "..")
}

function isSecretPath(inputPath: string): boolean {
  const normalized = inputPath
    .replaceAll("\\", "/")
    .toLowerCase()

  return (
    normalized.endsWith("/.env") ||
    normalized === ".env" ||
    normalized.includes("/.env.") ||
    normalized.endsWith(".pem") ||
    normalized.endsWith(".key")
  )
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

  if (containsParentTraversal(trimmed)) {
    throw new Error("Parent-directory traversal is not allowed")
  }

  if (isSecretPath(trimmed)) {
    throw new Error("Secret or credential files cannot be inspected")
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

function getNestedValue(
  record: ExperimentRecord,
  keys: string[],
): unknown {
  let current: unknown = record

  for (const key of keys) {
    if (!isRecord(current) || !(key in current)) {
      return undefined
    }

    current = current[key]
  }

  return current
}

function firstString(
  record: ExperimentRecord,
  candidates: string[][],
): string | null {
  for (const candidate of candidates) {
    const value = asString(getNestedValue(record, candidate))

    if (value) {
      return value
    }
  }

  return null
}

function artifactPath(
  record: ExperimentRecord,
  artifactName: string,
): string | null {
  const candidates: Record<string, string[][]> = {
    prompt: [
      ["artifacts", "prompt"],
      ["artifacts", "prompt_path"],
      ["prompt_path"],
    ],
    netlist: [
      ["artifacts", "netlist"],
      ["artifacts", "generated_netlist"],
      ["artifacts", "netlist_path"],
      ["generated_netlist_path"],
      ["netlist_path"],
    ],
    circuit_graph: [
      ["artifacts", "circuit_graph"],
      ["artifacts", "circuit_graph_path"],
      ["circuit_graph_path"],
    ],
    gds: [
      ["artifacts", "gds"],
      ["artifacts", "generated_layout"],
      ["artifacts", "gds_path"],
      ["generated_gds_path"],
      ["gds_path"],
    ],
    pre_simulation: [
      ["artifacts", "pre_simulation"],
      ["artifacts", "pre_simulation_report"],
      ["pre_simulation_report_path"],
    ],
    drc: [
      ["artifacts", "drc"],
      ["artifacts", "drc_report"],
      ["drc_report_path"],
    ],
    lvs: [
      ["artifacts", "lvs"],
      ["artifacts", "lvs_report"],
      ["lvs_report_path"],
    ],
    pex: [
      ["artifacts", "pex"],
      ["artifacts", "pex_netlist"],
      ["pex_netlist_path"],
    ],
    post_simulation: [
      ["artifacts", "post_simulation"],
      ["artifacts", "post_simulation_report"],
      ["post_simulation_report_path"],
    ],
  }

  return firstString(record, candidates[artifactName] ?? [])
}

async function pathExists(targetPath: string): Promise<boolean> {
  try {
    await stat(targetPath)
    return true
  } catch {
    return false
  }
}

function artifactIsRequired(
  artifactName: string,
  record: ExperimentRecord,
): boolean {
  if (artifactName === "prompt") {
    return true
  }

  if (artifactName === "netlist") {
    return asBoolean(record.netlist_valid) === true
  }

  if (artifactName === "circuit_graph") {
    return false
  }

  if (artifactName === "gds") {
    return asBoolean(record.gds_generated) === true
  }

  const stageMap: Record<string, StageField> = {
    pre_simulation: "pre_simulation_status",
    drc: "drc_status",
    lvs: "lvs_status",
    pex: "pex_status",
    post_simulation: "post_simulation_status",
  }

  const stageField = stageMap[artifactName]

  if (!stageField) {
    return false
  }

  const status = normalizeStatus(record[stageField])

  return status === "PASS" || status === "FAIL"
}

async function checkArtifact(
  worktree: string,
  experimentDirectory: string,
  record: ExperimentRecord,
  name: string,
): Promise<ArtifactCheck> {
  const configuredPath = artifactPath(record, name)
  const required = artifactIsRequired(name, record)

  if (!configuredPath) {
    return {
      name,
      configuredPath: null,
      resolvedPath: null,
      required,
      exists: false,
      validPath: true,
      message: required
        ? "Required artifact path is missing"
        : "Optional artifact path is not configured",
    }
  }

  if (
    path.isAbsolute(configuredPath) ||
    containsParentTraversal(configuredPath) ||
    isSecretPath(configuredPath)
  ) {
    return {
      name,
      configuredPath,
      resolvedPath: null,
      required,
      exists: false,
      validPath: false,
      message:
        "Artifact path must be safe, relative, and non-secret",
    }
  }

  /*
   * Artifact paths may be:
   * 1. Relative to the experiment.json directory, or
   * 2. Relative to the Git worktree.
   */
  const relativeToExperiment = path.resolve(
    experimentDirectory,
    configuredPath,
  )

  const relativeToWorktree = path.resolve(
    worktree,
    configuredPath,
  )

  const candidates = [
    relativeToExperiment,
    relativeToWorktree,
  ]

  for (const candidate of candidates) {
    const relative = path
      .relative(worktree, candidate)
      .replaceAll("\\", "/")

    if (
      relative === "" ||
      relative === ".." ||
      relative.startsWith("../") ||
      path.isAbsolute(relative)
    ) {
      continue
    }

    if (await pathExists(candidate)) {
      return {
        name,
        configuredPath,
        resolvedPath: relative,
        required,
        exists: true,
        validPath: true,
        message: "Artifact exists",
      }
    }
  }

  const fallbackRelative = path
    .relative(worktree, relativeToExperiment)
    .replaceAll("\\", "/")

  return {
    name,
    configuredPath,
    resolvedPath: fallbackRelative,
    required,
    exists: false,
    validPath: true,
    message: "Configured artifact does not exist",
  }
}

function validateRequiredString(
  record: ExperimentRecord,
  field: string,
  errors: string[],
): string | null {
  const value = asString(record[field])

  if (!value) {
    errors.push(`Required string field is missing: ${field}`)
  }

  return value
}

function validateStatusField(
  record: ExperimentRecord,
  field: string,
  errors: string[],
): string | null {
  const status = normalizeStatus(record[field])

  if (!status) {
    errors.push(`Required status field is missing: ${field}`)
    return null
  }

  if (!VALID_STATUSES.has(status)) {
    errors.push(
      `Unsupported status '${status}' in field '${field}'`,
    )
  }

  return status
}

function detectCredentialMaterial(
  rawJson: string,
  errors: string[],
): void {
  if (/sk-[A-Za-z0-9_-]{20,}/.test(rawJson)) {
    errors.push("Possible API token detected in experiment metadata")
  }

  if (
    /DEEPSEEK_API_KEY\s*[:=]\s*["']?\S+/i.test(rawJson)
  ) {
    errors.push(
      "DeepSeek API credential material detected in experiment metadata",
    )
  }
}

function validatePersonalPaths(
  rawJson: string,
  errors: string[],
): void {
  const patterns = [
    /\/home\/jabir(?:mubarok)?\//i,
    /\/home\/huda\//i,
    /\/Users\/[^/]+\//,
    /C:\\Users\\[^\\]+\\/i,
  ]

  if (patterns.some((pattern) => pattern.test(rawJson))) {
    errors.push(
      "Personal absolute filesystem path detected in experiment metadata",
    )
  }
}

function validateFinalStatusConsistency(
  record: ExperimentRecord,
  finalStatus: string | null,
  errors: string[],
  warnings: string[],
): void {
  if (!finalStatus || !VALID_STATUSES.has(finalStatus)) {
    return
  }

  const stageStatuses = REQUIRED_STAGE_FIELDS.map((field) => ({
    field,
    status: normalizeStatus(record[field]),
  }))

  const failedStages = stageStatuses.filter(
    ({ status }) => status === "FAIL",
  )

  const incompleteStages = stageStatuses.filter(
    ({ status }) =>
      status === "NOT RUN" ||
      status === "NOT AVAILABLE" ||
      status === "PARTIAL" ||
      status === null,
  )

  if (
    finalStatus === "PASS" &&
    asBoolean(record.netlist_valid) !== true
  ) {
    errors.push(
      "final_status cannot be PASS when netlist_valid is not true",
    )
  }

  if (
    finalStatus === "PASS" &&
    asBoolean(record.gds_generated) !== true
  ) {
    errors.push(
      "final_status cannot be PASS when gds_generated is not true",
    )
  }

  if (finalStatus === "PASS" && failedStages.length > 0) {
    errors.push(
      [
        "final_status cannot be PASS because stages failed:",
        failedStages.map(({ field }) => field).join(", "),
      ].join(" "),
    )
  }

  if (finalStatus === "PASS" && incompleteStages.length > 0) {
    errors.push(
      [
        "final_status cannot be PASS because stages are incomplete:",
        incompleteStages.map(({ field }) => field).join(", "),
      ].join(" "),
    )
  }

  if (
    finalStatus === "FAIL" &&
    failedStages.length === 0 &&
    asBoolean(record.netlist_valid) !== false &&
    asBoolean(record.gds_generated) !== false
  ) {
    warnings.push(
      "final_status is FAIL but no explicit failed stage was found",
    )
  }

  if (
    finalStatus === "PARTIAL" &&
    failedStages.length === 0 &&
    incompleteStages.length === 0
  ) {
    warnings.push(
      "final_status is PARTIAL although all recorded stages appear complete",
    )
  }
}

export default tool({
  description:
    "Validate an MBG AI experiment.json file for reproducibility metadata, bounded LLM refinement, status consistency, safe artifact paths, and supporting evidence.",

  args: {
    experimentPath: tool.schema
      .string()
      .describe(
        "Repository-relative path to an MBG experiment.json file",
      ),
  },

  async execute(args, context) {
    const {
      absolutePath,
      relativePath,
    } = resolveInsideWorktree(
      context.worktree,
      args.experimentPath,
    )

    if (path.basename(relativePath) !== "experiment.json") {
      throw new Error(
        "The supplied file must be named experiment.json",
      )
    }

    let rawJson: string

    try {
      rawJson = await readFile(absolutePath, "utf8")
    } catch (error) {
      throw new Error(
        `Unable to read ${relativePath}: ${String(error)}`,
      )
    }

    let parsed: unknown

    try {
      parsed = JSON.parse(rawJson)
    } catch (error) {
      throw new Error(
        `Invalid JSON in ${relativePath}: ${String(error)}`,
      )
    }

    if (!isRecord(parsed)) {
      throw new Error(
        "The root value of experiment.json must be an object",
      )
    }

    const record = parsed
    const errors: string[] = []
    const warnings: string[] = []

    detectCredentialMaterial(rawJson, errors)
    validatePersonalPaths(rawJson, errors)

    const experimentId = validateRequiredString(
      record,
      "experiment_id",
      errors,
    )

    const model = validateRequiredString(
      record,
      "model",
      errors,
    )

    const pdk = validateRequiredString(
      record,
      "pdk",
      errors,
    )

    if (pdk && pdk !== "gf180mcuD") {
      errors.push(
        `Unsupported PDK '${pdk}'; expected 'gf180mcuD'`,
      )
    }

    const promptLevel = validateRequiredString(
      record,
      "prompt_level",
      errors,
    )

    if (
      promptLevel &&
      !VALID_PROMPT_LEVELS.has(promptLevel)
    ) {
      errors.push(
        [
          `Unsupported prompt_level '${promptLevel}'.`,
          "Expected minimal, constraint-based, or detailed.",
        ].join(" "),
      )
    }

    const apiCalls = asNonNegativeInteger(record.api_calls)

    if (apiCalls === null) {
      errors.push(
        "api_calls must be a non-negative integer",
      )
    } else if (apiCalls < 1) {
      errors.push(
        "api_calls must be at least 1 for an LLM experiment",
      )
    }

    const refinementIterations = asNonNegativeInteger(
      record.refinement_iterations,
    )

    if (refinementIterations === null) {
      errors.push(
        "refinement_iterations must be a non-negative integer",
      )
    }

    const maxRefinementIterations = asNonNegativeInteger(
      record.max_refinement_iterations,
    )

    if (maxRefinementIterations === null) {
      errors.push(
        "max_refinement_iterations must be a non-negative integer",
      )
    }

    if (
      refinementIterations !== null &&
      maxRefinementIterations !== null &&
      refinementIterations > maxRefinementIterations
    ) {
      errors.push(
        [
          "refinement_iterations exceeds",
          "max_refinement_iterations",
        ].join(" "),
      )
    }

    if (
      apiCalls !== null &&
      refinementIterations !== null &&
      apiCalls < refinementIterations + 1
    ) {
      warnings.push(
        [
          "api_calls is lower than the expected initial call",
          "plus refinement iterations",
        ].join(" "),
      )
    }

    const netlistValid = asBoolean(record.netlist_valid)

    if (netlistValid === null) {
      errors.push("netlist_valid must be a boolean")
    }

    const gdsGenerated = asBoolean(record.gds_generated)

    if (gdsGenerated === null) {
      errors.push("gds_generated must be a boolean")
    }

    const llmRuntimeSeconds = asFiniteNumber(
      record.llm_runtime_seconds,
    )

    if (
      llmRuntimeSeconds !== null &&
      llmRuntimeSeconds < 0
    ) {
      errors.push(
        "llm_runtime_seconds cannot be negative",
      )
    }

    if (llmRuntimeSeconds === null) {
      warnings.push(
        "llm_runtime_seconds is missing or invalid",
      )
    }

    const totalRuntimeSeconds = asFiniteNumber(
      record.total_runtime_seconds,
    )

    if (
      totalRuntimeSeconds !== null &&
      totalRuntimeSeconds < 0
    ) {
      errors.push(
        "total_runtime_seconds cannot be negative",
      )
    }

    if (totalRuntimeSeconds === null) {
      warnings.push(
        "total_runtime_seconds is missing or invalid",
      )
    }

    if (
      llmRuntimeSeconds !== null &&
      totalRuntimeSeconds !== null &&
      totalRuntimeSeconds < llmRuntimeSeconds
    ) {
      errors.push(
        "total_runtime_seconds cannot be less than llm_runtime_seconds",
      )
    }

    const stageResults: Record<string, unknown> = {}

    for (const field of REQUIRED_STAGE_FIELDS) {
      stageResults[field] = validateStatusField(
        record,
        field,
        errors,
      )
    }

    const finalStatus = validateStatusField(
      record,
      "final_status",
      errors,
    )

    validateFinalStatusConsistency(
      record,
      finalStatus,
      errors,
      warnings,
    )

    const experimentDirectory = path.dirname(absolutePath)

    const artifactNames = [
      "prompt",
      "netlist",
      "circuit_graph",
      "gds",
      "pre_simulation",
      "drc",
      "lvs",
      "pex",
      "post_simulation",
    ]

    const artifactChecks: ArtifactCheck[] = []

    for (const artifactName of artifactNames) {
      const check = await checkArtifact(
        context.worktree,
        experimentDirectory,
        record,
        artifactName,
      )

      artifactChecks.push(check)

      if (!check.validPath) {
        errors.push(
          `${artifactName}: ${check.message}`,
        )
      } else if (check.required && !check.exists) {
        errors.push(
          `${artifactName}: ${check.message}`,
        )
      } else if (!check.required && !check.exists) {
        warnings.push(
          `${artifactName}: ${check.message}`,
        )
      }
    }

    if (
      promptLevel === "detailed" &&
      asBoolean(record.independent_design_claim) === true
    ) {
      warnings.push(
        [
          "A detailed prompt is marked as an independent-design",
          "experiment; clarify that it measures constrained generation.",
        ].join(" "),
      )
    }

    const result: AuditResult = {
      valid: errors.length === 0,
      audit_status:
        errors.length === 0 ? "PASS" : "FAIL",
      experiment_path: relativePath,
      experiment_id: experimentId,
      model,
      pdk,
      prompt_level: promptLevel,
      final_status: finalStatus,
      errors,
      warnings,
      metrics: {
        api_calls: apiCalls,
        refinement_iterations: refinementIterations,
        max_refinement_iterations:
          maxRefinementIterations,
        llm_runtime_seconds: llmRuntimeSeconds,
        total_runtime_seconds: totalRuntimeSeconds,
      },
      stage_results: {
        netlist_valid: netlistValid,
        gds_generated: gdsGenerated,
        ...stageResults,
      },
      artifact_checks: artifactChecks,
    }

    return JSON.stringify(result, null, 2)
  },
})