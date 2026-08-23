drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_ota/iterations/preflight/ota/ota.gds
load ota
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/ox_alpha_ota/iterations/preflight/ota/ota.lef -hide
quit -noprompt
