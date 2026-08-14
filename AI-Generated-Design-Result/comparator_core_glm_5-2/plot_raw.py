"""
ngspice binary raw-file reader + matplotlib plotting for the comparator.

Reads the raw file written by ngspice (`write all` -> single multi-analysis
binary file) and produces per-analysis PNG plots.

Usage:
    python3 plot_raw.py comparator_pre.raw out_dir/png_prefix
"""
import os
import sys
import struct
import numpy as np
import matplotlib
matplotlib.use("Agg")  # non-interactive backend, write PNGs only
import matplotlib.pyplot as plt


def read_raw(path):
    """Parse a ngspice binary raw file with multiple analyses."""
    with open(path, "rb") as f:
        data = f.read()

    # The text header ends with the line "Binary:\n"
    sep = data.find(b"Binary:")
    if sep == -1:
        raise ValueError("Could not find 'Binary:' separator in raw file")
    header = data[:sep].decode("utf-8", errors="replace")
    body = data[sep + len(b"Binary:"):].lstrip(b"\n")

    # Parse header text for 'Title', 'Date', 'Plotname', 'Flags', 'No. Variables',
    # 'No. Points', 'Variables', etc. Each plot begins with "Plotname: ..."
    plot_record_lines = []
    plot_header_lines = []
    for ln in header.splitlines():
        if ln.startswith("Plotname:"):
            if plot_header_lines:
                plot_record_lines.append(plot_header_lines)
            plot_header_lines = [ln]
        else:
            if plot_header_lines:
                plot_header_lines.append(ln)
    if plot_header_lines:
        plot_record_lines.append(plot_header_lines)

    # Locate each plot's start byte offset in body (search "Plotname:" comes
    # before "Variables:" before "Binary:" section).  The body part is purely
    # binary - we have to slice using 'No. Variables' * 'No. Points' size.
    # Easier: walk the binary body deterministically using each plot's
    # declared #vars and #points.

    plots = []
    pos = 0
    for ph_lines in plot_record_lines:
        meta = {"header_lines": ph_lines}
        nv = None
        np_ = None
        reals = True
        var_names = []
        var_types = []
        in_var_section = False
        for ln in ph_lines:
            tokens = ln.split(":", 1)
            key = tokens[0]
            val = tokens[1].strip() if len(tokens) > 1 else ""
            if key == "Plotname":
                meta["plotname"] = val
            elif key == "Flags":
                if "complex" in val:
                    reals = False
            elif key == "No. Variables":
                nv = int(val)
            elif key == "No. Points":
                np_ = int(val)
            elif key == "Commandsimulation":
                meta["command"] = val
            else:
                if not in_var_section and key.strip().startswith("Variables"):
                    in_var_section = True
                    continue
        # Re-parse variables from raw text:
        var_section_only = []
        seen_vars_token = False
        for ln in ph_lines:
            if ln.lstrip().startswith("Variables:"):
                seen_vars_token = True
                continue
            # The "Variables:" line is followed by indented Var definitions:
            # "  0     v(op) voltage" / "  1     v(in) voltage" etc.
            # A signal ends when we hit "Binary:" or "EOF:" or another keyword
            if seen_vars_token:
                if ":" in ln and not (ln.startswith("    ") or ln.startswith("\t")) \
                       and not ln.startswith("  "):
                    break  # some other key
                if not ln.strip():
                    continue
                # match "   0    name  type"
                parts = ln.split()
                if len(parts) >= 3 and parts[0].isdigit():
                    var_names.append(parts[1])
                    var_types.append(parts[2])
                    var_metadata_extra = parts[3:]
                    _ = var_metadata_extra
            else:
                if ln.startswith("Binary:"):
                    break

        meta["var_names"] = var_names
        meta["var_types"] = var_types
        meta["nv"] = nv
        meta["np"] = np_
        meta["reals"] = reals

        # Move body position; compute stride for this plot
        if nv is None or np_ is None:
            continue
        if reals:
            stride = nv * np_ * 8
        else:
            stride = nv * np_ * 16  # complex data, re + im
        chunk = body[pos:pos + stride]
        pos += stride

        if reals:
            arr = np.frombuffer(chunk, dtype="<f8").reshape(np_, nv)
        else:
            arr = np.frombuffer(chunk, dtype="<f8").reshape(np_, nv * 2)
            arr_complex = arr[:, 0::2] + 1j * arr[:, 1::2]
            arr = arr_complex
        meta["arr"] = arr
        plots.append(meta)

    return plots


