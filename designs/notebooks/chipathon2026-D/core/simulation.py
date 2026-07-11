"""
@Owner: Huda (Lead Analog / Mixed-Signal Designer)
@Role: Analog Layout Strategist
@Responsibility: Pre-layout and post-layout simulation module (ngspice) to verify specifications (Gain, GBW, PM, Offset).
"""
import os
import re
import subprocess
import tempfile

_MODEL_PATH = os.path.join(
    os.environ.get("PDK_ROOT", os.path.expanduser("~/.volare")),
    os.environ.get("PDK", "gf180mcuD"),
    "libs.tech", "ngspice", "sm141064.ngspice",
)


def _parse_subckt_pins(netlist_content, cell_name):
    pat = r"^\.subckt\s+" + re.escape(cell_name) + r"\s+(.*)"
    for line in netlist_content.splitlines():
        m = re.match(pat, line.strip(), re.IGNORECASE)
        if m:
            return m.group(1).split()
    raise ValueError(f"Could not find .subckt {cell_name} in netlist")


# Standard pin order per cell type (the testbench always uses this)
_COMP_PINS = ("vin_p", "vin_n", "clk", "vout_p", "vout_n", "vdd", "vss")
_OTA_PINS  = ("vin_p", "vin_n", "vout", "vbias", "vdd", "vss")


def _fix_pex_pin_connections(netlist_content, cell_name, standard_pins):
    """Short PEX pins to their DIRECT capacitor neighbours.

    Magic's flat ext2spice names subcircuit pins correctly but does NOT
    connect them to the internal device nodes.  We add 0 V DC sources
    to short each standard pin to every node that has a DIRECT
    capacitor to it (1‑hop), recovering the lost metal connections.
    """
    actual_pins = list(standard_pins)

    neighbors = {p: set() for p in actual_pins}
    for line in netlist_content.splitlines():
        m = re.match(r"^C\d+\s+(\S+)\s+(\S+)\s+", line)
        if m:
            a, b = m.group(1), m.group(2)
            if a in neighbors:
                neighbors[a].add(b)
            if b in neighbors:
                neighbors[b].add(a)

    shorts = []
    node_pin_count = {}
    for pin in actual_pins:
        for node in neighbors[pin]:
            node_pin_count.setdefault(node, set()).add(pin)

    substrate_nodes = {n for n, pins in node_pin_count.items() if len(pins) >= 4}

    for pin in actual_pins:
        for node in sorted(neighbors[pin] - substrate_nodes):
            name = f"V_pex_{pin}_{node.translate(str.maketrans('','','#'))}"
            shorts.append(f"{name} {node} {pin} DC 0")

    if not shorts:
        return netlist_content

    insert = "* --- PEX pin shorts (1-hop, auto) ---\n" + "\n".join(shorts) + "\n"

    lines = netlist_content.splitlines()
    result = []
    inserted = False
    for line in reversed(lines):
        result.append(line)
        if not inserted and re.match(r"^\s*\.ends\s*$", line):
            result.append(insert)
            inserted = True
    result.reverse()

    return "\n".join(result)


def _fix_pex_supplies(netlist_content):
    """Short PEX supply pins to internal well/substrate body nodes.

    Magic PEX extraction creates separate internal nodes for well
    contacts that are NOT directly connected to the subcircuit vdd/vss
    pins — only tiny parasitic caps bridge them.  This function adds
    0 V DC voltage sources to short the pins to every body node found.
    """
    body_pmos = set()
    body_nmos = set()
    for line in netlist_content.splitlines():
        m = re.match(r"X\d+\s+\S+\s+\S+\s+\S+\s+(\S+)\s+(nfet|pfet)_03v3", line)
        if m:
            body = m.group(1)
            (body_nmos if "nfet" in m.group(2) else body_pmos).add(body)

    shorts = []
    for node in sorted(body_pmos):
        shorts.append(f"V_pex_vdd_{node.translate(str.maketrans('','','#'))} {node} vdd DC 0")
    for node in sorted(body_nmos):
        shorts.append(f"V_pex_vss_{node.translate(str.maketrans('','','#'))} {node} vss DC 0")

    if not shorts:
        return netlist_content

    insert = "* --- PEX supply shorts (auto-generated) ---\n" + "\n".join(shorts) + "\n"

    lines = netlist_content.splitlines()
    result = []
    inserted = False
    for line in reversed(lines):
        result.append(line)
        if not inserted and re.match(r"^\s*\.ends\s*$", line):
            result.append(insert)
            inserted = True
    result.reverse()

    return "\n".join(result)


