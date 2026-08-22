crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/cmp_2stage_clk/cmp_2stage_clk.gds
load cmp_2stage_clk
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/cmp_2stage_clk
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/cmp_2stage_clk -o /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/cmp_2stage_clk/cmp_2stage_clk_extracted.spice
quit -noprompt
