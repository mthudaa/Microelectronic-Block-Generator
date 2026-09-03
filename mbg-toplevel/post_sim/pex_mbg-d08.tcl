crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/mbg-toplevel/layout/mbg-d08.gds
load mbg-d08
select top cell
flatten mbg-d08_flat
load mbg-d08_flat
cellname delete mbg-d08
cellname rename mbg-d08_flat mbg_d08_post
select top cell
extract path /tmp/claude-1000/-home-huda-opensource-project-Microelectronic-Block-Generator/40843d62-a34e-49bb-a822-2cc2d772f724/scratchpad/full/pex
extract all
ext2spice cthresh 0.01
ext2spice subcircuit top on
ext2spice format ngspice
ext2spice scale off
ext2spice -p /tmp/claude-1000/-home-huda-opensource-project-Microelectronic-Block-Generator/40843d62-a34e-49bb-a822-2cc2d772f724/scratchpad/full/pex -o /tmp/claude-1000/-home-huda-opensource-project-Microelectronic-Block-Generator/40843d62-a34e-49bb-a822-2cc2d772f724/scratchpad/full/pex/mbg-d08.pex.spice
quit -noprompt
