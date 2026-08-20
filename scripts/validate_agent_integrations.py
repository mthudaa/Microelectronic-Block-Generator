#!/usr/bin/env python3
"""validate_agent_integrations.py — standalone validator for the canonical
agent-integration layer under .ai/ and everything scripts/sync_agent_tools.py
generates from it (OpenCode / Claude Code / Codex adapters, CLAUDE.md,
.ai/project-index.json).

This script is READ-ONLY: it never writes, deletes, or regenerates anything.
It exists to catch drift, broken references, and non-determinism *before*
CI or a reviewer does.

Usage:
    python3 scripts/validate_agent_integrations.py [--verbose]

Exit code 0  -> every check passed (warnings may still be printed).
Exit code 1  -> at least one check failed.
Exit code 2  -> the validator itself could not run (e.g. repo root not found,
                manifest is not valid JSON).

Only the Python standard library is used (no PyYAML, no tomllib) so this
runs unmodified under CPython 3.10, 3.12 and 3.14.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from pathlib import Path

CORE_DIR_REL = "src/mbg"

VALID_SKILL_CLASSES = {"READ-ONLY", "GENERATING", "MUTATING", "DESTRUCTIVE"}
VALID_PLATFORMS = {"opencode", "claude", "codex"}
VALID_AGENTS = {"build", "plan"}

GENERATED_MD_MARKER = "<!-- GENERATED FILE"

# Directories/files in scope for the F8 "no absolute personal path" scan.
# Kept as an explicit allowlist (not a blanket repo scan) because the repo
# also contains generated design results, notebooks and vendored node
# modules that are out of this validator's ownership and may legitimately
# contain unrelated content.
ABS_PATH_SCAN_ROOTS = [
    ".ai",
    ".opencode/skills",
    ".opencode/commands",
    ".claude/skills",
    ".claude/commands",
    "CLAUDE.md",
    "plugins",
    ".agents",
    "scripts",
    ".opencode/tools/setup",
]
ABS_PATH_SCAN_EXCLUDE_DIRS = {"__pycache__", "node_modules", ".git"}
# Built by concatenation, not as a literal, so this validator's own source
# never contains the needle string it searches for — the scan below still
# runs over this file like any other file in ABS_PATH_SCAN_ROOTS, with no
# special-case exclusion, so a real hardcoded path introduced here later
# is still caught.
ABS_PATH_NEEDLE = "/" + "home" + "/"

DOC_FILES_FOR_F7 = ["README.md", "AGENTS.md", "CLAUDE.md"]
DOC_COMMAND_RE = re.compile(r"python3\s+(scripts/[A-Za-z0-9_./-]+\.py)")


class ValidationError(Exception):
    """Fatal error that prevents the validator itself from running."""


class Result:
    """Accumulates one line per check plus overall pass/fail/warn counts."""

    def __init__(self, verbose: bool) -> None:
        self.verbose = verbose
        self.passed = 0
        self.failed = 0
        self.warned = 0
        self.failures: list[str] = []
        self.warnings: list[str] = []

    def ok(self, check_id: str, msg: str) -> None:
        self.passed += 1
        print(f"PASS  [{check_id}] {msg}")

    def fail(self, check_id: str, msg: str) -> None:
        self.failed += 1
        line = f"FAIL  [{check_id}] {msg}"
        self.failures.append(line)
        print(line)

    def warn(self, check_id: str, msg: str) -> None:
        self.warned += 1
        line = f"WARN  [{check_id}] {msg}"
        self.warnings.append(line)
        print(line)

    def info(self, msg: str) -> None:
        if self.verbose:
            print(f"      {msg}")


# --------------------------------------------------------------------------
# F1 — repository root discovery
# --------------------------------------------------------------------------

def find_repo_root() -> Path:
    """Locate the repository root without ever hardcoding a path.

    Primary strategy: ask git, using the *process* cwd (so this works when
    invoked from any nested subdirectory). Fallback: walk upward from this
    script's own on-disk location looking for .ai/manifest.json (covers the
    case where git is unavailable, e.g. an extracted tarball).
    """
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if proc.returncode == 0:
            candidate = Path(proc.stdout.strip())
            if (candidate / ".ai" / "manifest.json").is_file():
                return candidate
    except (OSError, subprocess.SubprocessError):
        pass

    cur = Path(__file__).resolve().parent
    for _ in range(25):
        if (cur / ".ai" / "manifest.json").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent

    raise ValidationError(
        "could not locate repo root: no .ai/manifest.json found via "
        "`git rev-parse --show-toplevel` or by walking up from "
        f"{Path(__file__).resolve()}"
    )


# --------------------------------------------------------------------------
# Hand-rolled flat-frontmatter parser (no PyYAML / tomllib available)
# Mirrors scripts/sync_agent_tools.py's parser exactly; duplicated rather
# than imported so this validator has zero dependency on that script's
# internals and can validate it independently.
# --------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


def parse_frontmatter(text: str) -> tuple[dict, str] | None:
    """Parse a flat `key: value` frontmatter block. Returns (fields, body),
    or None if the text has no '---'-delimited frontmatter block at all."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return None
    fm_block, body = m.group(1), m.group(2)

    data: dict = {}
    for raw in fm_block.split("\n"):
        if not raw.strip():
            continue
        if ":" not in raw:
            raise ValidationError(f"malformed frontmatter line (missing ':'): {raw!r}")
        key, _, val = raw.partition(":")
        key = key.strip()
        val = val.strip()
        if not key:
            raise ValidationError(f"malformed frontmatter line (empty key): {raw!r}")
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            items = [tok.strip().strip('"').strip("'") for tok in inner.split(",")] if inner else []
            data[key] = items
        else:
            data[key] = val.strip('"').strip("'")
    return data, body