def _sanitize_netlist(netlist_content):
    """Strip .lib and ng= from netlist (keep .option scale for ngspice)."""
    stripped = []
    for line in netlist_content.splitlines():
        if re.match(r"^\s*\.lib\s", line, re.IGNORECASE):
            continue
        line = re.sub(r"\bng\s*=\s*\d+\s*", "", line, flags=re.IGNORECASE)
        stripped.append(line)
    return "\n".join(stripped)


def _normalise_subckt(netlist_content, cell_name, standard_pins):
    """Ensure .subckt has standard pin order (add pins if missing)."""
    try:
        pin_order = _parse_subckt_pins(netlist_content, cell_name)
    except ValueError:
        pin_order = []

    if pin_order and tuple(p.lower() for p in pin_order) == tuple(p.lower() for p in standard_pins):
        return netlist_content

    lines = []
    for line in netlist_content.splitlines():
        if re.match(r"^\s*\.subckt\s+" + re.escape(cell_name) + r"(\s|$)", line, re.IGNORECASE):
            lines.append(f".subckt {cell_name} {' '.join(standard_pins)}")
        else:
            lines.append(line)
    return "\n".join(lines)


# ──────────────────────────────────────────────────
#  OTA  AC  simulation
# ──────────────────────────────────────────────────


def _generate_ota_testbench(netlist_content, cell_name, workdir,
                            vdd=1.8, vss=0.0, vcm=0.9, vbias=0.55,
                            cload=1e-12, fstart=1, fstop=1e9, ac_dec=20):
    cleaned = _sanitize_netlist(netlist_content)
    cleaned = _normalise_subckt(cleaned, cell_name, _OTA_PINS)
    cleaned = _fix_pex_pin_connections(cleaned, cell_name, _OTA_PINS)
    cleaned = _fix_pex_supplies(cleaned)

    dut_netlist = cleaned
    dut_path = os.path.join(workdir, f"{cell_name}_dut.spice")
    with open(dut_path, "w") as f:
        f.write(dut_netlist)

    x_line = f"Xota n_vin_p n_vin_n n_vout n_vbias n_vdd n_vss {cell_name}"

    tb = f"""
* OTA AC Testbench — {cell_name}
.param fnoicor=0 sw_stat_global=0 sw_stat_mismatch=0
.lib "{_MODEL_PATH}" typical
.include "{dut_path}"

.param VDD_VAL={vdd}
.param VSS_VAL={vss}
.param VCM_VAL={vcm}
.param VBIAS_VAL={vbias}

VDD    n_vdd  0  DC {{VDD_VAL}}
VSS    n_vss  0  DC {{VSS_VAL}}
Vb     n_vbias  0  DC {{VBIAS_VAL}}

Vin_p  n_vin_p  0  DC {{VCM_VAL}} AC 1
Vin_n  n_vin_n  0  DC {{VCM_VAL}}

Cload  n_vout  0  {cload}

{x_line}

.control
op
ac dec {ac_dec} {fstart} {fstop}
meas ac DCGAIN max vdb(n_vout)
meas ac GBW when vdb(n_vout)=0 fall=last
let vp_deg = vp(n_vout)*180/pi
let pm_vec = vp_deg + 180
meas ac PM find pm_vec at=GBW
let dc3db = DCGAIN - 3
meas ac FREQ_3DB when vdb(n_vout)=dc3db fall=last
echo MEAS_START
print DCGAIN
print GBW
print PM
print FREQ_3DB
echo MEAS_END
set wr_singlescale
wrdata {workdir}/{cell_name}_ac.dat vdb(n_vout) vp(n_vout)*180/pi
.endc

.end
"""
    tb_path = os.path.join(workdir, f"{cell_name}_tb.cir")
    with open(tb_path, "w") as f:
        f.write(tb)
    return tb_path


