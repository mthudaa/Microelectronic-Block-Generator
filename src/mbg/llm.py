"""
@Owner: Moh. Jabir Mubarok (AI/LLM Integration & Software Architect)
@Responsibility: LLM integration — natural-language spec to SPICE netlist.

Split out of pipeline.py so the layout flow does not carry the LLM/HTTP
concern. pipeline.py re-exports these names, so existing imports such as
``from mbg.pipeline import generate_netlist_from_prompt`` keep working.
"""
import os
import json as _json
import urllib.request
import urllib.error
from pathlib import Path
from time import perf_counter

from mbg.spice_parser import parse_netlist_with_pdk
from mbg.experiment_manifest import (
    ExperimentManifest,
    ExperimentStatus,
    PromptLevel,
    ensure_inside_repository,
    make_experiment_id,
)

# `spice_to_gds` lives in mbg.pipeline, which imports this module — import it
# lazily inside the function that needs it to avoid a circular import.


def _load_api_key():
    """Load DeepSeek API key from env or .env file."""
    key = os.environ.get("DEEPSEEK_API_KEY")
    if key:
        return key
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    if os.path.isfile(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line.startswith("DEEPSEEK_API_KEY="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    return None


def generate_netlist_from_prompt(user_prompt, model="deepseek-v4-flash",
                                 api_key=None,
                                 api_url="https://api.deepseek.com/v1/chat/completions",
                                 llm_feedback=None):
    api_key = api_key or _load_api_key()
    if not api_key:
        raise RuntimeError(
            "DEEPSEEK_API_KEY not set. "
            "Export it or create .env file with DEEPSEEK_API_KEY=sk-..."
        )
    context = """You are an analog IC design expert. Generate ONLY a SPICE subcircuit netlist.
Respond with NOTHING except the netlist -- no explanations, no markdown, no comments.

STRICT RULES:
1. First line MUST be: .lib "/path/to/gf180mcu/libs.tech/ngspice/sm141064.ngspice" typical
2. Second line MUST be: .subckt <name> <ports...>
3. Last line MUST be: .ends
4. ONLY use these models: nfet_03v3 (NMOS) and pfet_03v3 (PMOS).
5. Format EXACTLY: M<name> <drain> <gate> <source> <body> <model> W=<w>u L=<l>u
6. SUPPLY: Use VDD=1.8V. Connect PMOS body to vdd, NMOS body to vss.
7. NO empty lines between devices. NO markdown fences. NO other text.
8. Choose net names that reflect circuit function (e.g., n1, n2 for internal, vin/vout for I/O).
9. Keep W between 1u and 50u. Keep L=1u for analog. Use ng=1 (no multi-finger)."""

    messages = [
        {"role": "system", "content": context},
        {"role": "user", "content": user_prompt}
    ]
    
    if llm_feedback:
        messages.append({
            "role": "user", 
            "content": f"Here is the feedback from the previous simulation:\n{llm_feedback}\n\nPlease revise and output the new corrected SPICE netlist based on this feedback."
        })

    payload = _json.dumps({
        "model": model,
        "messages": messages,
        "temperature": 0.1,
        "max_tokens": 2000,
        "stream": False
    }).encode()

    req = urllib.request.Request(
        api_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}"
        }
    )

    max_retries = 3
    for attempt in range(max_retries):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read()
                print(f"[LLM] Response: {len(raw)} bytes (attempt {attempt+1}/{max_retries})")
                result = _json.loads(raw)
                if "choices" not in result:
                    print(f"[LLM] Unexpected: {str(result)[:200]}")
                    if attempt < max_retries - 1:
                        continue
                    return None
                netlist = result["choices"][0]["message"]["content"].strip()
                lines = []
                for line in netlist.split('\n'):
                    line = line.strip()
                    if line and not line.startswith('*') and not line.startswith('//') and not line.startswith('#'):
                        if not line.startswith('```'):
                            lines.append(line)
                cleaned = '\n'.join(lines)
                # Validate: must have .subckt and at least one device
                if '.subckt' not in cleaned:
                    print(f"[LLM] No .subckt found — retrying ({attempt+1}/{max_retries})")
                    continue
                try:
                    parsed = parse_netlist_with_pdk(cleaned)
                    if not parsed.get("components"):
                        print(f"[LLM] Parsed netlist has no devices — retrying")
                        continue
                    print(f"[LLM] Validated: {len(parsed['components'])} devices, PDK={parsed['metadata']['pdk']}")
                except Exception as parse_err:
                    print(f"[LLM] Parse failed: {parse_err} — retrying ({attempt+1}/{max_retries})")
                    continue
                print(f"[LLM] Cleaned ({len(lines)} lines):\n{cleaned[:400]}")
                return cleaned
        except urllib.error.HTTPError as e:
            body = e.read().decode()[:500] if e.fp else ""
            print(f"[LLM] HTTP {e.code}: {e.reason}\n{body}")
            if attempt < max_retries - 1:
                print(f"[LLM] Retrying ({attempt+1}/{max_retries})...")
                continue
            return None
        except (urllib.error.URLError, ConnectionError) as e:
            print(f"[LLM] Network error: {e} — retrying ({attempt+1}/{max_retries})")
            continue
        except Exception as e:
            print(f"[LLM] {type(e).__name__}: {e}")
            if attempt < max_retries - 1:
                continue
            return None
    return None


