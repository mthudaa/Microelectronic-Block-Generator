"""
Simplified comparator: smaller PMOS to reduce routing burden.
Same topology: NMOS diff pair + PMOS mirror load + NMOS tail + Stage2 CS + PMOS active load
Try sizing:  nf=2 for matched PMOS structures, larger nf=11 for bias-current tail maintained
Use W=4u L=1u nf=2 m=1 for PM3, PM4, PM7 (lower effective W = 8u each)
"""
import os
import sys
sys.path.insert(0, '/home/huda/.pi')
os.environ.setdefault('PDK_ROOT', '/home/huda/.volare')
os.environ.setdefault('PDK', 'gf180mcuD')
os.environ.setdefault('PDKPATH', '/home/huda/.volare/gf180mcuD')
import json
from core.pipeline import spice_to_gds_with_checks

NETLIST = r"""
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt two_stage_comparator vdd vss inp inm out ibias
XM8   ibias  ibias vss vss nfet_03v3  L=1u W=3u nf=2 m=1
XM3   int_p  int_p vdd vdd  pfet_03v3  L=1u W=4u nf=2 m=1
XM4   int_n  int_p vdd vdd  pfet_03v3  L=1u W=4u nf=2 m=1
XM1   int_p    inp int_src vss nfet_03v3  L=1u W=3u nf=2 m=1
XM2   int_n    inm int_src vss nfet_03v3  L=1u W=3u nf=2 m=1
XM5   int_src ibias vss vss  nfet_03v3  L=1u W=3u nf=2 m=1
XM7   out    int_p vdd vdd  pfet_03v3  L=1u W=4u nf=2 m=1
XM6   out    int_n vss vss  nfet_03v3  L=1u W=3u nf=2 m=1
.ends
"""

import json
print(f"[SIMPLIFIED] running with smaller PMOS (nf=2)")
out = '/home/huda/mbg_runs/comparator_simplified'
os.makedirs(out, exist_ok=True)
os.chdir(out)
result = spice_to_gds_with_checks(NETLIST, mode='analog', add_labels=True)
print(json.dumps({'drc': result['drc'].get('summary'), 'lvs': result['lvs'].get('summary').get('message'),
                  'pex': result['pex'].get('summary'), 'all_pass': result['all_pass']}, indent=2))
