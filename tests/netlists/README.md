# Public demonstration netlists

These flat MOS/passive subcircuits exercise parsing, simulation, layout and
ordinary physical verification. They are examples, not characterized IP.

`tests/fixtures.py` resolves the literal `{PDK_LIB}` placeholder against the
selected local PDK. Keep generated artifacts outside the source tree.

A fixture being present does not establish a successful physical or electrical
result. Check the actual reports produced by the public release tools.
