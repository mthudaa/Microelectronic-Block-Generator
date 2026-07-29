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

# Manually construct edges for out
memory = MemoryMap(0.3)
memory.add_device_geometry(top_level)

from core.routing import _try_route_combos

# Find the exact ports
def find_port(dev, terminal, arah):
    return port_map[dev][terminal][arah]["param"]

p1 = find_port("XM1p", "gate", "E")
p2 = find_port("XM1n", "gate", "E")
combos1 = [ (0, p1, p2) ]

p3 = find_port("XM3p", "drain", "E")
p4 = find_port("XM3n", "drain", "E")
combos2 = [ (0, p3, p4) ]

p5 = find_port("XM1p", "gate", "W")
p6 = find_port("XM3p", "drain", "E")
combos3 = [ (0, p5, p6) ]

print("Routing edge 1...")
res = _try_route_combos(top_level, combos1, 0, memory)
print(res)

print("Routing edge 2...")
res = _try_route_combos(top_level, combos2, 0, memory)
print(res)

print("Routing edge 3...")
res = _try_route_combos(top_level, combos3, 0, memory)
print(res)
