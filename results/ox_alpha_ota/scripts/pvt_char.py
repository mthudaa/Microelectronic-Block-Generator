"""PVT + extended characterization of the FINAL extracted OTA netlist.

Covers what /mbg-full-auto does not configure: PVT corners (VDD x TEMP x
process), CMRR, PSRR+, ICMR, input-referred noise, and mismatch offset.

Run from $MBG_ROOT:  $MBG_VENV/bin/python /tmp/opencode/ox_alpha/pvt_char.py
"""
from __future__ import annotations

import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ota_design as od
from mbg.simulation import run_spice

PEX = "results/ox_alpha_ota/final/ota.pex.spice"
OUTDIR = "results/ox_alpha_ota/pvt"
CELL = "ota"

os.makedirs(OUTDIR, exist_ok=True)
text = open(PEX).read()
core = od._strip(text)
by_name = {p.upper(): p for p in od._ports_of(text, CELL)}
PN = {k: by_name[k] for k in ("VDD", "VSS", "INP", "INN", "OUT", "IBIAS")}


def base_head(vdd, temp, corner):
    return f""".include '{od.DESIGN}'
.lib '{od.MODELS}' {corner}
.temp {temp}
{core}
XDUT {' '.join(od._ports_of(text, CELL))} {CELL}
"""


def quick_metrics(vdd=3.3, temp=27, corner="typical", tran=True):
    """op + ac (+tran slew optionally) without the swing sweep."""
    tran_block = (f"""
tran 1n 6u
wrdata tran.dat v({PN['OUT']})""") if tran else ""
    deck = base_head(vdd, temp, corner) + f"""VVDD {PN['VDD']} 0 {vdd}
VVSS {PN['VSS']} 0 0
VINP {PN['INP']} 0 PWL(0us 1.65 0.5us 1.65 0.51us 2.15
+ 2.5us 2.15 2.51us 1.15 4.5us 1.15 4.52us 1.65 6us 1.65) AC 1
VINN {PN['INN']} 0 DC 1.65
CLOAD {PN['OUT']} 0 5p
IIB 0 ibias_inj DC 20u
VMON ibias_inj {PN['IBIAS']} 0
.control
op
print v({PN['OUT']}) i(vvdd)
ac dec 401 1 1G
wrdata ac.dat vdb({PN['OUT']}) vp({PN['OUT']}){tran_block}
quit
.endc
.end"""
    tag = f"pvt_{corner}_{vdd:.1f}V_{temp:+04d}C".replace("+", "p").replace("-", "m")
    wd = os.path.join(OUTDIR, tag)
    r = run_spice(deck, workdir=wd, fmt="dat", timeout=900)
    scalars = {}
    for name, val in od._PRINT_RE.findall(r.get("stdout") or ""):
        try:
            scalars[name.lower()] = float(val)
        except ValueError:
            pass
    m: dict = {}
    ac = od._read_wrdata(os.path.join(r["workdir"], "ac.dat"))
    if not ac:
        m["error"] = "no ac data"
        return m
    freq = [row[0] for row in ac]
    vdb = [row[1] for row in ac]
    vp_raw = [row[3] for row in ac]
    # vp is unwrapped RADIANS that drift into garbage at the noise floor;
    # normalize per sample and read phase only at the first 0 dB crossing.
    m["gain_db"] = vdb[0]
    for i in range(1, len(vdb)):
        if vdb[i - 1] > 0.0 >= vdb[i]:
            m["ugf_hz"] = od._interp(freq[i - 1], vdb[i - 1], freq[i], vdb[i], 0.0)
            lag0 = (180.0 - math.degrees(vp_raw[i - 1])) % 360.0
            lag1 = (180.0 - math.degrees(vp_raw[i])) % 360.0
            t = ((m["ugf_hz"] - freq[i - 1]) / (freq[i] - freq[i - 1])
                 if freq[i] != freq[i - 1] else 0.0)
            m["pm_deg"] = 180.0 - (lag0 + t * (lag1 - lag0))
            break
    out_v = scalars.get("v(out)")
    ivdd = scalars.get("i(vvdd)")
    if out_v is not None:
        m["out_dc"] = out_v
    if ivdd is not None:
        m["idd_ua"] = abs(ivdd) * 1e6
    tran = od._read_wrdata(os.path.join(r["workdir"], "tran.dat"))
    if tran:
        t = [row[0] for row in tran]
        v = [row[1] for row in tran]
        sr_fall = _seg_slew(t, v, 0.55e-6, 2.45e-6, False)
        sr_rise = _seg_slew(t, v, 2.55e-6, 4.45e-6, True)
        if sr_rise:
            m["sr_rise_vus"] = sr_rise
        if sr_fall:
            m["sr_fall_vus"] = sr_fall
    return m


