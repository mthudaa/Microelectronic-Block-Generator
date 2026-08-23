drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/strongarm_comparator/strongarm_comparator.gds
load strongarm_comparator
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_strongarm_comparator/strongarm_comparator/strongarm_comparator.lef -hide
quit -noprompt
