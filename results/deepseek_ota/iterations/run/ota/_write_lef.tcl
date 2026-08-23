drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_ota/iterations/run/ota/ota.gds
load ota
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_ota/iterations/run/ota/ota.lef -hide
quit -noprompt