def _seg_slew(t, v, t_lo, t_hi, rising):
    xs = [(ti, vi) for ti, vi in zip(t, v) if t_lo <= ti <= t_hi]
    if len(xs) < 10:
        return None
    head = [vi for _, vi in xs[:20]]
    tail = [vi for _, vi in xs[-20:]]
    v0, v1 = sum(head) / len(head), sum(tail) / len(tail)
    dv = abs(v1 - v0)
    if dv < 0.05:
        return None
    lo_lvl = min(v0, v1) + 0.2 * dv
    hi_lvl = min(v0, v1) + 0.8 * dv
    txs = []
    for lvl in (lo_lvl, hi_lvl):
        tx = None
        for j in range(1, len(xs)):
            a, b = xs[j - 1][1], xs[j][1]
            hit = (a < lvl <= b) if rising else (a > lvl >= b)
            if hit:
                tx = od._interp(xs[j - 1][0], a, xs[j][0], b, lvl)
                break
        txs.append(tx)
    if any(x is None for x in txs):
        return None
    ta, tb = sorted(txs)
    return (0.6 * dv) / (tb - ta) / 1e6 if tb > ta else None


# ── extended analyses (nominal) ────────────────────────────────────────────

def cmrr():
    """Common-mode gain with both inputs driven together."""
    deck = base_head(3.3, 27, "typical") + f"""VVDD {PN['VDD']} 0 3.3
VVSS {PN['VSS']} 0 0
VIC {PN['INP']} 0 DC 1.65 AC 1
VJOIN {PN['INN']} {PN['INP']} 0
CLOAD {PN['OUT']} 0 5p
IIB 0 {PN['IBIAS']} DC 20u
.control
op
ac dec 101 1 1G
wrdata ac.dat vdb({PN['OUT']}) vp({PN['OUT']})
quit
.endc
.end"""
    r = run_spice(deck, workdir=os.path.join(OUTDIR, "cmrr"), fmt="dat")
    ac = od._read_wrdata(os.path.join(r["workdir"], "ac.dat"))
    adm = quick_metrics()
    if not ac or "gain_db" not in adm:
        return {"error": "no data"}
    return {"acm_db": round(ac[0][1], 3),
            "adm_db": round(adm["gain_db"], 3),
            "cmrr_dc_db": round(adm["gain_db"] - ac[0][1], 3)}


def psrr():
    """PSRR+: AC injected on VDD, ratio ADM/A(vdd->out)."""
    deck = base_head(3.3, 27, "typical") + f"""VVDD {PN['VDD']} 0 3.3 AC 1
VVSS {PN['VSS']} 0 0
VINP {PN['INP']} 0 DC 1.65
VINN {PN['INN']} 0 DC 1.65
CLOAD {PN['OUT']} 0 5p
IIB 0 {PN['IBIAS']} DC 20u
.control
ac dec 101 1 1G
wrdata ac.dat vdb({PN['OUT']})
quit
.endc
.end"""
    r = run_spice(deck, workdir=os.path.join(OUTDIR, "psrr"), fmt="dat")
    ac = od._read_wrdata(os.path.join(r["workdir"], "ac.dat"))
    adm = quick_metrics()
    if not ac or "gain_db" not in adm:
        return {"error": "no data"}
    avdd_db = ac[0][1]
    return {"avdd_db": round(avdd_db, 3),
            "psrr_p_dc_db": round(adm["gain_db"] - avdd_db, 3)}