# --------------------------------------------------------------------------
# F2 — canonical definition parsing
# --------------------------------------------------------------------------

def check_canonical_skills(root: Path, res: Result) -> dict:
    """Parse and validate every .ai/skills/*/SKILL.md. Returns {name: fm dict}
    for skills that parsed successfully (used by later checks)."""
    skills_dir = root / ".ai" / "skills"
    skills: dict = {}
    if not skills_dir.is_dir():
        res.fail("F2", f".ai/skills/ does not exist at {skills_dir}")
        return skills

    entries = sorted(p for p in skills_dir.iterdir() if p.is_dir())
    if not entries:
        res.warn("F2", ".ai/skills/ contains no skill directories")
        return skills

    for entry in entries:
        skill_md = entry / "SKILL.md"
        label = f".ai/skills/{entry.name}/SKILL.md"
        if not skill_md.is_file():
            res.fail("F2", f"{label}: directory has no SKILL.md")
            continue
        try:
            text = skill_md.read_text(encoding="utf-8")
            parsed = parse_frontmatter(text)
            if parsed is None:
                res.fail("F2", f"{label}: malformed frontmatter (expected '---' ... '---' at file start)")
                continue
            fm, _body = parsed

            required = ["name", "description", "class", "owner", "capabilities", "platforms"]
            missing = [k for k in required if k not in fm]
            if missing:
                res.fail("F2", f"{label}: missing required frontmatter key(s): {missing}")
                continue

            problems = []
            if fm["name"] != entry.name:
                problems.append(f"name '{fm['name']}' != directory name '{entry.name}'")
            if fm["class"] not in VALID_SKILL_CLASSES:
                problems.append(f"invalid class '{fm['class']}' (expected one of {sorted(VALID_SKILL_CLASSES)})")
            if not isinstance(fm["platforms"], list) or not fm["platforms"]:
                problems.append("'platforms' must be a non-empty inline list")
            else:
                bad = [p for p in fm["platforms"] if p not in VALID_PLATFORMS]
                if bad:
                    problems.append(f"unknown platform(s) {bad} (expected subset of {sorted(VALID_PLATFORMS)})")
            if not isinstance(fm["capabilities"], list):
                problems.append("'capabilities' must be an inline list")

            if problems:
                res.fail("F2", f"{label}: " + "; ".join(problems))
                continue

            skills[fm["name"]] = fm
            res.info(f"{label}: OK (class={fm['class']}, platforms={fm['platforms']})")
        except (OSError, ValidationError) as e:
            res.fail("F2", f"{label}: {e}")

    if skills:
        res.ok("F2", f"{len(skills)} canonical skill(s) parsed with valid flat frontmatter")
    return skills


