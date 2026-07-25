# MBG API Reference

## Core Library (`core/`)

### `core.pipeline`
| Function | Description |
|----------|-------------|
| `spice_to_gds(netlist, mode, add_labels, run_checks, gds_path)` | SPICE → GDS full flow |
| `llm_to_gds(prompt, model, api_key, mode)` | Natural language → GDS |
| `generate_netlist_from_prompt(prompt, model, api_key, api_url, llm_feedback)` | Spec → SPICE via LLM |

### `core.placement`
| Function | Description |
|----------|-------------|
| `manual_placement(devices, pdk, top_cell_name)` | Place devices at explicit (x,y). Returns `(component, port_map, device_map)` |
| `placement(config, pdk)` | Auto-placement from parsed config |

### `core.routing`
| Function | Description |
|----------|-------------|
| `manual_route(component, routes, memory)` | Draw explicit trace segments + vias |
| `auto_router(component, connection_goals)` | PathFinder NCR auto-routing |
| `set_pdk(pdk)` | Set active PDK for routing |
| `get_pdk()` | Get active PDK |

### `core.power`
| Function | Description |
|----------|-------------|
| `manual_power(component, pdk, strips, rails, guardring)` | Add power strips, local rails, guard rings |
| `add_power_strips(component, pdk, strip_width, margin)` | Auto power strips from bbox |

### `core.checks`
| Function | Description |
|----------|-------------|
| `run_drc(gds_path, cell_name, engine, workdir)` | DRC → `{clean, report_path, error_count, summary}` |
| `run_lvs(gds_path, netlist_path, netlist_content, cell_name, auto_fix_ports)` | LVS → `{match, report_path, summary}` |
| `run_pex(gds_path, cell_name, mode, workdir)` | PEX → `{pex_path, mode, summary}` |
| `check_tools()` | Tool availability → `{magic, netgen, pdk_ok}` |
| `validate_gds(gds_path, cell_name)` | GDS validation → `{valid, cells, size}` |
| `extract_layout_netlist(gds_path, cell_name)` | Magic no-RC extraction |
| `fix_port_order(extracted_path, correct_order)` | Fix .subckt port order |

### `core.simulation`
| Function | Description |
|----------|-------------|
| `run_spice(netlist_content, workdir, timeout)` | Run ngspice → `{raw_path, returncode, stdout}` |
| `raw_to_csv(raw_path)` | Parse ngspice raw → list of dicts |
| `pdk_path(subpath)` | Resolve PDK file path |

### `core.spice_parser`
| Function | Description |
|----------|-------------|
| `parse_netlist_with_pdk(file_content, manual_pdk, mode)` | Parse SPICE → component list |

## Layer Map (GF180MCU)

| Layer | Number | Direction | Usage |
|-------|--------|-----------|-------|
| met2 | 36 | — | Device port access |
| met3 | 42 | Horizontal | Primary routing |
| met4 | 46 | Vertical | Vertical routing |
| met5 | 81 | Horizontal | Power strips |
| met2_pin | (36,10) | — | Pin marker (Magic) |
| met2_label | (36,10) | — | Label (Magic) |
