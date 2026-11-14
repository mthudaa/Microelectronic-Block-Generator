"""Ordinary, connected macro framing and physical interface pins."""
from copy import deepcopy
from dataclasses import dataclass, field, asdict
import math
import re

from mbg.design_context import BoundingBox, Net, Obstacle, PinAccessPoint


def validate_identifier(value, kind="identifier"):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', value):
        raise ValueError(f'invalid {kind}: {value!r}')
    return value


@dataclass
class MacroConfig:
    enabled: bool = False
    guardring: str = 'ordinary'
    supplies: dict = field(default_factory=lambda: {'power': 'vdd', 'ground': 'vss'})
    pins: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, value=None):
        raw = value.as_dict() if isinstance(value, cls) else ({} if value is None else deepcopy(value))
        if not isinstance(raw, dict) or set(raw) - {'schema', 'enabled', 'guardring', 'supplies', 'pins'}:
            raise ValueError('unsupported ordinary macro configuration')
        if raw.get('schema', 'mbg.macro/1') != 'mbg.macro/1':
            raise ValueError('unsupported macro schema')
        if type(raw.get('enabled', False)) is not bool or raw.get('guardring', 'ordinary') != 'ordinary':
            raise ValueError('only ordinary macro guard rings are supported')
        raw.pop('schema', None)
        config = cls(**raw)
        if not isinstance(config.supplies, dict) or set(config.supplies) != {'power', 'ground'}:
            raise ValueError('macro supplies require power and ground')
        for name in config.supplies.values():
            validate_identifier(name, 'supply')
        if len({s.lower() for s in config.supplies.values()}) != 2:
            raise ValueError('macro power and ground must differ')
        if not isinstance(config.pins, dict):
            raise ValueError('macro pins must be an object')
        for name, pin in config.pins.items():
            validate_identifier(name, 'pin')
            if not isinstance(pin, dict) or set(pin) - {'edge', 'offset', 'width', 'height', 'layer', 'rect', 'direction'}:
                raise ValueError(f'unsupported pin configuration for {name}')
            if pin.get('edge', 'W') not in ('W', 'E', 'N', 'S'):
                raise ValueError(f'invalid edge for {name}')
            if pin.get('direction', 'inout') not in ('input', 'output', 'inout', 'power', 'ground'):
                raise ValueError(f'invalid direction for {name}')
            for key in ('offset', 'width', 'height'):
                if key in pin and (not isinstance(pin[key], (int, float)) or not math.isfinite(pin[key]) or pin[key] <= 0):
                    raise ValueError(f'{name}: {key} must be positive and finite')
            if 'rect' in pin:
                r = pin['rect']
                if not isinstance(r, (list, tuple)) or len(r) != 4 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in r) or r[0] >= r[2] or r[1] >= r[3]:
                    raise ValueError(f'{name}: invalid rectangle')
        return config

    def as_dict(self):
        return {'schema': 'mbg.macro/1', **asdict(self)}


def resolve_interface(netlist, config):
    from mbg.spice_parser import _logical_lines
    declarations = [line.split() for line in _logical_lines(netlist) if line.lower().startswith('.subckt ')]
    if len(declarations) != 1:
        raise ValueError('ordinary macros require exactly one flat subcircuit')
    header = declarations[0]
    validate_identifier(header[1], 'cell')
    ports = header[2:]
    for name in ports:
        validate_identifier(name, 'port')
    names = {n.lower(): n for n in ports}
    if len(names) != len(ports):
        raise ValueError('duplicate macro ports')
    config = MacroConfig.from_dict(config)
    config.supplies = {role: names.get(name.lower(), name) for role, name in config.supplies.items()}
    if any(name not in ports for name in config.supplies.values()):
        raise ValueError('ordinary macro supplies must be explicit subcircuit ports')
    return config, {'cell': header[1], 'ports': ports}


