crashbackups stop
drc off
gds read layout/mbg-d08.gds
load mbg-d08
select top cell
flatten mbg-d08_flat
load mbg-d08_flat
cellname delete mbg-d08
cellname rename mbg-d08_flat mbg_d08_post
select top cell
extract path /foss/designs/mbg-toplevel/post_sim
extract all
ext2spice cthresh 0.01
ext2spice subcircuit top on
ext2spice format ngspice
ext2spice scale off
ext2spice -p /foss/designs/mbg-toplevel/post_sim -o /foss/designs/mbg-toplevel/post_sim/mbg-d08.pex.spice
quit -noprompt
