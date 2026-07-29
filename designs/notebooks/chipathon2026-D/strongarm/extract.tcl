crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D/strongarm/strongarm.gds
load strongarm
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D/strongarm
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D/strongarm -o /home/huda/opensource-project/Microelectronic-Block-Generator/designs/notebooks/chipathon2026-D/strongarm/strongarm_extracted.spice
quit -noprompt
