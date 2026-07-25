#!/usr/bin/env python3
"""
Generate SPICE netlist from design specifications via LLM (DeepSeek).
Usage: python3 scripts/generate_netlist.py --prompt "..." [--output netlist.spice]
"""
import sys, os, argparse
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from common.utils import setup_env, print_banner
setup_env()

from core.pipeline import generate_netlist_from_prompt

def main():
    parser = argparse.ArgumentParser(description="Generate SPICE netlist from spec prompt")
    parser.add_argument("--prompt", "-p", help="Design specification prompt")
    parser.add_argument("--prompt-file", "-f", help="File containing prompt")
    parser.add_argument("--output", "-o", default="/tmp/output.spice", help="Output SPICE file")
    parser.add_argument("--model", default="deepseek-v4-flash", help="LLM model name")
    args = parser.parse_args()

    prompt = args.prompt
    if args.prompt_file:
        with open(args.prompt_file) as f:
            prompt = f.read()
    if not prompt:
        parser.print_help()
        sys.exit(1)

    print_banner("Generating SPICE Netlist from Specification")
    netlist = generate_netlist_from_prompt(prompt, model=args.model)

    if netlist:
        with open(args.output, "w") as f:
            f.write(netlist)
        print(f"\nNetlist saved to: {args.output}")
        print(f"Size: {len(netlist)} chars, {len(netlist.splitlines())} lines")
    else:
        print("Failed to generate netlist")
        sys.exit(1)

if __name__ == "__main__":
    main()
