# Regression netlists

One SPICE subcircuit per file, loaded by `tests/fixtures.py`.

Every file keeps the project convention used by the inline designs these
replaced: the model library is written as the literal placeholder

    .lib "{PDK_LIB}" typical

and `fixtures.load()` resolves it against the live `$PDKPATH`. No personal
path is ever committed, and the same file works on any machine.

`complexity` in the header comment is the rung each design occupies on the
scalability ladder (see `tests/test_complexity_ladder.py`); it is a label,
not something the loader parses.
