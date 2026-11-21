#!/usr/bin/env python3
"""Sign-off matrix for MOSFETs with nf>1, m>1 and interdigitated matched pairs.

Every case runs ``spice_to_gds_with_checks`` in its own subprocess. A case is
PASS only when Magic DRC, LVS and internal connectivity pass, a PEX netlist exists, and the extracted channel width of each
MOS model equals the schematic's (W * m summed; dummies excluded). ``single``
and matched cells use both supplies; ``lone`` cells are one transistor whose
drain, gate and source are single-terminal nets, so their pins land on the
device's own straps.

Statuses: PASS, FAIL, NOT RUN. Output: <out>/results.jsonl, <out>/summary.md,
<out>/<case>/.

Examples:
  .venv/bin/python scripts/qualify_multifinger.py --list
  .venv/bin/python scripts/qualify_multifinger.py --only single_nmos_nf2_m2_macro
  .venv/bin/python scripts/qualify_multifinger.py --jobs 3 --out ~/mbg/multifinger/public
"""
import argparse
import concurrent.futures as cf
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FINGER_W = 2.0
SINGLE = [(1, 1), (2, 1), (4, 1), (1, 2), (2, 2), (4, 2), (2, 6), (1, 24), (2, 20)]
MATCHED = [(2, 1), (1, 2), (2, 2), (4, 2)]


def mos(name, d, g, s, b, kind, nf=1, m=1):
    model = "nfet_03v3" if kind == "nmos" else "pfet_03v3"
    tail = f" m={m}" if m > 1 else ""
    return f"{name} {d} {g} {s} {b} {model} L=1u W={FINGER_W * nf:g}u nf={nf}{tail}"


def cell(name, ports, devices):
    return "\n".join([f".subckt {name} {' '.join(ports)}", *devices, ".ends", ""])


def single(kind, nf, m):
    if kind == "nmos":
        devs = [mos("XM1", "d", "g", "vss", "vss", "nmos", nf, m),
                mos("XM2", "d", "b", "vdd", "vdd", "pmos")]
    else:
        devs = [mos("XM1", "d", "g", "vdd", "vdd", "pmos", nf, m),
                mos("XM2", "d", "b", "vss", "vss", "nmos")]
    return cell("mf", ["vdd", "vss", "d", "g", "b"], devs)


def lone(kind, nf, m):
    supply = "vss" if kind == "nmos" else "vdd"
    return cell("mf", ["d", "g", "s", supply], [mos("XM1", "d", "g", "s", supply, kind, nf, m)])


def diff_pair(nf, m):
    return cell("mf", ["vdd", "vss", "o1", "o2", "inp", "inn", "vb", "vp"], [
        mos("XM1", "o1", "inp", "t", "vss", "nmos", nf, m),
        mos("XM2", "o2", "inn", "t", "vss", "nmos", nf, m),
        mos("XM3", "t", "vb", "vss", "vss", "nmos"),
        mos("XM4", "o1", "vp", "vdd", "vdd", "pmos"),
        mos("XM5", "o2", "vp", "vdd", "vdd", "pmos")])


def mirror(nf, m, ratio):
    return cell("mf", ["vdd", "vss", "iref", "iout", "vp"], [
        mos("XM1", "iref", "iref", "vss", "vss", "nmos", nf, m),
        mos("XM2", "iout", "iref", "vss", "vss", "nmos", nf, m * ratio),
        mos("XM3", "iref", "vp", "vdd", "vdd", "pmos"),
        mos("XM4", "iout", "vp", "vdd", "vdd", "pmos")])


def ota(nf, m):
    return cell("mf", ["vdd", "vss", "inn", "inp", "out", "vb"], [
        mos("XM1", "o1", "inn", "t", "vss", "nmos", nf, m),
        mos("XM2", "out", "inp", "t", "vss", "nmos", nf, m),
        mos("XM3", "o1", "o1", "vdd", "vdd", "pmos", nf, m),
        mos("XM4", "out", "o1", "vdd", "vdd", "pmos", nf, m),
        mos("XM5", "t", "vb", "vss", "vss", "nmos", nf, m)])


def cases():
    out = {}
    for macro, tag in ((True, "macro"), (False, "plain")):
        for kind in ("nmos", "pmos"):
            for nf, m in SINGLE:
                out[f"single_{kind}_nf{nf}_m{m}_{tag}"] = (single(kind, nf, m), macro)
                if not macro:     # public macros need explicit vdd and vss ports
                    out[f"lone_{kind}_nf{nf}_m{m}_{tag}"] = (lone(kind, nf, m), macro)
        for nf, m in MATCHED:
            out[f"diffpair_nf{nf}_m{m}_{tag}"] = (diff_pair(nf, m), macro)
            out[f"mirror11_nf{nf}_m{m}_{tag}"] = (mirror(nf, m, 1), macro)
            out[f"mirror12_nf{nf}_m{m}_{tag}"] = (mirror(nf, m, 2), macro)
            out[f"ota_nf{nf}_m{m}_{tag}"] = (ota(nf, m), macro)
    return out


_DEV = re.compile(r"^(?:X|M)\S*\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+([np]fet_03v3)\b(.*)$", re.I)
_UNIT = {"": 1.0, "u": 1.0, "n": 1e-3, "m": 1e3, "p": 1e-6}


