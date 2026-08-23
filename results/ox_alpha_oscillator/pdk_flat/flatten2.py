"""Flatten gf180mcuD ngspice model cards to literal parameters (nominal corner).

Binds design.ngspice default switches (sw_stat_global=0, sw_stat_mismatch=0,
fnoicor=0, mc_skew/res_mc_skew/cap_mc_skew=3); statistical terms multiply
those zeros and fold away. Expressions containing temper/dtemp stay dynamic.
Correctness is verified separately by comparing operating points.
"""
import re
import sys

SRC_LIB, SRC_DESIGN, DST = sys.argv[1], sys.argv[2], sys.argv[3]

lines = open(SRC_LIB).read().splitlines()
params = {}
for ln in open(SRC_DESIGN):
    s = ln.strip()
    m = re.match(r"\.param\s+(.+)", s, re.I)
    if m:
        for k, v in re.findall(r"(\w+)\s*=\s*('[^']*'|[^\s]+)", m.group(1)):
            params[k] = v
for ln in lines:
    s = ln.strip()
    m = re.match(r"\.param\s+(.+)", s, re.I)
    if m:
        for k, v in re.findall(r"(\w+)\s*=\s*('[^']*'|[^\s]+)", m.group(1)):
            params[k] = v

SCI = re.compile(r"\d+\.?\d*[eE][+-]?\d+")


BIND = {}
DYNAMIC = re.compile(r"temper|dtemp", re.I)
CALLFOLD = re.compile(r"\b(?:agauss|gauss|random)\s*\((?:[^()]*(?:\([^()]*\))?[^()]*)\)")
ZERONAMES = re.compile(r"\b(?:sw_stat_global|sw_stat_mismatch)\b|\bmc_[A-Za-z_]\w*|\bmis_[A-Za-z_]\w*")


def fold(expr):
    """Fold statistical calls/params to zero; return None if letters remain."""
    prev = None
    while prev != expr:
        prev = expr
        expr = CALLFOLD.sub("0.0", expr)
        expr = ZERONAMES.sub("0.0", expr)
    if SCI.sub("", expr) and re.search(r"[A-Za-z_]", SCI.sub("", expr)):
        return None
    return expr


def ev(expr):
    env = {"__builtins__": {}}
    return float(eval(expr, env, BIND))


def resolve(tok, depth=0):
    if depth > 16:
        return None
    tok = tok.strip()
    if tok.startswith("'") and tok.endswith("'"):
        tok = tok[1:-1].strip()
        if DYNAMIC.search(tok):
            return None

        def sub(mm):
            name = mm.group(0)
            r = resolve(params.get(name, name), depth + 1)
            return r if r is not None else name
        e = re.sub(r"[A-Za-z_]\w*", sub, tok)
        if ZERONAMES.search(e) or CALLFOLD.search(e):
            e = fold(e)
            if e is None:
                return None
        if SCI.sub("", e) and re.search(r"[A-Za-z_]", SCI.sub("", e)):
            return None
        try:
            return repr(ev(e))
        except Exception:
            return None
    try:
        return repr(float(tok))
    except ValueError:
        return None


resolved = {k: v for k, v in ((k, resolve(v)) for k, v in list(params.items()))
            if v is not None}
BIND.update({k: float(v) for k, v in resolved.items()})
if "--debug" in sys.argv:
    for probe in ("fnoicor", "nfet_03v3_noia", "mc_sig_vth", "nfet_03v3_sig_vth1",
                  "mc_sig_vth2", "sw_stat_global", "mc_skew", "nfet_03v3_sig_vthn",
                  "mc_sig_vthn"):
        print(probe, "| raw:", repr(params.get(probe)),
              "| resolved:", resolved.get(probe))
print(f"params={len(params)} flattened={len(resolved)}")

QREF = re.compile(r"'([^']+)'")
out, in_model, kept, flatn = [], False, 0, 0


def repl(mm):
    global kept, flatn
    e = mm.group(1)
    if DYNAMIC.search(e):
        kept += 1
        return mm.group(0)

    def sub(m2):
        return resolved.get(m2.group(0), m2.group(0))
    e2 = re.sub(r"[A-Za-z_]\w*", sub, e)
    if ZERONAMES.search(e2) or CALLFOLD.search(e2):
        e2 = fold(e2)
        if e2 is None:
            kept += 1
            return mm.group(0)
    if SCI.sub("", e2) and re.search(r"[A-Za-z_]", SCI.sub("", e2)):
        kept += 1
        return mm.group(0)
    try:
        f = repr(ev(e2))
    except Exception:
        kept += 1
        return mm.group(0)
    flatn += 1
    return f


for ln in lines:
    s = ln.strip()
    if s.lower().startswith(".model"):
        out.append(ln)
        in_model = True
        continue
    if in_model:
        if s.startswith("+"):
            out.append(QREF.sub(repl, ln))
            continue
        in_model = False
        out.append(ln)
        continue
    out.append(ln)

open(DST, "w").write("\n".join(out) + "\n")
print(f"in-model refs flattened={flatn} left-dynamic={kept}")
print("wrote", DST)
