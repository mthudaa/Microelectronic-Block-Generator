"""Connected ordinary GF180 P+ substrate / N+ Nwell supply rings.

No selective isolation or per-device body-bias connections are provided.
"""
import math
from mbg.design_context import BoundingBox, Obstacle, PinAccessPoint


def _check(ctx, pdk, config):
    if not str(getattr(pdk, 'name', '')).lower().startswith('gf180'):
        raise ValueError('ordinary macro guard rings are supported only for GF180')
    if config.guardring != 'ordinary':
        raise ValueError('only ordinary guard rings are supported')
    if any(n not in ctx.nets for n in config.supplies.values()):
        raise ValueError('macro supplies must exist in the circuit')


def _box_values(box):
    return [float(box.xmin), float(box.ymin), float(box.xmax), float(box.ymax)]

def _rect(top, box, layer):
    top.add_polygon([(box.xmin, box.ymin), (box.xmax, box.ymin),
                     (box.xmax, box.ymax), (box.xmin, box.ymax)], layer=layer)

def _rule(pdk, a, b=None, key='min_enclosure'):
    data = pdk.get_grule(a,b) if b else pdk.get_grule(a)
    value = float(data[key])
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'invalid guard-ring PDK rule {a}/{b}/{key}')
    return value

def _core_box(ctx):
    # Includes existing rail geometry as well as devices. Never use design_bbox:
    # that becomes macro_bbox once the caller reserves its pin aisle.
    if ctx.component is not None:
        return BoundingBox.from_gf(ctx.component.bbox)
    boxes=list(ctx.device_bboxes.values())
    if not boxes:
        raise ValueError('guard-ring planning requires a placed core')
    return BoundingBox(min(b.xmin for b in boxes),min(b.ymin for b in boxes),
                       max(b.xmax for b in boxes),max(b.ymax for b in boxes))

def _metal_obstacles(ctx,ref,pdk,owner,net):
    """Decompose actual polygons; never turn a hollow ring into a filled box."""
    import gdstk
    from mbg.geometry import rect_decompose
    polygons=ref.get_polygons(by_spec=True)
    records=[]
    for layer in ctx.rules.metals:
        pts=polygons.get(pdk.get_glayer(layer),[])
        if not pts:
            continue
        merged=gdstk.boolean(pts,[], 'or',precision=ctx.rules.manufacturing_grid())
        for polygon in merged:
            for rect in rect_decompose([tuple(p) for p in polygon.points]):
                box=BoundingBox(*map(float,rect))
                ctx.add_obstacle(Obstacle(layer,box,owner=owner,kind='guardring',net=net))
                records.append({'layer':layer,'rect':_box_values(box)})
    return records

def _terminal(ctx,instance,net,points):
    terminal=(instance,'tap')
    if terminal not in ctx.nets[net].terminals:
        ctx.nets[net].terminals.append(terminal)
    for layer,x,y,width in points:
        ctx.add_access_point(PinAccessPoint(instance,'tap',net,layer,
                                           x,y,orientation=0,width=width))

def _ring_connections(ctx,top,pdk,ring,rcfg):
    from glayout import via_stack
    from mbg.router import snap_to_grid
    owner='GUARD_'+ring['role']
    net=ring['net']; cx,cy=ring['center']; ew,eh=ring['enclosed']
    half=ring['tap_width']/2
    locations=[('met2',cx,cy+eh/2+half),('met2',cx,cy-eh/2-half),
               ('met1',cx+ew/2+half,cy),('met1',cx-ew/2-half,cy)]
    aps=[]
    for i,(layer,x,y) in enumerate(locations):
        x,y=ctx.rules.snap(x),ctx.rules.snap(y)
        gx,gy=snap_to_grid(ctx,x,y,rcfg)
        stack=via_stack(pdk,layer,rcfg.access_layer,centered=True)
        ref=top.add_ref(stack); ref.move((gx,gy))
        _metal_obstacles(ctx,ref,pdk,owner,net)
        width=max(ctx.rules.via_footprint(layer,rcfg.access_layer),
                  ctx.rules.min_width(layer))
        # Fill the tiny grid-alignment rectangle. An L-shaped stub can leave
        # a sub-spacing notch alongside the continuous ring even though both
        # pieces are the same net (observed GF180 M1.2a at 0.03um). This pad
        # occupies only the reserved perimeter channel, not the circuit core.
        h=width/2
        box=BoundingBox(min(x,gx)-h,min(y,gy)-h,max(x,gx)+h,max(y,gy)+h)
        _rect(top,box,pdk.get_glayer(layer))
        ctx.add_obstacle(Obstacle(layer,box,owner=owner,kind='guardring_drop',net=net))
        aps.append((rcfg.access_layer,gx,gy,width))
    _terminal(ctx,owner,net,aps)