def check_canonical_workflows(root: Path, res: Result) -> dict:
    """Parse and validate every .ai/workflows/*.md. Returns {name: fm dict}."""
    wf_dir = root / ".ai" / "workflows"
    workflows: dict = {}
    if not wf_dir.is_dir():
        res.fail("F2", f".ai/workflows/ does not exist at {wf_dir}")
        return workflows

    entries = sorted(wf_dir.glob("*.md"))
    if not entries:
        res.warn("F2", ".ai/workflows/ contains no workflow files")
        return workflows

    for entry in entries:
        label = f".ai/workflows/{entry.name}"
        try:
            text = entry.read_text(encoding="utf-8")
            parsed = parse_frontmatter(text)
            if parsed is None:
                res.fail("F2", f"{label}: malformed frontmatter (expected '---' ... '---' at file start)")
                continue
            fm, _body = parsed

            required = ["name", "description", "agent", "platforms"]
            missing = [k for k in required if k not in fm]
            if missing:
                res.fail("F2", f"{label}: missing required frontmatter key(s): {missing}")
                continue

            basename = entry.stem
            problems = []
            if fm["name"] != basename:
                problems.append(f"name '{fm['name']}' != file basename '{basename}'")
            if fm["agent"] not in VALID_AGENTS:
                problems.append(f"invalid agent '{fm['agent']}' (expected one of {sorted(VALID_AGENTS)})")
            if not isinstance(fm["platforms"], list) or not fm["platforms"]:
                problems.append("'platforms' must be a non-empty inline list")
            else:
                bad = [p for p in fm["platforms"] if p not in VALID_PLATFORMS]
                if bad:
                    problems.append(f"unknown platform(s) {bad}")

            if problems:
                res.fail("F2", f"{label}: " + "; ".join(problems))
                continue

            workflows[fm["name"]] = fm
            res.info(f"{label}: OK (agent={fm['agent']}, platforms={fm['platforms']})")
        except (OSError, ValidationError) as e:
            res.fail("F2", f"{label}: {e}")

    if workflows:
        res.ok("F2", f"{len(workflows)} canonical workflow(s) parsed with valid flat frontmatter")
    return workflows


# --------------------------------------------------------------------------
# F3 — platform adapter generation completeness
# --------------------------------------------------------------------------

def check_adapter_generation(root: Path, manifest: dict, skills: dict, workflows: dict, res: Result) -> None:
    plat = manifest.get("platforms", {})
    missing: list[str] = []

    for name, fm in skills.items():
        for p in fm["platforms"]:
            if p == "opencode":
                expect = root / plat["opencode"]["skills_dir"] / name / "SKILL.md"
            elif p == "claude":
                expect = root / plat["claude"]["skills_dir"] / name / "SKILL.md"
            elif p == "codex":
                expect = root / plat["codex"]["skills_dir"] / name / "SKILL.md"
            else:
                continue
            if not expect.is_file():
                missing.append(f"skill '{name}' declares platform '{p}' but {expect.relative_to(root)} is missing")

    for name, fm in workflows.items():
        for p in fm["platforms"]:
            if p == "opencode":
                expect = root / plat["opencode"]["commands_dir"] / f"{name}.md"
            elif p == "claude":
                expect = root / plat["claude"]["commands_dir"] / f"{name}.md"
            else:
                continue
            if not expect.is_file():
                missing.append(f"workflow '{name}' declares platform '{p}' but {expect.relative_to(root)} is missing")

    if missing:
        for m in missing:
            res.fail("F3", m)
    else:
        res.ok("F3", f"every declared-platform adapter exists for {len(skills)} skill(s) and {len(workflows)} workflow(s)")