def prepare_macro(ctx, top, pdk, config, router_config=None):
    from mbg.router import RouterConfig, grid_params, snap_to_grid
    from mbg.macro_guardring import plan_guardring_bounds, add_macro_guardrings
    config = MacroConfig.from_dict(config)
    router_config = router_config or RouterConfig()
    if set(config.pins) - set(ctx.top_ports):
        raise ValueError('macro pin overrides name unknown ports')
    origin, pitch = grid_params(ctx, router_config)
    frame = plan_guardring_bounds(ctx, pdk, config).inflate(6.0)
    # Enlarging the routing extent must preserve the existing rail grid.
    margin = router_config.margin
    low = [ctx.rules.snap(origin[i] + math.floor((v-margin-origin[i])/pitch)*pitch + margin)
           for i, v in enumerate((frame.xmin, frame.ymin))]
    bb = BoundingBox(low[0], low[1], ctx.rules.snap(frame.xmax), ctx.rules.snap(frame.ymax))
    ctx.macro_bbox = bb
    ctx.device_bboxes['MACRO_FRAME'] = bb
    rings = add_macro_guardrings(ctx, top, pdk, config, router_config)
    rules = ctx.rules
    pins = []
    edges = {'power': 'N', 'ground': 'S', 'input': 'W', 'output': 'E', 'inout': 'W'}
    for index, name in enumerate(ctx.top_ports):
        spec = config.pins.get(name, {})
        direction = ('power' if name == config.supplies['power'] else 'ground' if name == config.supplies['ground'] else spec.get('direction', 'inout'))
        if name in config.supplies.values() and spec.get('direction', direction) != direction:
            raise ValueError('supply pin direction conflicts with supply role')
        edge = spec.get('edge', edges[direction])
        layer = spec.get('layer', 'met5' if direction in ('power', 'ground') else 'met3')
        if layer not in rules.metals:
            raise ValueError(f'pin {name}: unavailable metal {layer}')
        access = router_config.access_layer
        pad = max(rules.via_footprint(layer, access), rules.min_width(layer))
        size = max(1.5, pad+pitch+2*rules.min_spacing(layer))
        width, height = spec.get('width', size), spec.get('height', size)
        length = bb.height if edge in ('W', 'E') else bb.width
        desired = spec.get('offset', length*(index+1)/(len(ctx.top_ports)+1))
        offsets = [desired] if 'offset' in spec or 'rect' in spec else sorted(
            [pitch*k for k in range(1, int(length/pitch))], key=lambda x: (abs(x-desired), x))
        chosen = None
        for offset in offsets:
            if 'rect' in spec:
                r = spec['rect']
                rect = BoundingBox(bb.xmin+r[0], bb.ymin+r[1], bb.xmin+r[2], bb.ymin+r[3])
                cx, cy = snap_to_grid(ctx, *rect.center, router_config)
            else:
                inset = max(width, height)/2 + rules.min_spacing(layer)
                point = {'W': (bb.xmin+inset, bb.ymin+offset), 'E': (bb.xmax-inset, bb.ymin+offset),
                         'S': (bb.xmin+offset, bb.ymin+inset), 'N': (bb.xmin+offset, bb.ymax-inset)}[edge]
                cx, cy = snap_to_grid(ctx, *point, router_config)
                rect = BoundingBox(rules.snap(cx-width/2), rules.snap(cy-height/2),
                                   rules.snap(cx+width/2), rules.snap(cy+height/2))
            landing = BoundingBox(cx-pad/2, cy-pad/2, cx+pad/2, cy+pad/2)
            if not bb.contains_box(rect) or not rect.contains_box(landing):
                continue
            if any(rect.inflate(rules.min_spacing(layer)).overlaps(BoundingBox(*p['rect'])) for p in pins if p['layer'] == layer):
                continue
            if any(ob.layer == layer and ob.net != name and rect.inflate(rules.min_spacing(layer)).overlaps(ob.bbox) for ob in ctx.obstacles):
                continue
            chosen = rect, cx, cy
            break
        if chosen is None:
            raise ValueError(f'pin {name}: no legal slot inside macro bounds')
        rect, cx, cy = chosen
        owner = 'PIN_'+name
        top.add_polygon([(rect.xmin,rect.ymin),(rect.xmax,rect.ymin),(rect.xmax,rect.ymax),(rect.xmin,rect.ymax)], layer=pdk.get_glayer(layer))
        ctx.add_obstacle(Obstacle(layer, rect, owner=owner, kind='macro_pin', net=name))
        if layer != access:
            from glayout import via_stack
            from mbg.macro_guardring import _metal_obstacles
            ref = top.add_ref(via_stack(pdk, access, layer, centered=True))
            ref.move((cx, cy))
            _metal_obstacles(ctx, ref, pdk, owner, name)
        ctx.nets.setdefault(name, Net(name)).terminals.append((owner, 'pin'))
        ctx.add_access_point(PinAccessPoint(owner, 'pin', name, access, cx, cy,
                             {'W':180,'E':0,'N':90,'S':270}[edge], width=pad))
        pins.append({'name': name, 'direction': direction, 'layer': layer, 'edge': edge,
                     'rect': [rect.xmin,rect.ymin,rect.xmax,rect.ymax], 'access': [cx,cy]})
    result = {'schema':'mbg.macro/1', 'cell':ctx.name, 'bounds':[bb.xmin,bb.ymin,bb.xmax,bb.ymax],
              'pins':pins, 'supplies':config.supplies, 'guardrings':rings, 'config':config.as_dict()}
    ctx.macro_interface = result
    return result


def label_macro_pins(ctx, top, pdk):
    for pin in ctx.macro_interface['pins']:
        x0,y0,x1,y1 = pin['rect']
        top.add_polygon([(x0,y0),(x1,y0),(x1,y1),(x0,y1)], layer=pdk.get_glayer(pin['layer']+'_pin'))
        top.add_label(pin['name'], position=((x0+x1)/2,(y0+y1)/2), layer=pdk.get_glayer(pin['layer']+'_label'))
