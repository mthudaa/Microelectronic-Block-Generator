#!/usr/bin/env python3
"""Read-only preflight using the public doctor registry."""
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"src"))


def main():
    try:
        from mbg.agent.cli import main as cli_main
        code=cli_main(["doctor"])
    except Exception as error:
        print(f"FAIL preflight: {type(error).__name__}: {error}",file=sys.stderr)
        return 1
    if code:
        print("FAIL preflight: required environment checks did not complete; see doctor result",file=sys.stderr)
    return code


if __name__=="__main__":
    raise SystemExit(main())
