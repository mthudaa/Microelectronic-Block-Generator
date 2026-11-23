# Coupled, capacitance-only extraction (scale off) of layout/mbg_d08.gds. Run from post_sim/:
#   magic -dnull -noconsole -rcfile $PDK_ROOT/gf180mcuD/libs.tech/magic/gf180mcuD.magicrc pex_mbg_d08.tcl
# Writes mbg_d08_coupled.ext and mbg_d08_coupled.spice here; mbg-d08.pex.spice is that netlist with the
# cell name mbg_d08_coupled renamed to mbg_d08 (sed s/mbg_d08_coupled/mbg_d08/g).
crashbackups stop
drc off
set here [file dirname [file normalize [info script]]]
gds read [file join [file dirname $here] layout mbg_d08.gds]
load mbg_d08
select top cell
flatten mbg_d08_coupled
load mbg_d08_coupled
select top cell
extract path $here
extract all
ext2spice cthresh 0.01
ext2spice subcircuit top on
ext2spice format ngspice
ext2spice scale off
ext2spice -p $here -o [file join $here mbg_d08_coupled.spice]
quit -noprompt