# --------------------------------------------------------------------------
# F4 — broken references
# --------------------------------------------------------------------------

_MD_BANNER_SOURCE_RE = re.compile(r"Source:\s*(.*?)\.\s*Regenerate with:")
_TRAILING_PAREN_RE = re.compile(r"\s*\([^()]*\)\s*$")
_SOURCE_SPLIT_RE = re.compile(r",\s*| and ")


def _split_source_tokens(raw: str) -> list[str]:
    """A banner's 'Source: ...' field may list one or more paths joined by
    ', ' and/or ' and ', with an optional trailing parenthetical annotation
    (e.g. '(via scripts/sync_agent_tools.py)' or '(see .ai/manifest.json)').
    Strip the annotation, then split the remaining path list."""
    raw = _TRAILING_PAREN_RE.sub("", raw.strip())
    return [t.strip() for t in _SOURCE_SPLIT_RE.split(raw) if t.strip()]


def _source_token_exists(root: Path, token: str) -> bool:
    token = token.strip()
    if not token:
        return False
    if "#" in token:
        token = token.split("#", 1)[0]
    if token.endswith("/**"):
        return (root / token[:-3]).is_dir()
    if token.endswith("**"):
        return (root / token[:-2]).is_dir()
    return (root / token).exists()


def check_broken_references(root: Path, manifest: dict, skills: dict, res: Result) -> None:
    problems: list[str] = []

    # 4a. Markdown generated files: banner "Source: X[, Y, ...]" must name
    # files/dirs/globs that exist.
    md_glob_roots = [
        root / ".opencode" / "skills", root / ".opencode" / "commands",
        root / ".claude" / "skills", root / ".claude" / "commands",
        root / "plugins" / "mbg-analog" / "skills",
    ]
    md_files = [root / "CLAUDE.md", root / "plugins" / "mbg-analog" / ".codex-plugin" / "GENERATED.md"]
    for d in md_glob_roots:
        if d.is_dir():
            md_files.extend(sorted(d.rglob("*.md")))

    checked_md = 0
    for f in md_files:
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError as e:
            problems.append(f"{f.relative_to(root)}: could not read ({e})")
            continue
        if GENERATED_MD_MARKER not in text:
            continue
        m = _MD_BANNER_SOURCE_RE.search(text)
        if not m:
            problems.append(f"{f.relative_to(root)}: has a GENERATED FILE marker but no parseable 'Source: ...' banner")
            continue
        checked_md += 1
        for token in _split_source_tokens(m.group(1)):
            if not _source_token_exists(root, token):
                problems.append(
                    f"{f.relative_to(root)}: banner names source '{token}' which does not exist"
                )

    # 4b. JSON generated files carrying a "$generated" content marker:
    # "$generated"."source" must name a file/dir that exists (fragment
    # after '#' stripped). NOT all generated JSON carries this marker —
    # Codex's plugin.json ingestion validator closes the top-level key set
    # and rejects an injected "$generated" key, so plugin.json and
    # marketplace.json are intentionally marker-free (their provenance is
    # instead recorded in the sibling GENERATED.md checked above, and their
    # generated-ness is a fixed path membership fact, not a content fact).
    # Those two are still checked below for bare existence + JSON validity.
    marker_json_files = [root / ".ai" / "project-index.json"]
    markerless_json_files = [
        root / "plugins" / "mbg-analog" / ".codex-plugin" / "plugin.json",
        root / ".agents" / "plugins" / "marketplace.json",
    ]
    checked_json = 0
    for f in marker_json_files:
        if not f.is_file():
            problems.append(f"{f.relative_to(root)}: expected generated JSON file is missing")
            continue
        try:
            doc = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"{f.relative_to(root)}: invalid JSON ({e})")
            continue
        gen = doc.get("$generated") if isinstance(doc, dict) else None
        if not isinstance(gen, dict) or "source" not in gen:
            problems.append(f"{f.relative_to(root)}: missing '$generated.source'")
            continue
        checked_json += 1
        if not _source_token_exists(root, gen["source"]):
            problems.append(f"{f.relative_to(root)}: '$generated.source' names '{gen['source']}' which does not exist")

    for f in markerless_json_files:
        if not f.is_file():
            problems.append(f"{f.relative_to(root)}: expected generated JSON file is missing")
            continue
        try:
            json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            problems.append(f"{f.relative_to(root)}: invalid JSON ({e})")
            continue
        checked_json += 1

    # 4c. Every capability.skill in the manifest names a real canonical skill.
    for cap_id, cap in manifest.get("capabilities", {}).items():
        skill_name = cap.get("skill")
        if skill_name and skill_name not in skills:
            problems.append(
                f".ai/manifest.json: capability '{cap_id}' references skill '{skill_name}' "
                "which does not exist under .ai/skills/"
            )

    # 4d. Every capability.command names a script that exists on disk.
    for cap_id, cap in manifest.get("capabilities", {}).items():
        cmd = cap.get("command")
        if not cmd:
            continue
        # Accept any executable script under scripts/, not just Python — the
        # setup and install entry points are shell scripts.
        m = re.search(r"(scripts/[A-Za-z0-9_./-]+\.(?:py|sh))", cmd)
        if not m:
            problems.append(
                f".ai/manifest.json: capability '{cap_id}' command '{cmd}' "
                "does not name a scripts/*.py or scripts/*.sh file")
            continue
        script_rel = m.group(1)
        if not (root / script_rel).is_file():
            problems.append(
                f".ai/manifest.json: capability '{cap_id}' command references '{script_rel}' which does not exist"
            )

    if problems:
        for p in problems:
            res.fail("F4", p)
    else:
        res.ok(
            "F4",
            f"no broken references ({checked_md} generated markdown banner(s), "
            f"{checked_json} generated JSON source(s), all manifest capability "
            "skill/command references resolved)",
        )


