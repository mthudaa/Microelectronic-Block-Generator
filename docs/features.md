# Public feature levels

This edition provides open-loop Basic and Intermediate tools. Work from an
explicit input circuit and inspect the evidence for each stage.

| Level | Feature | Public surface |
| --- | --- | --- |
| Basic | Environment and PDK inventory | `doctor`, `pdk list`, `pdk info` |
| Basic | Local workspaces and progress | `design init`, `design status`; outputs default to `~/mbg` |
| Basic | SPICE validation | `netlist check` |
| Basic | Operating point, DC, AC and transient simulation | `sim run` |
| Basic | CLI and agent interoperability | `mbg` and stdio MCP |
| Intermediate | Conventional flat-netlist placement, power and grid routing | `layout generate` |
| Intermediate | Layout inspection | `layout view` and SVG preview |
| Intermediate | Ordinary guard rings and physical pins | `layout generate --macro-config` |
| Intermediate | Magic DRC, netgen LVS and parasitic extraction | `verify drc`, `verify lvs`, `verify pex` |
| Intermediate | Reference and amplifier characterization | `measure vref`, `measure ota` |
| Intermediate | ADC/DAC metrics from measured data | `measure adc`, `measure dac` |
| Intermediate | Explicit specification checks | `spec check` |
| Intermediate | GDS, schematic/extracted SPICE, LEF, Liberty and Verilog views | Checked Python pipeline and layout tools |

## Boundaries

The layout entry point is `mbg.pipeline.spice_to_gds_with_checks`. Inputs must be
flat subcircuits with supported MOS/passive models and explicit dimensions.
Ordinary guarded macros require declared power and ground ports. They are
currently supported on GF180MCU D; other PDK profiles have separate limits.
Unsupported device/layout requests produce a diagnostic instead of a substitute
physical device. Use trusted input files and licensed, locally installed PDKs.

Physical checking in this edition is Magic DRC plus netgen LVS and internal
connectivity verification. PEX extraction must also produce an actual netlist.
These checks do not establish foundry sign-off or electrical specifications.
An extracted design must still be simulated and measured for its intended use.

Liberty output is an uncharacterized abstract, not measured timing data. Macro
views do not demonstrate an executed chip-integration flow. Converter metrics
consume supplied measured data; they do not synthesize or simulate a converter.

Generated outputs and user-supplied designs are local working material. Their
publication requires separate explicit authorization.
