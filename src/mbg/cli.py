"""Console entry points installed by `pip install mbg`.

    mbg-sync       regenerate the agent adapters from .ai/
    mbg-validate   run the agent-integration checks

Both operate on a repository checkout: they locate the repo by walking up from
the current directory, so they work from anywhere inside a clone. Installing
the package alone does not give you a repository to act on — that is by design,
these are developer commands for this project, not general-purpose tools.
"""

import os
import subprocess
import sys


def _find_repo(start=None):
    """Walk up from `start` (default: cwd) looking for the repository root."""
    d = os.path.abspath(start or os.getcwd())
    for _ in range(10):
        if os.path.isfile(os.path.join(d, ".ai", "manifest.json")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return None


def _run(script_name, argv):
    root = _find_repo()
    if root is None:
        sys.stderr.write(
            "mbg: no repository found — run this from inside a clone of the\n"
            "     Microelectronic Block Generator (looking for .ai/manifest.json)\n")
        return 2
    script = os.path.join(root, "scripts", script_name)
    if not os.path.isfile(script):
        sys.stderr.write(f"mbg: {script} not found\n")
        return 2
    return subprocess.call([sys.executable, script, *argv], cwd=root)


def sync_entry(argv=None):
    return _run("sync_agent_tools.py", list(argv if argv is not None else sys.argv[1:]))


def validate_entry(argv=None):
    return _run("validate_agent_integrations.py",
                list(argv if argv is not None else sys.argv[1:]))


if __name__ == "__main__":
    sys.exit(sync_entry())
