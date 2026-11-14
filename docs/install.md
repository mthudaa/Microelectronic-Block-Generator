# Installation and reproducibility

Use Python 3.11 and the supplied requirements-lock.txt. `./install.sh --stage
python` creates the project environment and installs its locked dependencies.
A locked dependency failure stops installation; it never falls back to floating
versions. Record the interpreter, OS and tool versions with run evidence.
`MBG_LOCKED=0` explicitly opts into a flexible dependency solve.

Inspect first with `./install.sh --list` and `./install.sh --check`. These checks
must not install tools. Reuse compatible native tools or a user-managed container.
Run container commands only after confirming the environment. The helper scripts
used by public physical verification live under scripts/eda.

For PDK installation, select a reviewed upstream revision explicitly:

```bash
MBG_VOLARE_VERSION=<reviewed-volare-version> MBG_PDK_VERSION=<reviewed-volare-revision> ./install.sh --stage pdk
./install.sh --stage eda
./install.sh --stage shell
./install.sh --stage agents
```

Magic and netgen builds use the selected version tags and fail if those revisions
cannot be fetched. Keep downloaded PDKs outside this Git tree and comply with
their licenses. Use MBG_VENV, MBG_TOOLS_ROOT and MBG_HOME to select installation
locations. Never delete an existing environment automatically to repair it.

Offline validation, without fetching packages or running physical tools:

```bash
bash -n install.sh
python3 scripts/sync_agent_tools.py --check
python3 scripts/validate_agent_integrations.py
python3 -m pytest tests/test_public_setup.py -q
```

Fresh installation and EDA results must be reported only after they are actually
executed in the intended environment. A passing static check proves neither.

The shell stage uses `MBG_HOME` (default `~/.mbg`) for activation and launchers.
After installing it, use `mbg check` to inspect the environment. From a checkout,
`scripts/mbg doctor` provides the same public environment report.

KLayout is optional for the public Magic-based checks. Set
`MBG_INSTALL_KLAYOUT=1` explicitly when adopting/installing it. Install ngspice
for circuit simulation; `./install.sh --deps` prints platform prerequisites.
