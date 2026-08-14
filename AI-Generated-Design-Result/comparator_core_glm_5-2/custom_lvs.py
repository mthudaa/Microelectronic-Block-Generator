"""
Custom LVS runner that does NOT use the broken `_merge_schematic_nets`
heuristic in MBG `run_lvs`. It performs:
  1. Extract netlist from GDS using Magic (no net merging).
  2. Fix port order on extracted (`fix_port_order`).
  3. Run netgen LVS directly with PDK setup file (permute adds D/S swap).
"""
import os
import sys
import subprocess as sp

sys.path.insert(0, '/home/huda/.pi')

from core.checks import (
    extract_layout_netlist,
    fix_port_order,
    _flatten_netlist,
    _parse_lvs_summary,
)


def custom_run_lvs(gds_path, sch_path, cell_name, workdir, timeout=600):
    """
    Args:
        gds_path: GDS file path
        sch_path: Original schematic SPICE (untouched)
        cell_name: Top cell name
        workdir: Workdir for outputs
    Returns:
        nget-style result dict like run_lvs.
    """
    os.makedirs(workdir, exist_ok=True)
    gds_path = os.path.abspath(gds_path)
    sch_path = os.path.abspath(sch_path)

    # Read schematic port order
    sch_ports = []
    with open(sch_path) as f:
        for ln in f:
            if ln.startswith('.subckt'):
                sch_ports = ln.strip().split()[2:]
                break
    print(f"[CUSTOM_LVS] schematic ports: {sch_ports}")

    # Extract layout netlist from GDS using Magic (unfiltered).
    xtr = extract_layout_netlist(gds_path, cell_name, workdir, timeout=timeout)
    if not xtr["success"]:
        print(f"[CUSTOM_LVS] Extract FAILED: {xtr.get('log','')[-1500:]}")
        return {"match": False, "log": "Extract FAILED", "summary": {"message": "Magic extract failed"}}
    print(f"[CUSTOM_LVS] Extract OK: {xtr['netlist_path']}")

    # Look at extracted subckt ports:
    with open(xtr["netlist_path"]) as f:
        for ln in f:
            if ln.startswith('.subckt'):
                xtr_ports = ln.strip().split()[2:]
                print(f"[CUSTOM_LVS] extracted ports (raw, hash-named): {xtr_ports}")
                break

    # Copy + flatten
    flat_path = _flatten_netlist(xtr["netlist_path"])
    fix_port_order(flat_path, sch_ports)
    print(f"[CUSTOM_LVS] flatten + port fix done: {flat_path}")

    # Custom netgen setup: standard gf180mcuD setup + permute for D/S swap on MOSFETs
    _pdk_root = os.environ['PDK_ROOT']
    _pdk = os.environ['PDK']
    _pdkpath = os.environ['PDKPATH']
    setup_path = os.path.join(_pdkpath, 'libs.tech', 'netgen', f'{_pdk}_setup.tcl')
    custom_setup = os.path.join(workdir, "lvs_custom_setup.tcl")
    with open(setup_path) as f:
        setup_text = f.read()
    setup_text = setup_text.replace("permute default\n", "")
    setup_text += (
        '\n# Unconditional drain-source permute for MOSFETs (spelled out)\n'
        'permute "-circuit1 pfet_03v3" 1 3\n'
        'permute "-circuit2 pfet_03v3" 1 3\n'
        'permute "-circuit1 nfet_03v3" 1 3\n'
        'permute "-circuit2 nfet_03v3" 1 3\n'
    )
    with open(custom_setup, 'w') as f:
        f.write(setup_text)

    report = os.path.join(workdir, f"{cell_name}.lvs.out")
    cmd = [
        "netgen", "-batch", "lvs",
        f"{flat_path} {cell_name}",
        f"{sch_path} {cell_name}",
        custom_setup, report,
    ]
    print(f"[CUSTOM_LVS] cmd: {' '.join(cmd)}")
    r = sp.run(cmd, capture_output=True, text=True, timeout=timeout)
    log = r.stdout + "\n" + r.stderr
    print("[CUSTOM_LVS] netgen finished.")
    print("=== summary from report ===")
    summary = _parse_lvs_summary(report if os.path.isfile(report) else None)
    return {
        "match": summary["match"],
        "report_path": report if os.path.isfile(report) else None,
        "log": log.strip(),
        "summary": summary,
    }


if __name__ == "__main__":
    os.environ.setdefault('PDK_ROOT', '/home/huda/.volare')
    os.environ.setdefault('PDK', 'gf180mcuD')
    os.environ.setdefault('PDKPATH', '/home/huda/.volare/gf180mcuD')
    # Use the simplified-PMOS comparator output for testing.
    gds = "/home/huda/mbg_runs/comparator_simplified/two_stage_comparator/two_stage_comparator.gds"
    sch = "/home/huda/mbg_runs/comparator_simplified/two_stage_comparator/two_stage_comparator.sch.spice"
    # Write the ORIGINAL (unmodified) schematic source for LVS use.
    # The one shipped in `*/two_stage_comparator.sch.spice` was already
    # corrupted by _merge_schematic_nets. We use the canonical refresh here.
    sch_canonical = "/home/huda/mbg_runs/comparator_simplified/two_stage_comparator/canonical_sub.spice"
    canonical = """
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
    with open(sch_canonical, 'w') as f:
        f.write(canonical.strip() + "\n")

    import json
    r = custom_run_lvs(gds, sch_canonical, 'two_stage_comparator',
                      '/tmp/mbg_CUSTOM_lvs')
    print(f"=== match: {r['match']}")
    print(f"=== summary: {json.dumps(r['summary'], indent=2)}")
    print(f"=== log (last 3000 chars):")
    print(r['log'][-3000:])
