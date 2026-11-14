# Public release validation

The following native smoke cases executed the public checkout with GF180MCU D.
Every PASS required Magic DRC, netgen LVS, internal connectivity and an actual
PEX netlist. Ordinary macros also produced their configured physical views.

| Demonstration | Ordinary macro | Physical checks |
| --- | --- | --- |
| inverter | Disabled | PASS |
| inverter | Enabled | PASS |
| ota_5t | Disabled | PASS |
| ota_5t | Enabled | PASS |
| rc_filter | Disabled | PASS |
| vref_1v2 | Disabled | PASS |
| ring_osc_3 | Disabled | PASS |
| strongarm | Disabled | PASS |
| cmp_2stage_clk | Disabled | PASS |

Tools: Magic 8.3.681, netgen 1.5.323, ngspice 46. EDA checks ran sequentially
with at least 2 GiB available RAM before starting each job.

The public checkout regression passed 162 tests and 57 subtests, with two
optional checks skipped. Separate distribution-content tests cover bundled
verification helpers and source-archive launcher/client configuration files.
Agent integration validation passed all ten checks. Offline wheel/source-archive
builds also passed. Extracted-source validation checked the launcher and MCP
client configurations; isolated wheel imports found all three verification
helpers with bytes identical to their maintained sources.
An isolated installed-wheel inverter run also passed Magic DRC, netgen LVS,
internal connectivity and PEX extraction, using the bundled verification helpers.

```bash
python3 scripts/sync_agent_tools.py --check
python3 scripts/validate_agent_integrations.py
python -m pytest -q
```

These are software/physical smoke results, not silicon measurements or a
tapeout qualification. No foundry sign-off, full operating-envelope acceptance
or characterized timing is claimed. Generated layouts, runtime logs and user
design data are not part of the published source tree.
