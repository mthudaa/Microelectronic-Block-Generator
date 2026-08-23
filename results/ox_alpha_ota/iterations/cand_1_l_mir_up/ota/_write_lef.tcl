drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_ota/iterations/cand_1_l_mir_up/ota/ota.gds
load ota
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_ota/iterations/cand_1_l_mir_up/ota/ota.lef -hide
quit -noprompt