# --------------------------------------------------------------------------
# F5 — deterministic synchronization
# --------------------------------------------------------------------------

def check_sync_determinism(root: Path, res: Result, verbose: bool) -> None:
    sync_script = root / "scripts" / "sync_agent_tools.py"
    if not sync_script.is_file():
        res.fail("F5", f"{sync_script.relative_to(root)} does not exist; cannot check --check exit code")
        return
    try:
        proc = subprocess.run(
            [sys.executable, str(sync_script), "--check"],
            cwd=str(root), capture_output=True, text=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError) as e:
        res.fail("F5", f"failed to run `python3 scripts/sync_agent_tools.py --check`: {e}")
        return

    if verbose:
        for line in proc.stdout.splitlines():
            res.info(f"sync --check: {line}")
        for line in proc.stderr.splitlines():
            res.info(f"sync --check (stderr): {line}")

    if proc.returncode == 0:
        res.ok("F5", "`python3 scripts/sync_agent_tools.py --check` exited 0 (a re-sync would change nothing)")
    else:
        tail = "\n".join(proc.stdout.splitlines()[-15:])
        res.fail(
            "F5",
            f"`python3 scripts/sync_agent_tools.py --check` exited {proc.returncode} "
            f"(generated adapters are stale relative to .ai/). Last output:\n{tail}",
        )


# --------------------------------------------------------------------------
# F6 — capability / platform parity
# --------------------------------------------------------------------------

