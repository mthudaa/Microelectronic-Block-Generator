drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/iterations/pex_tune_1_w_x1.0_net_0.35um_/strongarm_comparator/strongarm_comparator.gds
load strongarm_comparator
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/iterations/pex_tune_1_w_x1.0_net_0.35um_/strongarm_comparator/strongarm_comparator.lef -hide
quit -noprompt
