crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/ota_5t/ota_5t.gds
load ota_5t
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/ota_5t
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/ota_5t -o /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/ota_5t/ota_5t_extracted.spice
quit -noprompt