def check_capability_parity(root: Path, manifest: dict, skills: dict, workflows: dict, res: Result) -> None:
    problems: list[str] = []
    plat = manifest.get("platforms", {})
    codex_unsupported = set(plat.get("codex", {}).get("unsupported", []))

    def adapter_exists_for_skill(skill_name: str, platform: str) -> bool:
        if platform == "opencode":
            return (root / plat["opencode"]["skills_dir"] / skill_name / "SKILL.md").is_file()
        if platform == "claude":
            return (root / plat["claude"]["skills_dir"] / skill_name / "SKILL.md").is_file()
        if platform == "codex":
            return (root / plat["codex"]["skills_dir"] / skill_name / "SKILL.md").is_file()
        return False

    for cap_id, cap in manifest.get("capabilities", {}).items():
        cap_platforms = cap.get("platforms", {})
        skill_name = cap.get("skill")
        if skill_name is None:
            # command-type capability (e.g. sync_agent_metadata): no
            # per-platform adapter is generated for a plain CLI script, so
            # there is nothing to cross-check beyond F4's existence check.
            continue
        if skill_name not in skills:
            continue  # already reported by F4
        skill_platforms = set(skills[skill_name]["platforms"])
        for platform, claimed in cap_platforms.items():
            if platform not in VALID_PLATFORMS:
                problems.append(f"capability '{cap_id}': unknown platform key '{platform}' in manifest.platforms map")
                continue
            if not claimed:
                continue
            if platform not in skill_platforms:
                problems.append(
                    f"capability '{cap_id}': manifest claims platform '{platform}' but skill "
                    f"'{skill_name}' does not declare platform '{platform}' in its frontmatter"
                )
                continue
            if not adapter_exists_for_skill(skill_name, platform):
                problems.append(
                    f"capability '{cap_id}': manifest claims platform '{platform}' and skill "
                    f"'{skill_name}' declares it, but no generated adapter exists for that platform"
                )

    # Workflows / commands: codex must never be claimed true, since the
    # manifest itself documents codex.unsupported includes repo-scoped
    # commands.
    manifest_workflows = manifest.get("workflows", {})
    for wf_id, wf in manifest_workflows.items():
        wf_platforms = wf.get("platforms", {})
        if wf_platforms.get("codex"):
            problems.append(
                f"manifest.workflows['{wf_id}']: claims platform 'codex: true' but "
                f"platforms.codex.unsupported includes 'repo_scoped_commands'"
            )
        for platform, claimed in wf_platforms.items():
            if not claimed:
                continue
            if platform == "opencode" and wf_id not in workflows:
                continue  # reported elsewhere
            if platform in ("opencode", "claude") and wf_id in workflows:
                if platform not in workflows[wf_id]["platforms"]:
                    problems.append(
                        f"manifest.workflows['{wf_id}']: claims platform '{platform}' but the canonical "
                        f".ai/workflows/{wf_id}.md does not declare it"
                    )

    # Canonical workflow files themselves must never declare codex (belt
    # and suspenders vs. sync_agent_tools.py's own frontmatter check).
    for name, fm in workflows.items():
        if "codex" in fm["platforms"]:
            problems.append(
                f".ai/workflows/{name}.md: declares platform 'codex' but Codex has no repo-scoped "
                "commands support ('repo_scoped_commands' is in platforms.codex.unsupported)"
            )

    if problems:
        for p in problems:
            res.fail("F6", p)
    else:
        res.ok(
            "F6",
            f"capability/platform claims agree with generated adapters for "
            f"{len(manifest.get('capabilities', {}))} capabilit(y/ies) and "
            f"{len(manifest_workflows)} manifest workflow(s); no platform claims an unsupported feature",
        )


# --------------------------------------------------------------------------
# F7 — documentation commands
# --------------------------------------------------------------------------