def icmr_run():
    """ICMR: vicm range where +/-5 mV differential still produces >= half of
    the maximum differential output response."""
    outs = {}
    for label, off in (("p", "+5m"), ("m", "-5m")):
        neg = "-5m" if off == "+5m" else "+5m"
        deck = f""".include '{od.DESIGN}'
.lib '{od.MODELS}' typical
.temp 27
{core}
XDUT {' '.join(od._ports_of(text, CELL))} {CELL}
VVDD {PN['VDD']} 0 3.3
VVSS {PN['VSS']} 0 0
VINP {PN['INP']} cmnode DC {off}
VINN {PN['INN']} cmnode DC {neg}
VICM cmnode 0 DC 1.65
CLOAD {PN['OUT']} 0 5p
IIB 0 {PN['IBIAS']} DC 20u
.control
dc VICM 0 3.3 0.02
wrdata dc.dat v({PN['OUT']})
quit
.endc
.end"""
        r = run_spice(deck, workdir=os.path.join(OUTDIR, f"icmr_{label}"),
                      fmt="dat")
        rows = od._read_wrdata(os.path.join(r["workdir"], "dc.dat"))
        outs[label] = [(row[0], row[1]) for row in rows]
    if not outs.get("p") or not outs.get("m"):
        return {"error": "no data"}
    diff = [(vp[0], abs(vp[1] - vm[1]))
            for vp, vm in zip(outs["p"], outs["m"])]
    dmax = max(d for _, d in diff)
    thr = 0.5 * dmax
    ok = [vc for vc, d in diff if d >= thr]
    return {"icmr_low_v": round(min(ok), 3), "icmr_high_v": round(max(ok), 3),
            "crit": "diff response >= 50pct of max ({:.3f} V)".format(dmax)}


def noise():
    deck = base_head(3.3, 27, "typical") + f"""VVDD {PN['VDD']} 0 3.3
VVSS {PN['VSS']} 0 0
VINP {PN['INP']} 0 DC 1.65 AC 1
VINN {PN['INN']} 0 DC 1.65
CLOAD {PN['OUT']} 0 5p
IIB 0 {PN['IBIAS']} DC 20u
.control
noise v({PN['OUT']}) VINP dec 20 10 100MEG
wrdata nz.dat inoise_spectrum onoise_spectrum
print inoise_total onoise_total
quit
.endc
.end"""
    r = run_spice(deck, workdir=os.path.join(OUTDIR, "noise"), fmt="dat")
    rows = od._read_wrdata(os.path.join(r["workdir"], "nz.dat"))
    res: dict = {}
    tot = []
    for line in (r.get("stdout") or "").splitlines():
        if "inoise_total" in line or "onoise_total" in line:
            parts = line.split("=")
            if len(parts) == 2:
                try:
                    tot.append((line.split()[0].strip(), float(parts[1])))
                except ValueError:
                    pass
    res["totals_stdout"] = tot
    if rows:
        # stride 6: f, in_f, f^2?, ... -> take first two columns conservatively
        res["inoise_spot_1k_sqrtVHz"] = rows[min(range(len(rows)),
                                                 key=lambda i: abs(rows[i][0] - 1e3))][1]
        idx_1m = min(range(len(rows)), key=lambda i: abs(rows[i][0] - 1e6))
        res["inoise_spot_1M_sqrtVHz"] = rows[idx_1m][1]
    return res


