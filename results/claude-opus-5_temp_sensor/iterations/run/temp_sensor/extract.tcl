crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/claude-opus-5_temp_sensor/iterations/run/temp_sensor/temp_sensor.gds
load temp_sensor
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/results/claude-opus-5_temp_sensor/iterations/run/temp_sensor
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/results/claude-opus-5_temp_sensor/iterations/run/temp_sensor -o /home/huda/opensource-project/Microelectronic-Block-Generator/results/claude-opus-5_temp_sensor/iterations/run/temp_sensor/temp_sensor_extracted.spice
quit -noprompt