def _plan(ctx, pdk, config):
    from glayout import tapring
    from gdsfactory.components import rectangular_ring
    _check(ctx, pdk, config)
    core = _core_box(ctx)
    cx, cy = (ctx.rules.snap(v) for v in core.center)
    grid = ctx.rules.manufacturing_grid()
    gap = max(5.0, _rule(pdk, 'nwell', key='min_separation'), 2*ctx.rules.max_metal_separation())
    tap_width = max(_rule(pdk, 'active_tap', key='min_width'),
                    2*_rule(pdk, 'active_tap', 'mcon')+_rule(pdk, 'mcon', key='width'))
    enc = max(_rule(pdk, 'active_tap', 'nwell'), (_rule(pdk, 'nwell', key='min_width')-tap_width)/2)
    enc = ctx.rules.snap(enc+2*grid)
    rings = []
    enclosure = core.inflate(gap)
    for role, doping, net in [('inner_ground', 'p+s/d', config.supplies['ground']),
                             ('outer_power', 'n+s/d', config.supplies['power'])]:
        ew = 2*max(abs(enclosure.xmin-cx), abs(enclosure.xmax-cx))
        eh = 2*max(abs(enclosure.ymin-cy), abs(enclosure.ymax-cy))
        enclosed = tuple(math.ceil((v-1e-9)/(2*grid))*2*grid for v in (ew,eh))
        cell = tapring(pdk, enclosed_rectangle=enclosed, sdlayer=doping).copy()
        if doping == 'n+s/d':
            cell.add_ref(rectangular_ring(enclosed_size=(enclosed[0]-2*enc,enclosed[1]-2*enc),
                                         width=tap_width+2*enc, centered=True, layer=pdk.get_glayer('nwell')))
        bb = BoundingBox.from_gf(cell.bbox)
        world = BoundingBox(bb.xmin+cx,bb.ymin+cy,bb.xmax+cx,bb.ymax+cy)
        rings.append({'component':cell,'role':role,'doping':doping,'net':net,
                      'enclosed':enclosed,'bounds':world,'center':(cx,cy),'tap_width':tap_width})
        enclosure = world.inflate(gap)
    return {'core':core,'rings':rings,'bounds':rings[-1]['bounds']}


def plan_guardring_bounds(ctx, pdk, config):
    plan = _plan(ctx, pdk, config)
    ctx._ordinary_ring_plan = (id(ctx.component),plan)
    return plan['bounds']


def add_macro_guardrings(ctx, top, pdk, config, router_config):
    _check(ctx,pdk,config)
    cached = getattr(ctx,'_ordinary_ring_plan',None)
    plan = cached[1] if cached and cached[0] == id(ctx.component) else _plan(ctx,pdk,config)
    records = []
    for ring in plan['rings']:
        ref = top.add_ref(ring['component'])
        ref.move(ring['center'])
        metal = _metal_obstacles(ctx,ref,pdk,'GUARD_'+ring['role'],ring['net'])
        _ring_connections(ctx,top,pdk,ring,router_config)
        records.append({'role':ring['role'],'net':ring['net'],'doping':ring['doping'],
                        'bounds':_box_values(ring['bounds']),'metal':metal,'closed':True})
    return {'mode':'ordinary','rings':records,'bounds':_box_values(plan['bounds'])}
