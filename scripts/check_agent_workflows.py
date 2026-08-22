#!/usr/bin/env python3
"""Verify every agent platform describes the same PEX-aware design flow.

Three agent systems read three generated copies of the same instructions. The
failure mode this guards against is drift: one platform still telling its
agent that PEX is the last step while the others have moved on. Manual
inspection does not catch that reliably, so it is checked.

    python3 scripts/check_agent_workflows.py          # report
    python3 scripts/check_agent_workflows.py --quiet  # exit status only

Exit 0 when every platform covers the required concepts and none of them
contain a claim the methodology forbids.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

# Each platform, and for each the files it actually reads. Concepts are
# checked PER FILE, not against the concatenation: pooling the text lets one
# document quietly lose a concept while a sibling still mentions it, which is
# exactly the drift this script exists to catch.
FLOW_SKILL = "skills/mbg-pex-aware-flow/SKILL.md"
VERIFY_SKILL = "skills/mbg-ic-verify/SKILL.md"

PLATFORMS = {
    "canonical (.ai)": {
        "full_auto": REPO / ".ai/skills/mbg-full-auto/SKILL.md",
        "reviewers": REPO / ".ai/skills/mbg-reviewers/SKILL.md",
        "knowledge2": REPO / ".ai/knowledge/FULL_AUTOMATE.md",
        "flow": REPO / ".ai/skills/mbg-pex-aware-flow/SKILL.md",
        "verify": REPO / ".ai/skills/mbg-ic-verify/SKILL.md",
        "workflows": [REPO / ".ai/workflows/mbg-full-auto.md",
                      REPO / ".ai/workflows/mbg-partial-automate.md"],
        "knowledge": REPO / ".ai/knowledge/DESIGN_FLOW.md",
        "setup": REPO / ".ai/skills/mbg-setup/SKILL.md",
        "complexity": REPO / ".ai/skills/mbg-routing-debug/SKILL.md",
        "economy": REPO / ".ai/skills/mbg-context-economy/SKILL.md",
    },
    "Claude Code": {
        "full_auto": REPO / ".claude/skills/mbg-full-auto/SKILL.md",
        "reviewers": REPO / ".claude/skills/mbg-reviewers/SKILL.md",
        "flow": REPO / ".claude" / FLOW_SKILL,
        "verify": REPO / ".claude" / VERIFY_SKILL,
        "workflows": [REPO / ".claude/commands/mbg-full-auto.md",
                      REPO / ".claude/commands/mbg-partial-automate.md"],
        "setup": REPO / ".claude/skills/mbg-setup/SKILL.md",
        "complexity": REPO / ".claude/skills/mbg-routing-debug/SKILL.md",
        "economy": REPO / ".claude/skills/mbg-context-economy/SKILL.md",
    },
    "OpenCode": {
        "full_auto": REPO / ".opencode/skills/mbg-full-auto/SKILL.md",
        "reviewers": REPO / ".opencode/skills/mbg-reviewers/SKILL.md",
        "flow": REPO / ".opencode" / FLOW_SKILL,
        "verify": REPO / ".opencode" / VERIFY_SKILL,
        "workflows": [REPO / ".opencode/commands/mbg-full-auto.md",
                      REPO / ".opencode/commands/mbg-partial-automate.md"],
        "setup": REPO / ".opencode/skills/mbg-setup/SKILL.md",
        "complexity": REPO / ".opencode/skills/mbg-routing-debug/SKILL.md",
        "economy": REPO / ".opencode/skills/mbg-context-economy/SKILL.md",
    },
    "Codex": {
        "full_auto": REPO / "plugins/mbg-analog/skills/mbg-full-auto/SKILL.md",
        "reviewers": REPO / "plugins/mbg-analog/skills/mbg-reviewers/SKILL.md",
        "flow": REPO / "plugins/mbg-analog" / FLOW_SKILL,
        "verify": REPO / "plugins/mbg-analog" / VERIFY_SKILL,
        "workflows": [],
        "setup": REPO / "plugins/mbg-analog/skills/mbg-setup/SKILL.md",
        "complexity": REPO / "plugins/mbg-analog/skills/mbg-routing-debug/SKILL.md",
        "economy": REPO / "plugins/mbg-analog/skills/mbg-context-economy/SKILL.md",
    },
}

# Concept -> pattern. The flow skill must carry all of these on its own.
REQUIRED = {
    "pre-layout iteration":   r"pre-?layout.{0,40}(iterat|loop|fine-?tune|optimi)",
    "layout generation":      r"(generate|regenerate).{0,20}layout|layout generation",
    "DRC":                    r"\bDRC\b",
    "LVS":                    r"\bLVS\b",
    "PEX extraction":         r"PEX[ _-]?(extraction|EXTRACTION)|extract.{0,20}parasitic",
    "PEX simulation":         r"PEX[ _-]?(simulation|SIMULATION)|simulate.{0,30}extracted",
    "PEX spec evaluation":    r"(spec\w*).{0,60}(PEX|post-?layout)|(PEX|post-?layout).{0,60}(spec\w*)",
    "post-layout fine-tuning": r"(PEX-?aware|post-?layout).{0,40}(fine-?tune|optimi)",
    "repeat loop":            r"\brepeat\b|\bre-?run\b|\bloop\b",
    "stop conditions":        r"(iteration limit|max_pex_iterations|stop condition|NOT_CONVERGED|converge)",
    "failure classification": r"TOOL_FAILURE|SPEC_FAILURE|VERIFICATION_FAILURE",
    # Dual-engine DRC — Magic alone is no longer a sign-off.
    "KLayout DRC":          r"KLayout",
    "Magic DRC":            r"Magic",
    "dual DRC":             r"dual[- ]engine|both engines|Magic and KLayout|Magic \*and\* KLayout",
    "KLayout is sign-off":  r"sign-?off authority|primary.{0,20}sign-?off|KLayout.{0,40}sign-?off",
    "DRC reconciliation":   r"reconcil|DRC_DISAGREEMENT|consensus",
}

# A workflow document has to get the loop right, but need not restate the
# whole taxonomy.
WORKFLOW_REQUIRED = {
    "two loops":            r"LOOP A|LOOP B|two (optimi[sz]ation )?loops",
    "PEX simulation":       r"PEX[ _-]?(simulation|SIMULATION)|simulate.{0,30}extracted",
    "post-layout re-verify": r"(re-?run|repeat).{0,40}(DRC|LVS|PEX)|DRC\s*(→|->)\s*LVS\s*(→|->)\s*PEX",
}

# The FULL AUTOMATE skill must carry these on its own.
FULL_AUTO_REQUIRED = {
    "canonical command":    r"/mbg-full-auto",
    "FULL AUTOMATE mode":   r"FULL AUTOMATE|fully automated",
    "specification parsing": r"(parse|normalis|normaliz).{0,30}(specification|request)",
    "pre-layout loop":      r"LOOP A|pre-?layout.{0,40}(loop|iterat|fine-?tune)",
    "PEX-aware loop":       r"LOOP B|PEX-?aware.{0,40}(loop|iterat|fine-?tune)",
    "reviewers":            r"Devil|Angel",
    "final sign-off":       r"sign-?off",
    "tapeout-ready gate":   r"tapeout-?ready|TAPEOUT_READY",
    "design report":        r"design report|final_design_report",
    "bounded iteration":    r"max_pex_iterations|max_pre_iterations|bounded",
    "non-convergence":      r"NOT_CONVERGED|non-?convergence",
    "no invented specs":    r"(never|not).{0,40}invent|CONFIGURATION_FAILURE",
    # Convergence methodology — the difference between a search and two guesses.
    "candidate experiments": r"candidate|branch-and-compare|several distinct",
    "measured independently": r"independent|attributab|measure each",
    "best-design retention": r"best design|incumbent|archive",
    "rollback":             r"roll ?back",
    "many bounded iterations": r"budget|effort|for_effort|iteration",
    "does not stop early":  r"do not stop|not a shutdown|continue through",
}

# The reviewer skill must carry these.
REVIEWER_REQUIRED = {
    "Devil role":           r"Devil",
    "Angel role":           r"Angel",
    "independence":         r"independen|neither summaris|does not summaris",
    "no direct edits":      r"never edit|not edit|cannot edit|advise",
    "severity scale":       r"CRITICAL.*HIGH|INFO.*CRITICAL|Severity",
    "synthesis precedence": r"precedence|outranks|takes priority",
    "evidence wins":        r"cannot approve past|evidence.{0,40}(outrank|priority|decide)",
    "verdicts":             r"ACCEPT|BLOCK|ESCALATE",
}

#: The verification skill must describe dual-engine DRC on its own.
VERIFY_REQUIRED = {
    "KLayout DRC":         r"KLayout",
    "Magic DRC":           r"Magic",
    "KLayout is sign-off": r"sign-?off authority|primary.{0,20}sign-?off",
    "Magic complementary": r"complementary|independent",
    "reconciliation":      r"reconcil|DRC_DISAGREEMENT|dual[- ]engine",
    "no Magic-only DRC":   r"never report DRC from Magic alone|not.{0,30}Magic alone",
}


#: The setup skill must describe the environment MBG actually installs into.
#: This exists because all three platforms once documented only "run the
#: installer" and knew nothing about $MBG_HOME — so an agent asked why `mbg`
#: was not a command, or why /mbg-* worked only inside the clone, had nothing
#: to go on.
SETUP_REQUIRED = {
    "single installer":     r"\./install\.sh",
    "stages":               r"--stage|six stages",
    "MBG_HOME":             r"MBG_HOME|\$HOME/\.mbg|~/\.mbg",
    "activate.sh":          r"activate\.sh",
    "mbg launcher":         r"`?mbg check`?|mbg-python|bin/mbg",
    "rc file integration":  r"bashrc|zshrc|rc file",
    "tools pinned by path": r"absolute path|MBG_KLAYOUT|MBG_MAGIC",
    "KLayout installed":    r"KLayout",
    "global install":       r"--stage global|user account|user-wide",
    "venv not auto-active": r"not activated|deliberately not|without activating",
}

#: The routing-debug skill must describe how the flow behaves on circuits
#: large enough to matter. This exists because MBG's first hard complexity
#: boundary — a 12-MOS clocked comparator — was reached with every platform's
#: documentation still describing an all-or-nothing router, a Magic-only DRC
#: gate, and "opens and shorts" as the whole of internal connectivity. An
#: agent asked why a supply net vanished, or why a body terminal could not
#: escape, had nothing to go on.
COMPLEXITY_REQUIRED = {
    "complex subcircuit":     r"complex|complexity",
    "multi-terminal routing": r"multi-?terminal|terminal group|Steiner|high-?degree",
    "net degree":             r"net degree|degree \d|max(imum)? degree",
    "partial routing":        r"partial|RoutePlan\.partial|all-?or-?nothing",
    "pin access / via landing": r"via landing|pin escape|access point",
    "same-net merge rule":    r"same-?net|merged? (into )?one (conductor|polygon)",
    "per-layer geometry":     r"per-?layer|layer's own minimum|MT\.1",
    "congestion awareness":   r"congestion|ripup|rip-?up|negotiat",
    "placement-routing feedback": r"place_with_routability|placement feedback|feedback loop|re-?place",
    "internal connectivity":  r"internal connectivity|connectivity\.verify|opens.{0,20}shorts",
    "missing access gate":    r"missing_access|no access point",
    "dual DRC":               r"KLayout",
    "LVS":                    r"\bLVS\b",
    "measure, do not assume": r"measure|do not (reach|assume)|not.{0,30}device count",
}

#: The context-economy skill must carry the concrete discipline, not a vague
#: "be efficient". This exists because a measured Codex session in this
#: repository spent 87% of a 1 MB conversation on tool output — one 1000-line
#: script re-read 22 times, git state polled 27+ times, and 33 KB spent
#: searching $HOME for a repository whose path was already in $MBG_ROOT.
#: Advice that does not name the habit does not change it, so each concept
#: below is a specific behaviour an agent can check itself against.
ECONOMY_REQUIRED = {
    "measured evidence":      r"\b87%|1,?065 ?KB|22 times|27\+? times",
    "resolve repo from env":  r"MBG_ROOT",
    "never search HOME":      r"(never search|do not (search|crawl)|hunting for)",
    "index before reading":   r"[Ii]ndex before|grep -n .\^def|structural question",
    "do not re-read":         r"[Rr]e-?read only|already in (your )?context|does not refresh",
    "do not poll state":      r"[Dd]o not poll|git status.{0,40}(twice|once)|State does not change",
    "verification ladder":    r"cheapest[- ]first|ladder",
    "internal check gates":   r"internal connectivity.{0,60}(gate|before)|gates the expensive",
    "reuse artifacts":        r"artifacts are on disk|from disk instead of|already wrote",
    "cap command output":     r"\| head -|\| tail -|[Cc]ap anything",
    "delegate bulk reading":  r"sub-?agent",
    "economy is not skipping checks": r"([Rr]eading less|verifying less|checking\s+less is not|never about not checking)",
}

# Generic names that must never be OFFERED as MBG commands. A line that
# forbids a name necessarily contains it, so prohibitions are exempt —
# otherwise the documentation telling agents not to use /full-auto would
# itself fail the check.
BAD_COMMANDS = r"(?<![\w/-])/(full-auto|full-design|design-auto|signoff|mbg-full-automate)\b"
PROHIBITION = r"\b(never|not|don'?t|do not|avoid|obsolete|instead of|rather than|deprecated|forbidden|must not)\b"


def offers_bad_command(text):
    out = []
    for line in text.splitlines():
        if re.search(BAD_COMMANDS, line) and not re.search(PROHIBITION, line, re.I):
            out.append(line.strip()[:70])
    return out


# Claims the methodology forbids anywhere.
FORBIDDEN = {
    "PEX treated as a completed gate":
        r"\|\s*PEX\s*\|\s*Extraction done\s*\|",
    "flow ends at PEX":
        r"PEX\s*(->|→)\s*(TAPEOUT|REPORT)\s*$",
    "success after extraction":
        r"PEX (extraction )?(complete|done)[^.\n]{0,20}(therefore|=)\s*(success|pass)",
}


def _check(text, required, label, say):
    bad = 0
    for concept, pattern in required.items():
        ok = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        say(f"    {concept:<26} {'PASS' if ok else 'FAIL'}")
        if not ok:
            bad += 1
    for name, pattern in FORBIDDEN.items():
        hit = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
        if hit:
            say(f"    {name:<26} FAIL  {hit.group(0)[:60]!r}")
            bad += 1
    return bad


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    def say(*a):
        if not args.quiet:
            print(*a)

    failures = 0
    say("Agent design-flow consistency")
    say("=" * 52)

    for platform, spec in PLATFORMS.items():
        say(f"\n{platform}")

        flow = spec.get("flow")
        if flow is None or not flow.is_file():
            say(f"  {'flow skill':<28} FAIL  missing: "
                f"{flow.relative_to(REPO) if flow else '?'}")
            failures += 1
        else:
            say(f"  {flow.relative_to(REPO)}")
            failures += _check(flow.read_text(), REQUIRED, platform, say)

        for key, required, label in (("full_auto", FULL_AUTO_REQUIRED, "full-auto skill"),
                                     ("reviewers", REVIEWER_REQUIRED, "reviewer skill"),
                                     ("knowledge2", FULL_AUTO_REQUIRED, "full-auto knowledge"),
                                     ("verify", VERIFY_REQUIRED, "verification skill"),
                                     ("setup", SETUP_REQUIRED, "setup skill"),
                                     ("complexity", COMPLEXITY_REQUIRED,
                                      "complexity / routing-debug skill"),
                                     ("economy", ECONOMY_REQUIRED,
                                      "context-economy skill")):
            doc = spec.get(key)
            if doc is None:
                continue
            if not doc.is_file():
                say(f"  {label:<28} FAIL  missing: {doc.relative_to(REPO)}")
                failures += 1
                continue
            say(f"  {doc.relative_to(REPO)}")
            failures += _check(doc.read_text(), required, platform, say)

        for wf in spec.get("workflows", []):
            if not wf.is_file():
                say(f"  {'workflow':<28} FAIL  missing: {wf.relative_to(REPO)}")
                failures += 1
                continue
            say(f"  {wf.relative_to(REPO)}")
            failures += _check(wf.read_text(), WORKFLOW_REQUIRED, platform, say)

        # command-namespace drift, per file
        for key, doc in spec.items():
            docs = doc if isinstance(doc, list) else [doc]
            for dd in docs:
                if not hasattr(dd, "is_file") or not dd.is_file():
                    continue
                bad = offers_bad_command(dd.read_text())
                for line in bad:
                    say(f"    {'command namespace':<26} FAIL  "
                        f"{dd.name}: {line}")
                    failures += 1

        kn = spec.get("knowledge")
        if kn is not None:
            if not kn.is_file():
                say(f"  {'knowledge doc':<28} FAIL  missing: {kn.relative_to(REPO)}")
                failures += 1
            else:
                say(f"  {kn.relative_to(REPO)}")
                failures += _check(kn.read_text(), REQUIRED, platform, say)

    say("")
    if failures:
        say(f"{failures} check(s) failed. If the canonical .ai/ sources are")
        say("correct, regenerate the adapters:")
        say("  python3 scripts/sync_agent_tools.py")
        return 1
    say("All platforms describe the same PEX-aware flow.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