def llm_to_gds(user_prompt, model="deepseek-v4-flash",
               api_key=None,
               mode="analog"):
    print(f"[LLM] Generating netlist for: {user_prompt[:80]}...")
    netlist = generate_netlist_from_prompt(user_prompt, model=model, api_key=api_key)
    if netlist is None:
        raise RuntimeError("LLM gagal menghasilkan netlist")
    print(f"[LLM] Netlist generated:\n{netlist}")
    return spice_to_gds(netlist, mode=mode)


def llm_to_gds_with_manifest(
    user_prompt,
    model="deepseek-v4-flash",
    api_key=None,
    mode="analog",
    output_root="outputs",
    circuit_name="llm-design",
    prompt_level=PromptLevel.MINIMAL,
    max_api_attempts=3,
    experiment_id=None,
):
    """Run prompt-to-GDS and write a reproducible experiment manifest.

    This wrapper records only the AI/netlist/layout stages. Simulation,
    DRC, LVS, PEX, and post-layout simulation remain ``NOT RUN`` until
    their owning workflows provide evidence.

    API retries are recorded as API calls. This wrapper does not yet
    perform feedback-driven semantic refinement, so its refinement
    iteration count remains zero.
    """
    if not isinstance(user_prompt, str) or not user_prompt.strip():
        raise ValueError("user_prompt must be a non-empty string")

    if (
        not isinstance(max_api_attempts, int)
        or isinstance(max_api_attempts, bool)
        or max_api_attempts < 1
    ):
        raise ValueError(
            "max_api_attempts must be an integer "
            "greater than zero"
        )

    level = (
        prompt_level
        if isinstance(prompt_level, PromptLevel)
        else PromptLevel(prompt_level)
    )

    project_root = Path(__file__).resolve().parents[1]
    configured_output_root = Path(output_root)

    if not configured_output_root.is_absolute():
        configured_output_root = (
            project_root / configured_output_root
        )

    resolved_output_root = configured_output_root.resolve()

    ensure_inside_repository(
        repository=project_root,
        target=resolved_output_root,
    )

    resolved_experiment_id = (
        experiment_id
        or make_experiment_id(circuit_name, level)
    )

    experiment_directory = (
        resolved_output_root / resolved_experiment_id
    ).resolve()

    ensure_inside_repository(
        repository=project_root,
        target=experiment_directory,
    )

    experiment_directory.mkdir(
        parents=True,
        exist_ok=False,
    )

    prompt_path = experiment_directory / "prompt.txt"
    netlist_path = (
        experiment_directory / "generated_netlist.spice"
    )
    gds_path = (
        experiment_directory / "generated_layout.gds"
    )

    prompt_path.write_text(
        user_prompt.rstrip() + "\n",
        encoding="utf-8",
    )

    manifest = ExperimentManifest(
        experiment_id=resolved_experiment_id,
        model=model,
        prompt_level=level,
        # This wrapper currently performs no semantic
        # feedback-driven refinement. Transport and validation
        # retries are recorded only as API calls.
        max_refinement_iterations=0,
    )
    manifest.metadata["api_attempt_limit"] = (
        max_api_attempts
    )
    manifest.set_artifact("prompt", "prompt.txt")

    total_started = perf_counter()
    llm_started = perf_counter()
    failure_stage = "llm"

    def record_attempt(_attempt_number):
        # Retrying an HTTP request or invalid response is not
        # equivalent to feedback-driven LLM refinement.
        manifest.record_llm_call(refinement=False)

    try:
        print(
            "[LLM] Generating netlist with manifest: "
            f"{resolved_experiment_id}"
        )

        netlist = generate_netlist_from_prompt(
            user_prompt,
            model=model,
            api_key=api_key,
            max_retries=max_api_attempts,
            attempt_callback=record_attempt,
        )

        manifest.llm_runtime_seconds = (
            perf_counter() - llm_started
        )
        manifest.touch()

        if netlist is None:
            raise RuntimeError(
                "LLM failed to generate a valid netlist"
            )

        netlist_path.write_text(
            netlist.rstrip() + "\n",
            encoding="utf-8",
        )

        manifest.mark_netlist(
            valid=True,
            artifact_path="generated_netlist.spice",
        )

        failure_stage = "layout"

        from mbg.pipeline import spice_to_gds

        top_level = spice_to_gds(
            netlist,
            mode=mode,
            run_checks=False,
        )

        top_level.write_gds(str(gds_path))

        if not gds_path.is_file():
            raise RuntimeError(
                "GDS writer did not create generated_layout.gds"
            )

        manifest.mark_gds(
            generated=True,
            artifact_path="generated_layout.gds",
        )

        manifest.finalize(
            total_runtime_seconds=(
                perf_counter() - total_started
            )
        )

        manifest_path = manifest.write(
            experiment_directory,
            repository_root=project_root,
        )

        print(
            f"[EXPERIMENT] Manifest written: {manifest_path}"
        )

        return top_level, manifest_path

    except Exception as error:
        if manifest.llm_runtime_seconds is None:
            manifest.llm_runtime_seconds = (
                perf_counter() - llm_started
            )

        manifest.total_runtime_seconds = (
            perf_counter() - total_started
        )
        manifest.final_status = ExperimentStatus.FAIL
        manifest.metadata["failure_stage"] = failure_stage
        manifest.metadata["error_type"] = (
            type(error).__name__
        )
        manifest.touch()

        manifest_path = manifest.write(
            experiment_directory,
            repository_root=project_root,
        )

        print(
            "[EXPERIMENT] Failed manifest written: "
            f"{manifest_path}"
        )

        raise
