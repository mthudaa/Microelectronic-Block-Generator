drc off
gds read /tmp/opencode/ox_alpha/results/ox_alpha_ota/iterations/run/ota/ota.gds
load ota
select top cell
lef write /tmp/opencode/ox_alpha/results/ox_alpha_ota/iterations/run/ota/ota.lef -hide
quit -noprompt
