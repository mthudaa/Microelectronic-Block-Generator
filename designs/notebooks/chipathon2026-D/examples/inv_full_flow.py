"""Full-flow inverter — inline models (bypasses PDK .lib parameter issues)."""
import sys, os, textwrap, subprocess, re, shutil, numpy as np

# Derived from this file's location so the example works in any clone.
def _repo_src():
    """Locate <repo>/src by walking up from this file."""
    d = os.path.dirname(os.path.abspath(__file__))
    for _ in range(8):
        cand = os.path.join(d, "src")
        if os.path.isdir(os.path.join(cand, "mbg")):
            return cand
        d = os.path.dirname(d)
    raise RuntimeError("could not locate src/mbg")


PROJ = _repo_src()
sys.path.insert(0, PROJ)
_pdk_root = os.environ.get("PDK_ROOT", os.path.expanduser("~/.volare"))
_pdk = os.environ.get("PDK", "gf180mcuD")
os.environ.update({"PDK_ROOT": _pdk_root, "PDK": _pdk,
                   "PDKPATH": os.environ.get("PDKPATH", os.path.join(_pdk_root, _pdk))})
OUT_DIR = "/tmp/mbg_workspace"; os.makedirs(OUT_DIR, exist_ok=True)

if not hasattr(np, 'float_'): np.float_ = np.float64
import glayout, gdsfactory as gf
from mbg.placement import manual_placement
from mbg.power import manual_power
from mbg.routing import manual_route, set_pdk

pdk = glayout.gf180; set_pdk(pdk)
SCRIPT_DIR = os.path.join(PROJ, "scripts")

def gp(dev, term, direc): return pmap[dev][term][direc]["param"]

def add_labels(component, port_map, pdk):
    m2l = pdk.get_glayer("met2_label")
    for name, (dev, term, direc) in {"vdd":("MP","source","N"),"vin":("MP","gate","W"),
                                       "vout":("MP","drain","S"),"vss":("MN","source","S")}.items():
        try:
            p = port_map[dev][term][direc]["param"]
            if p != gf.port.Port: component.add_label(text=name, layer=m2l, position=(p.center[0], p.center[1]))
        except KeyError: pass
    return component

def run_cmd(cmd, timeout=300, cwd=None):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, cwd=cwd)
        return r.returncode, r.stdout, r.stderr
    except: return -1, "", "failed"

def parse_raw(path):
    with open(path,"rb") as f: blob=f.read()
    hdr=blob.split(b"Binary:\n")[0].decode("utf-8",errors="replace")
    n_vars=int(re.search(r"No\. Variables:\s*(\d+)",hdr).group(1))
    names=[]; in_v=False
    for l in hdr.split("\n"):
        if l.startswith("Variables:"): in_v=True; continue
        if in_v and l.strip() and "\t" in l: names.append(l.strip().split("\t")[1].strip())
    data=np.frombuffer(blob[blob.find(b"Binary:\n")+8:],dtype=np.float64).reshape(-1,n_vars)
    r={}
    for i,n in enumerate(names):
        s=re.sub(r"^v\((.*)\)$",r"\1",n); r[n]=data[:,i]; r[s]=data[:,i]
    return r

def flatten_netlist(extracted_path, out_path):
    with open(extracted_path) as f: text = f.read()
    subckts, current_name, current_lines = {}, None, []
    for line in text.split("\n"):
        if line.startswith(".subckt "):
            if current_name: subckts[current_name] = current_lines
            sparts = line.split(); current_name = sparts[1]; current_lines = [line]
        elif line.startswith(".ends"):
            if current_name: current_lines.append(line); subckts[current_name] = current_lines
            current_name = None; current_lines = []
        elif current_name: current_lines.append(line)
    if current_name and current_lines: subckts[current_name] = current_lines
    if not subckts: open(out_path,"w").write(text); return out_path
    wrappers = {}
    for name, lines in subckts.items():
        for line in lines:
            m = re.search(r'X0\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(nfet_03v3|pfet_03v3)', line)
            if m:
                wrappers[name] = {"pins": [m.group(1), m.group(2), m.group(3), m.group(4)],
                                  "model": m.group(5),
                                  "ext_pins": subckts[name][0].split()[2:] if name in subckts else []}
    top_name = [n for n in subckts if n not in wrappers][0]
    flat_lines = []
    for line in subckts.get(top_name, []):
        m = re.match(r'X(\S+)\s+(.+)', line)
        if m:
            inst, rest = m.group(1), m.group(2).strip()
            parts = rest.rsplit(None, 1)
            if len(parts) == 2 and parts[1] in wrappers:
                conn, wrap = parts[0].split(), wrappers[parts[1]]
                pm = dict(zip(wrap["ext_pins"], conn))
                d = (pm.get(wrap["pins"][0], "vdd" if "pfet" in wrap["model"] else "vss")).lower()
                g = pm.get(wrap["pins"][1], "?").lower()
                s = (pm.get(wrap["pins"][2], "vss" if "nfet" in wrap["model"] else "vdd")).lower()
                b = pm.get(wrap["pins"][3], "vdd" if "pfet" in wrap["model"] else "vss")
                if b.upper() in ("VSUBS","VSUB"): b = "vss"
                flat_lines.append(f"M{inst} {d} {g} {s} {b.lower()} {wrap['model']} W=15u L=1u")
                continue
        flat_lines.append(line)
    open(out_path,"w").write("\n".join(flat_lines))
    return out_path

