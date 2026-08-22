---
description: Set up this repository for AI-agent use — Python, PDK, EDA tools, the $HOME/.mbg shell integration, then the OpenCode / Claude Code / Codex integrations, repo-scoped or user-wide — and verify the result.
---
<!-- GENERATED FILE — do not edit by hand. Source: .ai/workflows/mbg-install.md. Regenerate with: python3 scripts/sync_agent_tools.py -->

Set up the Microelectronic Block Generator on this machine.

There is **one** installer, `./install.sh`, with six stages. Run it, then
report what it actually said. Do not paraphrase a failure as a success, and
name the stage that failed.

## 1. Install

```bash
./install.sh          # all six stages, in dependency order
./install.sh --list   # show the stages and stop
./install.sh --check  # full preflight, installs nothing
```

| Stage | What it does |
| :--- | :--- |
| `python` | `.venv`, pinned dependencies, `pip install -e .` |
| `pdk` | GF180MCU via volare into `$PDK_ROOT` |
| `eda` | Magic, netgen and KLayout into `$MBG_TOOLS_ROOT` — only what is missing or incompatible |
| `shell` | `$MBG_HOME/activate.sh`, the `mbg` launchers, one `~/.bashrc` line |
| `agents` | repo-scoped `/mbg-*` adapters + the Codex plugin *(optional)* |
| `global` | `/mbg-*` for the whole user account *(optional)* |

Use `--stage <name>` to run one at a time when a fresh machine fails and you
need to know which layer broke. Everything lands in three directories the user
controls — `$MBG_VENV` (`<repo>/.venv`), `$MBG_TOOLS_ROOT`
(`~/.local/mbg-tools`) and `$MBG_HOME` (`~/.mbg`). Nothing is written to
`/usr`, `/usr/local` or the system package database unless `--deps --yes` is
used, which is the only step that asks for sudo.

## 2. Pick up the environment

After the `shell` stage a **new shell already has everything** — that stage
writes `$MBG_HOME/activate.sh` and adds one idempotent block to `~/.bashrc`
(and `~/.zshrc` if present). In the current shell, or inside the clone:

```bash
source scripts/activate_mbg.sh   # delegates to $MBG_HOME/activate.sh
mbg check                        # environment preflight
```

That exports `MBG_HOME`, `MBG_ROOT`, `MBG_VENV`, the four GF180 variables, and
pins Magic, netgen, KLayout and ngspice by **absolute path**. Any value the
user already exported wins.

The virtualenv is deliberately **not** activated — that would change what
`python` means in every unrelated shell. `$MBG_HOME/bin` goes on `PATH`
instead, with `mbg` and `mbg-python` launchers that name MBG's interpreter
explicitly.

## 3. Agent integrations

```bash
./install.sh --stage agents    # works inside this checkout
./install.sh --stage global    # works from any directory, for this user
```

- OpenCode and Claude Code read `.opencode/` and `.claude/` straight from the
  clone, so the repo-scoped layer needs no registration.
- Codex has no repo-scoped skills, so its plugin is registered once per
  machine. That writes to `~/.codex/config.toml` and asks first.
- `global` symlinks `mbg-*` into `~/.claude/` and `~/.config/opencode/`, so a
  `sync_agent_tools.py` run reaches it immediately. Only `mbg-*` entries are
  touched.

## 4. Verify

```bash
./install.sh --check
python3 scripts/validate_agent_integrations.py
python3 tests/test_all_designs.py
```

Report the real output: the validator's PASS/FAIL summary, and how many of the
seven reference designs pass DRC and LVS.

## Troubleshooting

- **No Python 3.10–3.12.** gdsfactory 7 and numpy 1 have no wheels for 3.13+.
  Install a supported interpreter; `install.sh` picks one automatically, or pin
  it with `MBG_PYTHON`.
- **PDK not found.** Run `./install.sh --stage pdk`, or set
  `PDK_ROOT=/foss/pdks` inside the IIC-OSIC-TOOLS container.
- **KLayout missing.** DRC sign-off reports `CONFIGURATION_FAILURE`, never
  PASS. The `klayout` pip package is not sufficient — it ships no executable.
  Point at a real binary with `MBG_KLAYOUT=/path/to/klayout`.
- **`mbg` is not a command.** The `shell` stage has not run, or the shell
  predates it. Run `./install.sh --stage shell` and open a new shell.
- **`/mbg-*` works in the clone but nowhere else.** Run
  `./install.sh --stage global`.
- **A `/mbg-*` command runs stale instructions.** The global install was made
  with `--copy` instead of symlinks; re-run it without `--copy`.
- **Codex still shows old skills.** The plugin is cached at install time;
  re-run `./install.sh --stage agents` to refresh it.
- **Undo one layer.** `--check` and `--uninstall` both accept `--stage`:
  `./install.sh --uninstall --stage global` removes only the `mbg-*` entries.
  `--uninstall` deliberately leaves the venv, PDK and built tools alone.
