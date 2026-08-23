crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_ota/iterations/run/ota/ota.gds
load ota
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_ota/iterations/run/ota
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_ota/iterations/run/ota -o /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_ota/iterations/run/ota/ota_extracted.spice
quit -noprompt
