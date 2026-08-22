drc off
gds read /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/cmp_2stage_clk/cmp_2stage_clk.gds
load cmp_2stage_clk
select top cell
lef write /home/huda/opensource-project/Microelectronic-Block-Generator/tests/notebooks/cmp_2stage_clk/cmp_2stage_clk.lef -hide
quit -noprompt