def _um(text, key):
    found = re.search(rf"\b{key}=([0-9.eE+-]+)([unmp]?)", text, re.I)
    return float(found.group(1)) * _UNIT[found.group(2).lower()] if found else None


def channel_width(text, schematic):
    """Total channel width per model; a device with drain == source is a dummy."""
    total = {}
    for line in re.sub(r"\n\+", " ", text).splitlines():
        hit = _DEV.match(line.strip())
        if not hit:
            continue
        d, _g, s, _b, model, rest = hit.groups()
        if not schematic and d == s:
            continue
        w = _um(rest, "w")
        mult = re.search(r"\bm=(\d+)", rest, re.I)
        count = int(mult.group(1)) if mult and schematic else 1
        if w is not None:
            total[model.lower()] = round(total.get(model.lower(), 0.0) + w * count, 3)
    return total


def child(name, out):
    netlist, macro = cases()[name]
    from mbg.pipeline import spice_to_gds_with_checks
    run = Path(out) / name
    run.mkdir(parents=True, exist_ok=True)
    (run / "input.spice").write_text(netlist)
    kw = {"macro_config": {"enabled": True}} if macro else {}
    r = spice_to_gds_with_checks(netlist, outdir=str(run / "run"), verbosity=0, **kw)
    ver = r.get("verification") or {}
    lvs = r.get("lvs") or {}
    report = run / "run" / "mf.lvs.out"
    final = ""
    if report.is_file():
        finals = re.findall(r"Final result:\s*(.*)", report.read_text(errors="replace"))
        final = finals[-1] if finals else ""
    extracted = run / "run" / "mf_extracted.spice"
    want = channel_width(netlist, True)
    got = channel_width(extracted.read_text(), False) if extracted.is_file() else {}
    pex = (r.get("pex") or {}).get("pex_path")
    legs = {
        "magic": bool((r.get("drc") or {}).get("clean")),
        "lvs": bool(lvs.get("match")),
        "connectivity": bool(ver.get("clean")),
        "pex": bool(pex and os.path.isfile(pex)),
        "width": bool(got) and got == want,
    }
    return {
        "case": name, "status": "PASS" if all(legs.values()) else "FAIL", "legs": legs,
        "drc_rules": list((r.get("drc") or {}).get("rules_violated") or [])[:6],
        "lvs_final": final, "width_schematic": want, "width_extracted": got,
        "opens": ver.get("open_details", [])[:4], "shorts": ver.get("short_details", [])[:4],
        "missing": ver.get("missing_access_details", [])[:4],
    }


def launch(name, out, timeout):
    env = dict(os.environ, PYTHONPATH=str(REPO / "src"))
    start = time.time()
    try:
        p = subprocess.run([sys.executable, __file__, "--child", name, "--out", str(out)],
                           env=env, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"case": name, "status": "FAIL", "error": f"timeout after {timeout}s",
                "elapsed": round(time.time() - start, 1)}
    marks = [ln for ln in p.stdout.splitlines() if ln.startswith("@@RESULT ")]
    if marks:
        res = json.loads(marks[-1][9:])
    else:
        tail = [ln for ln in p.stderr.strip().splitlines() if ln.strip()][-1:] or ["no output"]
        res = {"case": name, "status": "FAIL", "error": tail[0][:300]}
    res["elapsed"] = round(time.time() - start, 1)
    return res


def summarize(out, rows):
    rows = sorted(rows, key=lambda r: r["case"])
    passed = sum(r["status"] == "PASS" for r in rows)
    lines = [f"# Multi-finger matrix: {passed}/{len(rows)} PASS", "",
             "| case | status | failing legs / reason |", "|---|---|---|"]
    for r in rows:
        bad = [k for k, v in (r.get("legs") or {}).items() if not v]
        why = r.get("error") or ", ".join(bad + r.get("drc_rules", []))
        if r.get("lvs_final") and "lvs" in bad:
            why += f"; {r['lvs_final']}"
        lines.append(f"| {r['case']} | {r['status']} | {why} |")
    (Path(out) / "summary.md").write_text("\n".join(lines) + "\n")
    return passed


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--only", default="", help="comma-separated case names or substrings")
    ap.add_argument("--jobs", type=int, default=3)
    ap.add_argument("--timeout", type=int, default=1200)
    ap.add_argument("--out", default=os.path.expanduser(
        f"~/mbg/multifinger/{time.strftime('%Y%m%dT%H%M%S')}"))
    ap.add_argument("--child", help=argparse.SUPPRESS)
    a = ap.parse_args()
    if a.child:
        print("@@RESULT " + json.dumps(child(a.child, a.out)), flush=True)
        return 0
    names = list(cases())
    if a.only:
        keys = [k for k in a.only.split(",") if k]
        names = [n for n in names if any(k in n for k in keys)]
    if a.list:
        print("\n".join(names))
        print(f"{len(names)} cases", file=sys.stderr)
        return 0
    out = Path(a.out).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    rows = []
    with cf.ThreadPoolExecutor(max_workers=max(1, a.jobs)) as pool, \
            open(out / "results.jsonl", "a") as log:
        for fut in cf.as_completed([pool.submit(launch, n, out, a.timeout) for n in names]):
            res = fut.result()
            rows.append(res)
            log.write(json.dumps(res) + "\n")
            log.flush()
            print(f"{res['status']:5} {res['case']} ({res.get('elapsed')}s)", flush=True)
    passed = summarize(out, rows)
    print(f"{passed}/{len(rows)} PASS; {out}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