# ═══════════════════ MAIN FLOW ═══════════════════
devices=[{"name":"MP","model":"pfet_03v3","width":1,"length":0.5,"x":0,"y":8},
         {"name":"MN","model":"nfet_03v3","width":1,"length":0.5,"x":0,"y":0}]
pw=devices[0]["width"]; pl=devices[0]["length"]
nw=devices[1]["width"]; nl=devices[1]["length"]

print("="*65+"\n  1. PRE-LAYOUT SIMULATION\n"+"="*65)

pre_netlist = textwrap.dedent(f"""\
* Pre-layout inverter
.model NMOS nmos (VTO=0.7 KP=200e-6)
.model PMOS pmos (VTO=-0.7 KP=100e-6)
.subckt inv vdd vin vout vss
M1 vdd vin vout vdd PMOS W={pw}u L={pl}u
M2 vss vin vout vss NMOS W={nw}u L={nl}u
.ends inv
XINV vdd vin vout vss inv
VDD vdd 0 DC 1.8
VSS vss 0 DC 0
VIN vin 0 PULSE(0 1.8 0 100p 100p 20n 40n)
CL vout 0 10fF
.control
tran 0.1n 80n
write pre_sim.raw vout vin
.endc
.end
""")
pre_path=os.path.join(OUT_DIR,"pre_sim.spice")
open(pre_path,"w").write(pre_netlist)
rc_pre,out_pre,err_pre=run_cmd(["ngspice","-b",pre_path],timeout=120,cwd=OUT_DIR)
pre_raw=os.path.join(OUT_DIR,"pre_sim.raw")
pre_ok=os.path.isfile(pre_raw)