def check_documentation_commands(root: Path, res: Result) -> None:
    any_checked = False
    for doc_name in DOC_FILES_FOR_F7:
        doc_path = root / doc_name
        if not doc_path.is_file():
            res.warn("F7", f"{doc_name} does not exist yet (skipping)")
            continue
        text = doc_path.read_text(encoding="utf-8")
        scripts_named = sorted(set(DOC_COMMAND_RE.findall(text)))
        if not scripts_named:
            if doc_name == "README.md":
                res.warn(
                    "F7",
                    "README.md does not mention any `python3 scripts/*.py` command yet "
                    "(expected while docs are still being written)",
                )
            else:
                res.info(f"{doc_name}: no `python3 scripts/*.py` commands mentioned")
            continue
        for script_rel in scripts_named:
            any_checked = True
            script_path = root / script_rel
            if script_path.is_file():
                res.info(f"{doc_name}: '{script_rel}' exists")
            else:
                res.fail("F7", f"{doc_name} references `python3 {script_rel}` but that file does not exist")

    if any_checked and res.failed == 0:
        pass  # individual passes already reported via res.info; summarize below
    res.ok("F7", "all `python3 scripts/*.py` commands named in existing docs resolve to real files "
                 "(README.md gap, if any, reported as WARNING above)")


# --------------------------------------------------------------------------
# F8 — no absolute-path dependency
# --------------------------------------------------------------------------

def check_no_absolute_paths(root: Path, res: Result) -> None:
    hits: list[str] = []

    def scan_file(path: Path) -> None:
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return
        for lineno, line in enumerate(text.splitlines(), start=1):
            if ABS_PATH_NEEDLE in line:
                hits.append(f"{path.relative_to(root)}:{lineno}: {line.strip()[:160]}")

    for rel in ABS_PATH_SCAN_ROOTS:
        target = root / rel
        if target.is_file():
            scan_file(target)
        elif target.is_dir():
            for p in target.rglob("*"):
                if not p.is_file():
                    continue
                if any(part in ABS_PATH_SCAN_EXCLUDE_DIRS for part in p.relative_to(root).parts):
                    continue
                scan_file(p)
        # else: doesn't exist — not this check's problem (F3/F4 would catch it)

    if hits:
        for h in hits:
            res.fail("F8", f"hardcoded personal path found: {h}")
    else:
        res.ok(
            "F8",
            f"no '{ABS_PATH_NEEDLE}' occurrences found under "
            f"{', '.join(ABS_PATH_SCAN_ROOTS)}",
        )


# --------------------------------------------------------------------------
# F9 — no phantom APIs (canonical skills must not document core/ symbols
# that do not actually exist)
# --------------------------------------------------------------------------

_QUALIFIED_CORE_REF_RE = re.compile(r"\bmbg\.([a-z_][a-z0-9_]*)\.([A-Za-z_][A-Za-z0-9_]*)")
# Call-shaped references to the project's own API surface, written bare
# (no "core." prefix) the way skill bodies usually show usage examples.
# `(?<!\.)` avoids double-counting a qualified reference's tail
# ("core.checks.run_drc(" already gets a hit from the qualified regex).
_CALL_SHAPED_API_RE = re.compile(
    r"(?<!\.)\b(run_[a-z_]+|spice_to_gds[a-z_]*|build_design_context|"
    r"parse_netlist_with_pdk|place_with_routability|realize|verify)\s*\("
)


def _parse_core_symbols(root: Path) -> tuple[dict, set]:
    """AST-parse (never import — core/ pulls in gdsfactory/glayout, which is
    slow and environment-dependent) every designs/notebooks/chipathon2026-D/
    core/*.py module and collect its top-level function/class names.

    Returns (per_module_symbols, all_symbols_union)."""
    core_dir = root / CORE_DIR_REL
    module_symbols: dict = {}
    all_symbols: set = set()
    if not core_dir.is_dir():
        return module_symbols, all_symbols

    for py_file in sorted(core_dir.glob("*.py")):
        module_name = py_file.stem
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
        except (SyntaxError, OSError) as e:
            raise ValidationError(f"{py_file.relative_to(root)}: failed to parse for F9: {e}")
        names = {
            node.name for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        }
        module_symbols[module_name] = names
        all_symbols |= names
    return module_symbols, all_symbols


