crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/rc_filter/rc_filter.gds
load rc_filter
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/rc_filter
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/rc_filter -o /home/huda/opensource-project/Microelectronic-Block-Generator/rc_filter/rc_filter_extracted.spice
quit -noprompt
