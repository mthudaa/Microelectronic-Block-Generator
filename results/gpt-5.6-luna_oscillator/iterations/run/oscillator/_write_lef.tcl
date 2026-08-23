drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_oscillator/iterations/run/oscillator/oscillator.gds
load oscillator
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/results/gpt-5.6-luna_oscillator/iterations/run/oscillator/oscillator.lef -hide
quit -noprompt