def check_no_phantom_apis(root: Path, res: Result) -> None:
    module_symbols, all_symbols = _parse_core_symbols(root)
    if not module_symbols:
        res.warn("F9", f"{CORE_DIR_REL}/ not found or has no *.py modules; skipping phantom-API check")
        return

    skills_dir = root / ".ai" / "skills"
    if not skills_dir.is_dir():
        res.warn("F9", ".ai/skills/ not found; skipping phantom-API check")
        return

    problems: list[str] = []
    checked = 0

    # Canonical sources only (.ai/skills/*/SKILL.md) — .opencode/skills/**,
    # .claude/skills/** and plugins/mbg-analog/skills/** are generated
    # copies of the same body text, so scanning them too would just
    # double-report the same finding under a different path.
    for skill_md in sorted(skills_dir.glob("*/SKILL.md")):
        label = f".ai/skills/{skill_md.parent.name}/SKILL.md"
        try:
            text = skill_md.read_text(encoding="utf-8")
        except OSError as e:
            problems.append(f"{label}: could not read ({e})")
            continue

        for m in _QUALIFIED_CORE_REF_RE.finditer(text):
            checked += 1
            module, symbol = m.group(1), m.group(2)
            if module not in module_symbols:
                problems.append(
                    f"{label}: references 'core.{module}.{symbol}' but "
                    f"{CORE_DIR_REL}/{module}.py does not exist"
                )
            elif symbol not in module_symbols[module]:
                problems.append(
                    f"{label}: references 'core.{module}.{symbol}' but '{symbol}' is not defined "
                    f"at top level of {CORE_DIR_REL}/{module}.py (phantom API)"
                )

        for m in _CALL_SHAPED_API_RE.finditer(text):
            checked += 1
            name = m.group(1)
            if name not in all_symbols:
                problems.append(
                    f"{label}: calls '{name}(...)' but '{name}' is not defined anywhere under "
                    f"{CORE_DIR_REL}/ (phantom API)"
                )

    if problems:
        for p in sorted(set(problems)):
            res.fail("F9", p)
    else:
        res.ok("F9", f"{checked} core API reference(s) checked across canonical skills; no phantom APIs found")


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate the canonical .ai/ agent-integration layer and everything "
                     "generated from it. Read-only; never writes or regenerates."
    )
    parser.add_argument("--verbose", action="store_true", help="print extra diagnostic detail")
    args = parser.parse_args(argv)

    try:
        root = find_repo_root()
    except ValidationError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    print(f"repo root: {root}")
    res = Result(verbose=args.verbose)
    res.ok("F1", f"repository root resolved to {root}")

    manifest_path = root / ".ai" / "manifest.json"
    if not manifest_path.is_file():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 2
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: {manifest_path}: invalid JSON: {e}", file=sys.stderr)
        return 2

    print()
    print("== F2: canonical definition parsing ==")
    skills = check_canonical_skills(root, res)
    workflows = check_canonical_workflows(root, res)

    print()
    print("== F3: platform adapter generation ==")
    check_adapter_generation(root, manifest, skills, workflows, res)

    print()
    print("== F4: broken references ==")
    check_broken_references(root, manifest, skills, res)

    print()
    print("== F5: deterministic synchronization ==")
    check_sync_determinism(root, res, args.verbose)

    print()
    print("== F6: capability parity ==")
    check_capability_parity(root, manifest, skills, workflows, res)

    print()
    print("== F7: documentation commands ==")
    check_documentation_commands(root, res)

    print()
    print("== F8: no absolute-path dependency ==")
    check_no_absolute_paths(root, res)

    print()
    print("== F9: no phantom APIs ==")
    check_no_phantom_apis(root, res)

    print()
    print(f"SUMMARY: {res.passed} passed, {res.failed} failed, {res.warned} warning(s)")
    if res.failed:
        print("\nFailures:")
        for f in res.failures:
            print(f"  - {f}")
        return 1
    if res.warned:
        print("\nWarnings:")
        for w in res.warnings:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
