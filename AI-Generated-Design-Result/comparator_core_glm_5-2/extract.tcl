crashbackups stop
drc off
gds read /home/huda/mbg_runs/comparator_simplified/two_stage_comparator/two_stage_comparator.gds
load two_stage_comparator
expand
select top cell
extract path /home/huda/mbg_runs/comparator_simplified/two_stage_comparator
extract no capacitance
extract no coupling
extract no resistance
extract no length
extract all
ext2spice lvs
ext2spice -p /home/huda/mbg_runs/comparator_simplified/two_stage_comparator -o /home/huda/mbg_runs/comparator_simplified/two_stage_comparator/two_stage_comparator_extracted.spice
quit -noprompt
