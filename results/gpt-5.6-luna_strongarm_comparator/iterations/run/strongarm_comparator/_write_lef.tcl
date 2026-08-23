drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_strongarm_comparator/iterations/run/strongarm_comparator/strongarm_comparator.gds
load strongarm_comparator
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_strongarm_comparator/iterations/run/strongarm_comparator/strongarm_comparator.lef -hide
quit -noprompt