def run_ota_ac(netlist_content, cell_name,
               vdd=1.8, vss=0.0, vcm=0.9, vbias=0.55,
               cload=1e-12, fstart=1, fstop=1e9, ac_dec=20,
               workdir=None, timeout=120):
    """Run OTA AC simulation via ngspice.

    Returns dict with: dc_gain_db, gbw_hz, phase_margin_deg,
    f_3db_hz, ac_data (list of {freq,vdb,vp}), log.
    """
    wd = workdir or tempfile.mkdtemp(prefix="ngspice_")
    os.makedirs(wd, exist_ok=True)

    tb_path = _generate_ota_testbench(
        netlist_content, cell_name, wd,
        vdd=vdd, vss=vss, vcm=vcm, vbias=vbias,
        cload=cload, fstart=fstart, fstop=fstop, ac_dec=ac_dec,
    )

    try:
        result = subprocess.run(
            ["ngspice", "-b", tb_path],
            capture_output=True, text=True, timeout=timeout, cwd=wd,
        )
    except subprocess.TimeoutExpired:
        return {
            "dc_gain_db": None, "gbw_hz": None, "phase_margin_deg": None,
            "f_3db_hz": None, "ac_data": [], "log": "Simulation timed out",
            "tb_path": tb_path,
        }

    log = result.stdout + "\n" + result.stderr

    if result.returncode != 0:
        return {
            "dc_gain_db": None, "gbw_hz": None, "phase_margin_deg": None,
            "f_3db_hz": None, "ac_data": [], "log": log.strip(),
            "tb_path": tb_path,
        }

    parsed = _parse_meas(log)

    ac_data = []
    ac_dat = os.path.join(wd, f"{cell_name}_ac.dat")
    if os.path.isfile(ac_dat):
        ac_data = _parse_ac_data(ac_dat)

    if not workdir:
        import shutil
        shutil.rmtree(wd, ignore_errors=True)

    return {
        "dc_gain_db": parsed.get("dcgain"),
        "gbw_hz": parsed.get("gbw"),
        "phase_margin_deg": parsed.get("pm"),
        "f_3db_hz": parsed.get("freq_3db"),
        "ac_data": ac_data,
        "log": log.strip(),
        "tb_path": tb_path,
    }


# ──────────────────────────────────────────────────
#  Comparator TRANSIENT simulation
# ──────────────────────────────────────────────────


