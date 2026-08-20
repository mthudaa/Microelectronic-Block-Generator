drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/rc_filter/rc_filter.gds
load rc_filter
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/rc_filter/rc_filter.lef -hide
quit -noprompt
