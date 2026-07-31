---

description: Review an MBG OpenCode extension against project authoring and safety rules
agent: plan
-----------

Review the following Microelectronic Block Generator OpenCode extension:

```text
$1
```

## Required Workflow

1. Load the `mbg-extension-authoring` skill.
2. Confirm that the provided path:

   * Is repository-relative.
   * Is located under `.opencode/`.
   * Does not contain parent-directory traversal.
3. Run the `mbg-validate-extension` tool on the file.
4. Review the extension for:

   * One clear responsibility.
   * Correct `mbg-` naming.
   * Correct owner and dependencies.
   * Documented inputs and outputs.
   * Minimum required permissions.
   * Safe filesystem handling.
   * Secret and API-key protection.
   * Explicit failure behavior.
   * One success test.
   * One failure test.
5. Report errors before warnings.
6. Reference the exact file and rule for every finding.
7. Do not modify the reviewed file.
8. Do not stage, commit, or push changes.

## ⚠️ PDK Body Constraint

**MOSFET body: pfet_03v3→VDD ONLY, nfet_03v3→VSS ONLY.** Extensions that
generate or process SPICE must enforce this rule.

## Output Format

```text
Extension:
Type:
Validation status:
Errors:
Warnings:
Owner:
Dependencies:
Security findings:
Required corrections:
Recommended next action:
```

If no path is supplied, stop and request a repository-relative path under
`.opencode/`.
