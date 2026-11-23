# Chipathon readiness: READY (all required checks pass; density and organizer items still listed)

| Check | Status | Required | Detail |
|---|---|---|---|
| info.project fields | PASS | yes | all readiness fields present |
| export control document exists | PASS | yes | Export_Control_GF_Rev8.2_signed.docx exists |
| info.pins count | PASS | yes | 16 pins listed |
| pin io_type valid for template | NOT RUN | no | template file not found; pin io_types not checked against it |
| analog pins carry secondary_esd | PASS | yes | 14 analog pins; without secondary_esd: none |
| info.pins match routed DEF pins | PASS | yes | identical sets of 16 names |
| routing layers within Metal1-Metal5 | PASS | yes | layers used: ['Metal1', 'Metal2', 'Metal3', 'Metal4', 'Metal5'] |
| info.project.lvs_config names this file | PASS | yes | info says 'lvs_config.json', checked lvs_config.json |
| lvs_config layout and netlist paths exist | PASS | yes | all exist |
| single top cell | PASS | yes | top cells: ['mbg_d08'] |
| top cell name equals GDS file name | PASS | yes | top cell ['mbg_d08'] vs file stem 'mbg_d08' |
| verified GDS is this GDS | PASS | yes | sha256 de202cd8d79c6b45... matches |
| PR boundary equals committee DEF DIEAREA | PASS | yes | DEF DIEAREA (0.0, 0.0, 605.0, 1110.0) um; top-level (0,0) boundaries [(0.0, 0.0, 605.0, 1110.0)] |
| drc | PASS | yes | Magic 0 and KLayout 0 on submission-prep/layout/mbg_d08.gds (user layout + name on Metal5; re-run 2026-11-23) |
| lvs | PASS | yes | match vs submission-prep/mbg-d08_lvs.spice (re-run 2026-11-23) |
| pex_coupled | PASS | yes | raw extraction 405 C, 0 R (includes 47 floating name-artwork nodes); simulation netlist 318 C without the artwork capacitors (sim/make_sim_netlist.py) |
| pex_full_rc | FAIL | no | FAIL: Magic PEX stops after its start message (open) [waived: D08 team decisions 2026-11-23: the team owns the block area only; full-RC PEX not pursued; power pads, density fill and wafer.space frame confirmation are handled by the Chipathon committee; post-layout results are scored by the committee testbench; NEURO1B replaces the temperature sensor on temp_out/W12 with the pin name kept] |
| landing_connectivity | PASS | yes | 124 rectangles in 16 clusters against the committee D08_BV.def (re-run after the rename) |
| density rules (die-level fill) | PARTIAL | no | DCF.1b, PL.8, M1.4-M5.4, MT.3 need die-level fill; not run [waived: D08 team decisions 2026-11-23: the team owns the block area only; full-RC PEX not pursued; power pads, density fill and wafer.space frame confirmation are handled by the Chipathon committee; post-layout results are scored by the committee testbench; NEURO1B replaces the temperature sensor on temp_out/W12 with the pin name kept] |
| wafer.space frame decision | PARTIAL | no | no record in the repository of whether the wafer.space frame is targeted [waived: D08 team decisions 2026-11-23: the team owns the block area only; full-RC PEX not pursued; power pads, density fill and wafer.space frame confirmation are handled by the Chipathon committee; post-layout results are scored by the committee testbench; NEURO1B replaces the temperature sensor on temp_out/W12 with the pin name kept] |
| power pad cells (VDD/VSS) in the GDS | PARTIAL | no | no gf180mcu_fd_io__vdd / __vss instances in the top cell; the pad rule is not confirmed [waived: D08 team decisions 2026-11-23: the team owns the block area only; full-RC PEX not pursued; power pads, density fill and wafer.space frame confirmation are handled by the Chipathon committee; post-layout results are scored by the committee testbench; NEURO1B replaces the temperature sensor on temp_out/W12 with the pin name kept] |
| W12 temp_out signal confirmed by organizer | PARTIAL | no | NEURO1B uses temp_out_core; organizer confirmation not recorded [waived: D08 team decisions 2026-11-23: the team owns the block area only; full-RC PEX not pursued; power pads, density fill and wafer.space frame confirmation are handled by the Chipathon committee; post-layout results are scored by the committee testbench; NEURO1B replaces the temperature sensor on temp_out/W12 with the pin name kept] |
| extracted specifications (post-layout) | NOT RUN | no | not part of the readiness gate in this check; see the benchmark report [waived: D08 team decisions 2026-11-23: the team owns the block area only; full-RC PEX not pursued; power pads, density fill and wafer.space frame confirmation are handled by the Chipathon committee; post-layout results are scored by the committee testbench; NEURO1B replaces the temperature sensor on temp_out/W12 with the pin name kept] |