def _generate_comparator_testbench(netlist_content, cell_name, workdir,
                                   vdd=1.8, vss=0.0, vcm=0.9,
                                   clk_period=1e-6, clk_rise=0.1e-9,
                                   tstop=5e-6, tstep=100e-12,
                                   measure_offset=False,
                                   corner="typical", temperature=None):
    cleaned = _sanitize_netlist(netlist_content)
    cleaned = _normalise_subckt(cleaned, cell_name, _COMP_PINS)
    cleaned = _fix_pex_pin_connections(cleaned, cell_name, _COMP_PINS)
    cleaned = _fix_pex_supplies(cleaned)

    dut_netlist = cleaned
    dut_path = os.path.join(workdir, f"{cell_name}_dut.spice")
    with open(dut_path, "w") as f:
        f.write(dut_netlist)

    clk_pw = clk_period / 2
    vdelta = 0.01
    xcmp_line = f"Xcmp n_vin_p n_vin_n n_clk n_vout_p n_vout_n n_vdd n_vss {cell_name}"

    if measure_offset:
        ramp_end = tstop * 0.9
        vin_p_line = f"Vin_p n_vin_p 0 PWL(0 {{VCM-0.05}}  {ramp_end:.2e} {{VCM+0.05}})"
        meas_block = f"""meas tran VOUT_H max v(n_vout_p)
meas tran VOUT_L min v(n_vout_p)
echo MEAS_START
print VOUT_H VOUT_L
echo MEAS_END"""
    else:
        vin_p_line = f"Vin_p n_vin_p 0 PWL(0 {{VCM-VDELTA}}  4.9n {{VCM-VDELTA}}  5.1n {{VCM+VDELTA}})"
        meas_block = f"""meas tran VOUT_H max v(n_vout_p)
meas tran VOUT_L min v(n_vout_p)
meas tran TDELAY trig v(n_clk) val={vdd/2} rise=1
+                  targ v(n_vout_p) val={vdd/2} cross=1
echo MEAS_START
print VOUT_H VOUT_L TDELAY
echo MEAS_END"""

    temp_line = f".temp {temperature}" if temperature is not None else ""

    tb = f"""
* Comparator Transient Testbench — {cell_name}
.param fnoicor=0 sw_stat_global=0 sw_stat_mismatch=0
.lib "{_MODEL_PATH}" {corner}
.include "{dut_path}"
{temp_line}

.param VDD_VAL={vdd}
.param VCM={vcm}
.param VDELTA={vdelta}
.param CLK_PER={clk_period}
.param CLK_PW={clk_pw}
.param CLK_RISE={clk_rise}

VDD  n_vdd  0 DC {{VDD_VAL}}
VSS  n_vss  0 DC 0

Vclk n_clk 0 PULSE(0 {{VDD_VAL}} 0 {{CLK_RISE}} {{CLK_RISE}} {{CLK_PW}} {{CLK_PER}})

{vin_p_line}
Vin_n n_vin_n 0 DC {{VCM}}

Coutp n_vout_p 0 1f
Coutn n_vout_n 0 1f
Routp n_vout_p 0 1e12
Routn n_vout_n 0 1e12

{xcmp_line}

.control
tran {tstep:.2e} {tstop:.2e}
run
{meas_block}
set wr_singlescale
wrdata {workdir}/{cell_name}_tran.dat v(n_clk) v(n_vin_p) v(n_vin_n) v(n_vout_p) v(n_vout_n)
.endc

.end
"""
    tb_path = os.path.join(workdir, f"{cell_name}_tb.cir")
    with open(tb_path, "w") as f:
        f.write(tb)
    return tb_path


