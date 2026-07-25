#!/usr/bin/env python3
"""
Parse and summarize Magic DRC or netgen LVS reports.
Usage: python3 scripts/parse_report.py <report_file>
"""
import sys, re

def parse_drc(path):
    with open(path) as f:
        text = f.read()
    violations = re.findall(r"^[-0-9.]+\s+[-0-9.]+\s+[-0-9.]+\s+[-0-9.]+", text, re.MULTILINE)
    rules = re.findall(r"^([\w\d.]+)\s*(?:spacing|width|enclosure)\s*[<>=]", text, re.MULTILINE | re.IGNORECASE)
    count_m = re.search(r"COUNT:\s*(\d+)", text)
    count = count_m.group(1) if count_m else "?"
    print(f"DRC Report: {path}")
    print(f"  Rule violations: {len(violations)} geometric checks")
    print(f"  Rules triggered: {set(rules)}")
    print(f"  COUNT: {count} {'(clean!)' if count == '0' else ''}")
    if violations:
        for v in violations[:5]:
            print(f"    {v}")

def parse_lvs(path):
    with open(path) as f:
        text = f.read()
    match = "Circuits match uniquely" in text
    devices = re.search(r"Number of devices:\s*(\d+).*?Number of devices:\s*(\d+)", text)
    nets = re.search(r"Number of nets:\s*(\d+).*?Number of nets:\s*(\d+)", text)
    swaps = re.findall(r"(\w+)\s+\|\s+(\w+)\s+\*\*Mismatch", text)
    print(f"LVS Report: {path}")
    print(f"  Match: {'YES ✅' if match else 'NO ❌'}")
    if devices: print(f"  Devices: {devices.group(1)} vs {devices.group(2)}")
    if nets: print(f"  Nets: {nets.group(1)} vs {nets.group(2)}")
    if swaps: print(f"  Port swaps: {', '.join(f'{a}↔{b}' for a,b in swaps)}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: parse_report.py <report_file>")
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        sys.exit(1)
    if "drc" in path.lower():
        parse_drc(path)
    else:
        parse_lvs(path)
