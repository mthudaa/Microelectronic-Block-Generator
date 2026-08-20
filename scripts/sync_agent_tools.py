#!/usr/bin/env python3
"""sync_agent_tools.py — regenerate the OpenCode / Claude Code / Codex agent
adapters and the project index from the canonical sources under .ai/.

Canonical inputs (owned by other sub-agents, read-only here):
    .ai/manifest.json          project metadata, capabilities, workflows, index_targets
    .ai/skills/<name>/SKILL.md flat-frontmatter skill definitions
    .ai/workflows/<name>.md    flat-frontmatter workflow/command definitions

Generated outputs (owned by this script — safe to overwrite/delete):
    .ai/project-index.json
    .opencode/skills/<name>/SKILL.md   .opencode/commands/<name>.md
    .claude/skills/<name>/SKILL.md     .claude/commands/<name>.md
    CLAUDE.md
    plugins/mbg-analog/skills/<name>/SKILL.md
    plugins/mbg-analog/.codex-plugin/plugin.json
    .agents/plugins/marketplace.json

Usage:
    python3 scripts/sync_agent_tools.py [--check] [--verbose]

--check   write nothing; exit 1 if any generated file would change, else 0.
--verbose print unchanged files too, and other diagnostic detail.

Only the Python standard library is used (no PyYAML, no tomllib) so this
runs unmodified under CPython 3.10, 3.12 and 3.14.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REGEN_COMMAND = "python3 scripts/sync_agent_tools.py"

VALID_SKILL_CLASSES = {"READ-ONLY", "GENERATING", "MUTATING", "DESTRUCTIVE"}
VALID_OWNERS = {"huda", "ahmad", "jabir"}
VALID_PLATFORMS = {"opencode", "claude", "codex"}
VALID_AGENTS = {"build", "plan"}

GENERATED_MD_MARKER = "<!-- GENERATED FILE"


class SyncError(Exception):
    """A fatal, precisely-attributable configuration or content error."""


# --------------------------------------------------------------------------
# Repo root discovery
# --------------------------------------------------------------------------

def find_repo_root() -> Path:
    """Locate the repository root without ever hardcoding a path.

    Primary strategy: ask git, using the *process* cwd (so this works when
    invoked from any nested subdirectory). Fallback: walk upward from this
    script's own on-disk location looking for .ai/manifest.json (covers the
    case where git is unavailable).
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

    raise SyncError(
        "could not locate repo root: no .ai/manifest.json found via "
        "`git rev-parse --show-toplevel` or by walking up from "
        f"{Path(__file__).resolve()}"
    )


# --------------------------------------------------------------------------
# Hand-rolled flat-frontmatter parser (no PyYAML / tomllib available)
# --------------------------------------------------------------------------

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)\Z", re.DOTALL)