def get_signal(plots, plotname_substring, signal_name):
    for p in plots:
        if plotname_substring.lower() in p["plotname"].lower():
            if signal_name in p["var_names"]:
                i = p["var_names"].index(signal_name)
                return p["arr"][:, i], p
    return None, None


def main():
    if len(sys.argv) != 3:
        print("Usage: python3 plot_raw.py comparator_pre.raw out_dir/png_prefix")
        sys.exit(1)

    raw_path = sys.argv[1]
    out_prefix = sys.argv[2]
    outdir = os.path.dirname(out_prefix) or "."
    os.makedirs(outdir, exist_ok=True)

    plots = read_raw(raw_path)
    print("Found plots:")
    for p in plots:
        print(f"  {p['plotname']:<30}  np={p['np']}  nv={p['nv']}  vars={p['var_names']}")


    # ------- DC plot -------
    vmag_in, _ = get_signal(plots, "transfer", "v(inp)")
    vmag_out_dc, _ = get_signal(plots, "transfer", "v(out)")
    if vmag_in is not None and vmag_out_dc is not None:
        plt.figure(figsize=(7, 5))
        plt.plot(vmag_in, vmag_out_dc)
        plt.xlabel("Vin+ [V]")
        plt.ylabel("Vout [V]")
        plt.title("Pre-layout: DC transfer")
        plt.grid(True, alpha=0.4)
        plt.tight_layout()
        plt.savefig(f"{out_prefix}_dc.png", dpi=130)
        plt.close()
        print(f"Saved {out_prefix}_dc.png")


    # ------- AC plot -------
    freq_lin, _ = get_signal(plots, "ac", "sweep")
    if freq_lin is None:
        # Some ngspice raws label the sweep as the first variable / "frequency"
        for plots_p in plots:
            if "ac" in plots_p["plotname"].lower():
                freq_lin = plots_p["arr"][:, 0]
                _ = plots_p
                break
    vout_ac, p_ac = get_signal(plots, "ac", "v(out)")
    vinp_ac, _ = get_signal(plots, "ac", "v(inp)")
    if vout_ac is not None and vinp_ac is not None:
        vout_ac = np.asarray(vout_ac, dtype=complex)
        vinp_ac = np.asarray(vinp_ac, dtype=complex)
        ratio = np.abs(vout_ac) / np.abs(vinp_ac)
        gain_db = 20 * np.log10(np.maximum(ratio, 1e-30))
        plt.figure(figsize=(7, 5))
        plt.semilogx(freq_lin, gain_db)
        plt.xlabel("Frequency [Hz]")
        plt.ylabel("Voltage gain |Vout/Vin+| [dB]")
        plt.title("Pre-layout: AC small-signal gain")
        plt.grid(True, which="both", alpha=0.4)
        plt.tight_layout()
        plt.savefig(f"{out_prefix}_ac.png", dpi=130)
        plt.close()
        print(f"Saved {out_prefix}_ac.png")


    # ------- TRAN plot -------
    t_tran, p_tran = get_signal(plots, "transient", "time")
    vinp_tr, _ = get_signal(plots, "transient", "v(inp)")
    vout_tr, _ = get_signal(plots, "transient", "v(out)")
    if t_tran is not None and vinp_tr is not None and vout_tr is not None:
        plt.figure(figsize=(8, 4.5))
        plt.plot(t_tran * 1e9, vinp_tr, label="Vin+ (input)")
        plt.plot(t_tran * 1e9, vout_tr, label="Vout (output)")
        plt.xlabel("Time [ns]")
        plt.ylabel("Voltage [V]")
        plt.title("Pre-layout: Transient step response")
        plt.grid(True, alpha=0.4)
        plt.legend(loc="best")
        plt.tight_layout()
        plt.savefig(f"{out_prefix}_tran.png", dpi=130)
        plt.close()
        print(f"Saved {out_prefix}_tran.png")


if __name__ == "__main__":
    main()
