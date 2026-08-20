drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/ota_5t/ota_5t.gds
load ota_5t
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/ota_5t/ota_5t.lef -hide
quit -noprompt
