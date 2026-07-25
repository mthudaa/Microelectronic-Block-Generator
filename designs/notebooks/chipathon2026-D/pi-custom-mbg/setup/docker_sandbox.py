#!/usr/bin/env python3
"""
Docker-based sandbox: run MBG tools in a pre-configured IIC-OSIC-TOOLS container.
No local installation needed — just Docker.
Usage: python3 setup/docker_sandbox.py [--cmd "python inv_full_flow.py"]
"""
import sys, os, argparse, subprocess, json

MBG_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DESIGNS_DIR = os.path.abspath(os.path.join(MBG_DIR, ".."))

def check_docker():
    try:
        r = subprocess.run(["docker", "--version"], capture_output=True, text=True)
        return r.returncode == 0
    except FileNotFoundError:
        return False

def get_container_name():
    """Return running IIC-OSIC-TOOLS container name."""
    try:
        r = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}"],
            capture_output=True, text=True
        )
        for name in r.stdout.strip().split("\n"):
            if "iic-osic" in name.lower() or "chipathon" in name.lower():
                return name
    except:
        pass
    return None

def start_container():
    """Start a new IIC-OSIC-TOOLS container."""
    print("[SANDBOX] Starting IIC-OSIC-TOOLS container...")
    image = "hpretl/iic-osic-tools:chipathon26"
    cmd = [
        "docker", "run", "-d", "--rm",
        "-v", f"{DESIGNS_DIR}:/foss/designs",
        "-v", f"{os.path.expanduser('~/.volare')}:/home/huda/.volare",
        "--name", "mbg_sandbox",
        image, "sleep", "infinity"
    ]
    subprocess.run(cmd, check=True)
    print("[SANDBOX] Container started: mbg_sandbox")
    return "mbg_sandbox"

def ensure_venv_in_container(container):
    """Create .venv inside container if it doesn't exist."""
    r = subprocess.run(
        ["docker", "exec", container, "bash", "-c", "test -d /foss/designs/chipathon2026-D/.venv && echo exists || echo missing"],
        capture_output=True, text=True
    )
    if "missing" in r.stdout:
        print("[SANDBOX] Creating .venv inside container (one-time setup)...")
        subprocess.run(
            ["docker", "exec", container, "bash", "-c",
             "cd /foss/designs/chipathon2026-D && "
             "python3 -m venv .venv && "
             "source .venv/bin/activate && "
             "pip install --quiet numpy gdsfactory gdstk 2>/dev/null && "
             "pip install --quiet glayout@git+https://github.com/ReaLLMASIC/gLayout.git --no-deps 2>/dev/null"],
            capture_output=True, text=True, timeout=300
        )
        print("[SANDBOX] .venv created in container")

def run_in_container(container, command, use_venv=True):
    """Run a command inside the container."""
    workdir = os.environ.get("MBG_WORKDIR", "/tmp/mbg_workspace")
    if use_venv:
        ensure_venv_in_container(container)
        command = f"cd /foss/designs/chipathon2026-D && source .venv/bin/activate && export MBG_WORKDIR={workdir} && {command}"
    print(f"[SANDBOX] Running: {command}")
    r = subprocess.run(
        ["docker", "exec", "-w", "/foss/designs/chipathon2026-D",
         "-e", "PDK_ROOT=/foss/pdks",
         "-e", "PDK=gf180mcuD",
         "-e", "PDKPATH=/foss/pdks/gf180mcuD",
         "-e", f"MBG_WORKDIR={workdir}",
         container, "bash", "-c", command],
        capture_output=True, text=True
    )
    print(r.stdout)
    if r.stderr:
        print(f"[STDERR] {r.stderr[:500]}")
    return r.returncode

def main():
    parser = argparse.ArgumentParser(description="MBG Docker sandbox")
    parser.add_argument("--cmd", default="python3 inv_full_flow.py",
                        help="Command to run in container")
    parser.add_argument("--start", action="store_true", help="Force start new container")
    parser.add_argument("--stop", action="store_true", help="Stop sandbox container")
    args = parser.parse_args()

    if args.stop:
        subprocess.run(["docker", "stop", "mbg_sandbox"], capture_output=True)
        print("[SANDBOX] Container stopped")
        return

    if not check_docker():
        print("[ERROR] Docker not found. Install from https://docker.com")
        sys.exit(1)

    container = get_container_name()
    if args.start or not container:
        container = start_container()

    print(f"[SANDBOX] Using container: {container}")
    rc = run_in_container(container, args.cmd)
    sys.exit(rc)

if __name__ == "__main__":
    main()
