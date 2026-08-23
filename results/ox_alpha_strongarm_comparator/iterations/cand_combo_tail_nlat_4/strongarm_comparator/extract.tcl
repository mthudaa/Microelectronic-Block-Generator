crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_strongarm_comparator/iterations/cand_combo_tail_nlat_4/strongarm_comparator/strongarm_comparator.gds
load strongarm_comparator
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_strongarm_comparator/iterations/cand_combo_tail_nlat_4/strongarm_comparator
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_strongarm_comparator/iterations/cand_combo_tail_nlat_4/strongarm_comparator -o /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_strongarm_comparator/iterations/cand_combo_tail_nlat_4/strongarm_comparator/strongarm_comparator_extracted.spice
quit -noprompt