def run_comparator_tran(netlist_content, cell_name,
                        vdd=1.8, vcm=0.9, vdelta=0.01,
                        clk_period=1e-6, tstop=5e-6,
                        measure_offset=False,
                        corner="typical", temperature=None,
                        workdir=None, timeout=120):
    """Run comparator transient simulation via ngspice.

    Args:
        measure_offset: If True, use slow ramp on vin_p to measure
            input offset. Returns 'vos' in result dict.
        corner: 'typical', 'slow', or 'fast'
        temperature: Celsius (e.g. -40, 25, 125), or None

    Returns dict with: vout_high, vout_low, tdelay, vos (if offset mode),
    tran_data (list of {time, clk, vin_p, vin_n, vout_p, vout_n}), log.
    """
    wd = workdir or tempfile.mkdtemp(prefix="ngspice_")
    os.makedirs(wd, exist_ok=True)

    tb_path = _generate_comparator_testbench(
        netlist_content, cell_name, wd,
        vdd=vdd, vss=0.0, vcm=vcm,
        clk_period=clk_period, tstop=tstop,
        measure_offset=measure_offset,
        corner=corner, temperature=temperature,
    )

    try:
        with open(tb_path, "r") as f:
            tb_content = f.read()
    except Exception:
        tb_content = ""

    try:
        result = subprocess.run(
            ["ngspice", "-b", tb_path],
            capture_output=True, text=True, timeout=timeout, cwd=wd,
        )
    except subprocess.TimeoutExpired:
        if not workdir:
            import shutil
            shutil.rmtree(wd, ignore_errors=True)
        return {
            "vout_high": None, "vout_low": None, "tdelay": None,
            "vos": None, "tran_data": [], "log": "Simulation timed out",
            "corner": corner, "temperature": temperature,
            "llm_feedback": f"CRITICAL ERROR: Simulation timed out. The circuit may have severe convergence issues or positive feedback causing infinite loops.\n\nHere is the Testbench used:\n```spice\n{tb_content}\n```",
            "finetune": True,
        }

    log = result.stdout + "\n" + result.stderr

    if result.returncode != 0:
        error_lines = [line for line in log.split("\n") if "error" in line.lower() or "warning" in line.lower() or "fatal" in line.lower()]
        error_summary = "\n".join(error_lines[:10])
        if not workdir:
            import shutil
            shutil.rmtree(wd, ignore_errors=True)
        return {
            "vout_high": None, "vout_low": None, "tdelay": None,
            "vos": None, "tran_data": [], "log": log.strip(),
            "corner": corner, "temperature": temperature,
            "llm_feedback": f"CRITICAL ERROR: Simulation failed (ngspice exit code {result.returncode}).\nThis usually means incorrect pin connections, missing models, or syntax errors.\n\nError Log snippet:\n{error_summary}\n\nHere is the Testbench used for simulation so you can check pin orders and signals:\n```spice\n{tb_content}\n```\n\nPlease fix the netlist syntax or pin connections based on these errors.",
            "finetune": True,
        }

    parsed = _parse_tran_meas(log)

    tran_data = []
    dat = os.path.join(wd, f"{cell_name}_tran.dat")
    if os.path.isfile(dat):
        tran_data = _parse_tran_data(dat)

    if not workdir:
        import shutil
        shutil.rmtree(wd, ignore_errors=True)

    vos_val = None
    if measure_offset and tran_data:
        vos_val = _compute_offset(tran_data, vdd)

    vout_high = None
    vout_low = None
    tdelay_val = None
    if tran_data:
        vout_high = max(pt["vout_p"] for pt in tran_data)
        vout_low  = min(pt["vout_p"] for pt in tran_data)
        tdelay_val = _compute_tdelay(tran_data, vdd)

    def _fmt_v(v, unit=""):
        return f"{v:.3g} {unit}" if v is not None else "N/A"

    functional = True
    if measure_offset:
        if vos_val is None or abs(vos_val) > 0.001:
            functional = False
        llm_feedback = (
            f"Offset Simulation Result ({corner.upper()}, {temperature}C, VDD={vdd}V):\n"
            f"- Input Offset Voltage (Vos): {_fmt_v(vos_val, 'V')}\n"
            f"If Vos is N/A or > 10mV, the comparator failed to resolve properly."
        )
    else:
        if tdelay_val is None or vout_high is None or vout_low is None:
            functional = False
        elif vout_high < vdd * 0.8 or vout_low > vdd * 0.2:
            functional = False
            
        llm_feedback = (
            f"Delay Simulation Result ({corner.upper()}, {temperature}C, VDD={vdd}V):\n"
            f"- Propagation Delay: {_fmt_v(tdelay_val or parsed.get('tdelay'), 's')}\n"
            f"- Output High Voltage (VOH): {_fmt_v(vout_high, 'V')}\n"
            f"- Output Low Voltage (VOL): {_fmt_v(vout_low, 'V')}\n"
            f"If Delay is N/A or VOH/VOL do not swing rail-to-rail, the comparator is non-functional."
        )

    return {
        "vout_high": vout_high,
        "vout_low": vout_low,
        "tdelay": tdelay_val or parsed.get("tdelay"),
        "vos": vos_val,
        "tran_data": tran_data,
        "log": log.strip(),
        "corner": corner,
        "temperature": temperature,
        "llm_feedback": llm_feedback,
        "finetune": not functional,
    }


