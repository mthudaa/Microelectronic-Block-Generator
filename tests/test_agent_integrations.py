"""Tests for the canonical agent-integration layer (.ai/**) and everything
scripts/sync_agent_tools.py generates from it, cross-checked against
scripts/validate_agent_integrations.py's own check functions.

These are integration/regression tests, not unit tests of internal helpers:
each test either (a) exercises a check function imported directly from
scripts/validate_agent_integrations.py against the real repo tree, or
(b) shells out to sync_agent_tools.py / validate_agent_integrations.py as a
subprocess and asserts on its exit code. Nothing here writes to the repo —
the idempotence test uses `sync_agent_tools.py --check` rather than mutating
the real tree.

Run:  python -m pytest designs/notebooks/chipathon2026-D/tests/test_agent_integrations.py -v
      python designs/notebooks/chipathon2026-D/tests/test_agent_integrations.py   # plain runner
"""
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

# ── repo root discovery (independent of the validator under test) ──────────
#
# Deliberately re-implemented here rather than imported: this test suite
# needs to prove root discovery works from this file's own perspective
# before it can trust anything else, and a bug in the shared implementation
# should not be able to make this bootstrap step silently agree with it.

def _find_repo_root() -> Path:
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
    raise RuntimeError(
        f"could not locate repo root by walking up from {Path(__file__).resolve()}"
    )


ROOT = _find_repo_root()
VALIDATOR_PATH = ROOT / "scripts" / "validate_agent_integrations.py"
SYNC_PATH = ROOT / "scripts" / "sync_agent_tools.py"


def _load_validator_module():
    """Import scripts/validate_agent_integrations.py by file path (it is not
    a package under sys.path by default)."""
    spec = importlib.util.spec_from_file_location("validate_agent_integrations", VALIDATOR_PATH)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod


V = _load_validator_module()


def _fresh_result():
    return V.Result(verbose=False)


# ── Test 1 — repo root discovery from a nested cwd ─────────────────────────

def test_root_discovery_from_nested_cwd():
    nested = Path(__file__).resolve().parent  # .../designs/notebooks/chipathon2026-D/tests
    assert nested != ROOT
    assert str(nested).startswith(str(ROOT))

    original_cwd = os.getcwd()
    try:
        os.chdir(str(nested))
        discovered = V.find_repo_root()
    finally:
        os.chdir(original_cwd)

    assert discovered.resolve() == ROOT.resolve(), (
        f"find_repo_root() from nested cwd {nested} returned {discovered}, expected {ROOT}"
    )


# ── Test 2 — manifest parses and has expected top-level keys ──────────────

def test_manifest_parses_and_has_expected_keys():
    manifest_path = ROOT / ".ai" / "manifest.json"
    assert manifest_path.is_file(), f"{manifest_path} does not exist"

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    required_top_level = ["schema_version", "project", "platforms", "capabilities", "workflows", "index_targets"]
    missing = [k for k in required_top_level if k not in manifest]
    assert not missing, f".ai/manifest.json missing top-level key(s): {missing}"

    for platform in ("opencode", "claude", "codex"):
        assert platform in manifest["platforms"], f"manifest.platforms missing '{platform}'"

    assert isinstance(manifest["capabilities"], dict) and manifest["capabilities"], (
        "manifest.capabilities must be a non-empty dict"
    )
    assert isinstance(manifest["workflows"], dict) and manifest["workflows"], (
        "manifest.workflows must be a non-empty dict"
    )


# ── Test 3 — every canonical skill parses with valid flat frontmatter ─────

def test_every_canonical_skill_parses():
    res = _fresh_result()
    skills = V.check_canonical_skills(ROOT, res)
    assert res.failed == 0, "canonical skill parsing failed:\n" + "\n".join(res.failures)
    assert len(skills) > 0, ".ai/skills/ produced zero parsed skills"
    for name, fm in skills.items():
        assert fm["name"] == name
        assert fm["class"] in V.VALID_SKILL_CLASSES
        assert isinstance(fm["platforms"], list) and fm["platforms"]
        assert set(fm["platforms"]) <= V.VALID_PLATFORMS


# ── Test 4 — every canonical workflow parses with valid flat frontmatter ──

def test_every_canonical_workflow_parses():
    res = _fresh_result()
    workflows = V.check_canonical_workflows(ROOT, res)
    assert res.failed == 0, "canonical workflow parsing failed:\n" + "\n".join(res.failures)
    assert len(workflows) > 0, ".ai/workflows/ produced zero parsed workflows"
    for name, fm in workflows.items():
        assert fm["name"] == name
        assert fm["agent"] in V.VALID_AGENTS
        assert "codex" not in fm["platforms"], (
            f"workflow '{name}' declares platform 'codex', which has no repo-scoped commands support"
        )


