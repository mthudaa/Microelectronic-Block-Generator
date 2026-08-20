#!/usr/bin/env python3
"""Execute every notebook under tests/notebooks/ and assert it runs clean.

A notebook that is never executed rots silently, so this runs each one in a
throwaway working directory and fails on the first cell error.

Run:  python tests/test_notebooks.py
      python tests/test_notebooks.py --list
"""

import os
import sys
import tempfile
import unittest

NB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "notebooks")


def _repo_root():
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        if os.path.isdir(os.path.join(d, "src", "mbg")):
            return d
        d = os.path.dirname(d)
    raise RuntimeError("could not locate the repository root")


def notebooks():
    if not os.path.isdir(NB_DIR):
        return []
    return sorted(os.path.join(NB_DIR, f) for f in os.listdir(NB_DIR)
                  if f.endswith(".ipynb") and ".ipynb_checkpoints" not in f)


def run_notebook(path, timeout=1200):
    """Execute one notebook; return (ok, message)."""
    try:
        import nbformat
        from nbclient import NotebookClient
        from nbclient.exceptions import CellExecutionError
    except ImportError as e:                       # optional dependency
        return None, f"skipped — {e}"

    nb = nbformat.read(path, as_version=4)
    root = _repo_root()
    outdir = os.path.join(root, "outputs", "notebooks")
    os.makedirs(outdir, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=outdir) as wd:
        env = dict(os.environ)
        env.setdefault("PDK_ROOT", os.path.expanduser("~/.volare"))
        env.setdefault("PDK", "gf180mcuD")
        env.setdefault("PDKPATH", os.path.join(env["PDK_ROOT"], env["PDK"]))
        client = NotebookClient(nb, timeout=timeout, kernel_name="python3",
                                resources={"metadata": {"path": wd}})
        try:
            client.execute()
        except CellExecutionError as e:
            return False, str(e)[:400]
        except Exception as e:
            return False, f"{type(e).__name__}: {str(e)[:400]}"

    for cell in nb.cells:
        for out in cell.get("outputs", []):
            if out.get("output_type") == "error":
                return False, f"{out['ename']}: {out['evalue']}"
    return True, "ok"


class NotebookTests(unittest.TestCase):
    def test_notebooks_execute(self):
        found = notebooks()
        self.assertTrue(found, f"no notebooks found under {NB_DIR}")
        for path in found:
            with self.subTest(notebook=os.path.basename(path)):
                ok, msg = run_notebook(path)
                if ok is None:
                    self.skipTest(msg)
                self.assertTrue(ok, f"{os.path.basename(path)}: {msg}")


def main():
    found = notebooks()
    if "--list" in sys.argv:
        for p in found:
            print(" ", os.path.relpath(p, _repo_root()))
        return 0
    if not found:
        print("no notebooks found"); return 1
    failures = 0
    for path in found:
        name = os.path.basename(path)
        print(f"--- {name} ---", flush=True)
        ok, msg = run_notebook(path)
        if ok is None:
            print(f"SKIP  {name}: {msg}")
        elif ok:
            print(f"PASS  {name}")
        else:
            print(f"FAIL  {name}: {msg}"); failures += 1
    print(f"\n=== {len(found) - failures}/{len(found)} notebooks pass ===")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