def parse_frontmatter(text: str, path: Path) -> tuple[dict, str]:
    """Parse a flat `key: value` frontmatter block. List values must be
    written inline as `[a, b]`. Returns (fields, body)."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        raise SyncError(f"{path}: malformed frontmatter (expected '---' ... '---' at file start)")
    fm_block, body = m.group(1), m.group(2)

    data: dict = {}
    for raw in fm_block.split("\n"):
        if not raw.strip():
            continue
        if ":" not in raw:
            raise SyncError(f"{path}: malformed frontmatter line (missing ':'): {raw!r}")
        key, _, val = raw.partition(":")
        key = key.strip()
        val = val.strip()
        if not key:
            raise SyncError(f"{path}: malformed frontmatter line (empty key): {raw!r}")
        if val.startswith("[") and val.endswith("]"):
            inner = val[1:-1].strip()
            items = [tok.strip().strip('"').strip("'") for tok in inner.split(",")] if inner else []
            data[key] = items
        else:
            data[key] = val.strip('"').strip("'")
    return data, body


# --------------------------------------------------------------------------
# Discovery of canonical skills / workflows
# --------------------------------------------------------------------------

def discover_skills(root: Path) -> dict:
    skills_dir = root / ".ai" / "skills"
    skills: dict = {}
    if not skills_dir.is_dir():
        return skills

    for entry in sorted(skills_dir.iterdir()):
        if not entry.is_dir():
            continue
        skill_md = entry / "SKILL.md"
        if not skill_md.is_file():
            raise SyncError(f"{entry}: skill directory has no SKILL.md")

        text = skill_md.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text, skill_md)

        required = ["name", "description", "class", "owner", "capabilities", "platforms"]
        missing = [k for k in required if k not in fm]
        if missing:
            raise SyncError(f"{skill_md}: missing required frontmatter key(s): {missing}")

        if fm["name"] != entry.name:
            raise SyncError(
                f"{skill_md}: frontmatter name '{fm['name']}' does not match "
                f"directory name '{entry.name}'"
            )
        if fm["class"] not in VALID_SKILL_CLASSES:
            raise SyncError(
                f"{skill_md}: invalid class '{fm['class']}' "
                f"(expected one of {sorted(VALID_SKILL_CLASSES)})"
            )
        if fm["owner"] not in VALID_OWNERS:
            raise SyncError(
                f"{skill_md}: invalid owner '{fm['owner']}' (expected one of {sorted(VALID_OWNERS)})"
            )
        if not isinstance(fm["platforms"], list) or not fm["platforms"]:
            raise SyncError(f"{skill_md}: 'platforms' must be a non-empty inline list")
        bad = [p for p in fm["platforms"] if p not in VALID_PLATFORMS]
        if bad:
            raise SyncError(
                f"{skill_md}: unknown platform(s) {bad} (expected subset of {sorted(VALID_PLATFORMS)})"
            )
        if not isinstance(fm["capabilities"], list):
            raise SyncError(f"{skill_md}: 'capabilities' must be an inline list")

        skills[fm["name"]] = {
            "name": fm["name"],
            "description": fm["description"],
            "class": fm["class"],
            "owner": fm["owner"],
            "capabilities": fm["capabilities"],
            "platforms": fm["platforms"],
            "body": body,
            "source": skill_md.relative_to(root).as_posix(),
        }
    return skills


def discover_workflows(root: Path) -> dict:
    wf_dir = root / ".ai" / "workflows"
    workflows: dict = {}
    if not wf_dir.is_dir():
        return workflows

    for entry in sorted(wf_dir.glob("*.md")):
        text = entry.read_text(encoding="utf-8")
        fm, body = parse_frontmatter(text, entry)

        required = ["name", "description", "agent", "platforms"]
        missing = [k for k in required if k not in fm]
        if missing:
            raise SyncError(f"{entry}: missing required frontmatter key(s): {missing}")

        basename = entry.stem
        if fm["name"] != basename:
            raise SyncError(
                f"{entry}: frontmatter name '{fm['name']}' does not match file basename '{basename}'"
            )
        if fm["agent"] not in VALID_AGENTS:
            raise SyncError(
                f"{entry}: invalid agent '{fm['agent']}' (expected one of {sorted(VALID_AGENTS)})"
            )
        if not isinstance(fm["platforms"], list) or not fm["platforms"]:
            raise SyncError(f"{entry}: 'platforms' must be a non-empty inline list")
        if "codex" in fm["platforms"]:
            raise SyncError(
                f"{entry}: workflow targets platform 'codex', which does not support "
                "repo-scoped commands (see platforms.codex.unsupported in the manifest)"
            )
        bad = [p for p in fm["platforms"] if p not in VALID_PLATFORMS]
        if bad:
            raise SyncError(f"{entry}: unknown platform(s) {bad}")

        workflows[fm["name"]] = {
            "name": fm["name"],
            "description": fm["description"],
            "agent": fm["agent"],
            "platforms": fm["platforms"],
            "body": body,
            "source": entry.relative_to(root).as_posix(),
        }
    return workflows


def validate_manifest_refs(manifest: dict, skills: dict) -> None:
    """Cross-check manifest capabilities against discovered skills.

    Deliberately tolerant during bootstrap: if .ai/skills is completely
    empty (Sub-Agent D hasn't produced any canonical skills yet), there is
    nothing meaningful to validate against, so we skip this check rather
    than fail every run. Once at least one skill exists, every capability
    that names a skill must resolve.
    """
    if not skills:
        return
    for cap_id, cap in manifest.get("capabilities", {}).items():
        skill_name = cap.get("skill")
        if skill_name and skill_name not in skills:
            raise SyncError(
                f".ai/manifest.json: capability '{cap_id}' references skill "
                f"'{skill_name}' which does not exist under .ai/skills/"
            )


# --------------------------------------------------------------------------
# Generated-file banners
# --------------------------------------------------------------------------

def md_banner(source_rel: str) -> str:
    return (
        f"{GENERATED_MD_MARKER} — do not edit by hand. "
        f"Source: {source_rel}. Regenerate with: {REGEN_COMMAND} -->"
    )


def json_generated(source_rel: str) -> dict:
    return {
        "generated": True,
        "do_not_edit": True,
        "source": source_rel,
        "command": REGEN_COMMAND,
    }


def is_generated_md(path: Path) -> bool:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return False
    return GENERATED_MD_MARKER in text


def generated_json_targets(root: Path, manifest: dict) -> set:
    """The small, fixed set of JSON files this script generates without a
    `$generated` content marker.

    Codex's plugin ingestion contract (`plugin-creator/scripts/validate_plugin.py`)
    closes the top-level key set of `plugin.json` — an injected `$generated`
    key is rejected as unknown, and by extension we keep `marketplace.json`
    marker-free too since nothing guarantees its schema is any more open.
    Because these two files can't self-identify via content, "is this ours
    to overwrite" is instead an exact-path membership test against paths
    derived straight from the manifest — never a heuristic that could match
    an arbitrary JSON file.
    """
    cx = manifest["platforms"]["codex"]
    return {
        (root / cx["plugin_manifest"]).resolve(),
        (root / cx["marketplace_file"]).resolve(),
    }


def sync_path_generated_json(
    path: Path, content: str, targets: set, stats: "Stats", check: bool, verbose: bool
) -> None:
    """Like sync_file, but only for JSON files whose generated-ness is
    established by PATH membership in `targets` rather than by a `$generated`
    content marker. Refuses to run against anything outside that fixed set,
    so this can never be widened by accident into "overwrite any JSON"."""
    if path.resolve() not in targets:
        raise SyncError(
            f"{path}: refusing to sync as a marker-less generated JSON file "
            "(not one of the known Codex plugin/marketplace targets)"
        )
    sync_file(path, content, stats, check, verbose)


def short_description(text: str, limit: int = 160) -> str:
    """One-line summary for Codex's `metadata.short-description`.

    Prefer the first whole sentence. Only if that is still too long do we
    truncate, and then at a word boundary — cutting mid-word left visible
    fragments like "using the De…" in a field Codex shows in its UI.
    """
    text = " ".join(text.strip().split())
    if not text:
        return text
    idx = text.find(". ")
    if 0 < idx <= limit:
        return text[: idx + 1]
    if len(text) <= limit:
        return text
    clipped = text[:limit]
    cut = clipped.rfind(" ")
    if cut > limit // 2:
        clipped = clipped[:cut]
    return clipped.rstrip(" ,;:—-") + "…"


# --------------------------------------------------------------------------
# Renderers
#
# Design note on banner placement: the spec says every generated Markdown
# file "starts with" the banner comment. For files with no frontmatter
# (CLAUDE.md) that is literal — the banner is the first line. For files
# with YAML-style frontmatter (SKILL.md, command .md) the frontmatter block
# must remain the first bytes of the file or OpenCode/Claude/Codex cannot
# parse `name`/`description` out of it, so the banner is instead the first
# line of the body, immediately after the closing `---`. This is the
# smallest deviation from the literal wording that keeps the generated
# files actually loadable by the tools they target.
# --------------------------------------------------------------------------

def render_opencode_skill(skill: dict) -> str:
    header = "\n".join([
        "---",
        f"name: {skill['name']}",
        f"description: {skill['description']}",
        "license: Apache-2.0",
        "compatibility: opencode",
        "metadata:",
        f"  owner: {skill['owner']}",
        "  project: microelectronic-block-generator",
        "  status: experimental",
        "---",
    ])
    body = skill["body"].strip("\n")
    return f"{header}\n{md_banner(skill['source'])}\n\n{body}\n"


def render_claude_skill(skill: dict) -> str:
    header = "\n".join([
        "---",
        f"name: {skill['name']}",
        f"description: {skill['description']}",
        "---",
    ])
    body = skill["body"].strip("\n")
    return f"{header}\n{md_banner(skill['source'])}\n\n{body}\n"


def render_codex_skill(skill: dict) -> str:
    header = "\n".join([
        "---",
        f"name: {skill['name']}",
        f"description: {skill['description']}",
        "metadata:",
        f"  short-description: {short_description(skill['description'])}",
        "---",
    ])
    body = skill["body"].strip("\n")
    return f"{header}\n{md_banner(skill['source'])}\n\n{body}\n"


def render_opencode_command(wf: dict) -> str:
    header = "\n".join([
        "---",
        f"description: {wf['description']}",
        f"agent: {wf['agent']}",
        "---",
    ])
    body = wf["body"].strip("\n")
    return f"{header}\n{md_banner(wf['source'])}\n\n{body}\n"


def render_claude_command(wf: dict) -> str:
    header = "\n".join([
        "---",
        f"description: {wf['description']}",
        "---",
    ])
    body = wf["body"].strip("\n")
    return f"{header}\n{md_banner(wf['source'])}\n\n{body}\n"


def render_claude_md(manifest: dict, skills: dict, workflows: dict) -> str:
    proj = manifest["project"]
    lines = [
        md_banner(".ai/manifest.json, .ai/skills/**, .ai/workflows/** (via scripts/sync_agent_tools.py)"),
        "",
        "@AGENTS.md",
        "",
        f"## Claude Code Adapter for {proj['name']}",
        "",
        "This section is generated. Shared project rules live in AGENTS.md above"
        " (Claude Code does not read AGENTS.md natively, hence the `@AGENTS.md`"
        " import); this section adds the Claude-Code-specific inventory of"
        " generated skills and commands.",
        "",
        "### Generated skills (`.claude/skills/`)",
        "",
    ]
    claude_skills = sorted(n for n, s in skills.items() if "claude" in s["platforms"])
    if claude_skills:
        lines += [f"- `{n}` — {skills[n]['description']}" for n in claude_skills]
    else:
        lines.append(
            "_None yet — run `python3 scripts/sync_agent_tools.py` after adding "
            "skills under `.ai/skills/`._"
        )
    lines += ["", "### Generated commands (`.claude/commands/`)", ""]
    claude_wf = sorted(n for n, w in workflows.items() if "claude" in w["platforms"])
    if claude_wf:
        lines += [f"- `/{n}` — {workflows[n]['description']}" for n in claude_wf]
    else:
        lines.append(
            "_None yet — run `python3 scripts/sync_agent_tools.py` after adding "
            "workflows under `.ai/workflows/`._"
        )
    lines += [
        "",
        "### Keeping this in sync",
        "",
        "```bash",
        f"{REGEN_COMMAND}          # regenerate adapters + project index",
        f"{REGEN_COMMAND} --check  # CI: fail if adapters are stale",
        "python3 scripts/validate_agent_integrations.py  # validate the result",
        "./scripts/install_agents.sh                     # setup / refresh Codex",
        "```",
        "",
    ]
    return "\n".join(lines) + "\n"


def render_plugin_json(manifest: dict, skills: dict) -> str:
    # NOTE: no "$generated" key here — Codex's plugin.json schema is closed
    # (validate_plugin.py rejects any top-level key outside its allow-list),
    # so the generated-provenance note lives in the sibling GENERATED.md
    # instead. See generated_json_targets()/sync_path_generated_json().
    proj = manifest["project"]
    codex_skill_count = sum(1 for s in skills.values() if "codex" in s["platforms"])
    doc = {
        "name": "mbg-analog",
        "version": "0.1.0",
        "description": (
            f"{proj['name']} analog IC design skills "
            f"({proj['framework']}, {proj['pdk']} PDK)."
        ),
        "author": {"name": f"{proj['name']} Team"},
        "skills": "./skills/",
        "interface": {
            "displayName": proj["name"],
            "shortDescription": (
                f"Analog IC design skills for {proj['name']} ({codex_skill_count} skills)."
            ),
            "longDescription": (
                f"{proj['name']} packages SPICE-to-GDS layout generation, placement and "
                f"routing debugging, DRC/LVS/PEX verification, and design-regression "
                f"skills for the {proj['framework']} analog IC flow on the {proj['pdk']} PDK."
            ),
            "developerName": f"{proj['name']} Team",
            "category": "Developer Tools",
            "capabilities": [],
            "defaultPrompt": (
                "Help me design, verify, and review analog IC blocks in this "
                "repository using the MBG skills."
            ),
        },
    }
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def render_marketplace_json(manifest: dict) -> str:
    # NOTE: no "$generated" key here either — kept marker-free to match
    # plugin.json's closed-schema treatment; see render_plugin_json().
    codex_cfg = manifest["platforms"]["codex"]
    proj = manifest["project"]
    doc = {
        "name": codex_cfg["marketplace_name"],
        "interface": {"displayName": f"{proj['name']} (local)"},
        "plugins": [
            {
                "name": "mbg-analog",
                "source": {"source": "local", "path": "./plugins/mbg-analog"},
                "policy": {"installation": "AVAILABLE", "authentication": "ON_INSTALL"},
                "category": "Developer Tools",
            }
        ],
    }
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


def render_codex_generated_marker() -> str:
    """Provenance note living next to plugin.json, since plugin.json itself
    can't carry a `$generated` key (Codex's schema is closed)."""
    lines = [
        md_banner(
            "plugins/mbg-analog/.codex-plugin/plugin.json and "
            ".agents/plugins/marketplace.json (see .ai/manifest.json)"
        ),
        "",
        "# Generated Codex plugin files",
        "",
        "`plugin.json` in this directory, and `../../../.agents/plugins/marketplace.json`,",
        "are generated from `.ai/manifest.json` by `python3 scripts/sync_agent_tools.py`.",
        "",
        "They deliberately carry no `$generated` marker key: Codex's plugin",
        "ingestion validator (`plugin-creator/scripts/validate_plugin.py`) rejects",
        "any top-level `plugin.json` key outside its fixed allow-list, so an",
        "injected marker fails validation. This file exists only to record that",
        "provenance for humans; the sync script itself identifies both files by",
        "their fixed path, not by content.",
        "",
        "Do not edit `plugin.json` or `marketplace.json` by hand — edit",
        "`.ai/manifest.json` and re-run the sync command instead.",
        "",
    ]
    return "\n".join(lines) + "\n"


# --------------------------------------------------------------------------
# Project index
# --------------------------------------------------------------------------

def _file_entry(root: Path, path: Path) -> dict:
    entry = {"path": path.relative_to(root).as_posix()}
    if path.suffix == ".py":
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return entry
        entry["lines"] = text.count("\n") + (1 if text and not text.endswith("\n") else 0)
    return entry


def build_project_index(root: Path, manifest: dict) -> dict:
    targets_spec = manifest.get("index_targets", {})
    result: dict = {}
    for tid in sorted(targets_spec):
        spec = targets_spec[tid]
        target_root = root / spec["root"]
        entries: list = []
        if target_root.is_dir():
            if spec.get("dirs_only"):
                for child in target_root.iterdir():
                    if child.is_dir() and not child.name.startswith("."):
                        entries.append({"path": child.relative_to(root).as_posix()})
            elif "glob" in spec:
                for child in target_root.glob(spec["glob"]):
                    if child.is_file():
                        entries.append(_file_entry(root, child))
            elif "match" in spec:
                stems = set(spec["match"])
                for child in target_root.iterdir():
                    if child.is_file() and child.stem in stems:
                        entries.append(_file_entry(root, child))
            else:
                raise SyncError(
                    f".ai/manifest.json: index_target '{tid}' has none of "
                    "glob, match, dirs_only"
                )
        entries.sort(key=lambda e: e["path"])
        result[tid] = entries
    return result


def render_project_index(root: Path, manifest: dict) -> str:
    doc = {
        "$generated": json_generated(".ai/manifest.json#index_targets"),
        "schema_version": 1,
        "project": manifest.get("project", {}).get("slug", ""),
        "targets": build_project_index(root, manifest),
    }
    return json.dumps(doc, indent=2, sort_keys=True) + "\n"


# --------------------------------------------------------------------------
# Write / change-detection / pruning
# --------------------------------------------------------------------------

class Stats:
    def __init__(self) -> None:
        self.created = 0
        self.updated = 0
        self.unchanged = 0
        self.removed = 0
        self.would_change: list = []


def sync_file(path: Path, content: str, stats: Stats, check: bool, verbose: bool) -> None:
    exists = path.is_file()
    old = path.read_text(encoding="utf-8") if exists else None
    if old == content:
        stats.unchanged += 1
        if verbose:
            print(f"  unchanged  {path}")
        return

    if check:
        stats.would_change.append(str(path))
        print(f"  WOULD {'UPDATE' if exists else 'CREATE'}  {path}")
        return

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    if exists:
        stats.updated += 1
        print(f"  updated    {path}")
    else:
        stats.created += 1
        print(f"  created    {path}")


def prune_stale(
    dir_path: Path,
    expected_names: set,
    stats: Stats,
    check: bool,
    verbose: bool,
    is_dir_based: bool,
) -> None:
    if not dir_path.is_dir():
        return
    for child in sorted(dir_path.iterdir()):
        if is_dir_based:
            if not child.is_dir():
                continue
            name = child.name
        else:
            if not child.is_file() or child.suffix != ".md":
                continue
            name = child.stem

        if name in expected_names:
            continue

        if is_dir_based:
            marker_file = child / "SKILL.md"
            generated = marker_file.is_file() and is_generated_md(marker_file)
        else:
            generated = is_generated_md(child)

        if not generated:
            if verbose:
                print(f"  skip stale hand-written file: {child}")
            continue

        if check:
            stats.would_change.append(f"REMOVE {child}")
            print(f"  WOULD REMOVE (stale)  {child}")
            continue

        if is_dir_based:
            shutil.rmtree(child)
        else:
            child.unlink()
        stats.removed += 1
        print(f"  removed    {child}")


def sync_json_file(path: Path, content: str, stats: Stats, check: bool, verbose: bool) -> None:
    # JSON generated files use the same write path as markdown; kept as a
    # separate name only for readability at call sites.
    sync_file(path, content, stats, check, verbose)


# --------------------------------------------------------------------------
# Main
# --------------------------------------------------------------------------

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate OpenCode/Claude/Codex agent adapters and the project index "
                     "from .ai/manifest.json, .ai/skills/, .ai/workflows/."
    )
    parser.add_argument("--check", action="store_true", help="write nothing; exit 1 if stale")
    parser.add_argument("--verbose", action="store_true", help="print unchanged files too")
    args = parser.parse_args(argv)

    try:
        root = find_repo_root()
        manifest_path = root / ".ai" / "manifest.json"
        if not manifest_path.is_file():
            raise SyncError(f"manifest not found at {manifest_path}")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as e:
            raise SyncError(f"{manifest_path}: invalid JSON: {e}")

        skills = discover_skills(root)
        workflows = discover_workflows(root)
        validate_manifest_refs(manifest, skills)

        print(f"repo root: {root}")
        print(f"canonical skills found: {len(skills)}" + ("" if skills else "  (none yet)"))
        print(f"canonical workflows found: {len(workflows)}" + ("" if workflows else "  (none yet)"))

        stats = Stats()
        plat = manifest["platforms"]

        # 1. project index
        sync_json_file(
            root / ".ai" / "project-index.json",
            render_project_index(root, manifest),
            stats, args.check, args.verbose,
        )

        # 2. OpenCode adapter
        oc = plat["opencode"]
        oc_skill_names = {n for n, s in skills.items() if "opencode" in s["platforms"]}
        for name in sorted(oc_skill_names):
            sync_file(
                root / oc["skills_dir"] / name / oc["skill_file"],
                render_opencode_skill(skills[name]), stats, args.check, args.verbose,
            )
        oc_cmd_names = {n for n, w in workflows.items() if "opencode" in w["platforms"]}
        for name in sorted(oc_cmd_names):
            sync_file(
                root / oc["commands_dir"] / f"{name}.md",
                render_opencode_command(workflows[name]), stats, args.check, args.verbose,
            )
        prune_stale(root / oc["skills_dir"], oc_skill_names, stats, args.check, args.verbose, True)
        prune_stale(root / oc["commands_dir"], oc_cmd_names, stats, args.check, args.verbose, False)

        # 3. Claude Code adapter
        cl = plat["claude"]
        cl_skill_names = {n for n, s in skills.items() if "claude" in s["platforms"]}
        for name in sorted(cl_skill_names):
            sync_file(
                root / cl["skills_dir"] / name / cl["skill_file"],
                render_claude_skill(skills[name]), stats, args.check, args.verbose,
            )
        cl_cmd_names = {n for n, w in workflows.items() if "claude" in w["platforms"]}
        for name in sorted(cl_cmd_names):
            sync_file(
                root / cl["commands_dir"] / f"{name}.md",
                render_claude_command(workflows[name]), stats, args.check, args.verbose,
            )
        prune_stale(root / cl["skills_dir"], cl_skill_names, stats, args.check, args.verbose, True)
        prune_stale(root / cl["commands_dir"], cl_cmd_names, stats, args.check, args.verbose, False)

        sync_file(root / "CLAUDE.md", render_claude_md(manifest, skills, workflows), stats, args.check, args.verbose)

        # 4. Codex adapter (no repo-scoped commands)
        cx = plat["codex"]
        cx_skill_names = {n for n, s in skills.items() if "codex" in s["platforms"]}
        for name in sorted(cx_skill_names):
            sync_file(
                root / cx["skills_dir"] / name / cx["skill_file"],
                render_codex_skill(skills[name]), stats, args.check, args.verbose,
            )
        prune_stale(root / cx["skills_dir"], cx_skill_names, stats, args.check, args.verbose, True)

        json_targets = generated_json_targets(root, manifest)
        sync_path_generated_json(
            root / cx["plugin_manifest"], render_plugin_json(manifest, skills),
            json_targets, stats, args.check, args.verbose,
        )
        sync_path_generated_json(
            root / cx["marketplace_file"], render_marketplace_json(manifest),
            json_targets, stats, args.check, args.verbose,
        )
        sync_file(
            (root / cx["plugin_manifest"]).parent / "GENERATED.md",
            render_codex_generated_marker(), stats, args.check, args.verbose,
        )

        print(
            f"\ncreated={stats.created} updated={stats.updated} "
            f"unchanged={stats.unchanged} removed={stats.removed}"
        )

        if args.check:
            if stats.would_change:
                print(f"\n--check: {len(stats.would_change)} file(s) would change")
                return 1
            print("\n--check: up to date")
            return 0
        return 0

    except SyncError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