def _compute_tdelay(tran_data, vdd):
    vth = vdd / 2
    # Find the clock cycle where vout_p crosses vth (either up or down)
    for i in range(1, len(tran_data)):
        prev = tran_data[i-1]
        curr = tran_data[i]
        
        # Check if vout_p crossed vth
        if (prev["vout_p"] <= vth < curr["vout_p"]) or (prev["vout_p"] > vth >= curr["vout_p"]):
            cross_time = curr["time"]
            # Look back to find the most recent clock rising edge
            for j in range(i, 0, -1):
                if tran_data[j-1]["clk"] <= vth < tran_data[j]["clk"]:
                    return cross_time - tran_data[j]["time"]
    return None


def _compute_offset(tran_data, vdd):
    vth = vdd / 2
    if not tran_data:
        return None
    for i in range(1, len(tran_data)):
        prev = tran_data[i - 1]
        curr = tran_data[i]
        # Look for vout_p crossing vth (either upwards or downwards)
        if (prev["vout_p"] <= vth < curr["vout_p"]) or (prev["vout_p"] > vth >= curr["vout_p"]):
            # Depending on if it's the reset edge or the evaluate edge,
            # we just return the diff of inputs. The slow ramp ensures vin_p - vin_n is the offset.
            return curr["vin_p"] - curr["vin_n"]
    return None