def offset_mc(runs=25):
    """Input-referred offset via device-mismatch Monte Carlo.

    Runs on the SCHEMATIC netlist: the PEX deck's `.option scale=5n` plus
    unscaled numeric instance parameters silently disables the GF180
    statistical wrapper's per-instance agauss draws (verified empirically),
    so every PEX sample came back identical.
    """
    sch = od.build_netlist(od.DEFAULT_PARAMS)
    sch_core = od._strip(sch)
    ports_sch = od._ports_of(sch, CELL)
    vals = []
    for i in range(runs):
        deck = f""".include '{od.DESIGN}'
.lib '{od.MODELS}' statistical
.temp 27
.param sw_stat_mismatch=1
.option seed={i + 1}
{sch_core}
XDUT {' '.join(ports_sch)} {CELL}
VVDD {PN['VDD']} 0 3.3
VVSS {PN['VSS']} 0 0
VINP {ports_sch[2]} 0 DC 1.65
VINN {ports_sch[3]} 0 DC 1.65
CLOAD {ports_sch[4]} 0 5p
IIB 0 ibias_inj DC 20u
VMON ibias_inj {ports_sch[5]} 0
.control
op
print v({ports_sch[4]})
quit
.endc
.end"""
        wd = os.path.join(OUTDIR, f"mc{i:03d}")
        r = run_spice(deck, workdir=wd, fmt="dat")
        sc = dict(od._PRINT_RE.findall(r.get("stdout") or ""))
        v = sc.get("v(out)")
        if v is not None:
            vals.append(float(v))
    if len(vals) < runs // 2:
        return {"error": f"only {len(vals)}/{runs} runs produced data"}
    n = len(vals)
    mean = sum(vals) / n
    var = sum((x - mean) ** 2 for x in vals) / max(1, n - 1)
    std = var ** 0.5
    adm_vv = 10 ** (52.0 / 20.0)  # nominal gain ~333 V/V, refined below
    gm = quick_metrics()
    if "gain_db" in gm:
        adm_vv = 10 ** (gm["gain_db"] / 20.0)
    return {"runs": n,
            "out_mean_v": round(mean, 4),
            "out_std_v": round(std, 5),
            "offset_input_uV": round(std / adm_vv * 1e6, 1),
            "note": "input-referred offset = sigma(vout)/ADM"}


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "all"
    out: dict = {}
    if which in ("all", "pvt"):
        grid = []
        for corner in ("typical", "ff", "ss", "fs", "sf"):
            for vdd in (3.0, 3.3, 3.6):
                for temp in (-40, 27, 125):
                    m = quick_metrics(vdd=vdd, temp=temp, corner=corner,
                                      tran=False)
                    m.update(corner=corner, vdd=vdd, temp=temp)
                    grid.append(m)
                    status = "ok" if ("gain_db" in m and "error" not in m) else "FAIL"
                    print(f"{corner:8s} {vdd:.1f}V {temp:+4d}C  "
                          f"A0={m.get('gain_db', float('nan')):6.2f}dB  "
                          f"GBW={m.get('ugf_hz', float('nan'))/1e6:6.2f}MHz  "
                          f"PM={m.get('pm_deg', float('nan')):7.2f}deg  "
                          f"IDD={m.get('idd_ua', float('nan')):7.2f}uA  "
                          f"VOUT={m.get('out_dc', float('nan')):6.3f}V  [{status}]",
                          flush=True)
        sr_spots = []
        for corner in ("typical", "ff", "ss"):
            for vdd, temp in ((3.0, -40), (3.6, 125)):
                m = quick_metrics(vdd=vdd, temp=temp, corner=corner,
                                  tran=True)
                m.update(corner=corner, vdd=vdd, temp=temp, kind="sr_spot")
                sr_spots.append(m)
                print(f"SR spot {corner} {vdd}V {temp}C: "
                      f"{m.get('sr_rise_vus')}, {m.get('sr_fall_vus')} V/us",
                      flush=True)
        out["sr_spots"] = sr_spots
        out["pvt_grid"] = grid
        with open(os.path.join(OUTDIR, "pvt_summary.json"), "w") as f:
            json.dump(grid, f, indent=1)
    if which in ("all", "ext"):
        out["cmrr"] = cmrr(); print("CMRR:", out["cmrr"], flush=True)
        out["psrr"] = psrr(); print("PSRR:", out["psrr"], flush=True)
        out["icmr"] = icmr_run(); print("ICMR:", out["icmr"], flush=True)
        out["noise"] = noise(); print("NOISE:", out["noise"], flush=True)
        out["offset_mc"] = offset_mc(); print("OFFSET:", out["offset_mc"], flush=True)
        with open(os.path.join(OUTDIR, "extended.json"), "w") as f:
            json.dump(out, f, indent=1)
    with open(os.path.join(OUTDIR, "characterization.json"), "w") as f:
        json.dump(out, f, indent=1)
    print("done")
