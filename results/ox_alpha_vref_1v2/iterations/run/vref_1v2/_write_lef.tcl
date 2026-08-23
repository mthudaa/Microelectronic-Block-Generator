drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_vref_1v2/iterations/run/vref_1v2/vref_1v2.gds
load vref_1v2
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_vref_1v2/iterations/run/vref_1v2/vref_1v2.lef -hide
quit -noprompt