def run_comparator_pvt(netlist_content, cell_name,
                       vdd=1.8, vcm=0.9,
                       clk_period=1e-6, tstop=5e-6,
                       workdir=None, timeout=120):
    """Run comparator across PVT corners: delay + offset per corner.

    PVT matrix: 3 process × 3 temperature × 2 voltage = up to 18 corners.
    Default runs 5 key corners (TT/SS/FF × min/max temp × VDD±10%).

    Returns dict with:
        corners: [{corner, temp, vdd, tdelay, vos, vout_high, vout_low, log}, ...]
        summary: {tdelay_min, tdelay_max, tdelay_typ, vos_min, vos_max, vos_typ}
    """
    _PVT_CORNERS = [
        ("typical", 25,  1.0, "TT, 25°C, 1.80V"),
        ("ss",      125, 0.9, "SS, 125°C, 1.62V"),
        ("ss",      -40, 0.9, "SS, -40°C, 1.62V"),
        ("ff",      -40, 1.1, "FF, -40°C, 1.98V"),
        ("ff",      125, 1.1, "FF, 125°C, 1.98V"),
        ("sf",      25,  1.0, "SF, 25°C, 1.80V"),
        ("fs",      25,  1.0, "FS, 25°C, 1.80V"),
    ]

    corners_results = []
    for corner, temp, vscale, desc in _PVT_CORNERS:
        vdd_scaled = round(vdd * vscale, 3)
        print(f"  [PVT] {desc} ...")

        res = run_comparator_tran(
            netlist_content, cell_name,
            vdd=vdd_scaled, vcm=vcm,
            clk_period=clk_period, tstop=tstop,
            measure_offset=False,
            corner=corner, temperature=temp,
            workdir=workdir, timeout=timeout,
        )
        corners_results.append({
            "description": desc,
            "corner": corner,
            "temperature": temp,
            "vdd": vdd_scaled,
            "tdelay": res.get("tdelay"),
            "vout_high": res.get("vout_high"),
            "vout_low": res.get("vout_low"),
            "log": res.get("log", ""),
        })

    print(f"  [PVT] Offset measurement (TT, 25°C, 1.80V)...")
    offset_res = run_comparator_tran(
        netlist_content, cell_name,
        vdd=vdd, vcm=vcm,
        clk_period=clk_period, tstop=tstop * 2,
        measure_offset=True,
        corner="typical", temperature=25,
        workdir=workdir, timeout=timeout,
    )

    delays = [c["tdelay"] for c in corners_results if c["tdelay"] is not None]
    summary = {
        "tdelay_typ": delays[0] if len(delays) > 0 else None,
        "tdelay_min": min(delays) if delays else None,
        "tdelay_max": max(delays) if delays else None,
        "vos": offset_res.get("vos"),
    }

    def _fmt_v(v, unit=""):
        return f"{v:.3g} {unit}" if v is not None else "N/A"

    functional = True
    if summary.get('tdelay_typ') is None or summary.get('tdelay_max') is None:
        functional = False
    elif summary.get('vos') is None or abs(summary.get('vos')) > 0.01:
        functional = False

    feedback_lines = []
    feedback_lines.append(f"PVT Simulation Summary (Temperature: -40C to 125C, VDD: {vdd*0.9:.2f}V to {vdd*1.1:.2f}V):")
    feedback_lines.append(f"- Min Propagation Delay: {_fmt_v(summary.get('tdelay_min'), 's')}")
    feedback_lines.append(f"- Max Propagation Delay: {_fmt_v(summary.get('tdelay_max'), 's')}")
    feedback_lines.append(f"- Typical Delay: {_fmt_v(summary.get('tdelay_typ'), 's')}")
    feedback_lines.append(f"- Input Offset Voltage: {_fmt_v(summary.get('vos'), 'V')}")
    
    feedback_lines.append("\nDetailed Corners (TT, SS, FF, SF, FS):")
    error_logs = []
    for c in corners_results:
        td = _fmt_v(c.get('tdelay'), 's')
        feedback_lines.append(f"  {c['description']:<25} ({c['temperature']:>3}C, {c['vdd']:.2f}V) -> Delay: {td}")
        if c.get('tdelay') is None:
            functional = False
        if c.get("log") and ("error" in c.get("log").lower() or "fatal" in c.get("log").lower()):
            if c.get("log") not in error_logs:
                error_logs.append(c.get("log"))
            
    feedback_lines.append("\nContext for LLM:")
    feedback_lines.append("If any delay is 'N/A', the comparator failed in that specific PVT corner. "
                          "If the offset is > 10mV, the design suffers from high mismatch sensitivity. "
                          "Please fix the circuit topology or transistor sizing based on these metrics.")
                          
    if error_logs:
        feedback_lines.append("\nCRITICAL ERRORS DETECTED IN SIMULATION:")
        # Just grab the first unique error log to avoid spamming the LLM
        err_lines = [line for line in error_logs[0].split("\n") if "error" in line.lower() or "warning" in line.lower() or "fatal" in line.lower()]
        feedback_lines.append("\n".join(err_lines[:15]))
        feedback_lines.append("Please fix the SPICE netlist syntax, pin connections, or models to resolve the above errors.")
    
    llm_feedback = "\n".join(feedback_lines)

    return {
        "corners": corners_results, 
        "offset": offset_res, 
        "summary": summary,
        "llm_feedback": llm_feedback,
        "finetune": not functional,
    }


