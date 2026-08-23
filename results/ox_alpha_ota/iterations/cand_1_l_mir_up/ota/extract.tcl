crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_ota/iterations/cand_1_l_mir_up/ota/ota.gds
load ota
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_ota/iterations/cand_1_l_mir_up/ota
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_ota/iterations/cand_1_l_mir_up/ota -o /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_ota/iterations/cand_1_l_mir_up/ota/ota_extracted.spice
quit -noprompt
