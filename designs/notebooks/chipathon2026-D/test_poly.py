from glayout.gf180 import gf180
import gdsfactory as gf
pdk = gf180
pdk.activate()
from glayout.pdk.util.comp_utils import evaluate_bbox
from glayout.gf180.pcells.fet import nfet_03v3
from gdsfactory.components import rectangle
c = gf.Component()
c.add_ref(nfet_03v3())
c.add_polygon([(0,0), (1,0), (1,1), (0,1)], layer=pdk.get_glayer("met1"))
print("Num polygons:", len(c.polygons))