def _parse_tran_meas(log):
    result = {}
    patterns = {
        "vout_h": r"vout_h\s*=\s*([\d\.\+\-e]+)",
        "vout_l": r"vout_l\s*=\s*([\d\.\+\-e]+)",
        "tdelay": r"tdelay\s*=\s*([\d\.\+\-e]+)",
        "vos": r"vos\s*=\s*([\d\.\+\-e]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, log, re.IGNORECASE)
        if m:
            try:
                result[key] = float(m.group(1))
            except ValueError:
                result[key] = None
    return result


# ──────────────────────────────────────────────────
#  Shared parsers
# ──────────────────────────────────────────────────


def _parse_meas(log):
    result = {}
    patterns = {
        "dcgain": r"dcgain\s*=\s*([\d\.\+\-e]+)",
        "gbw": r"gbw\s*=\s*([\d\.\+\-e]+)",
        "pm": r"pm\s*=\s*([\d\.\+\-e]+)",
        "freq_3db": r"freq_3db\s*=\s*([\d\.\+\-e]+)",
    }
    for key, pat in patterns.items():
        m = re.search(pat, log, re.IGNORECASE)
        if m:
            try:
                result[key] = float(m.group(1))
            except ValueError:
                result[key] = None
    return result


def _parse_ac_data(dat_path):
    data = []
    with open(dat_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 3:
                try:
                    data.append({
                        "freq": float(parts[0]),
                        "vdb": float(parts[1]),
                        "vp": float(parts[2]),
                    })
                except (ValueError, IndexError):
                    pass
    return data


def _parse_tran_data(dat_path):
    data = []
    with open(dat_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("*"):
                continue
            parts = line.split()
            if len(parts) >= 6:
                try:
                    data.append({
                        "time": float(parts[0]),
                        "clk": float(parts[1]),
                        "vin_p": float(parts[2]),
                        "vin_n": float(parts[3]),
                        "vout_p": float(parts[4]),
                        "vout_n": float(parts[5]),
                    })
                except (ValueError, IndexError):
                    pass
    return data


# ──────────────────────────────────────────────────
#  Compare pre/post (backward compat)
# ──────────────────────────────────────────────────


def compare_pre_post(schematic_netlist, pex_path, cell_name, **kwargs):
    """Compare AC performance of schematic vs PEX-extracted netlist."""
    with open(pex_path) as f:
        pex_content = f.read()

    auto_cload = kwargs.pop("cload", None)
    vcm = kwargs.pop("vcm", 0.9)
    vbias = kwargs.pop("vbias", 0.55)

    pre = run_ota_ac(schematic_netlist, cell_name,
                     cload=auto_cload or 1e-12, vcm=vcm, vbias=vbias,
                     **kwargs)
    post = run_ota_ac(pex_content, cell_name,
                      cload=auto_cload or 1e-12, vcm=vcm, vbias=vbias,
                      **kwargs)

    delta = {}
    for key in ("dc_gain_db", "gbw_hz", "phase_margin_deg", "f_3db_hz"):
        pre_val = pre.get(key)
        post_val = post.get(key)
        if pre_val is not None and post_val is not None:
            delta[key] = round(post_val - pre_val, 4)
        elif pre_val is not None and post_val is None:
            delta[key] = "post N/A"
        elif pre_val is None and post_val is not None:
            delta[key] = "pre N/A"
        else:
            delta[key] = None

    return {"pre": pre, "post": post, "delta": delta}


def compare_comp_pre_post(schematic_netlist, pex_path, cell_name, **kwargs):
    """Compare comparator transient performance of schematic vs PEX."""
    with open(pex_path) as f:
        pex_content = f.read()

    vcm = kwargs.pop("vcm", 0.9)
    vdd = kwargs.pop("vdd", 1.8)
    clk_period = kwargs.pop("clk_period", 1e-6)
    tstop = kwargs.pop("tstop", 5e-6)

    pre = run_comparator_tran(schematic_netlist, cell_name,
                              vdd=vdd, vcm=vcm,
                              clk_period=clk_period, tstop=tstop,
                              **kwargs)
    post = run_comparator_tran(pex_content, cell_name,
                               vdd=vdd, vcm=vcm,
                               clk_period=clk_period, tstop=tstop,
                               **kwargs)

    delta = {}
    for key in ("tdelay", "vos", "vout_high", "vout_low"):
        pre_val = pre.get(key)
        post_val = post.get(key)
        if pre_val is not None and post_val is not None:
            delta[key] = round(post_val - pre_val, 10)
        elif pre_val is not None and post_val is None:
            delta[key] = "post N/A"
        elif pre_val is None and post_val is not None:
            delta[key] = "pre N/A"
        else:
            delta[key] = None

    return {"pre": pre, "post": post, "delta": delta}
