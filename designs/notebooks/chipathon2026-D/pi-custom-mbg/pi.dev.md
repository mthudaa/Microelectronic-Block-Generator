# pi-custom-mbg Development Tracking

> Auto-generated: 2026-07-30 | Owner: Huda

## Active Tasks

### 🔴 High Priority
- [ ] **Slash Commands**: Add `/mbg-full-automate` and `/mbg-partial-automate` in `.opencode/commands/`
- [ ] **Full Automate Flow**: Research → Sim → Layout → LVS → PEX → Tapeout
- [ ] **Partial Automate Flow**: Same steps with user confirmation at each stage
- [ ] **LVS Debug**: Fix ro3 pin-swap mismatch, inv/ota regression

### 🟡 Medium Priority
- [ ] **XC/XR Extraction**: Fix magic extraction for `rm1` and `cap_mim_2f0fF` devices
- [ ] **StrongArm Performance**: Optimize routing for 11T+ designs (currently ~974s)
- [ ] **SPICE-in-the-Loop**: Auto-finetuning MOSFET sizing based on ngspice results

### 🟢 Low Priority
- [ ] **DRC Auto-Fix**: Auto-correct DRC violations from placement/routing
- [ ] **Multi-PDK Support**: Add SkyWater 130nm support alongside GF180
- [ ] **GUI Preview**: SVG/PNG generation for quick layout review

## Completed
- [x] PathFinder NCR penalty_threshold threading
- [x] Via cache for faster routing (~10x)
- [x] XC/XR multi-row placement in spice_parser
- [x] Terminal name alignment (p/n) in placement.py
- [x] Merge PR #2 (OpenCode foundation + experiment audit)

## Notes
- OTA_5T LVS MATCH achieved after removing MAX_COMBOS_PER_EDGE cap
- RC filter routing works but extraction doesn't recognize passives
- See `UPDATE_JABIR.md` for collaborator message