# ── Test 5 — platform adapter generation is complete ───────────────────────

def test_adapter_generation_complete():
    manifest = json.loads((ROOT / ".ai" / "manifest.json").read_text(encoding="utf-8"))
    res_skills, res_workflows = _fresh_result(), _fresh_result()
    skills = V.check_canonical_skills(ROOT, res_skills)
    workflows = V.check_canonical_workflows(ROOT, res_workflows)
    assert res_skills.failed == 0 and res_workflows.failed == 0

    res = _fresh_result()
    V.check_adapter_generation(ROOT, manifest, skills, workflows, res)
    assert res.failed == 0, "adapter generation incomplete:\n" + "\n".join(res.failures)


# ── Test 6 — no broken references ──────────────────────────────────────────

def test_no_broken_references():
    manifest = json.loads((ROOT / ".ai" / "manifest.json").read_text(encoding="utf-8"))
    res_skills = _fresh_result()
    skills = V.check_canonical_skills(ROOT, res_skills)
    assert res_skills.failed == 0

    res = _fresh_result()
    V.check_broken_references(ROOT, manifest, skills, res)
    assert res.failed == 0, "broken references found:\n" + "\n".join(res.failures)


# ── Test 7 — capability / platform parity ──────────────────────────────────

def test_capability_parity():
    manifest = json.loads((ROOT / ".ai" / "manifest.json").read_text(encoding="utf-8"))
    res_skills, res_workflows = _fresh_result(), _fresh_result()
    skills = V.check_canonical_skills(ROOT, res_skills)
    workflows = V.check_canonical_workflows(ROOT, res_workflows)
    assert res_skills.failed == 0 and res_workflows.failed == 0

    res = _fresh_result()
    V.check_capability_parity(ROOT, manifest, skills, workflows, res)
    assert res.failed == 0, "capability parity check failed:\n" + "\n".join(res.failures)


# ── Test 8 — no hardcoded personal home directories ────────────────────────

def test_no_hardcoded_home_directories():
    res = _fresh_result()
    V.check_no_absolute_paths(ROOT, res)
    assert res.failed == 0, "hardcoded personal path(s) found:\n" + "\n".join(res.failures)


# ── Test 9 — no phantom APIs (skills must not document core/ symbols that
#             do not actually exist) ───────────────────────────────────────

def test_no_phantom_apis():
    res = _fresh_result()
    V.check_no_phantom_apis(ROOT, res)
    assert res.failed == 0, "phantom API reference(s) found:\n" + "\n".join(res.failures)


# ── Test 10 — sync is deterministic / idempotent, without mutating the tree

def test_sync_is_idempotent():
    assert SYNC_PATH.is_file(), f"{SYNC_PATH} does not exist"

    # Run --check twice. --check never writes, so this is safe against the
    # real tree; two consecutive clean runs is direct evidence that a normal
    # (write) sync run would also produce no further changes on a second
    # pass, i.e. that generation is idempotent.
    for attempt in (1, 2):
        proc = subprocess.run(
            [sys.executable, str(SYNC_PATH), "--check"],
            cwd=str(ROOT), capture_output=True, text=True, timeout=60,
        )
        assert proc.returncode == 0, (
            f"`python3 scripts/sync_agent_tools.py --check` (attempt {attempt}) exited "
            f"{proc.returncode}, expected 0 (adapters stale relative to .ai/).\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )


# ── Test 11 — end-to-end: the validator script itself exits 0 ─────────────

def test_full_validator_script_passes():
    assert VALIDATOR_PATH.is_file(), f"{VALIDATOR_PATH} does not exist"
    proc = subprocess.run(
        [sys.executable, str(VALIDATOR_PATH)],
        cwd=str(ROOT), capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, (
        f"python3 scripts/validate_agent_integrations.py exited {proc.returncode}, expected 0.\n"
        f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
    )


ALL = [
    test_root_discovery_from_nested_cwd,
    test_manifest_parses_and_has_expected_keys,
    test_every_canonical_skill_parses,
    test_every_canonical_workflow_parses,
    test_adapter_generation_complete,
    test_no_broken_references,
    test_capability_parity,
    test_no_hardcoded_home_directories,
    test_no_phantom_apis,
    test_sync_is_idempotent,
    test_full_validator_script_passes,
]

if __name__ == "__main__":
    results = []
    for t in ALL:
        try:
            t()
            print(f"PASS  {t.__name__}")
            results.append(True)
        except AssertionError as e:
            print(f"FAIL  {t.__name__}\n      {e}")
            results.append(False)
        except Exception as e:
            import traceback
            print(f"FAIL  {t.__name__} raised {type(e).__name__}: {e}")
            traceback.print_exc()
            results.append(False)
    print(f"\n=== {sum(results)}/{len(results)} PASS ===")
    sys.exit(0 if all(results) else 1)
