"""Characterize the sign-off PEX netlist across requested PVT conditions."""
import json
import os
import sys

from mbg.specs import evaluate_specs

import run_oscillator as flow


PEX = os.path.join(flow.OUTDIR, "final", "oscillator.pex.spice")
PVT_POINTS = (
    [(v, t, "typical") for v in (3.0, 3.3, 3.6) for t in (-40.0, 27.0, 125.0)]
    + [(3.3, 27.0, c) for c in ("ff", "ss", "sf", "fs")]
)


def main():
    with open(PEX) as stream:
        netlist = stream.read()
    records = []
    for vdd, temp, corner in PVT_POINTS:
        label = f"vdd_{vdd:g}_temp_{temp:g}_{corner}"
        workdir = os.path.join(flow.OUTDIR, "pvt", label)
        print(f"[PVT] {label}", flush=True)
        try:
            metrics = flow.measure_osc(
                netlist, "oscillator", vdd=vdd, temp=temp, corner=corner,
                workdir=workdir, stop="12u",
            )
            report = evaluate_specs(metrics, flow.SPECS, source=label)
            status = "PASS" if report.passed else "FAIL"
            records.append({
                "vdd": vdd, "temp_c": temp, "corner": corner,
                "status": status, "metrics": metrics, "specs": report.as_dict(),
            })
            print(f"[PVT] {label}: {status}", flush=True)
        except Exception as exc:
            records.append({
                "vdd": vdd, "temp_c": temp, "corner": corner,
                "status": "NOT RUN", "error": f"{type(exc).__name__}: {exc}",
            })
            print(f"[PVT] {label}: NOT RUN ({exc})", flush=True)

    passed = all(r["status"] == "PASS" for r in records) and len(records) == len(PVT_POINTS)
    result = {
        "status": "PASS" if passed else "FAIL",
        "scope": {
            "netlist": PEX,
            "nominal_grid": "VDD=3.0/3.3/3.6 V x TEMP=-40/27/125 C at typical",
            "process_corners": ["typical", "ff", "ss", "sf", "fs"],
            "corner_grid": "3.3 V, 27 C for ff/ss/sf/fs",
            "startup": "normal VDD PWL ramp; no pulse or forced internal initial condition",
        },
        "records": records,
    }
    out = os.path.join(flow.OUTDIR, "pvt_results.json")
    with open(out, "w") as stream:
        json.dump(result, stream, indent=2)
        stream.write("\n")
    print("\nPVT SUMMARY:", result["status"])
    for r in records:
        m = r.get("metrics", {})
        f = m.get("freq_mhz", None)
        s = m.get("startup_us", None)
        d = m.get("duty_pct", None)
        print(f"  {r['corner']:>8} VDD={r['vdd']:.1f} T={r['temp_c']:>6g}C "
              f"{r['status']:>6}  f={f} MHz start={s} us duty={d}%")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
