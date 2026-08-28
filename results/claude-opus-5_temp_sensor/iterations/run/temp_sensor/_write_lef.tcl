drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/claude-opus-5_temp_sensor/iterations/run/temp_sensor/temp_sensor.gds
load temp_sensor
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/claude-opus-5_temp_sensor/iterations/run/temp_sensor/temp_sensor.lef -hide
quit -noprompt
