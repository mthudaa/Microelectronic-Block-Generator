---
description: Create or repair the Python environment, EDA tools and shell integration for this repository, and report exactly what is installed, what is missing, and what the PDK looks like.
agent: build
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/workflows/mbg-setup-env.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

Set up or diagnose the environment.

```bash
./install.sh --check           # report only, change nothing
./install.sh --stage python    # .venv + pinned dependencies + pip install -e .
./install.sh --stage eda       # Magic, netgen, KLayout — only what is missing
./install.sh --stage shell     # $MBG_HOME/activate.sh + the mbg launchers
```

Report the sections the script prints — Python environment, PDK, EDA toolchain,
shell integration — without softening anything it marks as missing.

## Where things land

| Variable | Default | Holds |
| :--- | :--- | :--- |
| `MBG_VENV` | `<repo>/.venv` | the Python environment |
| `MBG_TOOLS_ROOT` | `$HOME/.local/mbg-tools` | EDA builds |
| `MBG_HOME` | `$HOME/.mbg` | `activate.sh`, `bin/mbg`, `bin/mbg-python` |

After `--stage shell`, a new shell has the environment already. In the current
one, `source scripts/activate_mbg.sh` delegates to `$MBG_HOME/activate.sh`, and
`mbg check` prints the same preflight as `./install.sh --check`.

Tools are pinned by **absolute path** in `MBG_MAGIC`, `MBG_NETGEN`,
`MBG_KLAYOUT` and `MBG_NGSPICE` rather than left to `PATH` order — several
distributions ship no `klayout` package, so a `PATH`-only setup silently loses
DRC sign-off. Any value the user already exported wins.

## Version constraints that matter

These upper bounds are load-bearing, not caution:

- **gdsfactory `>=7.7,<8`** — version 8 moved to a kfactory backend and drops
  `Component.references`, `ref.get_polygons(by_spec=True)` and
  `gf.Port(center=...)`, all of which this code uses.
- **numpy `>=1.24,<2`** — numpy 2 removed `np.float_`, which gdsfactory 7 still
  expects.
- **Python 3.10–3.12** — neither of the above has wheels for 3.13+.

If someone reports an import error mentioning `references`, `get_polygons` or
`float_`, check the installed versions first — it is almost always one of these.

## What this does and does not install

`--stage eda` **does** build Magic, netgen and KLayout into `$MBG_TOOLS_ROOT`,
and reuses whatever already works: if a compatible tool is present it is
adopted, not rebuilt. `--stage pdk` installs GF180MCU with volare. None of this
needs Docker or root.

It does **not** install OS build prerequisites silently. Building from source
needs a C toolchain, Tcl/Tk, Cairo and X11 headers; `./install.sh --deps`
prints the exact package list for the detected distribution and
`--deps --yes` installs it. That is the only step that asks for sudo.

Inside the IIC-OSIC-TOOLS container the EDA tools and the PDK are already
present, and the script detects and reuses them rather than building anything.
