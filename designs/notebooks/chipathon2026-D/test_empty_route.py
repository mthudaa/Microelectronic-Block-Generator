import os, sys
sys.path.insert(0, os.path.abspath("../../../"))
os.environ['PDK_ROOT'] = os.environ.get('PDK_ROOT', '/home/huda/.volare')
os.environ['PDK'] = os.environ.get('PDK', 'gf180mcuD')
from core.routing import auto_router, set_pdk, MemoryMap
from core.spice_parser import parse_netlist_with_pdk
from core.placement import placement, petakan_koneksi_net, buat_daftar_koneksi
from glayout import gf180

netlist = """
.lib "/home/huda/.volare/gf180mcuD/libs.tech/ngspice/sm141064.ngspice" typical
.subckt ring_osc_3 vdd vss out
XM1p n1 out vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM1n n1 out vss vss nfet_03v3 L=1u W=2u nf=1 m=1
XM2p n2 n1 vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM2n n2 n1 vss vss nfet_03v3 L=1u W=2u nf=1 m=1
XM3p out n2 vdd vdd pfet_03v3 L=1u W=4u nf=1 m=1
XM3n out n2 vss vss nfet_03v3 L=1u W=2u nf=1 m=1
.ends
"""

set_pdk(gf180)
config = parse_netlist_with_pdk(netlist)
top_level, port_map = placement(config, gf180)
peta = petakan_koneksi_net(config)
goals = buat_daftar_koneksi(peta, port_map)

out_goals = [g for g in goals if g[0] == 'out']
print("Routing ONLY 'out' net...")
auto_router(top_level, out_goals)
print("Done!")
