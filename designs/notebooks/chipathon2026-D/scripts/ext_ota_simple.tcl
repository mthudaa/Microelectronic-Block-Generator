crashbackups stop
drc off
gds read /home/huda/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D/out.gds
load ota_simple
expand
select top cell
extract path /home/huda/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D -o /home/huda/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D/ota_simple.ext.spc
quit -noprompt
