# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Tool surface for any AI agent** (`src/mbg/agent/`): one registry of 19
  tools served as the `scripts/mbg` command line (also `python -m mbg` and the
  `mbg` console script) and as a dependency-free stdio MCP server
  (`scripts/mbg mcp`). Every call prints one `mbg.result/1` JSON envelope
  (status PASS/FAIL/PARTIAL/NOT RUN/NOT AVAILABLE, metrics, artifacts,
  issues with hints, suggested next calls); logs go to the run directory;
  long runs become background jobs. Design workspaces under `outputs/<name>/`
  keep `experiment.json` current.
- **Declarative PDK profiles** (`src/mbg/pdks/*.json`, `mbg.pdk_profile`):
  gf180mcuD (default) and sky130A (smoke-verified, MOS-only layout,
  Magic-only DRC). `import mbg` no longer loads gLayout until it is needed.
- **Simulation**: model sections per device kind, temperature and supply
  sweeps, current sources; `mbg.measure` recipes for voltage references and
  amplifiers (`mbg measure vref|ota`).
- **Devices**: gf180 vertical PNPs from the PDK's fixed cells, `ppolyf_u_1k`
  high-resistance poly, native `Q` lines, `bjt` device kind.
- **Placement hints** (rows, order, matching groups, arrays, fixed
  positions) and a text layout view (`mbg layout view`).
- **Static netlist checks** against the PDK catalogue (`mbg netlist check`).
- **Agent-harness integration**: generated `.agents/skills/` (Agent Skills
  standard), MCP configs for Claude Code, Codex, Cursor and Gemini CLI, an
  OpenCode `mcp` entry, a generated tool/skill index in `AGENTS.md`,
  `docs/TOOLS.md` and `docs/ai_interface.md`; skills `mbg-agent-interface`
  and `mbg-voltage-reference`.
- **Two 1.2 V references** designed through the CLI on gf180mcuD (bandgap
  and MOS-only), evidence in `results/claude-code_vref_1v2_{bgr,cmos}/`, and
  both added to the regression set.

### Fixed
- PEX netlists simulated poly resistors and MIM capacitors with Magic's
  scaled geometry read as metres (`.option scale` does not reach subcircuit
  parameters); `checks.run_pex` now writes them in µm.
- sky130 layer lookups matched on GDS layer number alone; access points sat
  outside narrow pins.
- `place()` dropped a device whose build failed instead of reporting it.
- Error messages named the removed `scripts/setup_env.sh`; the installer's
  Magic probe failed a good build when the PDK was not yet installed.
- The LLM netlist prompt contradicted the PDK (1.8 V, `M` prefix); it is now
  generated from the profile.
- OpenCode tools parsed polluted stdout; they now wrap `scripts/mbg`.
- `sync_agent_tools.py --check` (validator F5) failed on gitignored files.

## [v1.0.0] - 2025-07-25

### Added
- **GDS3D Integration**: Complete GDS3D support with gf180mcu process configuration. Added GDS3D alias for easy access
- **Quality of Life Improvements**
  - Active PDK info display in shell prompt
  - Added `/foss/designs/scripts` to system PATH
  - Set xschem netlist directory to `/foss/designs/simulations` so that simulation results are accessible from host machine.
  - The `setup_pdk.sh` script is fully merged into `/foss/designs/.designinit` script. Users don't need to explicitly run it now.
- **KLayout Library Manager**: Python-based library management plugin implemented from sratch. Automatic `.gds` file discoveries, library rebuild and reload. One-click workflow.
  - `klayout_rebuild_libraries.py` is deprecated.
  - `klayout_start.sh` is now an alias in `.designinit`
  - simply use `klayout` to launch Klayout with the new library reloading plugin.
- **Updated Documentation**: Clean up of workflow documentation and improved user guides.

## [v0.2.0] - 2025-07-12

### Added
- **Complete OTA Layout**: 5-transistor OTA with DRC and LVS clean implementation
- **Enhanced Documentation**: 
  - Updated README.md with new screenshots for Xschem and KLayout
  - Preliminary documentation for schematic and layout workflows
  - Improved setup instructions and troubleshooting guides
- **Development Environment**: Moved devcontainer.json to dedicated branch `devcontainer`

## [v0.1.0] - 2025-07-09

### Added
- **Initial Project Structure**: Complete analog design project template
- **KLayout Libraries Integration**: Comprehensive library management system
  - Automated library symbolic link creation to `~/.klayout/libraries/`
  - Force update mechanism for GDS files under `libs`
  - Library wipe and recreation functionality
- **5-Transistor OTA Design**: 
  - Complete schematic implementation with proper transistor sizing
  - Functional OTA design in `core_analog` library
  - Testbench setup in `tb_analog` library
- **Library Management System**:
  - CI scripts for library hierarchy validation
  - Batch netlisting with `netlist_all.sh`
  - Relaxed file naming conventions for testbenches
- **Development Infrastructure**:
  - Docker container setup with VNC access
  - PDK setup scripts (`setup_pdk.sh`)
  - Cross-platform startup scripts
  - Git ignore configuration for design files

---

## Release Notes

### Version Highlights

**v1.0.0** represents the first stable release with streamlined shell environment and mature library management system.

**v0.2.0** focused on completing the reference OTA design with full layout implementation and significantly improving documentation.

**v0.1.0** established the foundational project structure, library management system, and initial analog design examples.

### Migration Notes

- **v0.1.0 → v0.2.0**: No breaking changes. Added layout capabilities and enhanced documentation.
- **v0.2.0 → v1.0.0**: Enhanced shell environment. Change of layout library management system.

### Compatibility

- All versions are compatible with IIC-OSIC-TOOLS Docker environment
- GlobalFoundries 180nm PDK (gf180mcuD) support throughout all versions
- Cross-platform support (Windows, macOS, Linux) maintained across releases