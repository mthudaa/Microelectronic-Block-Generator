#!/usr/bin/env python3
"""Preflight report for the MBG local environment.

Run through ``./scripts/setup_env.sh --check``. Kept in Python rather than
shell so that it asks the *same* resolver the pipeline uses — a check that
re-implements tool lookup in shell can pass while the real run picks a
different binary.

Exit status is 0 when every REQUIRED component is usable. Optional
components (KLayout, ngspice) are reported but never fail the run.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mbg import config  # noqa: E402

G, Y, R, C, N, B = "\033[32m", "\033[33m", "\033[31m", "\033[36m", "\033[0m", "\033[1m"
if not sys.stdout.isatty():
    G = Y = R = C = N = B = ""

failures = 0


def row(label, state, detail=""):
    global failures
    colour = {"PASS": G, "WARN": Y, "FAIL": R, "OPTIONAL": C, "MISSING": Y,
              "READY": G, "BLOCKED": R}.get(state, "")
    if state in ("FAIL", "BLOCKED"):
        failures += 1
    print(f"  {label:<22}{colour}{state}{N}  {detail}")


def section(title):
    print(f"\n{B}{title}{N}")


def main() -> int:
    cfg = config.pdk_config()

    section("PDK")
    row("PDK", "PASS" if cfg.pdk else "FAIL", cfg.pdk)
    row("PDK_ROOT", "PASS" if cfg.root.is_dir() else "FAIL", str(cfg.root))
    row("PDKPATH", "PASS" if cfg.path.is_dir() else "FAIL", str(cfg.path))
    std = cfg.path / "libs.ref" / cfg.std_cell_library
    row("standard cells", "PASS" if std.is_dir() else "WARN", cfg.std_cell_library)
    row("Magic techfile", "PASS" if cfg.magic_techfile.is_file() else "FAIL",
        str(cfg.magic_techfile) if not cfg.magic_techfile.is_file() else
        f"requires magic-{'.'.join(map(str, config.required_magic_version(cfg)))}")
    row("Netgen setup", "PASS" if cfg.netgen_setup.is_file() else "FAIL",
        "" if cfg.netgen_setup.is_file() else str(cfg.netgen_setup))

    section("EDA")
    magic = config.resolve_magic(cfg)
    netgen = config.resolve_netgen()
    row("Magic executable", "PASS" if magic.ok else "FAIL", magic.path or "not found")
    row("Magic version", "PASS" if magic.ok else "FAIL",
        magic.version_string or "-")
    row("Netgen executable", "PASS" if netgen.ok else "FAIL", netgen.path or "not found")
    row("Netgen version", "PASS" if netgen.ok else "FAIL",
        netgen.version_string or "-")

    klayout = config.resolve_klayout()
    row("KLayout executable", "PASS" if klayout.ok else "OPTIONAL",
        klayout.path or "not installed (not needed for the GF180 flow)")
    ngspice = config.resolve_ngspice()
    row("ngspice", "PASS" if ngspice.ok else "OPTIONAL",
        ngspice.path or "not installed (needed only for simulation)")

    section("Regression readiness")
    pdk_ok = not cfg.missing()
    row("GDS generation", "READY" if pdk_ok else "BLOCKED",
        "" if pdk_ok else "PDK incomplete")
    row("Magic DRC", "READY" if (pdk_ok and magic.ok) else "BLOCKED", "")
    row("Magic extraction", "READY" if (pdk_ok and magic.ok) else "BLOCKED", "")
    row("Netgen LVS", "READY" if (pdk_ok and magic.ok and netgen.ok) else "BLOCKED",
        "" if netgen.ok else "requires Magic extraction and netgen")

    print()
    if failures:
        print(f"{R}{failures} required component(s) failed.{N}")
        for tool in (magic, netgen):
            if not tool.ok and tool.reason:
                print()
                print(tool.reason)
        if cfg.missing():
            print("\nPDK files not found:")
            for m in cfg.missing():
                print(f"  {m}")
            print("\nInstall with:  ./scripts/setup_env.sh --pdk")
        return 1

    print(f"{G}Environment OK — the GF180 regression can run.{N}")
    for t in (klayout, ngspice):
        if not t.ok:
            for note in t.notes:
                print(f"  note: {t.name}: {note}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
