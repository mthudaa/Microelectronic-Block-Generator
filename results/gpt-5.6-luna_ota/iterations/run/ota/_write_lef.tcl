drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_ota/iterations/run/ota/ota.gds
load ota
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_ota/iterations/run/ota/ota.lef -hide
quit -noprompt
