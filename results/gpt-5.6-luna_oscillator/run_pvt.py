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
            metrics = flow.measure_oscillator(
                netlist, vdd=vdd, temp=temp, corner=corner, workdir=workdir,
                stop="3u",
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
    report = os.path.join(flow.OUTDIR, "final_design_report.md")
    with open(report) as stream:
        base = stream.read().split("\n## 13. Post-PEX PVT Characterization", 1)[0]
    with open(report, "w") as stream:
        stream.write(base.rstrip() + "\n")
        stream.write("\n## 13. Post-PEX PVT Characterization\n\n")
        stream.write(f"- **Status:** `{result['status']}`\n")
        stream.write("- Nominal process grid: VDD 3.0/3.3/3.6 V x TEMP -40/27/125 C, typical.\n")
        stream.write("- Process corners: typical, ff, ss, sf, fs at 3.3 V and 27 C.\n")
        stream.write("- Detailed measurements: `pvt_results.json`.\n")
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
