crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_vref_1v2/iterations/run/vref_1v2/vref_1v2.gds
load vref_1v2
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_vref_1v2/iterations/run/vref_1v2
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_vref_1v2/iterations/run/vref_1v2 -o /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_vref_1v2/iterations/run/vref_1v2/vref_1v2_extracted.spice
quit -noprompt
