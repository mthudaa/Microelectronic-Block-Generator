---

description: Create a safe MBG OpenCode custom tool using the project authoring standard
agent: build
------------

Create a new OpenCode custom tool for the Microelectronic Block Generator
project.

Requested input:

```text
$ARGUMENTS
```

Interpret the first argument as the tool name. Treat the remaining arguments as
the requested operation or purpose.

## Requirements

1. Load the `mbg-extension-authoring` skill.
2. Require a tool name beginning with `mbg-`.
3. Require lowercase alphanumeric kebab-case.
4. Create the tool at:

```text
.opencode/tools/<tool-name>.ts
```

5. Do not overwrite an existing tool without explicit approval.
6. Use the `tool()` helper from `@opencode-ai/plugin`.
7. Give the tool one clear responsibility.
8. Define a precise description.
9. Define validated arguments with `tool.schema`.
10. Return a structured and readable result.
11. Identify side effects and generated artifacts.
12. Do not invent project APIs or modules that do not exist.

## Path Safety

When accepting a filesystem path:

1. Prefer repository-relative paths.
2. Resolve paths against `context.worktree`.
3. Reject empty paths.
4. Reject absolute paths when repository-relative input is required.
5. Reject parent-directory traversal such as `../`.
6. Reject targets outside the Git worktree.
7. Never read `.env` or credential files.
8. Never include personal absolute filesystem paths.

Recommended pattern:

```typescript
import path from "node:path"

function resolveInsideWorktree(
  worktree: string,
  inputPath: string,
): string {
  const trimmed = inputPath.trim()

  if (!trimmed) {
    throw new Error("Path cannot be empty")
  }

  if (path.isAbsolute(trimmed)) {
    throw new Error("Use a repository-relative path")
  }

  const target = path.resolve(worktree, trimmed)
  const relative = path.relative(worktree, target)

  if (
    relative === "" ||
    relative === ".." ||
    relative.startsWith("../") ||
    path.isAbsolute(relative)
  ) {
    throw new Error("Path must remain inside the Git worktree")
  }

  return target
}
```

## Execution Safety

* Do not construct raw shell commands from untrusted input.
* Prefer argument arrays for subprocess execution.
* Preserve stderr and nonzero exit codes.
* Use a timeout for potentially long operations.
* Require user approval for destructive side effects.
* Do not silently suppress failures.
* Do not automatically stage, commit, or push files.
* Do not claim simulation or verification success without report evidence.

## Required Tool Structure

```typescript
import { tool } from "@opencode-ai/plugin"

export default tool({
  description: "Describe one exact MBG operation.",

  args: {
    inputPath: tool.schema
      .string()
      .describe("Repository-relative input path"),
  },

  async execute(args, context) {
    return JSON.stringify(
      {
        status: "not-implemented",
        worktree: context.worktree,
        inputPath: args.inputPath,
      },
      null,
      2,
    )
  },
})
```

Replace the placeholder implementation with the requested validated operation.

## Validation

After creating the tool:

1. Run `mbg-validate-extension` on the new TypeScript file.
2. Confirm that the file name starts with `mbg-`.
3. Confirm that it imports `tool` from `@opencode-ai/plugin`.
4. Confirm that it defines a description, argument schema, and execute function.
5. Confirm that paths are restricted to `context.worktree`.
6. Run one valid-input test.
7. Run one invalid-input or traversal test.
8. Do not claim completion if validation fails.

## Output Format

```text
Tool:
Owner:
Purpose:
File created:
Arguments:
Side effects:
Permissions:
Validation status:
Errors:
Warnings:
Success test:
Failure test:
Generated artifacts:
Known limitations:
Git status:
```

If no tool name is supplied, stop and request a valid `mbg-` tool name.