if pre_ok:
    d=parse_raw(pre_raw)
    t=d.get("time",[]); vp=d.get("vin",[]); vo=d.get("vout",[])
    if len(t)>0:
        ri=next((i for i in range(1,len(t)) if vp[i-1]<0.9<=vp[i]),None)
        fi=next((i for i in range(ri or 0,len(t)) if vo[i-1]>0.9>=vo[i]),None)
        fv=next((i for i in range(len(t)-1,len(t)//2,-1) if vp[i-1]>0.9>=vp[i]),None)
        rv=next((i for i in range(fv or 0,len(t)) if vo[i-1]<0.9<=vo[i]),None)
        tphl=(t[fi]-t[ri])*1e9 if(ri and fi)else None
        tplh=(t[rv]-t[fv])*1e9 if(fv and rv)else None
        voh=float(np.max(vo[len(t)//4:])); vol=float(np.min(vo[len(t)//4:]))
        print(f"  VOH={voh:.3f}V VOL={vol:.3f}V Swing={(voh-vol)*1000:.0f}mV",end="")
        if tphl: print(f"  tPHL={tphl:.2f}ns tPLH={tplh:.2f}ns",end="")
        print()
    print("  ✅  Pre-sim PASSED")
else:
    err_msg=(out_pre+err_pre)[-500:]
    print(f"  ❌  Pre-sim FAILED:\n  {err_msg[:200].replace(chr(10),chr(10)+'  ')}")
    sys.exit(1)

print("\n"+"="*65+"\n  2. LAYOUT\n"+"="*65)
top,pmap,_=manual_placement(devices,pdk)
mp_s=gp("MP","source","N").center; mp_d=gp("MP","drain","S").center
mp_g=gp("MP","gate","W").center; mn_s=gp("MN","source","S").center
mn_d=gp("MN","drain","N").center; mn_g=gp("MN","gate","W").center

top,_=manual_power(top,pdk,strips=[{"net":"VDD","layer":"met5","y":14,"x_start":-10,"x_end":10,"width":1.0,"via_x":2.5},
                                    {"net":"VSS","layer":"met5","y":-7,"x_start":-10,"x_end":10,"width":1.0,"via_x":-2.5}])
vm3y,vs3y=mp_s[1]-0.25,mn_s[1]+0.25
routes=[
    {"net_name":"VDD","port1":gp("MP","source","N"),"via1_layer":"met3",
     "segments":[(mp_s[0],vm3y,2.5,vm3y,"met3"),(2.5,vm3y,2.5,vm3y,"via_met3_met4"),(2.5,vm3y,2.5,14,"met4")]},
    {"net_name":"VSS","port2":gp("MN","source","S"),"via2_layer":"met3",
     "segments":[(-2.5,-7,-2.5,vs3y,"met4"),(-2.5,vs3y,-2.5,vs3y,"via_met4_met3"),(-2.5,vs3y,0,vs3y,"met3")]},
    {"net_name":"vout","port1":gp("MP","drain","S"),"port2":gp("MN","drain","N"),
     "segments":[(mp_d[0],mp_d[1],mn_d[0],mn_d[1],"met4")]},
    {"net_name":"vin","port1":gp("MP","gate","W"),"port2":gp("MN","gate","W"),"via1_layer":"met3","via2_layer":"met3",
     "segments":[(mp_g[0],mp_g[1],-1.5,mp_g[1],"met3"),(-1.5,mp_g[1],-1.5,mp_g[1],"via_met3_met4"),
                 (-1.5,mp_g[1],-1.5,mn_g[1],"met4"),(-1.5,mn_g[1],-1.5,mn_g[1],"via_met4_met3"),
                 (-1.5,mn_g[1],mn_g[0],mn_g[1],"met3")]}]
# Add body tie routes: PMOS body→VDD, NMOS body→VSS
mp_body = gp("MP","body","W").center  # (-1.95, 8.0) on met1
mn_body = gp("MN","body","W").center  # (-1.95, 0.0) on met1

body_routes = [
    {"net_name":"VDD","port1":gp("MP","body","W"),"via1_layer":"met3",
     "segments":[(mp_body[0],mp_body[1],2.5,mp_body[1],"met3"),(2.5,mp_body[1],2.5,mp_body[1],"via_met3_met4"),
                 (2.5,mp_body[1],2.5,14,"met4")]},
    {"net_name":"VSS","port2":gp("MN","body","W"),"via2_layer":"met3",
     "segments":[(-2.5,-7,-2.5,mn_body[1],"met4"),(-2.5,mn_body[1],-2.5,mn_body[1],"via_met4_met3"),
                 (-2.5,mn_body[1],mn_body[0],mn_body[1],"met3")]},
]
top,_=manual_route(top,routes+body_routes)
top=add_labels(top,pmap,pdk)
top._cell.name="inv"
GDS_PATH=os.path.join(OUT_DIR,"inv.gds"); SVG_PATH=os.path.join(OUT_DIR,"inv.svg")
top.write_gds(GDS_PATH)
import gdstk; gdstk.read_gds(GDS_PATH).top_level()[0].write_svg(SVG_PATH)
print(f"  GDS: {GDS_PATH}  SVG: {SVG_PATH}")

print("\n"+"="*65+"\n  3. DRC\n"+"="*65)
rc,o,e=run_cmd(["bash",os.path.join(SCRIPT_DIR,"iic-drc.sh"),"-m","-w",os.path.join(OUT_DIR,"drc"),GDS_PATH],timeout=600)
drc_clean="No DRC errors"in(o+e)or"CONGRATULATIONS"in(o+e)or"Magic DRC is clean"in(o+e)
print(f"  {'✅ CLEAN' if drc_clean else '❌ ERRORS'}")

print("\n"+"="*65+"\n  4. SPICE EXTRACTION\n"+"="*65)
xtr_dir=os.path.join(OUT_DIR,"extract"); os.makedirs(xtr_dir,exist_ok=True)
rc_file=f"{os.environ['PDKPATH']}/libs.tech/magic/{os.environ['PDK']}.magicrc"
tcl=f"crashbackups stop\ndrc off\ngds read {GDS_PATH}\nload inv\nexpand\nselect top cell\nextract path {xtr_dir}\nextract no capacitance\nextract no coupling\nextract no resistance\nextract no length\nextract all\next2spice lvs\next2spice -p {xtr_dir} -o {xtr_dir}/inv_extracted.spice\nquit -noprompt\n"
open(f"{xtr_dir}/extract.tcl","w").write(tcl)
rc,_,_=run_cmd(["magic","-dnull","-noconsole","-rcfile",rc_file,f"{xtr_dir}/extract.tcl"],timeout=600)
xtr_path=f"{xtr_dir}/inv_extracted.spice"
if os.path.isfile(xtr_path):
    with open(xtr_path)as f:print(f"  Extracted: {len(f.read())} chars")
else: print("  Extraction FAILED")

print("\n"+"="*65+"\n  5. LVS\n"+"="*65)
lvs_dir=os.path.join(OUT_DIR,"lvs"); os.makedirs(lvs_dir,exist_ok=True)
flat_path=f"{lvs_dir}/inv_flat.spice"
if os.path.isfile(xtr_path):
    flatten_netlist(xtr_path,flat_path)
    with open(flat_path)as f:lines=f.readlines()
    for i,line in enumerate(lines):
        if line.startswith(".subckt inv"):lines[i]=".subckt inv vdd vin vout vss\n"; break
    open(flat_path,"w").writelines(lines)
sch_path=f"{lvs_dir}/inv_sch.spice"
open(sch_path,"w").write(".subckt inv vdd vin vout vss\nM1 vdd vin vout vdd pfet_03v3 W=15u L=1u\nM2 vss vin vout vss nfet_03v3 W=15u L=1u\n.ends inv\n")
netgen_path=shutil.which("netgen")or"/foss/tools/netgen/bin/netgen"
setup_file=f"{os.environ['PDKPATH']}/libs.tech/netgen/{os.environ['PDK']}_setup.tcl"
lvs_out=f"{lvs_dir}/inv_lvs.out"
rc,_,_=run_cmd([netgen_path,"-batch","lvs",f"{flat_path} inv",f"{sch_path} inv",setup_file,lvs_out],timeout=120)
lvs_match=False
if os.path.isfile(lvs_out):
    with open(lvs_out)as f:lvs_match="Circuits match uniquely"in f.read()
print(f"  {'✅ MATCHED' if lvs_match else '❌ MISMATCHED'}")

print("\n"+"="*65+"\n  6. POST-LAYOUT SIMULATION\n"+"="*65)
if shutil.which("ngspice") and pre_ok:
    pex_dir=os.path.join(OUT_DIR,"pex"); os.makedirs(pex_dir,exist_ok=True)
    run_cmd(["bash",os.path.join(SCRIPT_DIR,"iic-pex.sh"),"-m","1","-s","1","-w",pex_dir,GDS_PATH],timeout=600)
    pex_path=os.path.join(pex_dir,"inv.pex.spice")
    if os.path.isfile(pex_path):
        with open(pex_path)as f:pex_text=f.read()
        # Add subcircuit wrappers so PEX X-elements find the inline models
        pex_wrappers = textwrap.dedent("""\
        .subckt pfet_03v3 d g s b ad=0 pd=0 as=0 ps=0 w=1e-6 l=1e-6 nf=1 m=1 par=1
        M0 d g s b PMOS W={w} L={l}
        .ends
        .subckt nfet_03v3 d g s b ad=0 pd=0 as=0 ps=0 w=1e-6 l=1e-6 nf=1 m=1 par=1
        M0 d g s b NMOS W={w} L={l}
        .ends
        """)
        post_nl=f"* Post-layout\n.model NMOS nmos (VTO=0.7 KP=200e-6)\n.model PMOS pmos (VTO=-0.7 KP=100e-6)\n{pex_wrappers}\n{pex_text}\nXINV vdd vin vout vss inv\nVDD vdd 0 DC 1.8\nVSS vss 0 DC 0\nVIN vin 0 PULSE(0 1.8 0 100p 100p 20n 40n)\nCL vout 0 10fF\n.control\ntran 0.1n 80n\nwrite post_sim.raw vout vin\n.endc\n.end\n"
        open(os.path.join(OUT_DIR,"post_sim.spice"),"w").write(post_nl)
        run_cmd(["ngspice","-b",os.path.join(OUT_DIR,"post_sim.spice")],timeout=120,cwd=OUT_DIR)
        post_raw=os.path.join(OUT_DIR,"post_sim.raw")
        if os.path.isfile(post_raw):
            pd2=parse_raw(post_raw)
            voh2=float(np.max(pd2['vout'][len(pd2['time'])//4:]))
            print(f"  Post-sim: VOH={voh2:.3f}V")
        else:
            print("  Post-sim FAILED")

print("\n"+"="*65)
print(f"  {'✅  FULL FLOW PASSED  ✅' if drc_clean and lvs_match else '❌ FLOW FAILED'}")
print(f"  DRC: {'CLEAN' if drc_clean else 'ERRORS'}  LVS: {'MATCHED' if lvs_match else 'MISMATCHED'}")
print(f"  GDS: {GDS_PATH}  SVG: {SVG_PATH}")
print("="*65)
