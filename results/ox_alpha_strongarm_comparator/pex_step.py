"""Resumable PEX-aware optimization (LOOP B) for the Strong-Arm comparator.

The full in-process flow was repeatedly killed by OOM on this shared machine
(14 GB, several parallel agent sessions), losing all progress each time. This
driver runs ONE candidate per process invocation and checkpoints state to
disk after every measured step, so any kill loses at most one candidate.

Same stages as the framework's branch-and-compare: propose distinct
candidates from one baseline -> build layout (dual-engine DRC -> LVS -> PEX)
-> simulate the extracted netlist -> evaluate against specs -> promote the
winner / archive the rest / withhold moves that fail twice.

Usage:
    python3 pex_step.py            # advance exactly one step
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from run_flow import (SPECS, _simulate_pex, base, make_comparator_proposer,
                      tune_post)  # noqa: E402  (module-level hooks are pure)
from strongarm_tb import CELL, NETLIST  # noqa: E402

STATE = os.path.join(HERE, "pex_state.json")
BEST_DIR = os.path.join(HERE, "best")

MOVES = [
    ("tail_up", ["XMTAIL"], 1.50),
    ("pair_L_down", None, 0.70),
    ("pair_w_up", ["XMINN", "XMINP"], 1.25),
    ("nlat_up", ["XMLATN", "XMLATP"], 1.35),
    ("plat_up", ["XMPLTN", "XMPLTP"], 1.30),
    ("combo_tail_nlat", None, 0.0),
]
PATIENCE = 4


def load_state():
    if os.path.isfile(STATE):
        with open(STATE) as f:
            return json.load(f)
    return {"iteration": 0, "pending": [], "fails": {}, "patience": 0,
            "best": None, "done": None}


def save_state(st):
    with open(STATE, "w") as f:
        json.dump(st, f, indent=1)


def apply_move(netlist, name):
    from mbg.flow_runtime import scale_device_widths
    import re
    if name == "tail_up":
        return scale_device_widths(netlist, 1.50, only=["XMTAIL"], w_max=9.9)
    if name == "pair_L_down":
        out = []
        pat = re.compile(r"^(?P<h>\s*X\w+\s+(?:\S+\s+){3,4}\S*fet\S*\s+.*?)"
                         r"\bL\s*=\s*(?P<l>[0-9.]+)u(?P<t>.*)$")
        for line in netlist.splitlines():
            m = pat.match(line)
            if m and line.split()[0] in ("XMINN", "XMINP"):
                new_l = max(float(m.group("l")) * 0.70, 0.35)
                line = f"{m.group('h')}L={new_l:g}u{m.group('t')}"
            out.append(line)
        return "\n".join(out) + "\n"
    if name == "combo_tail_nlat":
        nl = scale_device_widths(netlist, 1.30, only=["XMTAIL"], w_max=9.9)
        return scale_device_widths(nl, 1.15, only=["XMLATN", "XMLATP"],
                                   w_max=9.9)
    move = next(m for m in MOVES if m[0] == name)
    return scale_device_widths(netlist, move[2], only=move[1], w_max=9.9)


def evaluate(design, tag):
    """Build + verify + PEX-simulate one design; returns (ok, metrics, layout)."""
    design = design.evolve(circuit={**design.circuit, "_tag": tag})
    try:
        layout = base.build_layout(design)
    except Exception as e:                                   # noqa: BLE001
        return False, {"error": f"build {type(e).__name__}: {e}"}, None
    if not layout.ok:
        return False, {"error": layout.message or "layout/verify failed"}, layout
    metrics = _simulate_pex(design, layout)
    from mbg.specs import evaluate_specs
    rep = evaluate_specs(metrics, SPECS, "pex")
    return True, {"metrics": metrics, "score": rep.score,
                  "passed": rep.passed,
                  "report": rep.as_dict()}, layout


def main() -> int:
    st = load_state()
    if st["done"]:
        print(f"[STEP] already done: {st['done']}")
        return 0

    # step 0: establish the baseline (current best-known netlist through the
    # full layout->DRC/LVS/PEX/sim leg)
    if st["best"] is None:
        seed_netlist = os.path.join(HERE, "seed_netlist.spice")
        netlist = open(seed_netlist).read() if os.path.isfile(seed_netlist) \
            else NETLIST
        from mbg.flow import DesignPoint
        ok, data, layout = evaluate(DesignPoint(cell=CELL, netlist=netlist,
                                                circuit={}, note="baseline"),
                                    "step0_baseline")
        if not ok:
            print("[STEP] baseline failed:", data.get("error"))
            return 1
        st["best"] = {"netlist": netlist, "iteration": 0,
                      "score": data["score"], "passed": data["passed"],
                      "metrics": data["metrics"]}
        os.makedirs(BEST_DIR, exist_ok=True)
        if layout.gds_path:
            shutil.copy2(layout.gds_path,
                         os.path.join(BEST_DIR, "strongarm_comparator.gds"))
        if layout.pex_netlist:
            shutil.copy2(layout.pex_netlist,
                         os.path.join(BEST_DIR, "strongarm_comparator_pex.spice"))
        if data["passed"]:
            st["done"] = "PASS"
            save_state(st)
            print("[STEP] baseline already passes all PEX specs")
            return 0
        print(f"[STEP] baseline score {data['score']:.4g}")
        save_state(st)
        return 0

    # pick the next move: rotate the vocabulary per iteration, skip moves
    # that failed twice without ever helping
    if not st["pending"]:
        st["iteration"] += 1
        order = [MOVES[(st["iteration"] - 1 + j) % len(MOVES)]
                 for j in range(3)]
        st["pending"] = [m[0] for m in order
                         if st["fails"].get(m[0], 0) < 2]
        if not st["pending"]:
            alive = [m for m, n in st["fails"].items() if n < 2]
            if not alive:
                st["done"] = "EXHAUSTED"
                save_state(st)
                print("[STEP] no moves left that have not failed twice")
                return 0
            st["pending"] = alive[:3]
        if st["iteration"] > 1 and st.get("last_promotion_iter") != st["iteration"] - 1:
            st["patience"] = st.get("patience", 0) + 1
            if st["patience"] >= PATIENCE:
                st["done"] = "NOT_CONVERGED_PATIENCE"
                save_state(st)
                print("[STEP] stopped improving; patience exhausted")
                return 0
        print(f"[STEP] iteration {st['iteration']} pending={st['pending']}")
        save_state(st)
        return 0

    name = st["pending"].pop(0)
    tag = f"cand_{name}_{st['iteration']}"
    print(f"[STEP] measuring {tag}")
    from mbg.flow import DesignPoint
    cand = DesignPoint(
        cell=CELL, netlist=apply_move(st["best"]["netlist"], name),
        circuit={"move": name})
    ok, data, layout = evaluate(cand, tag)
    if not ok:
        st["fails"][name] = st["fails"].get(name, 0) + 1
        print(f"[STEP]   {tag}: ERROR {data.get('error','')[:120]}")
        save_state(st)
        return 0

    base_score = st["best"]["score"]
    improved = data["score"] < base_score
    print(f"[STEP]   {tag}: score {data['score']:.4g} "
          f"(baseline {base_score:.4g})"
          + ("  PROMOTED" if improved else "")
          + ("  PASSES ALL SPECS" if data["passed"] else ""))
    if data["passed"]:
        st["best"] = {"netlist": cand.netlist, "iteration": st["iteration"],
                      "score": data["score"], "passed": True,
                      "metrics": data["metrics"], "move": name}
        os.makedirs(BEST_DIR, exist_ok=True)
        if layout.gds_path:
            shutil.copy2(layout.gds_path,
                         os.path.join(BEST_DIR, "strongarm_comparator.gds"))
        if layout.pex_netlist:
            shutil.copy2(layout.pex_netlist,
                         os.path.join(BEST_DIR, "strongarm_comparator_pex.spice"))
        st["done"] = "PASS"
    elif improved:
        st["best"] = {"netlist": cand.netlist, "iteration": st["iteration"],
                      "score": data["score"], "passed": False,
                      "metrics": data["metrics"], "move": name}
        st["last_promotion_iter"] = st["iteration"]
        os.makedirs(BEST_DIR, exist_ok=True)
        if layout.gds_path:
            shutil.copy2(layout.gds_path,
                         os.path.join(BEST_DIR, "strongarm_comparator.gds"))
        if layout.pex_netlist:
            shutil.copy2(layout.pex_netlist,
                         os.path.join(BEST_DIR, "strongarm_comparator_pex.spice"))
        st["patience"] = 0
    else:
        st["fails"][name] = st["fails"].get(name, 0) + 1
    save_state(st)
    return 0


if __name__ == "__main__":
    sys.exit(main())
