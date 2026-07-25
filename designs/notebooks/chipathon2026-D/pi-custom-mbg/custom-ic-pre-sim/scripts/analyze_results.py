#!/usr/bin/env python3
"""
Analyze ngspice raw simulation output and extract key metrics.
Usage: python3 scripts/analyze_results.py /tmp/sim.raw [--type tran|ac]
"""
import sys, os, argparse, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.utils import setup_env, print_banner, print_result
setup_env()

def parse_raw(raw_path):
    """Parse ngspice raw file into {name: array} dict."""
    with open(raw_path, "rb") as f:
        blob = f.read()
    hdr = blob.split(b"Binary:\n")[0].decode("utf-8", errors="replace")
    n_vars = int([l for l in hdr.split("\n") if "No. Variables" in l][0].split()[-1])
    names = []
    for l in hdr.split("\n"):
        if "Variables:" in l: pass
        elif "\t" in l and l.strip():
            names.append(l.strip().split("\t")[1].strip())
    data = np.frombuffer(blob[blob.find(b"Binary:\n")+8:], dtype=np.float64).reshape(-1, n_vars)
    d = {}
    for i, n in enumerate(names):
        s = n.replace("v(", "").replace(")", "").replace("V(", "").replace(")", "")
        d[s] = data[:, i]
    return d

def analyze_transient(data, vdd=1.8):
    """Extract VOH, VOL, delays from transient data."""
    t = data.get("time", [])
    vin = data.get("vin", data.get("v(vin)", []))
    vout = data.get("vout", data.get("v(vout)", []))
    if len(t) == 0:
        # Try to find any signal
        keys = [k for k in data if k != "time"]
        if keys:
            vout = data[keys[0]]
    half = vdd / 2
    voh = float(np.max(vout[len(t)//4:])) if len(t) > 0 else 0
    vol = float(np.min(vout[len(t)//4:])) if len(t) > 0 else 0
    
    tphl, tplh = None, None
    if len(t) > 0 and len(vin) > 0:
        ri = next((i for i in range(1, len(t)) if vin[i-1] < half <= vin[i]), None)
        fi = next((i for i in range(ri or 0, len(t)) if vout[i-1] > half >= vout[i]), None)
        tphl = (t[fi] - t[ri]) * 1e9 if (ri and fi) else None
        fv = next((i for i in range(len(t)-1, len(t)//2, -1) if vin[i-1] > half >= vin[i]), None)
        rv = next((i for i in range(fv or 0, len(t)) if vout[i-1] < half <= vout[i]), None)
        tplh = (t[rv] - t[fv]) * 1e9 if (fv and rv) else None
    
    return {"voh": voh, "vol": vol, "swing_mv": (voh-vol)*1000, "tphl_ns": tphl, "tplh_ns": tplh}

def analyze_ac(data):
    """Extract gain, GBW, phase margin from AC data."""
    freq = data.get("frequency", data.get("freq", []))
    vout = None
    for k, v in data.items():
        if "db" in k.lower() or "vout" in k.lower() or "mag" in k.lower():
            vout = v
            break
    if vout is None:
        keys = [k for k in data if k not in ("frequency", "freq")]
        vout = data[keys[0]] if keys else None
    
    if vout is None or len(freq) == 0:
        return {"error": "No AC data found"}
    
    dc_gain = float(vout[0]) if len(vout) > 0 else 0
    gbw_idx = next((i for i in range(len(vout)) if vout[i] < 0), len(vout)-1)
    gbw = float(freq[gbw_idx]) if gbw_idx < len(freq) else 0
    
    return {"dc_gain_db": dc_gain, "gbw_hz": gbw}

def main():
    parser = argparse.ArgumentParser(description="Analyze SPICE simulation output")
    parser.add_argument("raw_file", help="Path to .raw file")
    parser.add_argument("--type", choices=["tran", "ac"], default="tran")
    args = parser.parse_args()
    
    if not os.path.isfile(args.raw_file):
        print(f"File not found: {args.raw_file}")
        sys.exit(1)
    
    data = parse_raw(args.raw_file)
    print_banner("Simulation Results")
    print(f"  Signals: {[k for k in data.keys()][:8]}")
    
    if args.type == "tran":
        m = analyze_transient(data)
        print(f"  VOH = {m['voh']:.3f} V")
        print(f"  VOL = {m['vol']:.3f} V")
        print(f"  Swing = {m['swing_mv']:.0f} mV")
        if m["tphl_ns"]: print(f"  tPHL = {m['tphl_ns']:.3f} ns")
        if m["tplh_ns"]: print(f"  tPLH = {m['tplh_ns']:.3f} ns")
    else:
        m = analyze_ac(data)
        if "error" in m:
            print(f"  Error: {m['error']}")
        else:
            print(f"  DC Gain = {m['dc_gain_db']:.1f} dB")
            print(f"  GBW = {m['gbw_hz']/1e6:.2f} MHz")

if __name__ == "__main__":
    main()
