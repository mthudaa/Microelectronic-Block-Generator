crashbackups stop
drc off
gds read /tmp/opencode/ox_alpha/results/ox_alpha_ota/iterations/run/ota/ota.gds
load ota
expand
select top cell
extract path /tmp/opencode/ox_alpha/results/ox_alpha_ota/iterations/run/ota
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /tmp/opencode/ox_alpha/results/ox_alpha_ota/iterations/run/ota -o /tmp/opencode/ox_alpha/results/ox_alpha_ota/iterations/run/ota/ota_extracted.spice
quit -noprompt
