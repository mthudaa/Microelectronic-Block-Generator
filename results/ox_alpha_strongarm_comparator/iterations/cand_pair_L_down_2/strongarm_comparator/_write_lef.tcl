drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_strongarm_comparator/iterations/cand_pair_L_down_2/strongarm_comparator/strongarm_comparator.gds
load strongarm_comparator
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_strongarm_comparator/iterations/cand_pair_L_down_2/strongarm_comparator/strongarm_comparator.lef -hide
quit -noprompt
