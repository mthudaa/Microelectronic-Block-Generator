crashbackups stop
drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_oscillator/iterations/run/oscillator/oscillator.gds
load oscillator
expand
select top cell
extract path /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_oscillator/iterations/run/oscillator
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_oscillator/iterations/run/oscillator -o /home/huda/opensource-project/Microelectronic-Block-Generator/results/deepseek_oscillator/iterations/run/oscillator/oscillator_extracted.spice
quit -noprompt
