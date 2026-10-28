"""The one list of agent tools. CLI, MCP, OpenCode wrappers and docs read it.

A tool is a name, a one-line summary, a JSON-Schema for its input and a
handler named by string (``"module:function"``), so listing tools never
imports the layout stack. ``long`` tools run as background jobs (see
:mod:`mbg.agent.runio`); the rest run in-process.

Names are dotted (``layout.generate``); the CLI spells them as nested
commands (``mbg layout generate``) and also accepts the dotted form. MCP
names cannot contain dots, so tools that share an ``mcp`` group are
published as one MCP tool with a selector argument (``verify`` with
``check: drc|lvs|pex``) — fewer, coarser tools keep the schema an agent
has to carry in every prompt small.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class Tool:
    id: str
    summary: str
    schema: Dict[str, Any]
    handler: str
    long: bool = False
    #: MCP exposure: None = not published; "" = published under its own
    #: name (dots -> underscores); "group:key=value" = merged into MCP tool
    #: ``group`` and selected when argument ``key`` equals ``value``.
    mcp: Optional[str] = ""
    stage: Optional[str] = None          # stage directory inside a design workspace
    examples: tuple = ()
    #: a light tool gets a run directory only inside a design workspace;
    #: a one-off static check should not leave a directory behind
    light: bool = False

    @property
    def group(self) -> str:
        return self.id.split(".")[0]

    @property
    def cli(self) -> str:
        return "mbg " + self.id.replace(".", " ")

    def as_dict(self) -> Dict[str, Any]:
        return {"id": self.id, "cli": self.cli, "summary": self.summary,
                "long": self.long, "input_schema": self.schema,
                "examples": list(self.examples)}


# ── schema helpers ────────────────────────────────────────────────────

def _obj(props: Dict[str, Any], required: List[str] = (),
         positional: List[str] = ()) -> Dict[str, Any]:
    s: Dict[str, Any] = {"type": "object", "properties": props,
                         "additionalProperties": False}
    if required:
        s["required"] = list(required)
    if positional:
        s["x-positional"] = list(positional)
    return s


def S(desc: str, **kw) -> Dict[str, Any]:
    return {"type": "string", "description": desc, **kw}


def N(desc: str, **kw) -> Dict[str, Any]:
    return {"type": "number", "description": desc, **kw}


def I(desc: str, **kw) -> Dict[str, Any]:
    return {"type": "integer", "description": desc, **kw}


def B(desc: str, **kw) -> Dict[str, Any]:
    return {"type": "boolean", "description": desc, **kw}


def A(desc: str, items: str = "string", **kw) -> Dict[str, Any]:
    return {"type": "array", "items": {"type": items}, "description": desc, **kw}


def O(desc: str, **kw) -> Dict[str, Any]:
    return {"type": "object", "description": desc, **kw}


def FILE_OR_OBJ(desc: str) -> Dict[str, Any]:
    return {"type": ["object", "string"],
            "description": desc + " (inline JSON object, or a path to a .json file)"}


_PDK = S("PDK variant or family: gf180mcuD (default), gf180, sky130A, sky130. "
         "Omit to infer it from the netlist's device models.")
_NETLIST = S("Path to a SPICE file with exactly one .subckt. Omit when --design "
             "names a workspace that has one.")
_DESIGN = S("Design workspace name (from `mbg design init`). Artifacts then go "
            "to outputs/<design>/<stage>/ instead of outputs/runs/.")
_WAIT = N("Seconds to wait for a long tool before returning a job id "
          "(default 540 on the CLI, 50 over MCP). The work continues in the "
          "background; collect it with `mbg job wait <id>`.")
_CORNER = S("Process corner, e.g. typical/ff/ss/fs/sf (gf180) or tt/ff/ss/sf/fs "
            "(sky130). 'typical' and 'tt' are accepted for both.")


# ── the tools ─────────────────────────────────────────────────────────

TOOLS: List[Tool] = [
    Tool("doctor",
         "Check the environment: Python stack, Magic/netgen/KLayout/ngspice "
         "versions, installed PDKs. Run first; tells you which stages can run.",
         _obj({"pdk": _PDK}),
         "mbg.agent.handlers.core:doctor",
         examples=("mbg doctor",)),
    Tool("pdk.list", "List supported PDK variants and whether each is installed.",
         _obj({}), "mbg.agent.handlers.core:pdk_list",
         mcp="pdk:action=list", examples=("mbg pdk list",)),
    Tool("pdk.info",
         "What is legal in a PDK: supply, device models with terminal order and "
         "size limits, which devices the layout engine supports, simulation "
         "corners, sign-off decks, the tested complexity ceiling.",
         _obj({"pdk": _PDK,
               "section": S("Only one section", enum=["devices", "sim", "verification",
                                                       "supply", "conventions",
                                                       "tested_ceiling"]),
               "model": S("Only this device model")}),
         "mbg.agent.handlers.core:pdk_info",
         mcp="pdk:action=info",
         examples=("mbg pdk info --pdk gf180mcuD --section devices",
                   "mbg pdk info --model pnp_10p00x10p00")),
    Tool("design.init",
         "Create a design workspace outputs/<name>/ (AGENTS.md artifact layout + "
         "experiment.json). Later calls take --design <name>.",
         _obj({"name": S("Workspace name: 3-128 lowercase letters, digits and '-' "
                         "(it is the experiment id)"),
               "pdk": _PDK,
               "netlist": S("SPICE file to copy in as generated_netlist.spice"),
               "spec": FILE_OR_OBJ("Specification: {metric: {op, target, unit, tol}}"),
               "prompt": S("Original request text, kept as prompt.txt"),
               "model": S("Identifier of the AI model driving this experiment "
                          "(recorded in experiment.json)"),
               "prompt_level": S("Prompt detail level", enum=["minimal",
                                 "constraint-based", "detailed"]),
               "description": S("One-line description")},
              required=["name"], positional=["name"]),
         "mbg.agent.handlers.design:init",
         mcp="design:action=init",
         examples=("mbg design init bgr1 --pdk gf180mcuD --netlist bgr.spice",)),
    Tool("design.status",
         "Summarise a workspace: which stages ran, their status, key metrics and "
         "artifacts.",
         _obj({"name": S("Workspace name")}, required=["name"], positional=["name"]),
         "mbg.agent.handlers.design:status",
         mcp="design:action=status", examples=("mbg design status bgr1",)),
    Tool("netlist.check",
         "Static checks before simulating or laying out: syntax, models vs the "
         "PDK catalogue, terminal counts, W/L limits and units, body ties, "
         "instance prefixes, floating nets, layout support per device, and "
         "complexity against the tested ceiling. No EDA tools needed.",
         _obj({"netlist": _NETLIST, "pdk": _PDK, "design": _DESIGN},
              positional=["netlist"]),
         "mbg.agent.handlers.netlist:check",
         stage="netlist_check", light=True, examples=("mbg netlist check ota.spice",)),
    Tool("sim.run",
         "Simulate the subcircuit with ngspice in a generated testbench: op, dc "
         "(source, supply or temp sweep), ac or tran. Returns per-probe "
         "summaries; full data goes to CSV in the run directory.",
         _obj({"netlist": _NETLIST, "pdk": _PDK, "design": _DESIGN,
               "analysis": S("Analysis", enum=["op", "dc", "ac", "tran"]),
               "corner": _CORNER,
               "temp": N("Temperature in C (default 27)"),
               "supplies": O("DC supplies {node: volts}, e.g. {\"VDD\": 3.3, \"VSS\": 0}"),
               "sources": O("Other DC sources {node: volts or ngspice source spec}"),
               "isources": O("Current sources {node: amps} pushing current INTO "
                             "the node from ground; {node: [from_node, amps]} "
                             "from another node"),
               "loads": O("Load capacitors {node: value}, e.g. {\"VREF\": \"1p\"}"),
               "probes": A("Nodes or expressions to record, e.g. VREF i(Vsupply0)"),
               "sweep": O("dc: {source, start, stop, step}; source may be a "
                          "supply node or 'temp'"),
               "ac": O("ac: {fstart, fstop, points, node}"),
               "tran": O("tran: {step, stop}"),
               "post_layout": B("Simulating an extracted (PEX) netlist")},
              required=["analysis"], positional=["netlist"]),
         "mbg.agent.handlers.sim:run",
         stage="pre_simulation",
         examples=("mbg sim run ota.spice --analysis op --supplies '{\"VDD\":3.3,\"VSS\":0}' "
                   "--sources '{\"INP\":1.65,\"INN\":1.65}' --probes OUT",)),
    Tool("measure.vref",
         "Characterise a voltage reference: VREF at 27 C, temperature coefficient "
         "(box method), line regulation, supply current, IBIAS sensitivity, "
         "PSRR, startup, across corners; evaluates a spec. Works on schematic "
         "and PEX netlists.",
         _obj({"netlist": _NETLIST, "pdk": _PDK, "design": _DESIGN,
               "ports": O("Port roles {vdd, vss, vref, ibias}; default: the "
                          "ports named VDD, VSS, VREF, IBIAS"),
               "vdd": N("Nominal supply (default: the PDK nominal)"),
               "vdd_range": A("Line-regulation window [lo, hi] in V", "number"),
               "temp_range": A("Temperature sweep [lo, hi, step] in C", "number"),
               "ibias": N("Bias current into IBIAS in A (default 20e-6; 0 = none)"),
               "ibias_dir": S("'source' pushes IBIAS into the pin, 'sink' pulls it "
                              "out", enum=["source", "sink"]),
               "ibias_sweep": A("IBIAS values for the sensitivity check, A", "number"),
               "cl": S("Load capacitance on VREF (default 1p)"),
               "corners": A("Corners to run (default: the nominal corner only; "
                            "'all' for every corner)"),
               "quick": B("Skip PSRR, startup and IBIAS sensitivity"),
               "spec": FILE_OR_OBJ("Specification, or 'vref_md' for "
                                   "prompt-test/VREF.md, or 'bandgap' for the "
                                   "stretch targets"),
               "post_layout": B("Simulating an extracted (PEX) netlist")},
              positional=["netlist"]),
         "mbg.agent.handlers.measure:vref",
         stage="pre_simulation",
         examples=("mbg measure vref vref.spice --spec vref_md --corners all",)),
    Tool("measure.ota",
         "Characterise an amplifier: DC gain, -3 dB bandwidth, unity-gain "
         "frequency, phase margin and supply current.",
         _obj({"netlist": _NETLIST, "pdk": _PDK, "design": _DESIGN,
               "out": S("Output node"), "inp": S("Non-inverting input node"),
               "inn": S("Inverting input node (biased at the common mode)"),
               "supplies": O("{node: volts}"), "bias": O("Other DC nodes {node: volts}"),
               "vcm": N("Input common mode (default VDD/2)"),
               "cl": S("Load capacitance on the output (default 1p)"),
               "corner": _CORNER, "spec": FILE_OR_OBJ("Specification"),
               "post_layout": B("Simulating an extracted (PEX) netlist")},
              required=["out", "inp"], positional=["netlist"]),
         "mbg.agent.handlers.measure:ota",
         stage="pre_simulation",
         examples=("mbg measure ota ota.spice --out OUT --inp INP --inn INN",)),
    Tool("spec.check",
         "Evaluate metrics against a specification; PASS only if every required "
         "spec is met.",
         _obj({"metrics": FILE_OR_OBJ("Measured metrics {name: value}"),
               "spec": FILE_OR_OBJ("Specification {name: {op, target, unit, tol, "
                                   "required}}, or 'vref_md' / 'bandgap'")},
              required=["metrics", "spec"]),
         "mbg.agent.handlers.spec:check",
         examples=("mbg spec check --metrics m.json --spec spec.json",)),
    Tool("layout.generate",
         "SPICE -> GDS with the analog placer and DRC-aware router, then Magic + "
         "KLayout DRC, netgen LVS and PEX. Placement hints steer the placer.",
         _obj({"netlist": _NETLIST, "pdk": _PDK, "design": _DESIGN,
               "hints": FILE_OR_OBJ("Placement hints: {rows: {dev: row}, order: "
                                    "{row: [devs]}, groups: [{kind, devices}], "
                                    "fixed: {dev: {x, y}}, array: [{devices, cols}]}"),
               "placement": O("PlacementConfig overrides, e.g. {channel_x: 3}"),
               "router": O("RouterConfig overrides"),
               "verify": B("Run DRC/LVS/PEX after layout (default true)"),
               "wait_s": _WAIT},
              positional=["netlist"]),
         "mbg.agent.handlers.layout:generate",
         long=True, stage="layout",
         examples=("mbg layout generate ota.spice",
                   "mbg layout generate --design bgr1 --hints hints.json")),
    Tool("layout.view",
         "Text view of a generated layout: ASCII floorplan, device boxes, rows, "
         "per-device nets and routing failures, in the coordinates hints use.",
         _obj({"run": S("Run directory of a layout.generate call, or a "
                        "layout.json file"),
               "design": _DESIGN,
               "format": S("ascii (default) or json", enum=["ascii", "json"]),
               "width": I("ASCII width in characters (default 72)")},
              positional=["run"]),
         "mbg.agent.handlers.layout:view",
         examples=("mbg layout view outputs/runs/<id>",)),
    Tool("verify.drc", "Magic DRC plus the PDK's KLayout deck on a GDS (dual-engine sign-off).",
         _obj({"gds": S("GDS file"), "cell": S("Top cell (default: the GDS top cell)"),
               "pdk": _PDK, "design": _DESIGN, "wait_s": _WAIT},
              required=["gds"], positional=["gds"]),
         "mbg.agent.handlers.verify:drc", long=True, stage="drc",
         mcp="verify:check=drc", examples=("mbg verify drc cell.gds",)),
    Tool("verify.lvs", "netgen LVS of a GDS against its schematic netlist.",
         _obj({"gds": S("GDS file"), "netlist": S("Schematic SPICE"),
               "cell": S("Top cell"), "pdk": _PDK, "design": _DESIGN,
               "wait_s": _WAIT},
              required=["gds", "netlist"], positional=["gds"]),
         "mbg.agent.handlers.verify:lvs", long=True, stage="lvs",
         mcp="verify:check=lvs", examples=("mbg verify lvs cell.gds --netlist cell.spice",)),
    Tool("verify.pex", "Magic parasitic extraction to a SPICE netlist for post-layout simulation.",
         _obj({"gds": S("GDS file"), "cell": S("Top cell"), "pdk": _PDK,
               "design": _DESIGN, "mode": I("Magic PEX mode (default 2: R+C)"),
               "wait_s": _WAIT},
              required=["gds"], positional=["gds"]),
         "mbg.agent.handlers.verify:pex", long=True, stage="pex",
         mcp="verify:check=pex", examples=("mbg verify pex cell.gds",)),
    Tool("flow.run",
         "One call from netlist to sign-off: netlist check, pre-layout "
         "measurement, layout + DRC/LVS/PEX, post-layout measurement on the "
         "extracted netlist, spec evaluation pre vs post.",
         _obj({"netlist": _NETLIST, "pdk": _PDK, "design": _DESIGN,
               "recipe": S("Measurement recipe", enum=["vref", "ota", "none"]),
               "recipe_args": O("Arguments for the recipe (as for measure.<recipe>)"),
               "spec": FILE_OR_OBJ("Specification"),
               "hints": FILE_OR_OBJ("Placement hints (as for layout.generate)"),
               "wait_s": _WAIT},
              positional=["netlist"]),
         "mbg.agent.handlers.flow:run", long=True, stage="flow",
         examples=("mbg flow run --design bgr1 --recipe vref --spec vref_md",)),
    Tool("job.status", "State of a background job; its result when finished.",
         _obj({"id": S("Job id from a long tool's envelope")},
              required=["id"], positional=["id"]),
         "mbg.agent.handlers.job:status", mcp="job:action=status",
         examples=("mbg job status <id>",)),
    Tool("job.wait", "Wait for a background job and return its result.",
         _obj({"id": S("Job id"), "wait_s": _WAIT}, required=["id"], positional=["id"]),
         "mbg.agent.handlers.job:wait", mcp="job:action=wait",
         examples=("mbg job wait <id> --wait-s 300",)),
    Tool("job.cancel", "Stop a background job.",
         _obj({"id": S("Job id")}, required=["id"], positional=["id"]),
         "mbg.agent.handlers.job:cancel", mcp="job:action=cancel"),
]

_BY_ID = {t.id: t for t in TOOLS}


def get(tool_id: str) -> Optional[Tool]:
    return _BY_ID.get(tool_id)


def groups() -> Dict[str, List[Tool]]:
    out: Dict[str, List[Tool]] = {}
    for t in TOOLS:
        out.setdefault(t.group, []).append(t)
    return out


def load_handler(tool: Tool):
    import importlib
    mod, func = tool.handler.split(":")
    return getattr(importlib.import_module(mod), func)


# ── MCP view ──────────────────────────────────────────────────────────

def mcp_tools() -> List[Dict[str, Any]]:
    """MCP tool definitions: name, description, inputSchema, and dispatch."""
    merged: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []
    for t in TOOLS:
        if t.mcp is None:
            continue
        if t.mcp == "":
            name = t.id.replace(".", "_")
            schema = _mcp_schema(t.schema, long=t.long)
            merged[name] = {"name": name, "description": t.summary,
                            "inputSchema": schema, "dispatch": {None: t.id}}
            order.append(name)
            continue
        group, sel = t.mcp.split(":")
        key, value = sel.split("=")
        if group not in merged:
            merged[group] = {"name": group, "description": "", "inputSchema": {
                "type": "object", "properties": {
                    key: {"type": "string", "enum": [], "description": ""}},
                "required": [key], "additionalProperties": False},
                "dispatch": {}, "key": key, "_desc": []}
            order.append(group)
        m = merged[group]
        m["inputSchema"]["properties"][key]["enum"].append(value)
        m["dispatch"][value] = t.id
        m["_desc"].append(f"{key}={value}: {t.summary}")
        for pname, pschema in _mcp_schema(t.schema, long=t.long)["properties"].items():
            m["inputSchema"]["properties"].setdefault(pname, pschema)
    out = []
    for name in order:
        m = merged[name]
        if "_desc" in m:
            m["description"] = " | ".join(m.pop("_desc"))
            m["inputSchema"]["properties"][m["key"]]["description"] = \
                "Which operation: " + ", ".join(
                    m["inputSchema"]["properties"][m["key"]]["enum"])
        out.append(m)
    return out


def _mcp_schema(schema: Dict[str, Any], long: bool) -> Dict[str, Any]:
    s = {k: v for k, v in schema.items() if not k.startswith("x-")}
    s["properties"] = dict(s.get("properties", {}))
    return s
